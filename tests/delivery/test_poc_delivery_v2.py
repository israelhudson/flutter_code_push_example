import base64
import os
import sys
import json
import copy
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

class AndroidPlanTests(unittest.TestCase):
    def test_mobile_mode_requires_full_github_and_never_authorizes_stable(self):
        plan = v2.mobile_plan('android_staging', 'github_test', 'full')
        self.assertIs(plan['stable_authorized'], False)
        self.assertEqual(plan['track'], 'staging')
        self.assertEqual(plan['target']['release_version'], '1.1.0+2')
        self.assertIsNone(v2.mobile_plan('none', 'none', 'controls_only'))
        for mode, scope, validation in [('android_staging','none','full'),
                                        ('android_staging','github_test','controls_only'),
                                        ('stable','github_test','full')]:
            with self.subTest(mode=mode,scope=scope,validation=validation), self.assertRaises(v2.lab.LabError):
                v2.mobile_plan(mode, scope, validation)

    def test_changed_target_or_stable_grant_cannot_enter_frozen_report(self):
        report = {'publication_scope':'github_test','validation_mode':'full',
                  'mobile_execution_plan': v2.mobile_plan('android_staging','github_test','full')}
        self.assertEqual(v2.require_mobile_plan(report), report['mobile_execution_plan'])
        for field, value in [('stable_authorized', True), ('track', 'stable')]:
            bad = copy.deepcopy(report)
            bad['mobile_execution_plan'][field] = value
            with self.assertRaises(v2.lab.LabError):
                v2.require_mobile_plan(bad)

class RefreshTests(unittest.TestCase):
    def fixture(self):
        report = {'title':'Rodada Android','validation_mode':'full','publication_scope':'github_test',
                  'commits':[], 'mobile_execution_plan':v2.mobile_plan('android_staging','github_test','full')}
        c = {'id':'delivery-'+'a'*32,'version':'2.0.0','rc_tag':'poc-v2.0.0-rc.1',
             'source_sha':'b'*40,'status':'published','publication_run':'123',
             'report_digest':'c'*64,'report_text':v2.lab.canonical(report)}
        presentation = {'rows':[['GitHub','poc-v2.0.0','Release publicada'],
            ['Web','1.1.0+2','Preview validado; não comprova produção'],
            ['Android','1.1.0+2 (patch 5)','Patch em staging; execução em dispositivo não comprovada'],
            ['iOS','Não validada','Sem publicação comprovada nesta entrega']], 'sources':[]}
        before = copy.deepcopy(presentation)
        before['rows'][2] = ['Android','1.1.0+2',
            'Patch staging pendente; execução local após os aceites e a Release GitHub']
        release = {'id':42,'tag_name':'poc-v2.0.0','name':'Release 2.0.0 — Rodada Android',
                   'draft':False,'prerelease':False,'updated_at':'time','assets':[],
                   'body':v2.final_body(c,before)}
        return c, presentation, release

    def test_verified_receipt_refresh_preserves_publication_link_and_updates_only_body(self):
        with patch.dict(os.environ, {'GITHUB_RUN_ID':'999'}):
            c, presentation, release = self.fixture()
            calls = []
            def api(path, data=None, method='GET', **kwargs):
                if data is not None:
                    calls.append((method,copy.deepcopy(data)))
                    release.update(data)
                if '/git/ref/' in path:
                    return {'object':{'type':'commit','sha':c['source_sha']}}
                return copy.deepcopy(release)
            with tempfile.TemporaryDirectory() as out, patch.object(v2,'api_control',return_value={'candidate':c,'presentation':presentation}), patch.object(v2.lab,'api',side_effect=api):
                v2.refresh_presentation(c['id'],out)
                self.assertEqual(calls,[('PATCH',{'body':v2.final_body(c,presentation)})])
                self.assertIn('/actions/runs/123',release['body'])
                self.assertNotIn('/actions/runs/999',release['body'])
                calls.clear()
                v2.refresh_presentation(c['id'],out)
                self.assertEqual(calls,[])

    def test_manual_body_or_moved_tag_blocks_without_patch(self):
        with patch.dict(os.environ, {'GITHUB_RUN_ID':'999'}):
            for changed in ('body','tag'):
                c, presentation, release = self.fixture()
                if changed == 'body': release['body'] += '\nEdição humana.'
                writes = []
                def api(path, data=None, *args, **kwargs):
                    if data is not None: writes.append(data)
                    if '/git/ref/' in path:
                        return {'object':{'type':'commit','sha':'d'*40 if changed=='tag' else c['source_sha']}}
                    return copy.deepcopy(release)
                with tempfile.TemporaryDirectory() as out, patch.object(v2,'api_control',return_value={'candidate':c,'presentation':presentation}), patch.object(v2.lab,'api',side_effect=api):
                    with self.assertRaises(v2.lab.LabError): v2.refresh_presentation(c['id'],out)
                    self.assertEqual(writes,[])

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
