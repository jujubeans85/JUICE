import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audit', ROOT / 'portfolio_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
NOW = '2026-11-01T00:00:00+00:00'


class FakeAPI:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        return self.responses.get(path, {'error': 'not captured', 'status': 404})

    pages = audit.API.pages


def fixture():
    p = 'repos/alice/one'
    a, b = 'a'*40, 'b'*40
    repo = {'id': 1, 'name': 'one', 'full_name': 'alice/one', 'owner': {'login':'alice'}, 'private':False,
            'visibility':'public', 'html_url':'https://github.com/alice/one', 'default_branch':'main',
            'pushed_at': '2026-10-31T00:00:00Z', 'has_pages': True, 'size':0}
    pr = {'number':1, 'title':'Keep this <script>test</script>', 'draft':True, 'html_url':'https://github.com/alice/one/pull/1',
          'head':{'ref':'feature', 'sha':b}, 'base':{'sha':a}}
    run = {'id':2, 'workflow_id':1, 'event':'pull_request', 'head_sha':b, 'conclusion':'failure', 'status':'completed', 'name':'CI', 'created_at':'2026-10-31T00:00:00Z'}
    data = {p+'/branches?per_page=100&page=1':[{'name':'main','commit':{'sha':a}}, {'name':'feature','commit':{'sha':b}}, {'name':'rollback/old','commit':{'sha':'c'*40}}],
            p+'/pulls?state=open&per_page=100&page=1':[pr], p+'/git/trees/'+a+'?recursive=1':{'tree':[{'path':'README.md','type':'blob','mode':'100644','sha':'d'*40}], 'truncated':False},
            p+'/actions/workflows?per_page=100&page=1':{'workflows':[], 'total_count':0},
            p+'/actions/runs?per_page=50&page=1':{'workflow_runs':[run], 'total_count':1},
            p+'/compare/'+a+'...'+b:{'status':'diverged','ahead_by':2,'behind_by':3}}
    return repo, data


