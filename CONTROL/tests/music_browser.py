#!/usr/bin/env python3
"""Exercise the real Music Door in Chromium with an explicit test engine.

Run after installing playwright==1.62.0 and its Chromium browser:
    python3 CONTROL/tests/music_browser.py

The HTTP handler, persistent queue and browser app are real. FakeComfy replaces
only the GPU engine. It returns silence/transport fixtures, not generated music.
These checks verify UI integration and audio controls, not playback quality,
real GPU execution, Safari, or a physical iPhone/iPad.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import sys
import tempfile
import threading
import traceback

from playwright.sync_api import expect, sync_playwright


TEST_ROOT = Path(__file__).resolve().parent
CONTROL_ROOT = TEST_ROOT.parent
REPO_ROOT = CONTROL_ROOT.parent
for directory in (CONTROL_ROOT, TEST_ROOT):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import server as jc_server
from music.build_preview import build_preview
from music.http import MusicHTTP
from music.service import MusicService
from test_music_service import FakeComfy, WAV


VIEWPORTS = (
    ("iphone", 390, 844, True),
    ("ipad", 834, 1112, True),
    ("desktop", 1440, 1000, False),
)


@contextmanager
def running_jc():
    """Serve the actual JC Handler, without touching a user's install or data."""
    with tempfile.TemporaryDirectory(prefix="jc-browser-fixture-") as directory:
        engine = FakeComfy()
        service = MusicService(Path(directory), engine, start_worker=True)
        service.poll_interval = 0.01
        service.max_wait = 10
        music = MusicHTTP(directory, service=service, private_origin="", allowed_login="")
        previous_music = jc_server.MUSIC
        jc_server.MUSIC = music

        class QuietHandler(jc_server.Handler):
            def log_message(self, *_args):
                pass

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        httpd.daemon_threads = True
        thread = threading.Thread(target=httpd.serve_forever,
                                  kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}", service, engine
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)
            music.close()
            jc_server.MUSIC = previous_music


def no_horizontal_overflow(page, description):
    dimensions = page.evaluate("""() => ({
      viewport: innerWidth,
      document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth
    })""")
    assert max(dimensions["document"], dimensions["body"]) <= dimensions["viewport"] + 1, (
        f"Horizontal overflow in {description}: {dimensions}"
    )


def take_card(page, title):
    return page.locator(".take-card").filter(
        has=page.get_by_role("heading", name=title, exact=True)
    )


def exercise_viewport(browser, origin, service, engine, artifacts, name, width, height, mobile, log):
    context = browser.new_context(viewport={"width": width, "height": height},
                                  device_scale_factor=1, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.set_default_timeout(15000)
    errors, unexpected_requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: unexpected_requests.append(request.url)
            if request.url.startswith(("http://", "https://")) and not request.url.startswith(origin + "/") else None)
    before_submissions = len(engine.submissions)
    title = f"Warm funk · {name} browser fixture"
    lyrics = "[verse]\nLeave a little room for the rhythm\nLet the quiet find its feet"

    try:
        page.goto(origin + "/music/", wait_until="domcontentloaded")
        expect(page.locator("#connection-label")).to_have_text("Ready")
        expect(page.locator("#generate-button")).to_be_enabled()
        no_horizontal_overflow(page, f"{name} Create")

        page.locator('[data-preset="funk"]').click()
        style = page.locator("#style").input_value()
        assert "Soulful funk" in style
        page.locator("#title").fill(title)
        page.locator("#lyrics").fill(lyrics)
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#connection-label")).to_have_text("Ready")
        expect(page.locator("#title")).to_have_value(title)
        expect(page.locator("#style")).to_have_value(style)
        expect(page.locator("#lyrics")).to_have_value(lyrics)
        no_horizontal_overflow(page, f"{name} populated Create")
        page.screenshot(path=str(artifacts / f"{name}.png"), full_page=True)

        page.locator("#generate-button").click()
        expect(page.locator("#panel-takes")).to_be_visible()
        card = take_card(page, title)
        expect(card).to_be_visible()
        expect(card.locator(".take-status")).to_have_text("Ready to listen", timeout=20000)
        job_id = card.get_attribute("data-id")
        assert service.get(job_id)["status"] == "succeeded"
        expect(card.locator("audio").first).to_be_visible()
        assert card.locator("audio").first.get_attribute("controls") is not None
        expect(card.get_by_role("link", name="Download ↓").first).to_be_visible()
        # No play() call: FakeComfy's MP3 is deliberately an opaque transport fixture.
        no_horizontal_overflow(page, f"{name} Takes")

        card.locator(".keep-button").click()
        expect(card.locator(".keep-button")).to_have_attribute("aria-pressed", "true")
        assert service.get(job_id)["kept"] is True
        page.locator("#filter-kept").click()
        expect(page.locator("#filter-kept")).to_have_attribute("aria-pressed", "true")
        expect(card).to_be_visible()
        expect(page.locator('.take-card:visible .keep-button[aria-pressed="false"]')).to_have_count(0)

        page.locator("#tab-create").click()
        page.locator('input[name="task"][value="cover"]').check()
        expect(page.locator("#source-section")).to_be_visible()
        expect(page.locator("#composition")).to_be_disabled()
        expect(page.locator("#composition")).to_have_value("melody")
        expect(page.locator("#generate-button")).to_be_disabled()
        page.locator("#reference-file").set_input_files(
            {"name": "reference.wav", "mimeType": "audio/wav", "buffer": WAV}
        )
        expect(page.locator("#source-status")).to_contain_text("Reference saved in JC")
        expect(page.locator("#source-name")).to_have_text("reference.wav")
        cover_title = f"Rework · {name} browser fixture"
        page.locator("#title").fill(cover_title)
        expect(page.locator("#generate-button")).to_be_enabled()
        no_horizontal_overflow(page, f"{name} Rework")
        page.locator("#generate-button").click()
        expect(page.locator("#panel-takes")).to_be_visible()
        # A newly submitted, unkept take must be visible even after using Kept.
        expect(page.locator("#filter-all")).to_have_attribute("aria-pressed", "true")
        cover_card = take_card(page, cover_title)
        expect(cover_card).to_be_visible()
        expect(cover_card.locator(".take-status")).to_have_text("Ready to listen", timeout=20000)
        cover = service.get(cover_card.get_attribute("data-id"))
        assert cover["task"] == "cover" and cover["composition"] == "melody"
        assert cover["source_id"] and cover["kept"] is False
        assert engine.uploads[-1][2] == WAV, "Reference bytes changed before engine handoff"
        assert len(engine.submissions) == before_submissions + 2, "Expected exactly one new song and one rework"

        page.locator("#tab-setup").click()
        expect(page.locator("#setup-badge")).to_have_text("Ready")
        expect(page.locator("#capability-cover")).to_have_text("Available")
        no_horizontal_overflow(page, f"{name} Setup")
        assert not errors, f"Browser JavaScript errors: {errors}"
        assert not unexpected_requests, f"Unexpected external requests: {unexpected_requests}"
        log(f"PASS {name} {width}px: layout, readiness, preset, durable draft, real HTTP queue, Keep/filter, rework upload and visible new take")
    except Exception:
        try:
            page.screenshot(path=str(artifacts / f"failure-{name}.png"), full_page=True)
        except Exception:
            pass
        raise
    finally:
        context.close()


