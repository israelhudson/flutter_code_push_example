"""Frozen LAB notification identity; all effects use the offline emulator."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import release_lab as lab
import rehearse_release_lab as rehearsal


class NotificationProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lab-notification-profile-')
        self.addCleanup(self.temp.cleanup)
        self.world = rehearsal.OfflineWorld(self.temp.name)
        self.addCleanup(self.world.close)

    def pending_cut(self):
        self.world.inject_failure('git/refs')
        with self.assertRaises(lab.LabError):
            self.world.prepare()
        self.assertIn('preparation', self.world.state)

    def test_new_cut_freezes_exclusive_profile_in_record_and_report(self):
        tag = self.world.prepare()
        self.world.freeze_report(tag)
        record = self.world.state['candidates'][tag]
        self.assertEqual(record['notification_profile'], 'poc-v1')
        self.assertEqual(record['report']['notification_profile'], 'poc-v1')
        self.assertEqual(record['report_digest'], lab.digest(record['report']))
        self.world.assert_no_publication()

    def test_historical_partial_cut_remains_legacy_without_new_field(self):
        self.pending_cut()
        self.world.state['preparation'].pop('notification_profile')
        tag = self.world.prepare()
        self.world.freeze_report(tag)
        record = self.world.state['candidates'][tag]
        self.assertNotIn('notification_profile', record)
        self.assertNotIn('notification_profile', record['report'])
        self.assertEqual(lab.notification_profile(record), 'legacy')
        lab.frozen_material(record)

    def test_new_partial_cut_keeps_exclusive_profile_on_recovery(self):
        self.pending_cut()
        tag = self.world.prepare()
        self.assertEqual(self.world.state['candidates'][tag]['notification_profile'], 'poc-v1')

    def test_unknown_partial_profile_does_not_create_references(self):
        self.pending_cut()
        self.world.state['preparation']['notification_profile'] = 'another-project'
        before = copy.deepcopy(self.world.refs)
        with self.assertRaisesRegex(lab.LabError, 'Perfil de avisos desconhecido'):
            self.world.prepare()
        self.assertEqual(self.world.refs, before)
        self.assertFalse(self.world.state['candidates'])

    def test_frozen_profile_cannot_switch_after_report_before_approval(self):
        tag = self.world.prepare()
        self.world.freeze_report(tag)
        record = self.world.state['candidates'][tag]
        report = copy.deepcopy(record['report'])
        for changed in ('legacy', None, 'unknown'):
            with self.subTest(changed=changed):
                altered = copy.deepcopy(record)
                if changed is None:
                    altered.pop('notification_profile')
                else:
                    altered['notification_profile'] = changed
                with self.assertRaises(lab.LabError):
                    lab.frozen_material(altered)
        self.assertEqual(record['report'], report)
        self.world.assert_no_publication()

    def test_legacy_report_is_not_retroactively_enrolled(self):
        legacy = {'report': {'schema': 1}}
        self.assertEqual(lab.frozen_material(legacy), {})
        legacy['notification_profile'] = 'poc-v1'
        with self.assertRaisesRegex(lab.LabError, 'Perfil de avisos diverge'):
            lab.frozen_material(legacy)


if __name__ == '__main__':
    unittest.main()