class AuditTests(unittest.TestCase):
    def test_pagination_and_partial_page(self):
        api = FakeAPI({'x?per_page=100&page=1':[{}]*100, 'x?per_page=100&page=2':[{'id':101}]})
        self.assertEqual(len(api.pages('x')[0]), 101)
        self.assertTrue(api.pages('x')[1])
        del api.responses['x?per_page=100&page=2']
        rows, complete = api.pages('x')
        self.assertEqual(len(rows), 100)
        self.assertFalse(complete)

    def test_private_and_foreign_objects_are_discarded(self):
        repo, data = fixture()
        secret = {**repo, 'name':'secret-private-name', 'private':True}
        foreign = {**repo, 'name':'foreign', 'owner':{'login':'other'}}
        data['users/alice/repos?type=owner&per_page=100&page=1'] = [repo, secret, foreign]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'registry.json'
            path.write_text('{"repositories":[]}')
            s=audit.collect(FakeAPI(data), {'owner':'alice','registry_repository':'alice/index','registry_path':'registry.json','restricted_repository_count':1,'boundaries':{}}, NOW, path)
        self.assertEqual(len(s['repositories']),1)
        self.assertNotIn('secret-private-name',json.dumps(s))
        self.assertNotIn('foreign',json.dumps(s))

    def test_rollback_is_preserved_not_compared(self):
        repo, data=fixture()
        api=FakeAPI(data)
        s=audit.collect_repo(api,repo,NOW)
        self.assertEqual(s['branches'][1]['ahead_by'],2)
        self.assertTrue(s['branches'][2]['preserve'])
        self.assertFalse(any('...'+'c'*40 in x for x in api.calls))

    def test_size_zero_is_not_empty_repository(self):
        repo,data=fixture()
        self.assertFalse(audit.collect_repo(FakeAPI(data),repo,NOW)['empty_git_repository'])

    def test_actual_empty_repository_is_recognised(self):
        repo,data=fixture()
        data['repos/alice/one/branches?per_page=100&page=1']=[]
        data['repos/alice/one/git/trees/main?recursive=1']={'error':'HTTP 409','status':409}
        s=audit.collect_repo(FakeAPI(data),repo,NOW)
        self.assertTrue(s['empty_git_repository'])
        self.assertTrue(s['coverage']['tree'])

    def test_push_success_cannot_hide_failing_pr(self):
        repo,data=fixture()
        runs=data['repos/alice/one/actions/runs?per_page=50&page=1']['workflow_runs']
        runs.append({**runs[0],'id':3,'event':'push','conclusion':'success','created_at':'2026-10-31T00:01:00Z'})
        prs=audit.collect_repo(FakeAPI(data),repo,NOW)['pull_requests']
        self.assertEqual({r['conclusion'] for r in prs[0]['runs']},{'failure','success'})

    def test_old_pr_head_failure_not_claimed_current(self):
        repo,data=fixture()
        run=data['repos/alice/one/actions/runs?per_page=50&page=1']['workflow_runs'][0]
        run.update(head_sha='e'*40,pull_requests=[{'number':1,'head':{'sha':'e'*40}}])
        self.assertEqual(audit.collect_repo(FakeAPI(data),repo,NOW)['pull_requests'][0]['runs'],[])

    def test_external_preview_failure_is_reported(self):
        repo,data=fixture()
        data['repos/alice/one/commits/'+'b'*40+'/status']={'state':'failure','statuses':[{'context':'netlify/example/deploy-preview','state':'failure','target_url':'https://example.test/preview'}]}
        s={'repositories':[audit.collect_repo(FakeAPI(data),repo,NOW)],'registry':{'public_names':['one'],'unavailable':False,'url':'https://github.com/alice/index'},'enumeration_complete':True}
        fs=audit.findings(s,{'expected_public_repositories':1,'manual_gates':[],'owner':'alice'})
        self.assertTrue(any('netlify/example/deploy-preview' in f['observation'] for f in fs))

    def test_disabled_workflow_is_an_exception(self):
        repo,data=fixture()
        data['repos/alice/one/actions/workflows?per_page=100&page=1']={'workflows':[{'id':9,'name':'Audit','state':'disabled_inactivity'}]}
        s={'repositories':[audit.collect_repo(FakeAPI(data),repo,NOW)],'registry':{'public_names':['one'],'unavailable':False,'url':'https://github.com/alice/index'},'enumeration_complete':True}
        fs=audit.findings(s,{'expected_public_repositories':1,'manual_gates':[],'owner':'alice'})
        self.assertTrue(any(f['id']=='WORKFLOW-1-9' for f in fs))

    def test_no_network_in_recorded_mode(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'capture.json').write_text('{"known":[]}')
            with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
                api=audit.API(recorded_dir=d)
                self.assertEqual(api.get('known'),[])
                self.assertEqual(audit.error_status(api.get('unknown')),0)

    def test_api_rejects_arbitrary_hosts_and_paths(self):
        api=audit.API()
        for path in ['https://evil.test/','/repos/x/y','repos/x/../secret']:
            with self.assertRaises(ValueError): api.get(path)

    def test_redirect_does_not_forward_request(self):
        self.assertIsNone(audit.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.test'))

    def test_unchanged_findings_keep_history(self):
        f={'id':'X','state':'blocked','observation':'Known','recommendation':'Review once','evidence':'https://github.com/a/b'}
        first=audit.reconcile([f],{},NOW)
        second=audit.reconcile([f],{'findings':first},'2026-12-01T00:00:00Z')
        self.assertEqual(second[0]['change'],'unchanged')
        self.assertEqual(second[0]['first_seen'],NOW)
        self.assertEqual(second[0]['last_changed'],NOW)

    def test_incomplete_scan_does_not_resolve_previous_risk(self):
        f={'id':'X','state':'review','first_seen':NOW,'last_changed':NOW}
        self.assertEqual(audit.reconcile([],{'findings':[f]},NOW,False)[0]['state'],'review')
        self.assertEqual(audit.reconcile([],{'findings':[f]},NOW,True)[0]['state'],'resolved')

    def test_resolved_finding_can_reopen(self):
        f={'id':'X','state':'review','observation':'bad','recommendation':'fix','evidence':'https://github.com/a/b'}
        first=audit.reconcile([f],{},NOW)
        resolved=audit.reconcile([],{'findings':first},NOW)
        self.assertEqual(audit.reconcile([f],{'findings':resolved},NOW)[0]['change'],'reopened')

    def test_render_escapes_source_content(self):
        repo,data=fixture()
        s={'repositories':[audit.collect_repo(FakeAPI(data),repo,NOW)], 'captured_at':NOW,'findings':[], 'restricted_repository_count':1,'collection_complete':True,'registry':{'url':'https://github.com/a/b'},'owner':'alice','boundaries':{}}
        page=audit.report_html(s,'')
        self.assertNotIn('<script>test</script>',page)
        self.assertIn('&lt;script&gt;',page)
        self.assertIn("default-src 'none'",page)
        self.assertIsNone(audit.safe_url('https://user:password@evil.test/'))

    def test_artifact_restore_ignores_pr_and_reads_without_extracting(self):
        zbytes=io.BytesIO()
        with zipfile.ZipFile(zbytes,'w') as z:
            z.writestr('snapshot.json',json.dumps({'schema_version':1,'owner':'alice','repositories':[], 'collection_complete':True}))
            z.writestr('../../never-extracted','untrusted')
        api=FakeAPI({'repos/alice/JUICE/actions/artifacts?name=portfolio-state&per_page=100&page=1':{'artifacts':[
            {'id':3,'name':'portfolio-state','created_at':'3','workflow_run':{'head_branch':'feature'}},
            {'id':2,'name':'portfolio-state','created_at':'2','workflow_run':{'head_branch':'main'}}]}})
        api.token='test-token'
        class Opener:
            def open(self,req,timeout):
                self.path=req.full_url
                return io.BytesIO(zbytes.getvalue())
        api.opener=Opener()
        state,message=audit.previous_artifact(api,'alice/JUICE')
        self.assertEqual(state['owner'],'alice')
        self.assertIn('/artifacts/2/zip',api.opener.path)


class ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('control',ROOT.parent/'CONTROL'/'server.py')
        cls.control=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.control)

    def test_fixed_report_preference_and_symlink_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            live=root/'data'/'MAINTENANCE'/'latest'/'report.html'
            baseline=root/'repo'/'MAINTENANCE'/'baseline'/'report.html'
            live.parent.mkdir(parents=True)
            baseline.parent.mkdir(parents=True)
            baseline.write_bytes(b'baseline')
            with patch.object(self.control,'DATA_ROOT',root/'data'),patch.object(self.control,'CONTROL_ROOT',root/'repo'/'CONTROL'):
                self.assertEqual(self.control.maintenance_report(),b'baseline')
                live.write_bytes(b'latest')
                self.assertEqual(self.control.maintenance_report(),b'latest')
                live.unlink()
                secret=root/'secret'
                secret.write_bytes(b'private')
                live.symlink_to(secret)
                self.assertEqual(self.control.maintenance_report(),b'baseline')

    def test_http_home_health_report_and_no_path_selection(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),self.control.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        with patch.object(self.control,'zed_status',return_value={'available':True,'command':'test','error':None}),patch.object(self.control,'maintenance_report',return_value=b'public audit'):
            thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                with urllib.request.urlopen(base+'/maintenance?path=/etc/passwd') as r:
                    self.assertEqual(r.read(),b'public audit')
                    self.assertEqual(r.headers['Cache-Control'],'no-store')
                with urllib.request.urlopen(base+'/health') as r:
                    self.assertTrue(json.load(r)['ok'])
                with urllib.request.urlopen(base+'/') as r:
                    self.assertIn(b'href="/maintenance"',r.read())
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__=='__main__':
    unittest.main()
