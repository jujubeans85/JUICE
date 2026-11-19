"""Protect the durable queue against duplicate work, lost sources and restart loss.

The engine is a deterministic test double. These tests make no GPU calls and do
not imply that any music was generated. WAV and FLAC bytes are tiny valid silence
fixtures; MP3 bytes are explicitly an opaque fake transport payload.
"""
from __future__ import annotations

import base64
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import uuid
import wave


CONTROL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_ROOT))

from music.comfy import ComfyClient, EngineError, safe_audio_item
from music.service import MusicError, MusicService, atomic_json
from music.workflows import DEFAULT_AUDIO_ENCODER, DEFAULT_CHECKPOINT, build_workflow


def silence_wav():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 80)
    return stream.getvalue()


WAV = silence_wav()
# Embedded once from ffmpeg's FLAC encoder; the test suite needs no ffmpeg.
FLAC = base64.b64decode("ZkxhQwAAACICQAJAAAAAAASVAfQA8AAAAAAAAAAAAAAAAAAAAAAAAAAAhAAADgYAAABmZm1wZWcAAAAA//hkCABPCQAAAHyn")
FAKE_MP3 = b"ID3\x04\0\0\0\0\0\0TEST-DOUBLE-NOT-GENERATED-AUDIO"


def graph_schema_fixture():
    """Only the service/transport contract is under test, not ComfyUI schemas."""
    info = {}
    for task in ("create", "cover"):
        request = {"task": task, "style": "Test fixture", "seed": 1}
        if task == "cover":
            request.update(source_id="fixture-source", composition="melody")
        graph = build_workflow(request, "fixture-job", DEFAULT_CHECKPOINT,
                               "fixture.wav" if task == "cover" else None)
        for node in graph.values():
            fields = info.setdefault(node["class_type"], {"input": {"required": {}}})
            fields["input"]["required"].update({key: ["FIXTURE"] for key in node["inputs"]})
    return info


class FakeComfy:
    """Synchronous fake of the ComfyUI receipt, queue, history and file APIs."""
    checkpoint = DEFAULT_CHECKPOINT
    audio_encoder = DEFAULT_AUDIO_ENCODER
    validate_graph = staticmethod(ComfyClient.validate_graph)

    def __init__(self):
        self.available = True
        self.submissions = []
        self.uploads = []
        self.downloads = []
        self.requests = []
        self.submit_error = None
        self.download_error = None
        self.history_errors = 0
        self.prompt_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.entry = {
            "status": {"status_str": "success", "completed": True},
            "outputs": {
                "8": {"audio": [{"filename": "fixture.flac", "subfolder": "safe", "type": "output"}]},
                "10": {"audio": [{"filename": "fixture.mp3", "subfolder": "safe", "type": "output"}]},
                "9": {"text": ["X:1\nT:Test fixture\nM:4/4\nK:C\nz4|\n"]},
            },
        }

    def probe(self):
        if not self.available:
            raise EngineError("Fixture engine offline")
        return {
            "ready": True, "message": "Fixture engine ready",
            "capabilities": {"create": True, "cover": True},
            "models": {"checkpoint": self.checkpoint, "audio_encoder": self.audio_encoder},
            "checks": {"create": [], "cover": []},
        }, graph_schema_fixture()

    def submit(self, graph, job_id):
        self.submissions.append((job_id, copy.deepcopy(graph)))
        if self.submit_error:
            raise self.submit_error
        return self.prompt_id

    def upload_source(self, path, job_id):
        self.uploads.append((Path(path), job_id, Path(path).read_bytes()))
        return f"juice-music/{job_id}/source.wav"

    def json(self, path, payload=None):
        self.requests.append(path)
        if path.startswith("/history/"):
            if self.history_errors:
                self.history_errors -= 1
                raise EngineError("Fixture transient disconnect")
            return {} if self.entry is None else {self.prompt_id: copy.deepcopy(self.entry)}
        if path == "/queue":
            return {"queue_running": [[1, self.prompt_id]], "queue_pending": []}
        raise AssertionError(f"Unexpected fake-engine path: {path}")

    def download(self, item, destination):
        safe_audio_item(item)
        self.downloads.append(copy.deepcopy(item))
        if self.download_error:
            raise self.download_error
        payload = FAKE_MP3 if item["filename"].endswith(".mp3") else FLAC
        Path(destination).write_bytes(payload)
        return len(payload)


class MusicServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data_root = Path(self.temporary.name)
        self.engine = FakeComfy()
        self.service = self.make_service()

    def make_service(self, start_worker=False):
        service = MusicService(self.data_root, self.engine, start_worker=start_worker)
        service.poll_interval = 0.005
        service.max_wait = 0.4
        self.addCleanup(service.close)
        return service

    def request(self, **changes):
        request = {"request_id": str(uuid.uuid4()), "style": "Warm brass and dry funk drums", "seed": 7}
        request.update(changes)
        return request

    def restart(self, start_worker=False):
        self.service.close()
        self.service = self.make_service(start_worker=start_worker)
        return self.service

    def await_terminal(self, job_id, timeout=2):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            job = self.service.get(job_id)
            if job["status"] not in {"queued", "submitting", "running"}:
                return job
            self.service.wake.wait(0.005)
            time.sleep(0.005)
        self.fail(f"Job did not terminate: {self.service.get(job_id)}")

    def test_duplicate_request_is_one_durable_take_even_after_restart(self):
        request = self.request()
        request.pop("seed")  # The generated seed must also survive a retry.
        first = self.service.create(request)
        second = self.service.create(copy.deepcopy(request))
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["seed"], second["seed"])
        self.assertEqual(len(self.service.list_jobs()), 1)
        self.restart()
        self.engine.available = False  # A retry of existing work needs no engine.
        again = self.service.create(request)
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(again["seed"], first["seed"])
        self.assertEqual(len(list(self.service.jobs_root.glob("*/job.json"))), 1)
        self.assertEqual(self.engine.submissions, [])

    def test_reused_request_id_cannot_silently_change_content(self):
        request = self.request()
        first = self.service.create(request)
        changed = {**request, "style": "Completely different music"}
        with self.assertRaises(MusicError) as caught:
            self.service.create(changed)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.service.get(first["id"])["style"], request["style"])
        self.assertEqual(len(self.service.list_jobs()), 1)

    def test_concurrent_retries_create_only_one_job(self):
        request = self.request()
        barrier = threading.Barrier(5)
        results, errors = [], []
        def create():
            try:
                barrier.wait(timeout=2)
                results.append(self.service.create(request)["id"])
            except Exception as exc:
                errors.append(exc)
        workers = [threading.Thread(target=create) for _ in range(5)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=3)
        self.assertFalse(errors, errors)
        self.assertEqual(len(results), 5)
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(len(self.service.list_jobs()), 1)

    def test_queue_has_one_process_owner(self):
        with self.assertRaises(MusicError) as caught:
            MusicService(self.data_root, self.engine, start_worker=False)
        self.assertEqual(caught.exception.status, 409)
        self.restart()  # Releasing the first owner must permit a normal restart.
        self.assertEqual(self.service.list_jobs(), [])

    def test_upload_deduplicates_content_and_preserves_original(self):
        first = self.service.upload("My original.wav", io.BytesIO(WAV), len(WAV))
        duplicate = self.service.upload("Renamed.wav", io.BytesIO(WAV), len(WAV))
        self.assertEqual(first, duplicate)
        self.assertEqual(first["sha256"], hashlib.sha256(WAV).hexdigest())
        metadata, path = self.service.source(first["id"])
        self.assertEqual(metadata["name"], "My original.wav")
        self.assertEqual(path.read_bytes(), WAV)
        self.assertEqual(len(list(self.service.sources_root.glob("*/source.json"))), 1)
        self.assertEqual(list(self.service.sources_root.glob("*.part")), [])

    def test_interrupted_upload_leaves_no_published_source_or_partial(self):
        with self.assertRaises(MusicError) as caught:
            self.service.upload("cut-off.wav", io.BytesIO(WAV[:18]), len(WAV))
        self.assertIn("interrupted", str(caught.exception))
        self.assertEqual(list(self.service.sources_root.iterdir()), [])

    def test_source_and_job_identifiers_cannot_escape_data_root(self):
        for name in ("../private.wav", "/private.wav", "a\\private.wav", "bad\nname.wav", "bad\x00.wav"):
            with self.subTest(name=name), self.assertRaises(MusicError):
                self.service.upload(name, io.BytesIO(WAV), len(WAV))
        for value in ("../private", "/tmp", "a" * 32 + "/../", None):
            with self.subTest(value=value):
                with self.assertRaises(MusicError):
                    self.service.source(value)
                with self.assertRaises(MusicError):
                    self.service.get(value)
        self.assertEqual(list(self.service.sources_root.iterdir()), [])

    def test_restart_preserves_queue_and_quarantines_uncertain_submissions(self):
        queued = self.service.create(self.request(title="Queued"))
        submitting = self.service.create(self.request(title="Uncertain submission"))
        missing_receipt = self.service.create(self.request(title="Missing engine receipt"))
        running = self.service.create(self.request(title="Known engine job"))
        self.service._update(submitting["id"], status="submitting")
        self.service._update(missing_receipt["id"], status="running")
        self.service._update(running["id"], status="running", prompt_id=self.engine.prompt_id)
        self.restart()
        self.assertEqual(self.service.get(queued["id"])["status"], "queued")
        self.assertEqual(self.service.get(submitting["id"])["status"], "needs_attention")
        self.assertEqual(self.service.get(missing_receipt["id"])["status"], "needs_attention")
        self.assertEqual(self.service.get(running["id"])["status"], "running")
        self.assertEqual(self.engine.submissions, [])

    def test_damaged_record_is_preserved_for_recovery(self):
        folder = self.service.jobs_root / ("f" * 32)
        folder.mkdir()
        damaged = folder / "job.json"
        damaged.write_bytes(b'{"id": "partial write')
        self.restart()
        self.assertEqual(self.service.list_jobs(), [])
        self.assertEqual(damaged.read_bytes(), b'{"id": "partial write')

    def test_cancel_only_waiting_jobs_and_keep_survives_restart(self):
        job = self.service.create(self.request())
        self.service.keep(job["id"], True)
        cancelled = self.service.cancel(job["id"])
        self.assertEqual(cancelled["status"], "cancelled")
        with self.assertRaises(MusicError):
            self.service.cancel(job["id"])
        self.restart()
        self.assertTrue(self.service.get(job["id"])["kept"])
        self.assertEqual(self.service.get(job["id"])["status"], "cancelled")

    def test_real_worker_lifecycle_saves_fake_audio_receipts_and_score(self):
        job = self.service.create(self.request())
        self.restart(start_worker=True)
        result = self.await_terminal(job["id"])
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(len(self.engine.submissions), 1)
        self.assertEqual([x["kind"] for x in result["outputs"]], ["preview", "master"])
        folder = self.service.jobs_root / job["id"]
        self.assertTrue((folder / "workflow.json").is_file())
        self.assertTrue((folder / "engine_receipt.json").is_file())
        self.assertIn("T:Test fixture", (folder / "score.abc").read_text())
        for output in result["outputs"]:
            expected = FAKE_MP3 if output["kind"] == "preview" else FLAC
            path = self.service.artifact(job["id"], output["name"])
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(output["sha256"], hashlib.sha256(expected).hexdigest())
            self.assertNotIn("engine_item", output)
            self.assertTrue(output["url"].startswith(f"/api/music/jobs/{job['id']}/files/"))
        self.assertNotIn("prompt_id", result)
        self.assertNotIn("request_id", result)

    def test_cover_keeps_source_and_records_source_hash(self):
        source = self.service.upload("reference.wav", io.BytesIO(WAV), len(WAV))
        job = self.service.create(self.request(task="cover", source_id=source["id"], composition="melody"))
        self.restart(start_worker=True)
        result = self.await_terminal(job["id"])
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(result["source_sha256"], hashlib.sha256(WAV).hexdigest())
        self.assertEqual(len(self.engine.uploads), 1)
        self.assertEqual(self.engine.uploads[0][2], WAV)
        self.assertEqual(self.service.source(source["id"])[1].read_bytes(), WAV)

    def test_restart_resumes_known_receipt_without_resubmitting(self):
        job = self.service.create(self.request())
        self.service._update(job["id"], status="running", prompt_id=self.engine.prompt_id)
        self.restart(start_worker=True)
        result = self.await_terminal(job["id"])
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(self.engine.submissions, [])

    def test_transient_poll_disconnects_do_not_repeat_submission(self):
        self.engine.history_errors = 2
        job = self.service.create(self.request())
        self.restart(start_worker=True)
        result = self.await_terminal(job["id"])
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(len(self.engine.submissions), 1)

    def test_uncertain_submission_is_not_automatically_retried(self):
        self.engine.submit_error = EngineError("Fixture lost response after acceptance", uncertain=True)
        job = self.service.create(self.request())
        self.restart(start_worker=True)
        result = self.await_terminal(job["id"])
        self.assertEqual(result["status"], "needs_attention")
        self.restart(start_worker=True)
        time.sleep(0.03)
        self.assertEqual(len(self.engine.submissions), 1)
        self.assertEqual(self.service.get(job["id"])["status"], "needs_attention")

    def test_engine_execution_error_is_terminal_and_does_not_repeat(self):
        self.engine.entry = {"status": {"status_str": "error", "messages": [
            ["execution_error", {"exception_message": "Fixture out of memory"}]
        ]}}
        job = self.service.create(self.request())
        self.restart(start_worker=True)
        result = self.await_terminal(job["id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("Fixture out of memory", result["message"])
        self.assertEqual(len(self.engine.submissions), 1)

    def test_unsafe_engine_output_fails_without_downloading_or_retry_loop(self):
        self.engine.entry["outputs"]["8"]["audio"][0]["filename"] = "../../private.wav"
        job = self.service.create(self.request())
        self.restart(start_worker=True)
        result = self.await_terminal(job["id"])
        self.assertEqual(result["status"], "needs_attention", result)
        self.assertIn("unsafe", result["message"])
        self.assertTrue(result["recoverable"])
        self.assertEqual(self.engine.downloads, [])
        self.assertEqual(len(self.engine.submissions), 1)
        self.assertEqual(len(self.engine.requests), 1, "Unsafe output must not spin until the job timeout")

    def test_output_collection_can_recover_original_result_without_new_submission(self):
        self.engine.download_error = EngineError("Fixture download interrupted")
        job = self.service.create(self.request())
        self.restart(start_worker=True)
        interrupted = self.await_terminal(job["id"])
        self.assertEqual(interrupted["status"], "needs_attention")
        self.assertTrue(interrupted["recoverable"])
        self.assertEqual(len(self.engine.submissions), 1)
        self.restart()
        self.engine.download_error = None
        recovering = self.service.recover(job["id"])
        self.assertEqual(recovering["status"], "running")
        self.assertFalse(recovering["recoverable"])
        self.restart(start_worker=True)
        recovered = self.await_terminal(job["id"])
        self.assertEqual(recovered["status"], "succeeded", recovered)
        self.assertFalse(recovered["recoverable"])
        self.assertEqual(len(self.engine.submissions), 1)
        self.assertEqual(len(recovered["outputs"]), 2)

    def test_recovery_cannot_queue_new_work_without_original_engine_receipt(self):
        job = self.service.create(self.request())
        for state in ("queued", "needs_attention", "failed", "cancelled"):
            with self.subTest(state=state):
                self.service._update(job["id"], status=state)
                self.assertFalse(self.service.get(job["id"])["recoverable"])
                with self.assertRaises(MusicError) as caught:
                    self.service.recover(job["id"])
                self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.engine.submissions, [])

    def test_missing_preview_cannot_be_reported_as_completed_deliverable(self):
        del self.engine.entry["outputs"]["10"]
        job = self.service.create(self.request())
        self.restart(start_worker=True)
        result = self.await_terminal(job["id"])
        self.assertEqual(result["status"], "needs_attention")
        self.assertTrue(result["recoverable"])
        self.assertEqual(result["outputs"], [])
        self.assertEqual(self.engine.downloads, [])


class ComfyTransportTests(unittest.TestCase):
    """Validate HTTP receipts and redirects against a local fake Comfy server."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = []
        self.mode = "normal"
        test = self

        class Handler(BaseHTTPRequestHandler):
            def respond(self, status, body, content_type="application/json", extra=None):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def record(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                test.calls.append((self.command, self.path, dict(self.headers), body))
                return body

            def do_GET(self):
                self.record()
                if self.path == "/object_info":
                    self.respond(200, json.dumps(graph_schema_fixture()).encode())
                elif self.path.startswith("/view?"):
                    if test.mode == "redirect":
                        self.respond(302, b"", extra={"Location": "/must-not-receive-token"})
                    else:
                        self.respond(200, b"" if test.mode == "empty" else WAV, "audio/wav")
                else:
                    self.respond(500, b'{"error":{"message":"unexpected test request"}}')

            def do_POST(self):
                self.record()
                if self.path == "/prompt":
                    if test.mode == "server_error":
                        self.respond(503, b'{"error":{"message":"fixture server failure"}}')
                    elif test.mode == "bad_request":
                        self.respond(400, b'{"error":{"message":"fixture invalid prompt"}}')
                    elif test.mode == "invalid_json":
                        self.respond(200, b"not json")
                    elif test.mode == "missing_receipt":
                        self.respond(200, b"{}")
                    else:
                        self.respond(200, b'{"prompt_id":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","node_errors":{}}')
                elif self.path == "/upload/image":
                    self.respond(200, b'{"name":"source.wav","subfolder":"juice-music/fixture-job","type":"input"}')
                else:
                    self.respond(500, b"{}")

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.client = ComfyClient(f"http://127.0.0.1:{self.server.server_address[1]}", token="fixture-token-not-a-secret")

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_preflight_then_one_prompt_receipt_has_durable_client_correlation(self):
        result, info = self.client.probe()
        self.assertTrue(result["capabilities"]["create"])
        self.assertTrue(result["capabilities"]["cover"])
        graph = build_workflow({"style": "Fixture", "seed": 1}, "fixture-job", DEFAULT_CHECKPOINT)
        self.assertEqual(self.client.validate_graph(graph, info), [])
        receipt = self.client.submit(graph, "fixture-job")
        self.assertEqual(receipt, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual([call[1] for call in self.calls], ["/object_info", "/prompt"])
        posted = json.loads(self.calls[-1][3])
        self.assertEqual(posted["prompt"], graph)
        self.assertEqual(posted["extra_data"]["juice_music_job_id"], "fixture-job")
        self.assertEqual(self.calls[-1][2]["Authorization"], "Bearer fixture-token-not-a-secret")

    def test_uncertain_post_responses_are_distinguished_from_explicit_rejection(self):
        graph = build_workflow({"style": "Fixture", "seed": 1}, "fixture-job", DEFAULT_CHECKPOINT)
        for mode, uncertain in (("server_error", True), ("invalid_json", True),
                                ("missing_receipt", True), ("bad_request", False)):
            with self.subTest(mode=mode):
                self.mode = mode
                before = len(self.calls)
                with self.assertRaises(EngineError) as caught:
                    self.client.submit(graph, "fixture-job")
                self.assertEqual(caught.exception.uncertain, uncertain)
                self.assertEqual(len(self.calls) - before, 1, "Transport must not retry a POST")

    def test_audio_upload_uses_comfy_multipart_contract_and_preserves_bytes(self):
        source = self.root / "source.wav"
        source.write_bytes(WAV)
        uploaded = self.client.upload_source(source, "fixture-job")
        self.assertEqual(uploaded, "juice-music/fixture-job/source.wav")
        method, path, headers, body = self.calls[-1]
        self.assertEqual((method, path), ("POST", "/upload/image"))
        self.assertIn("multipart/form-data; boundary=", headers["Content-Type"])
        self.assertIn(b'name="image"; filename="source.wav"', body)
        self.assertIn(WAV, body)
        self.assertIn(b"juice-music/fixture-job", body)
        self.assertEqual(source.read_bytes(), WAV)

    def test_redirect_never_forwards_bearer_token_or_publishes_partial_audio(self):
        self.mode = "redirect"
        destination = self.root / "output.wav"
        item = {"filename": "output.wav", "subfolder": "safe", "type": "output"}
        with self.assertRaises(EngineError):
            self.client.download(item, destination)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.calls[0][1].startswith("/view?"))
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_empty_download_does_not_publish_file_but_valid_download_does(self):
        destination = self.root / "output.wav"
        item = {"filename": "output.wav", "subfolder": "safe", "type": "output"}
        self.mode = "empty"
        with self.assertRaises(EngineError):
            self.client.download(item, destination)
        self.assertEqual(list(self.root.iterdir()), [])
        self.mode = "normal"
        count = self.client.download(item, destination)
        self.assertEqual(count, len(WAV))
        self.assertEqual(destination.read_bytes(), WAV)
        self.assertEqual(list(self.root.glob("*.part")), [])


if __name__ == "__main__":
    unittest.main()
