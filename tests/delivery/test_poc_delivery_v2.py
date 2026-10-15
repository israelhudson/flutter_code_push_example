import base64
import os
import sys
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'/'delivery'))
import delivery_v2 as v2

class SourceChecks(unittest.TestCase):
    def test_v2_requires_successful_push_on_configured_main_or_exact_release(self):
        source = 'a' * 40
        release = 'poc-release/2.0.0'
        valid = {'id': 42, 'head_sha': source, 'head_branch': 'main',
                 'event': 'push', 'status': 'completed', 'conclusion': 'success'}
        job = {'name': 'Slack / Verificar contratos', 'status': 'completed',
               'conclusion': 'success'}
        cases = [({}, True), ({'head_branch': release}, True),
                 ({'head_branch': 'slack-main'}, False),
                 ({'head_branch': 'poc-release/3.0.0'}, False),
                 ({'event': 'pull_request'}, False),
                 ({'head_sha': 'b' * 40}, False),
                 ({'conclusion': 'failure'}, False)]
        with patch.dict(os.environ, {'DELIVERY_STATE_V2': 'true', 'POC_SOURCE_BRANCH': 'main'}):
            for changes, accepted in cases:
                with self.subTest(changes=changes), tempfile.TemporaryDirectory() as output, \
                        patch.object(v2.lab, 'api', side_effect=[
                            {'workflow_runs': [{**valid, **changes}]}, {'jobs': [job]}]):
                    if accepted:
                        v2.legacy.checked_source(source, output, release)
                    else:
                        with self.assertRaises(v2.lab.LabError):
                            v2.legacy.checked_source(source, output, release)
                    self.assertEqual(json.loads(Path(output, 'source-check.json').read_text())['success'], accepted)
            for conclusion in ('failure', 'skipped'):
                with self.subTest(job=conclusion), tempfile.TemporaryDirectory() as output, \
                        patch.object(v2.lab, 'api', side_effect=[
                            {'workflow_runs': [valid]}, {'jobs': [{**job, 'conclusion': conclusion}]}]):
                    with self.assertRaises(v2.lab.LabError):
                        v2.legacy.checked_source(source, output, release)

class JournalTests(unittest.TestCase):
    def test_existing_record_is_verified_at_immutable_commit_without_writes(self):
        value={'status':'approved','revision':2}
        encoded=base64.b64encode(v2.lab.canonical(value).encode()).decode()
        def api(path,data=None,*args,**kwargs):
            self.assertIsNone(data)
            return {'content':encoded} if '/contents/' in path else {'object':{'sha':'a'*40}}
        with patch.object(v2.lab,'api',side_effect=api):
            r=v2.write_record('candidates/delivery-'+'b'*32+'/event-2.json',value)
        self.assertEqual(r['commit'],'a'*40)
    def test_different_existing_record_is_never_overwritten(self):
        with patch.object(v2.lab,'api',side_effect=[{'object':{'sha':'a'*40}},{'content':base64.b64encode(b'{}').decode()}]):
            with self.assertRaises(v2.lab.LabError):
                v2.write_record('candidates/delivery-'+'b'*32+'/event-2.json',{'status':'approved'})
    def test_disabled_adapter_never_calls_remote(self):
        with patch.dict(os.environ,{'DELIVERY_V2_ENABLED':'false'}):
            with self.assertRaises(v2.lab.LabError):v2.api_control('take')
    def test_history_ack_requires_verified_write(self):
        work={'task':{'id':1,'kind':'history','revision':2,'event':{'status':'approved'}},'candidate':{'id':'delivery-'+'a'*32}}
        with patch.object(v2,'api_control',return_value=work) as api, patch.object(v2,'write_record',side_effect=v2.lab.LabError('github down')):
            with self.assertRaises(v2.lab.LabError):v2.drain('/tmp/unused-test')
            self.assertEqual(api.call_count,1)

    def test_final_release_keeps_table_changes_and_history_without_preview(self):
        report={'title':'Corrigir login','validation_mode':'full','rc_tag':'poc-v2.0.0-rc.2',
                'preview_url':'https://israelhudson.github.io/flutter_code_push_example/snapshots/'+'a'*40+'/',
                'changelog':'fix: login (#12)','commits':[{'title':'fix: login (#12)','sha':'a'*40}]}
        c={'id':'delivery-'+'a'*32,'version':'2.0.0','source_sha':'a'*40,'rc_tag':report['rc_tag'],
           'report_digest':'b'*64,'report_text':v2.lab.canonical(report)}
        with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','DELIVERY_STATE_V2':'true'}):
            body=v2.final_body(c)
            self.assertTrue(body.startswith('## Versões e publicação'))
            self.assertIn('## Mudanças',body)
            self.assertIn('/pull/12',body)
            self.assertIn('/actions/runs/123',body)
            self.assertNotIn(report['preview_url'],body)
            self.assertEqual(v2.legacy.release_name(c),'Release 2.0.0 — Corrigir login')

if __name__=='__main__':unittest.main()
