"""Names are a frozen identity, not a cosmetic alias for an old tag."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools' / 'delivery'))
import delivery_names as names
import delivery_v2 as delivery
import configure_delivery_names as configure
import poc_slack as adapter
import test_poc_delivery_android_staging as android_fixtures


class FrozenNamesTests(unittest.TestCase):
    def test_new_and_historical_lineages_have_no_cross_namespace_alias(self):
        for prefix, branch in [('', 'release/'), ('poc-', 'poc-release/')]:
            c = {'version': '1.16.0', 'rc_number': 2,
                 'rc_tag': prefix + 'v1.16.0-rc.2', 'branch': branch + '1.16.0'}
            self.assertEqual(names.final_tag(c), prefix + 'v1.16.0')
            self.assertEqual(names.frozen_names(c)['branch'], c['branch'])
            bad = {**c, 'branch': ('release/' if prefix else 'poc-release/') + '1.16.0'}
            with self.assertRaises(names.lab.LabError): names.frozen_names(bad)

    def test_malformed_or_mismatched_rc_cannot_choose_a_release(self):
        base = {'version': '1.16.0', 'rc_number': 2, 'rc_tag': 'v1.16.0-rc.2'}
        for field, value in [('version','1.17.0'),('rc_number',1),('rc_number',True),
                             ('rc_tag','v1.16.0'),('rc_tag','other-v1.16.0-rc.2'),
                             ('rc_tag','v1.16.0-rc.02'),('rc_tag','v1.16.0-rc.2\n')]:
            with self.subTest(field=field,value=value), self.assertRaises(names.lab.LabError):
                names.frozen_names({**base, field:value})

    def test_official_table_and_historical_table_keep_their_own_identifiers(self):
        for prefix in ('', 'poc-'):
            c = {'id':'delivery-'+'a'*32, 'version':'1.16.0', 'rc_tag':prefix+'v1.16.0-rc.1',
                 'source_sha':'a'*40, 'report_digest':'b'*64,
                 'report_text':json.dumps({'title':'Login','commits':[]})}
            with patch.dict(os.environ, {'GITHUB_RUN_ID':'123'}):
                body = delivery.final_body(c)
            self.assertIn('| GitHub | '+prefix+'v1.16.0 |', body)
            self.assertIn('Candidata preservada: `'+c['rc_tag']+'`', body)


class OfficialEffectsTests(unittest.TestCase):
    def test_publish_creates_only_final_tag_from_frozen_candidate_namespace(self):
        for prefix in ('', 'poc-'):
            report = {'title':'Login','commits':[], 'platforms':{}, 'validation_mode':'controls_only'}
            c = {'id':'delivery-'+'a'*32,'version':'1.16.0','rc_number':2,
                 'rc_tag':prefix+'v1.16.0-rc.2','source_sha':'a'*40,
                 'publication_scope':'github_test','report_digest':'b'*64,
                 'report_text':json.dumps(report)}
            calls = []
            def control(op, **kwargs):
                calls.append(op)
                return c if op=='state' else None if op=='presentation' else {}
            def api(path, data=None, method='GET', **kwargs):
                if method == 'POST':
                    return {**data, 'id':44, 'published_at':'time',
                            'html_url':'https://github.com/'+adapter.lab.REPOSITORY+'/releases/tag/'+prefix+'v1.16.0'}
                return None
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as out, \
                    patch.dict(os.environ, {'DELIVERY_STATE_V2':'true','GITHUB_RUN_ID':'123'}), \
                    patch.object(adapter,'control',side_effect=control), \
                    patch.object(adapter,'protect'), patch.object(adapter,'release_body',delivery.final_body), \
                    patch.object(adapter.lab,'api',side_effect=api), patch.object(adapter.lab,'create_ref_verified') as refs:
                receipt = adapter.publish(c['id'],out)
                refs.assert_called_once_with('tags/'+prefix+'v1.16.0','a'*40)
                self.assertEqual(receipt['tag'],prefix+'v1.16.0')
                self.assertEqual(calls[-1],'complete')

    def test_mismatched_plan_stops_before_ref_creation(self):
        plan = {'version':'1.16.0','rc_number':1,'rc_tag':'v1.16.0-rc.1',
                'branch':'poc-release/1.16.0'}
        with patch.dict(os.environ, {'DELIVERY_STATE_V2':'true'}), \
                patch.object(adapter,'protect'), patch.object(adapter,'control',return_value=plan), \
                patch.object(adapter.lab,'create_ref_verified') as refs:
            with self.assertRaises(adapter.lab.LabError):
                adapter.prepare('1.16.0','Login','none','/unused')
            refs.assert_not_called()


class OfficialProtectionTests(unittest.TestCase):
    def test_plan_has_only_additive_rules_and_no_human_review_requirement(self):
        definitions = configure.definitions()
        self.assertEqual({d['name'] for d in definitions},set(names.GUARDS))
        for d in definitions:
            self.assertEqual(d['bypass_actors'],[])
            self.assertEqual(d['enforcement'],'active')
            if d['target']=='branch':
                checks = next(r for r in d['rules'] if r['type']=='required_status_checks')['parameters']
                self.assertEqual({c['context'] for c in checks['required_status_checks']},names.CHECKS)
                self.assertTrue(checks['do_not_enforce_on_create'])
                self.assertEqual(next(r for r in d['rules'] if r['type']=='pull_request')['parameters']['required_approving_review_count'],0)

    def test_missing_official_guards_block_before_activation(self):
        with patch.object(names.lab,'api',return_value=[]):
            with self.assertRaises(names.lab.LabError): names.protect()


class OfficialAndroidAuthorizationTests(unittest.TestCase):
    def test_official_android_receipt_remains_bound_to_its_exact_final_tag(self):
        fixture = android_fixtures.AndroidStagingTests()
        fixture.setUp()
        fixture.manifest['rc_tag'] = fixture.manifest['rc_tag'].removeprefix('poc-')
        fixture.release['tag_name'] = fixture.release['tag_name'].removeprefix('poc-')
        fixture.release['html_url'] = fixture.release['html_url'].replace('/poc-v','/v')
        fixture.proof = fixture.authorize()
        receipt = android_fixtures.bridge.make_receipt(**fixture.receipt_inputs())
        self.assertEqual(receipt['github_tag'],'v1.20.0')
        self.assertEqual(receipt['rc_tag'],'v1.20.0-rc.2')
        self.assertEqual(receipt['track'],'staging')
        self.assertIs(receipt['promoted_to_stable'],False)
        with self.assertRaises(names.lab.LabError):
            fixture.authorize(release={**fixture.release,'tag_name':'poc-v1.20.0'})


if __name__ == '__main__': unittest.main()
