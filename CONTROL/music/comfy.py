"""Bounded ComfyUI transport. No model downloads or shell execution."""
from __future__ import annotations

import json
import mimetypes
import os
import uuid
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .workflows import DEFAULT_AUDIO_ENCODER, DEFAULT_CHECKPOINT, build_workflow


class EngineError(Exception):
    def __init__(self, message, *, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EngineError("The engine redirected this request. Configure its final private address.")


def safe_audio_item(item):
    if not isinstance(item, dict) or item.get("type") != "output":
        raise EngineError("The engine returned an unexpected audio location.")
    name, folder = item.get("filename", ""), item.get("subfolder", "")
    if (not isinstance(name, str) or not isinstance(folder, str)
            or not name or len(name) > 240 or len(folder) > 1024
            or any(c in name for c in "/\\\x00\r\n")
            or "\\" in folder or "\x00" in folder
            or PurePosixPath(folder).is_absolute()
            or any(p in {"..", "."} for p in folder.split("/") if p)
            or Path(name).suffix.lower() not in {".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a"}):
        raise EngineError("The engine returned an unsafe audio filename.")
    return {"filename": name, "subfolder": folder, "type": "output"}


class ComfyClient:
    def __init__(self, base_url=None, token=None):
        self.base_url = (base_url or os.environ.get("JUICE_MUSIC_COMFY_URL", "http://127.0.0.1:8188")).rstrip("/")
        parsed = urlsplit(self.base_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("JUICE_MUSIC_COMFY_URL must be an HTTP(S) engine address without credentials or query parameters.")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Use HTTPS for a remote engine, or forward its port to loopback over a private connection.")
        self.token = token if token is not None else os.environ.get("JUICE_MUSIC_COMFY_TOKEN", "")
        self.opener = build_opener(NoRedirect())
        self.checkpoint = os.environ.get("JUICE_MUSIC_CHECKPOINT", "")
        self.audio_encoder = os.environ.get("JUICE_MUSIC_AUDIO_ENCODER", DEFAULT_AUDIO_ENCODER)

    def _open(self, path, data=None, content_type=None, timeout=8):
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        req = Request(self.base_url + path, data=data, headers=headers)
        try:
            return self.opener.open(req, timeout=timeout)
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read(8192))
                error = detail.get("error", {})
                message = error.get("message", "") if isinstance(error, dict) else str(error)
            except (ValueError, OSError, AttributeError):
                message = ""
            raise EngineError(f"ComfyUI returned HTTP {exc.code}. {message[:350]}".strip(),
                              uncertain=path == "/prompt" and exc.code >= 500) from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise EngineError("Cannot reach the configured ComfyUI engine.", uncertain=path == "/prompt") from exc

    def json(self, path, payload=None):
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
        with self._open(path, data, "application/json" if data is not None else None) as response:
            raw = response.read(24 * 1024 * 1024 + 1)
        if len(raw) > 24 * 1024 * 1024:
            raise EngineError("The engine response exceeded the metadata limit.", uncertain=path == "/prompt")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise EngineError("The engine returned invalid JSON.", uncertain=path == "/prompt") from exc
        if not isinstance(result, dict):
            raise EngineError("The engine returned unexpected metadata.", uncertain=path == "/prompt")
        return result

    @staticmethod
    def validate_graph(graph, info, *, uploaded=False):
        """Check the installed schema, including model names, before spending GPU time."""
        errors = []
        for node in graph.values():
            kind, values = node["class_type"], node["inputs"]
            schema = info.get(kind)
            if not isinstance(schema, dict):
                errors.append("Missing node: " + kind)
                continue
            inputs = schema.get("input", {})
            required = inputs.get("required", {})
            declared = {**required, **inputs.get("optional", {})}
            for name in required:
                if name not in values:
                    errors.append(f"{kind} now requires {name}; update the adapter.")
            for name, value in values.items():
                if name not in declared:
                    errors.append(f"{kind} does not expose {name}; update ComfyUI or the adapter.")
                    continue
                spec = declared[name]
                choices = spec[0] if isinstance(spec, (list, tuple)) and spec else None
                is_link = isinstance(value, list) and len(value) == 2 and isinstance(value[1], int)
                if isinstance(choices, list) and not is_link:
                    if kind == "LoadAudio" and name == "audio" and not uploaded:
                        continue
                    if value not in choices:
                        errors.append(f"Unavailable {kind}.{name}: {value}")
        return list(dict.fromkeys(errors))

    def probe(self):
        info = self.json("/object_info")
        try:
            available = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        except (KeyError, IndexError, TypeError):
            available = []
        checkpoint = self.checkpoint or next((x for x in [DEFAULT_CHECKPOINT, "yue2_3b_bf16.safetensors"] if x in available), DEFAULT_CHECKPOINT)
        errors, capabilities = {}, {}
        for task in ["create", "cover"]:
            request = {"task": task, "style": "Capability check", "seed": 1,
                       "composition": "melody" if task == "cover" else "full"}
            if task == "cover":
                request["source_id"] = "capability-check"
            graph = build_workflow(request, "capability-check", checkpoint,
                                   "reference.wav" if task == "cover" else None, self.audio_encoder)
            errors[task] = self.validate_graph(graph, info)
            capabilities[task] = not errors[task]
        ready = capabilities["create"]
        message = "Ready to make music." if ready else "The engine needs the YuE2 nodes and checkpoint shown below."
        return {"ready": ready, "message": message, "capabilities": capabilities,
                "models": {"checkpoint": checkpoint, "audio_encoder": self.audio_encoder},
                "checks": errors}, info

    def upload_source(self, path, job_id):
        path = Path(path)
        if path.stat().st_size > 100 * 1024 * 1024:
            raise EngineError("Reference audio exceeds 100 MiB.")
        boundary = "juice" + uuid.uuid4().hex
        filename = "source" + path.suffix.lower()
        fields = {"type": "input", "subfolder": "juice-music/" + job_id, "overwrite": "false"}
        chunks = []
        for key, value in fields.items():
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
        chunks += [path.read_bytes(), f"\r\n--{boundary}--\r\n".encode()]
        with self._open("/upload/image", b"".join(chunks), "multipart/form-data; boundary=" + boundary, timeout=120) as response:
            try:
                result = json.loads(response.read(16384))
            except (ValueError, UnicodeError) as exc:
                raise EngineError("The engine did not confirm the reference upload.") from exc
        if not isinstance(result, dict) or result.get("type", "input") != "input":
            raise EngineError("The engine returned an invalid reference upload.")
        name = result.get("name", "")
        folder = result.get("subfolder", "")
        if not isinstance(name, str) or not isinstance(folder, str):
            raise EngineError("Invalid reference filename.")
        combined = (folder + "/" if folder else "") + name
        if not name or any(p in {"", ".", ".."} for p in combined.split("/")) or "\\" in combined or ":" in combined:
            raise EngineError("Unsafe reference filename returned by the engine.")
        return combined

    def submit(self, graph, job_id):
        result = self.json("/prompt", {"prompt": graph, "client_id": "juice-music",
                                      "extra_data": {"juice_music_job_id": job_id}})
        if result.get("error") or result.get("node_errors"):
            raise EngineError("ComfyUI rejected the workflow: " + json.dumps(result.get("error") or result["node_errors"])[:700])
        prompt_id = result.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id or len(prompt_id) > 128 or any(c not in "0123456789abcdefABCDEF-" for c in prompt_id):
            raise EngineError("The engine did not return a valid job ID. Check its queue before trying again.", uncertain=True)
        return prompt_id

    def download(self, item, destination):
        item = safe_audio_item(item)
        destination = Path(destination)
        part = destination.with_suffix(destination.suffix + ".part")
        count = 0
        try:
            with self._open("/view?" + urlencode(item), timeout=120) as response, part.open("wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > 512 * 1024 * 1024:
                        raise EngineError("Audio output exceeded the 512 MiB limit.")
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            if not count:
                raise EngineError("The engine returned an empty audio file.")
            part.replace(destination)
            return count
        finally:
            part.unlink(missing_ok=True)
