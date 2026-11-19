"""One durable music queue in the existing JC process and data root."""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .comfy import ComfyClient, EngineError, safe_audio_item
from .workflows import build_workflow, validate_request

ID = re.compile(r"[0-9a-f]{32}\Z")
ACTIVE = {"queued", "submitting", "running"}
ALLOWED_AUDIO = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".aif", ".aiff", ".ogg", ".opus"}


def now():
    return datetime.now(timezone.utc).isoformat()


class MusicError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class MusicService:
    def __init__(self, data_root, client=None, *, start_worker=True):
        self.root = Path(data_root) / "CREATIVE" / "MUSIC"
        self.jobs_root = self.root / "jobs"
        self.sources_root = Path(data_root) / "CAPTURE" / "music-source"
        for path in [self.jobs_root, self.sources_root]:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.owner = (self.root / ".owner.lock").open("a")
        try:
            fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.owner.close()
            raise MusicError("Another JC process owns this music queue. Use its existing address.", 409) from exc
        self.client = client or ComfyClient()
        self.lock = threading.RLock()
        self.probe_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.csrf_token = secrets.token_urlsafe(32)
        self.jobs = {}
        self.status_cache = None
        self.status_time = 0.0
        self.node_info = {}
        self.worker = None
        self.poll_interval = 2.0
        self.max_wait = 5400
        for path in self.jobs_root.glob("*/job.json"):
            if not ID.fullmatch(path.parent.name):
                continue
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if job.get("id") != path.parent.name:
                    continue
                if job.get("status") == "submitting":
                    job.update(status="needs_attention", message="JC restarted during submission. Check the engine queue before making another take.", updated_at=now())
                    atomic_json(path, job)
                if job.get("status") == "running" and not job.get("prompt_id"):
                    job.update(status="needs_attention", message="No engine receipt was saved. Check the engine queue before making another take.", updated_at=now())
                    atomic_json(path, job)
                self.jobs[job["id"]] = job
            except (OSError, ValueError, AttributeError):
                continue  # Preserve damaged files for manual recovery; never overwrite them.
        if start_worker:
            self.worker = threading.Thread(target=self._worker, name="jc-music", daemon=True)
            self.worker.start()

    def close(self):
        self.stop_event.set()
        self.wake.set()
        if self.worker:
            self.worker.join(timeout=12)
        if not self.worker or not self.worker.is_alive():
            self.owner.close()

    def _path(self, job_id):
        if not isinstance(job_id, str) or not ID.fullmatch(job_id):
            raise MusicError("Unknown take.", 404)
        return self.jobs_root / job_id

    def _persist(self, job):
        atomic_json(self._path(job["id"]) / "job.json", job)

    def _update(self, job_id, **changes):
        with self.lock:
            job = self.jobs[job_id]
            job.update(changes, updated_at=now())
            self._persist(job)
            return copy.deepcopy(job)

    def status(self, *, force=False):
        with self.probe_lock:
            if not force and self.status_cache and time.monotonic() - self.status_time < 20:
                return copy.deepcopy(self.status_cache)
            try:
                result, self.node_info = self.client.probe()
                result["connected"] = True
            except (EngineError, ValueError, OSError) as exc:
                result = {"ready": False, "connected": False, "message": str(exc),
                          "capabilities": {"create": False, "cover": False}, "checks": {},
                          "models": {"checkpoint": getattr(self.client, "checkpoint", "") or "yue2_3b_int8_convrot.safetensors"}}
            result.update(ok=True, configured=True, engine="YuE2 / ComfyUI", csrf_token=self.csrf_token,
                          checked_at=now(), max_upload_bytes=100 * 1024 * 1024)
            self.status_cache, self.status_time = result, time.monotonic()
            return copy.deepcopy(result)

    def public_job(self, job):
        public = {key: copy.deepcopy(value) for key, value in job.items()
                  if key not in {"request_id", "request_fingerprint", "prompt_id"}}
        prefix = "/api/music/jobs/" + job["id"]
        for output in public.get("outputs", []):
            output.pop("engine_item", None)
            output["url"] = prefix + "/files/" + output["name"]
            output["download_url"] = output["url"] + "?download=1"
        public["receipt_url"] = prefix + "/receipt"
        public["recoverable"] = bool(job.get("prompt_id") and job["status"] in {"needs_attention", "failed"})
        if (self._path(job["id"]) / "workflow.json").is_file():
            public["workflow_url"] = prefix + "/workflow"
        if (self._path(job["id"]) / "score.abc").is_file():
            public["score_url"] = prefix + "/score"
        return public

    def list_jobs(self):
        with self.lock:
            return [self.public_job(x) for x in sorted(self.jobs.values(), key=lambda j: j["created_at"], reverse=True)[:200]]

    def get(self, job_id):
        self._path(job_id)
        with self.lock:
            if job_id not in self.jobs:
                raise MusicError("Take not found.", 404)
            return self.public_job(self.jobs[job_id])

    def create(self, raw):
        if not isinstance(raw, dict):
            raise MusicError("Expected a music request object.")
        payload = dict(raw)
        request_id = payload.pop("request_id", None)
        try:
            if not isinstance(request_id, str) or str(uuid.UUID(request_id)) != request_id.lower():
                raise ValueError()
        except (ValueError, AttributeError):
            raise MusicError("A valid request_id is required to prevent duplicate takes.")
        request_id = request_id.lower()
        try:
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
        except (ValueError, TypeError) as exc:
            raise MusicError("The music request contains invalid values.") from exc
        with self.lock:
            for old in self.jobs.values():
                if old.get("request_id") == request_id:
                    if old.get("request_fingerprint") != fingerprint:
                        raise MusicError("This request ID already belongs to a different take.", 409)
                    return self.public_job(old)
            try:
                request = validate_request(payload)
            except ValueError as exc:
                raise MusicError(str(exc)) from exc
            if request["source_id"]:
                self.source(request["source_id"])
            if sum(j["status"] in ACTIVE for j in self.jobs.values()) >= 20:
                raise MusicError("The queue already has 20 takes. Let it finish before adding more.", 409)
            status = self.status()
            if not status["capabilities"].get(request["task"]):
                raise MusicError(status["message"] + " Check Setup before generating.", 503)
            job_id = uuid.uuid4().hex
            self._path(job_id).mkdir(mode=0o700)
            job = {**request, "id": job_id, "request_id": request_id, "request_fingerprint": fingerprint,
                   "status": "queued", "message": "Waiting for the engine.", "created_at": now(), "updated_at": now(),
                   "kept": False, "outputs": [], "engine": "YuE2 / ComfyUI", "models": status["models"],
                   "provenance": {"workflow": "native-yue2-api-v1", "adapter_version": "2026.11.16",
                                  "graph_source": "Official ComfyUI nodes; supplied attachment was unavailable",
                                  "model_license": "https://github.com/multimodal-art-projection/YuE/blob/main/MODEL_LICENSE"}}
            self._persist(job)
            self.jobs[job_id] = job
            self.wake.set()
            return self.public_job(job)

    def keep(self, job_id, kept):
        if not isinstance(kept, bool):
            raise MusicError("kept must be true or false.")
        self.get(job_id)
        return self.public_job(self._update(job_id, kept=kept))

    def cancel(self, job_id):
        self.get(job_id)
        with self.lock:
            if self.jobs[job_id]["status"] != "queued":
                raise MusicError("Only waiting takes can be cancelled here. A running engine task is left intact.", 409)
            return self.public_job(self._update(job_id, status="cancelled", message="Removed from the waiting queue."))

    def recover(self, job_id):
        self.get(job_id)
        with self.lock:
            job = self.jobs[job_id]
            if not job.get("prompt_id") or job["status"] not in {"needs_attention", "failed"}:
                raise MusicError("There is no interrupted engine receipt to check for this take.", 409)
            result = self._update(job_id, status="running", message="Checking the original engine result. This will not generate another take.")
            self.wake.set()
            return self.public_job(result)

    def source(self, source_id):
        if not isinstance(source_id, str) or not ID.fullmatch(source_id):
            raise MusicError("Unknown reference recording.", 404)
        folder = self.sources_root / source_id
        try:
            metadata = json.loads((folder / "source.json").read_text(encoding="utf-8"))
            path = folder / ("original" + metadata["extension"])
            if metadata["extension"] not in ALLOWED_AUDIO or not path.is_file():
                raise ValueError()
            return metadata, path
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise MusicError("Reference recording is unavailable. Choose it again.", 404) from exc

    def upload(self, filename, stream, length):
        if not isinstance(filename, str) or not filename or len(filename) > 240 or any(c in filename for c in "/\\\x00\r\n"):
            raise MusicError("Choose an audio file with a simple filename.")
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_AUDIO:
            raise MusicError("Choose WAV, AIFF, MP3, FLAC, M4A, AAC, OGG or OPUS audio.")
        if not 0 < length <= 100 * 1024 * 1024:
            raise MusicError("Reference audio must be between 1 byte and 100 MiB.", 413)
        temp = self.sources_root / ("upload-" + uuid.uuid4().hex + ".part")
        digest, remaining = hashlib.sha256(), length
        try:
            with temp.open("wb") as out:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise MusicError("The reference upload was interrupted. Choose the file again.")
                    digest.update(chunk)
                    out.write(chunk)
                    remaining -= len(chunk)
                out.flush()
                os.fsync(out.fileno())
            source_id = digest.hexdigest()[:32]
            with self.lock:
                folder = self.sources_root / source_id
                if (folder / "source.json").is_file():
                    metadata, _ = self.source(source_id)
                    return metadata
                folder.mkdir(exist_ok=True, mode=0o700)
                destination = folder / ("original" + extension)
                os.chmod(temp, 0o600)
                temp.replace(destination)
                metadata = {"id": source_id, "name": filename, "bytes": length, "sha256": digest.hexdigest(),
                            "extension": extension, "created_at": now()}
                atomic_json(folder / "source.json", metadata)
                return metadata
        finally:
            temp.unlink(missing_ok=True)

    def artifact(self, job_id, name):
        job = self.get(job_id)
        if name not in {x["name"] for x in job["outputs"]}:
            raise MusicError("Audio not found.", 404)
        path = self._path(job_id) / name
        if not path.is_file() or path.is_symlink():
            raise MusicError("Audio file is unavailable.", 404)
        return path

    def _worker(self):
        while not self.stop_event.is_set():
            with self.lock:
                active = sorted((j for j in self.jobs.values() if j["status"] in {"queued", "running"}), key=lambda j: (j["status"] != "running", j["created_at"]))
                job = copy.deepcopy(active[0]) if active else None
                if job and job["status"] == "queued":
                    # Claim under the same lock used by cancellation.
                    job = self._update(job["id"], status="submitting", message="Checking the workflow and sending it to YuE2.")
            if not job:
                self.wake.wait(2)
                self.wake.clear()
                continue
            try:
                self._run(job)
            except EngineError as exc:
                self._update(job["id"], status="needs_attention" if exc.uncertain else "failed", message=str(exc))
            except Exception:
                self._update(job["id"], status="needs_attention", message="JC could not complete this take. The source and job record are preserved; check the engine before retrying.")

    def _run(self, job):
        job_id = job["id"]
        if job["status"] == "submitting":
            status = self.status(force=True)
            if not status["capabilities"].get(job["task"]):
                raise EngineError(status["message"])
            reference_name = None
            if job["task"] == "cover":
                metadata, path = self.source(job["source_id"])
                reference_name = self.client.upload_source(path, job_id)
                self._update(job_id, source_sha256=metadata["sha256"])
            request = {k: job[k] for k in ["task", "title", "style", "lyrics", "duration", "seed", "composition", "source_id"]}
            graph = build_workflow(request, job_id, job["models"]["checkpoint"], reference_name, job["models"].get("audio_encoder", "sheetsage2_bf16.safetensors"))
            issues = self.client.validate_graph(graph, self.node_info)
            if issues:
                raise EngineError("Workflow is incompatible with this engine: " + "; ".join(issues)[:800])
            atomic_json(self._path(job_id) / "workflow.json", graph)
            workflow_hash = hashlib.sha256((self._path(job_id) / "workflow.json").read_bytes()).hexdigest()
            prompt_id = self.client.submit(graph, job_id)
            job = self._update(job_id, prompt_id=prompt_id, status="running", message="YuE2 is composing and rendering this take.", started_at=now(), workflow_sha256=workflow_hash)
        prompt_id = job["prompt_id"]
        began, missing_since, errors = time.monotonic(), None, 0
        while not self.stop_event.is_set():
            complete_entry = None
            try:
                history = self.client.json("/history/" + prompt_id)
                entry = history.get(prompt_id)
                if entry:
                    status = entry.get("status", {})
                    if status.get("status_str") == "error":
                        messages = status.get("messages", [])
                        detail = next((m[1].get("exception_message", "") for m in messages if isinstance(m, list) and len(m) > 1 and isinstance(m[1], dict) and m[0] == "execution_error"), "")
                        raise EngineError("YuE2 could not render this take. " + str(detail)[:500])
                    if status.get("completed") or status.get("status_str") == "success":
                        complete_entry = entry
                else:
                    queue = self.client.json("/queue")
                    ids = [row[1] for key in ["queue_running", "queue_pending"] for row in queue.get(key, []) if isinstance(row, list) and len(row) > 1]
                    if prompt_id not in ids:
                        missing_since = missing_since or time.monotonic()
                        if time.monotonic() - missing_since > 15:
                            raise EngineError("The engine no longer has this take in its queue or history. Check it before trying again.", uncertain=True)
                    else:
                        missing_since = None
                errors = 0
            except EngineError as exc:
                if exc.uncertain or "could not render" in str(exc):
                    raise
                errors += 1
                if errors >= 5:
                    raise EngineError("Lost contact with the engine. It may still be rendering; check its queue before retrying.", uncertain=True) from exc
                self._update(job_id, message="Reconnecting to the engine; this take will not be submitted twice.")
            if complete_entry is not None:
                try:
                    self._collect(job_id, complete_entry)
                except EngineError as exc:
                    raise EngineError("The engine finished, but JC could not collect the result: " + str(exc) + " Use Check original result to retrieve it without regenerating.", uncertain=True) from exc
                return
            if time.monotonic() - began > self.max_wait:
                raise EngineError("The engine has not finished within 90 minutes. Check its queue; JC has not stopped or repeated the task.", uncertain=True)
            self.stop_event.wait(self.poll_interval)

    def _collect(self, job_id, entry):
        outputs, score, items = [], [], []
        for node_id, payload in entry.get("outputs", {}).items():
            if not isinstance(payload, dict):
                continue
            items += [safe_audio_item(item) for item in payload.get("audio", [])]
            if str(node_id) == "9":
                score += [x for x in payload.get("text", []) if isinstance(x, str)]
        extensions = {Path(x["filename"]).suffix.lower() for x in items}
        if not items or len(items) > 8 or not {".flac", ".mp3"}.issubset(extensions):
            raise EngineError("The engine completed without both the FLAC master and MP3 preview.")
        folder = self._path(job_id)
        for i, item in enumerate(items):
            extension = Path(item["filename"]).suffix.lower()
            name = ("preview" if extension == ".mp3" else "master") + f"-{i + 1}" + extension
            path = folder / name
            size = self.client.download(item, path)
            outputs.append({"name": name, "bytes": size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "kind": "preview" if extension == ".mp3" else "master", "engine_item": item})
        outputs.sort(key=lambda x: x["kind"] != "preview")
        if score:
            text = "\n\n".join(score)
            if len(text.encode()) > 2 * 1024 * 1024:
                raise EngineError("The engine returned an unexpectedly large score.")
            (folder / "score.abc").write_text(text, encoding="utf-8")
        atomic_json(folder / "engine_receipt.json", {"status": entry.get("status"), "outputs": entry.get("outputs")})
        self._update(job_id, status="succeeded", message="Ready to listen.", outputs=outputs, finished_at=now())
