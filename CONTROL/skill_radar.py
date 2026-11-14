"""Thin, disabled-by-default JC transport for the canonical JUICE-SKILLS runtime."""
import importlib.util
import ipaddress
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse


class RadarBridge:
    def __init__(self):
        self.mode = os.environ.get('JUICE_RADAR_MODE', 'disabled')
        self.root = os.environ.get('JUICE_SKILLS_ROOT', '')
        self.token = secrets.token_urlsafe(32)
        self.runtime = None
        self.error = None
        if self.mode == 'manual-v1':
            try:
                root = Path(self.root).expanduser().resolve()
                if not self.root or root == Path(__file__).resolve().parent.parent or Path(__file__).resolve().parent.parent in root.parents:
                    raise ValueError('Use a separate private JUICE-SKILLS checkout')
                assets = root / 'skills/skill-radar/assets'
                spec = importlib.util.spec_from_file_location('juice_canonical_radar', assets / 'jc_runtime.py')
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if module.API_VERSION != 1:
                    raise ValueError('Unsupported runtime')
                self.runtime = module.Radar(root)
                self.assets = assets
            except Exception:
                self.error = 'Canonical Radar unavailable. Check JUICE_SKILLS_ROOT and the reviewed companion version; nothing was collected.'
        elif self.mode != 'disabled':
            self.error = 'Unknown Radar mode. Use disabled or the explicitly approved manual-v1 mode.'

    def local_request(self, handler):
        host = handler.headers.get('Host', '')
        port = handler.server.server_address[1]
        allowed = {f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}'}
        try:
            local = ipaddress.ip_address(handler.client_address[0]).is_loopback and ipaddress.ip_address(handler.server.server_address[0]).is_loopback
        except ValueError:
            local = False
        origin = handler.headers.get('Origin')
        return (local and host in allowed and (origin is None or origin == f'http://{host}')
                and handler.headers.get('Sec-Fetch-Site') not in ('cross-site',))

    def handle(self, handler):
        path = urlparse(handler.path).path
        if path != '/skill-radar' and not path.startswith('/skill-radar/') and not path.startswith('/api/skill-radar'):
            return False
        def send(data, status=200):
            handler.send_json(data, status)
        if not self.local_request(handler):
            send({'error': 'Radar requires a loopback, same-origin JC connection.'}, 403)
            return True
        if handler.command == 'GET' and path == '/api/skill-radar/status':
            try:
                result = {'mode': self.mode, 'enabled': self.runtime is not None, 'error': self.error,
                          'automatic_sources': [], 'collection': 'authorised manual summaries only'}
                if self.runtime:
                    result.update(self.runtime.status())
                    result['token'] = self.token
                send(result)
            except Exception:
                send({'error': 'Radar storage unavailable; existing state was not reset.'}, 503)
            return True
        if not self.runtime:
            if handler.command == 'GET' and path == '/skill-radar':
                handler.send_bytes(b'<!doctype html><meta name="viewport" content="width=device-width"><title>Skill Radar disabled</title><main><a href="/">Back to JC</a><h1>Skill Radar is disabled</h1><p>No summaries are being collected. Review the installation and data-flow instructions before approving manual-v1.</p><p>If already approved, check JUICE_SKILLS_ROOT and the companion runtime version.</p></main>')
            else:
                send({'error': self.error or 'Radar is disabled. Activation requires explicit approval.'}, 403)
            return True
        try:
            if handler.command == 'GET' and path in ('/skill-radar', '/skill-radar/app.js'):
                filename, mime = ('jc.html', 'text/html; charset=utf-8') if path == '/skill-radar' else ('jc.js', 'text/javascript; charset=utf-8')
                handler.send_bytes((self.assets / filename).read_bytes(), content_type=mime)
            elif handler.command == 'POST':
                if not secrets.compare_digest(handler.headers.get('X-Juice-Radar-Token', ''), self.token):
                    send({'error': 'Reload Radar before submitting (session token changed).'}, 403)
                    return True
                lengths = handler.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= 65536 or handler.headers.get('Transfer-Encoding'):
                    send({'error': 'One Content-Length of 1–65536 bytes is required.'}, 413)
                    return True
                if handler.headers.get_content_type() != 'application/json':
                    send({'error': 'Expected application/json.'}, 415)
                    return True
                handler.connection.settimeout(3)
                body = handler.rfile.read(int(lengths[0]))
                if len(body) != int(lengths[0]):
                    send({'error': 'Interrupted import; nothing saved.'}, 400)
                    return True
                payload = json.loads(body)
                if path == '/api/skill-radar/events':
                    send(self.runtime.ingest(payload))
                elif path in ('/api/skill-radar/review', '/api/skill-radar/ballot') and payload == {}:
                    send(self.runtime.review(ballot=path.endswith('/ballot')))
                elif path == '/api/skill-radar/decisions':
                    send(self.runtime.decide(payload))
                elif path == '/api/skill-radar/pause':
                    send(self.runtime.pause(payload))
                else:
                    send({'error': 'Unknown Radar action.'}, 404)
            else:
                send({'error': 'Not found.'}, 404)
        except Exception as exc:
            # Never echo request bodies, filenames, private paths, or tracebacks.
            if type(exc).__name__ == 'RadarError':
                send({'error': str(exc)}, 400)
            else:
                send({'error': 'Radar request failed. Check JSON or local storage; nothing was reset.'}, 503)
        return True
