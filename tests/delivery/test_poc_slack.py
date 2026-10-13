import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import poc_slack as poc
import release_lab as lab


class POCContracts(unittest.TestCase):
    def test_cut_requires_successful_post_merge_run_and_job(self):
        valid = {'id': 42, 'head_sha': 'a'*40, 'head_branch': 'slack-main',
                 'event': 'push', 'status': 'completed', 'conclusion': 'success'}
        job = {'name': 'Slack / Verificar contratos', 'status': 'completed', 'conclusion': 'success'}
        for changes in ({'event': 'pull_request'}, {'head_sha': 'b'*40},
                        {'head_branch': 'main'}, {'conclusion': 'failure'}, {'status': 'in_progress'}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as out, \
                    patch.object(lab, 'api', return_value={'workflow_runs': [{**valid, **changes}]}) as api:
                with self.assertRaisesRegex(lab.LabError, 'check do PR'):
                    poc.checked_source('a'*40, out, 'poc-release/1.14.0')
                self.assertEqual(api.call_count, 1)
        for conclusion in ('failure', 'skipped', 'success'):
            with self.subTest(job=conclusion), tempfile.TemporaryDirectory() as out, \
                    patch.object(lab, 'api', side_effect=[{'workflow_runs': [valid]},
                               {'jobs': [{**job, 'conclusion': conclusion}]}]):
                if conclusion == 'success':
                    poc.checked_source('a'*40, out, 'poc-release/1.14.0')
                    self.assertTrue(json.loads(Path(out, 'source-check.json').read_text())['success'])
                else:
                    with self.assertRaises(lab.LabError): poc.checked_source('a'*40, out, 'poc-release/1.14.0')
        with tempfile.TemporaryDirectory() as out, patch.object(lab, 'api', side_effect=[
                {'workflow_runs': [{**valid, 'head_branch': 'poc-release/1.14.0'}]}, {'jobs': [job]}]):
            poc.checked_source('a'*40, out, 'poc-release/1.14.0')
            self.assertTrue(json.loads(Path(out, 'source-check.json').read_text())['success'])

    def test_missing_post_merge_check_stops_before_git_effects(self):
        plan = {'version': '1.14.0', 'rc_tag': 'poc-v1.14.0-rc.1', 'rc_number': 1,
                'id': 'poc-'+'a'*32, 'source_sha': 'a'*40, 'branch': 'poc-release/1.14.0',
                'creator': 'israelhudson', 'publication_scope': 'none'}
        with tempfile.TemporaryDirectory() as out, patch.object(poc, 'protect'), \
                patch.object(poc, 'control', return_value=plan), patch.object(lab, 'trusted_source'), \
                patch.object(lab, 'api', return_value={'workflow_runs': []}), \
                patch.object(lab, 'create_ref_verified') as refs:
            with self.assertRaises(lab.LabError): poc.prepare('1.14.0', 'login', 'none', out)
            refs.assert_not_called()

    def test_exclusive_origin(self):
        self.assertEqual(poc.backend_origin('https://'+'a'*20+'.supabase.co/'),'https://'+'a'*20+'.supabase.co')
        for url in ('https://uvfwvplcziehxrkidrxh.supabase.co','http://'+'a'*20+'.supabase.co','https://'+'a'*20+'.supabase.co?x=1','https://token@'+'a'*20+'.supabase.co'):
            with self.subTest(url=url),self.assertRaises(lab.LabError):poc.backend_origin(url)

    def test_disabled_cli_has_no_network_effect(self):
        with tempfile.TemporaryDirectory() as out,patch.dict(os.environ,{},clear=True),patch.object(sys,'argv',['poc','prepare','--version','1.0.0','--title','Ensaio','--output',out]),patch.object(poc,'control') as remote:
            self.assertEqual(poc.main(),1)
            remote.assert_not_called()
            self.assertFalse(json.loads(Path(out,'blocked.json').read_text())['distribution_performed'])

    def test_preview_identity_blocks_before_registration(self):
        with tempfile.TemporaryDirectory() as out,patch.object(poc,'control') as remote:
            with self.assertRaises(lab.LabError):poc.register({'source_sha':'a'*40},{'source_sha':'b'*40},{'success':True},out)
            remote.assert_not_called()

    def test_existing_publication_returns_exact_receipt_without_git_effects(self):
        receipt={'release_id':123,'source_sha':'a'*40}
        with tempfile.TemporaryDirectory() as out,patch.object(poc,'protect'),patch.object(poc,'control',side_effect=[{'source_sha':'a'*40,'publication_scope':'github_test'},{'already_published':True,'receipt':receipt}]),patch.object(lab,'create_ref_verified') as tag,patch.object(lab,'api') as api:
            self.assertEqual(poc.publish('poc-'+'a'*32,out),receipt)
            tag.assert_not_called();api.assert_not_called()

    def test_lab_channel_and_publication_roles_are_not_shell_interpolated(self):
        root=Path(__file__).resolve().parents[2]
        prepare=(root/'.github/workflows/poc-slack-prepare.yml').read_text()
        self.assertIn('POC_REGISTRATION_SECRET',prepare)
        self.assertNotIn('SLACK_BOT_TOKEN',prepare)
        self.assertNotIn('issues: write',prepare)
        self.assertIn('group: pages-preview',prepare)
        publish=(root/'.github/workflows/poc-slack-publish.yml').read_text()
        self.assertIn('POC_PUBLICATION_SECRET',publish)
        self.assertNotIn('shorebird patch',publish)
        preview=(root/'.github/workflows/poc-slack-preview.yml').read_text()
        self.assertIn('github.event.pull_request.head.repo.full_name == github.repository',preview)
        self.assertIn('path: trusted',preview)
        self.assertIn('persist-credentials: false',preview)

    def test_release_notes_keep_platform_bases_and_actual_patches_separate(self):
        report={'platforms':{'android':{'base_release_version':'1.0.0+1','effective_patch':None},'ios':{'base_release_version':None,'effective_patch':None}}}
        text=poc.release_body({'source_sha':'a'*40,'report_digest':'b'*64,'report_text':lab.canonical(report)})
        self.assertIn('effective_patch',text)
        self.assertIn('base_release_version',text)


if __name__=='__main__':unittest.main()
