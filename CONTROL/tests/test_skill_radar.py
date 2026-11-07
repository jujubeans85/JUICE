"""Synthetic HTTP contract tests; no physical Mac or real personal data required."""
import contextlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

CONTROL = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CONTROL))
import skill_radar
spec=importlib.util.spec_from_file_location('jc_server',CONTROL/'server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)


class HTTPTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)/'JUICE-SKILLS'
        source=Path(os.environ.get('JUICE_RADAR_TEST_SKILLS_ROOT',CONTROL.parents[1]/'JUICE-SKILLS'))
        if not (source/'skills/skill-radar/assets/jc_runtime.py').is_file():
            self.fail('Set JUICE_RADAR_TEST_SKILLS_ROOT to the reviewed companion checkout')
        shutil.copytree(source,self.root,ignore=shutil.ignore_patterns('.git','.local','dist','__pycache__'))
        self.env=patch.dict(os.environ,{'JUICE_RADAR_MODE':'manual-v1','JUICE_SKILLS_ROOT':str(self.root)})
        self.env.start(); server.RADAR=skill_radar.RadarBridge()
        self.httpd=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.httpd.serve_forever,daemon=True);self.thread.start()
        self.port=self.httpd.server_address[1]; self.host=f'127.0.0.1:{self.port}'
        self.token=server.RADAR.token

    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close();self.thread.join();self.env.stop();self.temp.cleanup()

    def call(self,path='/api/skill-radar/status',data=None,headers=None,raw=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        hs={'Host':self.host}
        if data is not None or raw is not None:
            hs.update({'X-Juice-Radar-Token':self.token,'Content-Type':'application/json'})
        if headers: hs.update(headers)
        body=json.dumps(data) if raw is None and data is not None else raw
        conn.request('POST' if body is not None else 'GET',path,body=body,headers=hs)
        response=conn.getresponse(); content=response.read(); conn.close()
        try: content=json.loads(content)
        except ValueError: pass
        return response.status,content

    def event(self, identity='synthetic-a'):
        return dict(id=identity,source='manual',stage='task-complete',summary=f'Synthetic {identity} djay recording CSV session',source_quality='reported',sensitive=False,urgent=False,authorised=True,repeats=2)

    def test_disabled_means_no_state_and_no_ingest(self):
        with patch.dict(os.environ,{'JUICE_RADAR_MODE':'disabled'}): server.RADAR=skill_radar.RadarBridge()
        self.assertFalse(self.call()[1]['enabled'])
        self.assertEqual(self.call('/api/skill-radar/events',{'events':[self.event()]})[0],403)
        self.assertIn(b'disabled',self.call('/skill-radar')[1])
        self.assertFalse((self.root/'.local').exists())

    def test_missing_runtime_fails_closed(self):
        with patch.dict(os.environ,{'JUICE_SKILLS_ROOT':str(self.root/'missing')}): server.RADAR=skill_radar.RadarBridge()
        self.assertFalse(self.call()[1]['enabled'])
        self.assertEqual(self.call('/api/skill-radar/events',{'events':[self.event()]})[0],403)

    def test_end_to_end_review_decisions_and_restart(self):
        self.assertEqual(self.call('/api/skill-radar/events',{'events':[self.event()]})[1]['accepted'],1)
        rows=self.call('/api/skill-radar/review',{})[1]['suggestions'];self.assertTrue(rows)
        self.assertEqual(self.call('/api/skill-radar/decisions',{'id':'session-keeper','action':'save'})[0],200)
        server.RADAR=skill_radar.RadarBridge();self.token=server.RADAR.token
        state=self.call()[1];self.assertEqual(state['decisions']['session-keeper']['action'],'save')
        self.assertEqual(self.call('/api/skill-radar/events',{'events':[self.event()]})[1]['duplicates'],1)
        self.assertFalse(self.call('/api/skill-radar/review',{})[1]['suggestions'])

    def test_local_host_origin_and_csrf(self):
        for headers in [{'Host':'example.test'}, {'Origin':'https://example.test'}, {'Origin':'null'}, {'Sec-Fetch-Site':'cross-site'}]:
            with self.subTest(headers=headers):self.assertEqual(self.call(headers=headers)[0],403)
        self.assertEqual(self.call('/api/skill-radar/events',{'events':[self.event()]},{'X-Juice-Radar-Token':'old'})[0],403)
        self.assertEqual(self.call('/api/skill-radar/events',{'events':[self.event()]},{'Origin':'http://'+self.host})[0],200)

    def test_changed_token_after_restart(self):
        server.RADAR=skill_radar.RadarBridge()
        self.assertEqual(self.call('/api/skill-radar/events',{'events':[self.event()]})[0],403)

    def test_malformed_unknown_and_oversize_fail_without_writes(self):
        self.assertEqual(self.call('/api/skill-radar/events',raw='{broken')[0],503)
        self.assertEqual(self.call('/api/skill-radar/events',raw=' '*65537)[0],413)
        self.assertEqual(self.call('/api/skill-radar/events',{},headers={'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.call('/api/skill-radar/missing',{})[0],404)
        self.assertEqual(self.call('/api/skill-radar/events',{'events':[self.event(),{}]})[0],400)
        self.assertEqual(self.call()[1]['evidence_count'],0)

    def test_corrupt_state_fails_without_reset(self):
        self.call();path=self.root/'.local/skill-radar/state.json';path.write_text('{broken')
        self.assertEqual(self.call()[0],503);self.assertEqual(path.read_text(),'{broken')

    def test_ui_from_canonical_checkout_and_same_tab_back(self):
        status,html=self.call('/skill-radar');self.assertEqual(status,200)
        self.assertIn(b'href="/"',html);self.assertIn(b'/skill-radar/app.js',html)
        self.assertEqual(self.call('/skill-radar/app.js')[0],200)
        self.assertEqual(self.call('/skill-radar/../../catalog.json')[0],404)

    def test_pause_blocks_import_and_decision(self):
        self.assertEqual(self.call('/api/skill-radar/pause',{'paused':True})[0],200)
        self.assertEqual(self.call('/api/skill-radar/events',{'events':[self.event()]})[0],400)
        self.assertEqual(self.call('/api/skill-radar/decisions',{'id':'session-keeper','action':'save'})[0],400)
        self.assertEqual(self.call('/api/skill-radar/ballot',{})[1]['suggestions'],[])

    def test_root_and_folder_routes_preserved(self):
        with patch.object(server,'zed_status',return_value={'available':True}),patch.object(server,'diagnostics',return_value={}):
            status,html=self.call('/');self.assertEqual(status,200);self.assertIn(b'/skill-radar',html)
        self.assertEqual(self.call('/health')[0],200)
        with patch.object(server,'safe_target',return_value=Path(self.temp.name)),patch.object(server,'open_in_zed',return_value=(True,'Opened')),patch.object(server,'render_page',return_value=b'opened'):
            self.assertEqual(self.call('/open',raw='target=creative',headers={'Content-Type':'application/x-www-form-urlencoded'}),(200,b'opened'))

    def test_no_request_body_or_query_in_logs(self):
        import io
        output=io.StringIO()
        with contextlib.redirect_stderr(output):
            self.call('/api/skill-radar/status?private=SYNTHETIC_MARKER')
        self.assertNotIn('SYNTHETIC_MARKER',output.getvalue())

    def test_non_loopback_binding_rejected(self):
        address=self.httpd.server_address;self.httpd.server_address=('0.0.0.0',self.port)
        try:self.assertEqual(self.call()[0],403)
        finally:self.httpd.server_address=address

if __name__=='__main__':unittest.main()