def exercise_offline_preview(browser, artifacts, log):
    with tempfile.TemporaryDirectory(prefix="jc-offline-preview-") as directory:
        path = build_preview(Path(directory) / "preview.html")
        context = browser.new_context(viewport={"width": 390, "height": 844},
                                      is_mobile=True, has_touch=True)
        context.add_init_script("""(() => {
          window.__previewCalls = {fetch: [], worker: []};
          const fetchOriginal = window.fetch;
          window.fetch = function(...args) {
            window.__previewCalls.fetch.push(String(args[0]));
            return fetchOriginal.apply(this, args);
          };
          if (navigator.serviceWorker) {
            const registerOriginal = navigator.serviceWorker.register.bind(navigator.serviceWorker);
            navigator.serviceWorker.register = function(...args) {
              window.__previewCalls.worker.push(String(args[0]));
              return registerOriginal(...args);
            };
          }
        })();""")
        page = context.new_page()
        page.set_default_timeout(15000)
        requests, errors = [], []
        page.on("request", lambda request: requests.append(request.url)
                if request.url.startswith(("http://", "https://", "ws://", "wss://")) else None)
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(path.as_uri(), wait_until="load")
            expect(page.locator(".studio-heading .eyebrow")).to_have_text("INTERFACE PREVIEW")
            expect(page.locator("#connection-message")).to_have_text(
                "Draft and explore here. Generation connects through your installed JC Music Door."
            )
            expect(page.locator("#generate-button")).to_be_disabled()
            no_horizontal_overflow(page, "offline preview Create")
            page.locator('[data-preset="choir"]').click()
            expect(page.locator("#style")).to_have_value(re.compile(r"^A dark, expressive choir"))
            page.locator("#tab-takes").click()
            expect(page.locator("#panel-takes")).to_be_visible()
            expect(page.locator(".take-card")).to_have_count(0)
            page.locator("#tab-setup").click()
            expect(page.locator("#setup-badge")).to_have_text("Interface preview")
            expect(page.locator("#refresh-engine")).to_be_disabled()
            no_horizontal_overflow(page, "offline preview Setup")
            page.locator("#tab-create").click()
            page.screenshot(path=str(artifacts / "offline-preview.png"), full_page=True)
            calls = page.evaluate("window.__previewCalls")
            assert calls == {"fetch": [], "worker": []}, f"Preview attempted network or worker operations: {calls}"
            assert not requests, f"Preview attempted external connections: {requests}"
            assert not errors, f"Preview JavaScript errors: {errors}"
            log("PASS offline file preview: editable UI and tabs, disabled generation, no recordings, zero fetch/worker/network calls")
        except Exception:
            try:
                page.screenshot(path=str(artifacts / "failure-offline-preview.png"), full_page=True)
            except Exception:
                pass
            raise
        finally:
            context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", type=Path, default=REPO_ROOT / "artifacts" / "music-ui")
    arguments = parser.parse_args()
    artifacts = arguments.artifacts_dir.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    with (artifacts / "browser-smoke.log").open("w", encoding="utf-8") as output:
        def log(message):
            print(message, flush=True)
            output.write(message + "\n")
            output.flush()

        log("Music browser smoke: Chromium + real JC HTTP/service + explicit FakeComfy engine.")
        log("No GPU or real generated music. Audio control presence is tested; listening is not.")
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    with running_jc() as (origin, service, engine):
                        for name, width, height, mobile in VIEWPORTS:
                            exercise_viewport(browser, origin, service, engine, artifacts,
                                              name, width, height, mobile, log)
                    exercise_offline_preview(browser, artifacts, log)
                finally:
                    browser.close()
            log("PASS all browser smoke checks. Viewport screenshots are Chromium emulation, not physical Apple-device validation.")
            return 0
        except Exception:
            log(traceback.format_exc())
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
