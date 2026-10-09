"""Behavioral rehearsal with a stateful GitHub fake; never real approvals.

The same public CLI functions operate on API-shaped state with CAS, pagination,
create-only refs and lost responses. No token or external distribution is used.
"""
import base64
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import issue_release as issue
import configure_issue_release as configure
import release_lab as lab

SOURCE = 'a' * 40
CORRECTION = 'b' * 40
OWNER = {'id': 18661493, 'login': 'israelhudson', 'type': 'User'}
ATTACKER = {'id': 42, 'login': 'outsider', 'type': 'User'}
DATE = '2026-10-09T21:00:00Z'


class GitHub:
    def __init__(self):
        self.refs = {'heads/main': SOURCE, 'tags/v1.12.0': SOURCE}
        self.state = None
        self.sha = None
        self.counter = 0
        self.issues = {}
        self.comments = {}
        self.releases = {}
        self.effects = []
        self.denied_user = None
        self.lost_release_response = False
        self.fail_after_final_tag = False
        self.comment_pages = 100
        self.truncated = False

    def api(self, path, data=None, method='GET', missing=False):
        assert path.startswith('repos/' + lab.REPOSITORY)
        url = urlsplit(path[len('repos/' + lab.REPOSITORY) + 1:])
        p = unquote(url.path)
        query = parse_qs(url.query)
        page = int(query.get('page', ['1'])[0])
        if p == 'contents/' + issue.STATE_PATH:
            if method == 'GET':
                if self.state is None:
                    return None
                return {'sha': self.sha, 'content': base64.b64encode(lab.canonical(self.state).encode()).decode()}
            if data.get('sha') != self.sha:
                raise lab.LabError('Conflito CAS')
            self.state = json.loads(base64.b64decode(data['content']))
            self.counter += 1
            self.sha = str(self.counter)
            return {'content': {'sha': self.sha}}
        if p == 'rulesets':
            return [{'id': i, 'name': v['name']} for i, v in enumerate(configure.definitions(), 1)] if page == 1 else []
        if p.startswith('rulesets/'):
            return deepcopy(configure.definitions()[int(p.split('/')[-1]) - 1])
        if p == 'commits/main':
            return {'sha': self.refs['heads/main']}
        if p.startswith('git/ref/'):
            key = p[len('git/ref/'):]
            if key not in self.refs:
                if missing:
                    return None
                raise lab.LabError('Ref ausente')
            if self.fail_after_final_tag and key.startswith('tags/test-issue-') and '-rc.' not in key:
                # The next publication identity check observes a removed approval.
                self.comments[1] = [c for c in self.comments[1] if not c['body'].startswith('/aprovar')]
            return {'object': {'type': 'commit', 'sha': self.refs[key]}}
        if p == 'git/refs':
            key = data['ref'][5:]
            if key in self.refs:
                raise lab.LabError('Ref já existe')
            self.refs[key] = data['sha']
            self.effects.append(('ref', key))
            return {'object': {'type': 'commit', 'sha': data['sha']}}
        if p.startswith('git/matching-refs/'):
            prefix = p[len('git/matching-refs/'):]
            return [{'ref': 'refs/' + k} for k in self.refs if k.startswith(prefix)]
        if p == 'releases/latest':
            return {'tag_name': 'v1.12.0'}
        if p.startswith('compare/'):
            source = p.split('...')[-1]
            return {'status': 'ahead', 'total_commits': 2 if self.truncated else 1,
                    'commits': [{'sha': source, 'commit': {'message': 'Alteração testada'}}]}
        if p == 'issues':
            if method == 'GET':
                return deepcopy(list(self.issues.values())) if page == 1 else []
            n = len(self.issues) + 1
            value = {**data, 'number': n, 'state': 'open', 'locked': False, 'created_at': DATE,
                     'html_url': f'https://github.com/{lab.REPOSITORY}/issues/{n}',
                     'user': {'id': 41898282, 'login': 'github-actions[bot]', 'type': 'Bot'}}
            self.issues[n] = deepcopy(value)
            self.comments[n] = []
            self.effects.append(('issue', n))
            return value
        if p.startswith('issues/'):
            parts = p.split('/')
            n = int(parts[1])
            if len(parts) == 3 and parts[2] == 'comments':
                return deepcopy(self.comments[n][(page - 1) * 100:page * 100])
            if method == 'PATCH':
                self.issues[n].update(data)
            return deepcopy(self.issues[n])
        if p.startswith('collaborators/'):
            user = p.split('/')[1]
            return {'permission': 'read' if user == self.denied_user else 'admin'}
        if p.startswith('releases/tags/'):
            tag = p[len('releases/tags/'):]
            if tag not in self.releases and not missing:
                raise lab.LabError('Release ausente')
            return deepcopy(self.releases.get(tag))
        if p == 'releases' and method == 'POST':
            value = {**data, 'id': len(self.releases) + 1, 'published_at': DATE,
                     'html_url': 'https://github.com/' + lab.REPOSITORY + '/releases/tag/' + data['tag_name']}
            self.releases[data['tag_name']] = deepcopy(value)
            self.effects.append(('release', data['tag_name']))
            if self.lost_release_response:
                raise lab.LabError('Resposta perdida depois do efeito')
            return value
        raise AssertionError((p, method, data))

    def comment(self, n, body, user=None, edited=False):
        existing = [c['id'] for values in self.comments.values() for c in values]
        comment = {'id': max(existing, default=100) + 1, 'body': body,
                   'user': deepcopy(user or OWNER), 'created_at': DATE,
                   'updated_at': '2026-10-09T21:00:01Z' if edited else DATE}
        self.comments[n].append(comment)
        return deepcopy(comment)

    def event(self, n, comment=None, action='created'):
        value = {'repository': {'full_name': lab.REPOSITORY}, 'issue': deepcopy(self.issues[n]), 'action': action}
        if comment:
            value['comment'] = deepcopy(comment)
        return value


class IssueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = self.tmp.name
        self.github = GitHub()
        self.policy = issue.policy_load()
        self.patch = patch.object(lab, 'api', self.github.api)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.git = patch.object(lab, 'git', return_value=SOURCE)
        self.git.start(); self.addCleanup(self.git.stop)
        self.trusted = patch.object(lab, 'trusted_source', return_value=SOURCE)
        self.trusted.start(); self.addCleanup(self.trusted.stop)
        self.http = patch.object(issue, 'verify_http', return_value={'success': True})
        self.http.start(); self.addCleanup(self.http.stop)
        self.stdout = redirect_stdout(io.StringIO()); self.stdout.__enter__(); self.addCleanup(self.stdout.__exit__, None, None, None)
        self.env = patch.dict(os.environ, {'GITHUB_RUN_ID': '123', 'GITHUB_REPOSITORY': lab.REPOSITORY,
            'GITHUB_REF': 'refs/heads/main', 'GITHUB_ACTOR': 'israelhudson', 'GITHUB_ACTOR_ID': '18661493',
            'GITHUB_TRIGGERING_ACTOR': 'israelhudson', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'ISSUE_RELEASE_ENABLED': 'true', 'GITHUB_OUTPUT': str(Path(self.folder, 'outputs'))})
        self.env.start(); self.addCleanup(self.env.stop)

    def candidate(self, version='1.13.0'):
        record = issue.prepare(self.policy, version, 'Mudança de exemplo', self.folder)
        metadata = {'source_sha': record['source_sha'], 'web_content_sha256': 'c' * 64, 'snapshot_manifest_sha256': 'd' * 64}
        smoke = {**metadata, 'success': True,
                 'snapshot_url': 'https://israelhudson.github.io/flutter_code_push_example/snapshots/' + record['source_sha'] + '/'}
        return issue.open_issue(self.policy, record['tag'], metadata, smoke, self.folder)

    def vote(self, record, command, **kwargs):
        return self.github.comment(record['issue_number'], f'/{command} {record["tag"]}', **kwargs)

    def decide(self, record, comment, action='created'):
        return issue.decide(self.policy, self.github.event(record['issue_number'], comment, action), self.folder)

    def ready(self):
        record = self.candidate()
        self.decide(record, self.vote(record, 'aprovar'))
        command = self.vote(record, 'publicar')
        self.assertTrue(self.decide(record, command)['publish'])
        return record, command

    def test_one_approval_only_enables_separate_command(self):
        record = self.candidate()
        result = self.decide(record, self.vote(record, 'aprovar'))
        self.assertEqual(result['state'], 'approved')
        self.assertFalse(result['publish'])
        self.assertFalse(self.github.releases)
        self.assertNotIn('tags/' + record['stable_tag'], self.github.refs)

    def test_publish_without_approval_is_blocked(self):
        record = self.candidate()
        command = self.vote(record, 'publicar')
        self.assertFalse(self.decide(record, command)['publish'])
        with self.assertRaisesRegex(issue.IssueError, 'Falta'):
            issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertFalse(self.github.releases)

    def test_rejection_correction_rc2_does_not_inherit_approval(self):
        rc1 = self.candidate()
        self.decide(rc1, self.vote(rc1, 'aprovar'))
        self.assertEqual(self.decide(rc1, self.vote(rc1, 'reprovar'))['state'], 'rejected')
        self.github.refs['heads/' + rc1['branch']] = CORRECTION
        rc2 = self.candidate()
        self.assertTrue(rc2['tag'].endswith('rc.2'))
        self.assertEqual(rc2['source_sha'], CORRECTION)
        self.assertEqual(self.github.refs['tags/' + rc1['tag']], SOURCE)
        self.assertEqual(self.github.state['candidates'][rc1['tag']]['status'], 'superseded')
        command = self.vote(rc2, 'publicar')
        with self.assertRaises(issue.IssueError):
            issue.publish(self.policy, rc2['issue_number'], command['id'], self.folder)
        self.decide(rc2, self.vote(rc2, 'aprovar'))
        command = self.vote(rc2, 'publicar')
        receipt = issue.publish(self.policy, rc2['issue_number'], command['id'], self.folder)
        self.assertEqual(receipt['source_sha'], CORRECTION)
        self.assertFalse(receipt['distribution_performed'])
        self.assertEqual(len(self.github.releases), 1)

    def test_repeated_publication_has_one_tag_one_release(self):
        record, command = self.ready()
        first = issue.publish(self.policy, 1, command['id'], self.folder)
        second = issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertEqual(first, second)
        self.assertEqual(self.github.effects.count(('ref', 'tags/' + record['stable_tag'])), 1)
        self.assertEqual(self.github.effects.count(('release', record['stable_tag'])), 1)
        repeat = self.decide(record, self.vote(record, 'publicar'))
        self.assertEqual(repeat['state'], 'published')
        self.assertFalse(repeat['publish'])
        self.assertTrue(self.github.releases[record['stable_tag']]['prerelease'])
        self.assertEqual(self.github.releases[record['stable_tag']]['make_latest'], 'false')

    def test_lost_release_response_reconciles_same_effect(self):
        record, command = self.ready()
        self.github.lost_release_response = True
        receipt = issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertTrue(receipt['github_release_published'])
        self.assertEqual(len(self.github.releases), 1)

    def test_deleted_approval_between_tag_and_release_blocks_release(self):
        record, command = self.ready()
        self.github.fail_after_final_tag = True
        with self.assertRaises(issue.IssueError):
            issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertIn('tags/' + record['stable_tag'], self.github.refs)
        self.assertFalse(self.github.releases)
        with self.assertRaisesRegex(issue.IssueError, 'parcial'):
            issue.prepare(self.policy, '1.14.0', 'Outra', self.folder)

    def test_edited_approval_event_can_never_publish(self):
        record = self.candidate()
        approval = self.vote(record, 'aprovar')
        self.decide(record, approval)
        result = self.decide(record, approval, 'edited')  # Same-second edits still revoke by ID.
        self.assertEqual(result['state'], 'awaiting_approval')
        self.assertFalse(result['publish'])
        self.assertFalse(self.decide(record, self.vote(record, 'publicar'))['publish'])

    def test_deleted_approval_is_not_counted(self):
        record = self.candidate()
        approval = self.vote(record, 'aprovar')
        self.decide(record, approval)
        self.github.comments[1] = []
        result = self.decide(record, approval, 'deleted')
        self.assertEqual(result['state'], 'awaiting_approval')

    def test_edited_publicar_never_starts_publication(self):
        record = self.candidate()
        self.decide(record, self.vote(record, 'aprovar'))
        command = self.vote(record, 'publicar', edited=True)
        self.assertFalse(self.decide(record, command, 'edited')['publish'])
        with self.assertRaises(issue.IssueError):
            issue.publish(self.policy, 1, command['id'], self.folder)

    def test_bot_and_unauthorized_users_do_not_approve(self):
        for user in (ATTACKER, {**OWNER, 'type': 'Bot'}):
            record = self.candidate()
            result = self.decide(record, self.vote(record, 'aprovar', user=user))
            self.assertEqual(result['state'], 'awaiting_approval')
            # Reset only the fixture for the next independent case.
            self.github.state['candidates'][record['tag']]['status'] = 'rejected'

    def test_removed_collaborator_permission_invalidates_approval(self):
        record, command = self.ready()
        self.github.denied_user = OWNER['login']
        with self.assertRaises(issue.IssueError):
            issue.publish(self.policy, 1, command['id'], self.folder)

    def test_issue_body_tampering_does_not_authorize_and_revokes_old_vote(self):
        record, command = self.ready()
        self.github.issues[1]['body'] += '\n[x] aprovado'
        result = self.decide(record, command)
        self.assertEqual(result['state'], 'blocked')
        self.assertFalse(self.github.releases)

    def test_pull_request_comments_and_unregistered_issues_ignored(self):
        record = self.candidate()
        event = self.github.event(1, self.vote(record, 'aprovar'))
        event['issue']['pull_request'] = {'url': 'fixture'}
        self.assertEqual(issue.decide(self.policy, event, self.folder)['state'], 'ignored')
        event['issue'] = {'number': 1000}
        self.assertEqual(issue.decide(self.policy, event, self.folder)['state'], 'ignored-unregistered-issue')

    def test_wrong_rc_command_does_not_count(self):
        record = self.candidate()
        comment = self.github.comment(1, '/aprovar test-issue-1.99.0-rc.1')
        self.assertEqual(self.decide(record, comment)['state'], 'awaiting_approval')

    def test_publish_before_approval_requires_another_command(self):
        record = self.candidate()
        command = self.vote(record, 'publicar')
        self.decide(record, self.vote(record, 'aprovar'))
        self.assertFalse(self.decide(record, command)['publish'])
        with self.assertRaises(issue.IssueError):
            issue.publish(self.policy, 1, command['id'], self.folder)

    def test_tag_conflict_is_not_overwritten(self):
        record, command = self.ready()
        self.github.refs['tags/' + record['stable_tag']] = CORRECTION
        with self.assertRaises(lab.LabError):
            issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertEqual(self.github.refs['tags/' + record['stable_tag']], CORRECTION)
        self.assertFalse(self.github.releases)

    def test_release_conflict_is_not_overwritten(self):
        record, command = self.ready()
        self.github.releases[record['stable_tag']] = {'id': 500, 'body': 'fora da intenção'}
        with self.assertRaises(issue.IssueError):
            issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertEqual(self.github.releases[record['stable_tag']]['id'], 500)

    def test_branch_advance_blocks_old_candidate(self):
        record, command = self.ready()
        self.github.refs['heads/' + record['branch']] = CORRECTION
        with self.assertRaisesRegex(issue.IssueError, 'avançou'):
            issue.publish(self.policy, 1, command['id'], self.folder)

    def test_one_active_candidate_does_not_touch_native_state(self):
        record = self.candidate()
        with self.assertRaisesRegex(issue.IssueError, 'Uma RC'):
            issue.prepare(self.policy, '1.14.0', 'Outra', self.folder)
        self.assertTrue(all(not key.startswith(('heads/release/', 'tags/v1.13')) for key in self.github.refs))
        self.assertEqual(self.github.refs['tags/v1.12.0'], SOURCE)

    def test_failed_build_reuses_prepared_cut_without_rc_increment(self):
        record = issue.prepare(self.policy, '1.13.0', 'Mudança', self.folder)
        again = issue.prepare(self.policy, '1.13.0', 'Mudança', self.folder)
        self.assertEqual(record['tag'], again['tag'])
        self.assertEqual(self.github.effects.count(('ref', 'tags/' + record['tag'])), 1)

    def test_all_comment_pages_are_consulted(self):
        record = self.candidate()
        for _ in range(101):
            self.github.comment(1, 'Comentário comum', ATTACKER)
        self.assertEqual(self.decide(record, self.vote(record, 'aprovar'))['state'], 'approved')

    def test_truncated_changelog_does_not_open_issue(self):
        self.github.truncated = True
        with self.assertRaisesRegex(issue.IssueError, 'truncado'):
            self.candidate()
        self.assertFalse(self.github.issues)

    def test_foreign_or_unverified_preview_does_not_open_issue(self):
        record = issue.prepare(self.policy, '1.13.0', 'Mudança', self.folder)
        meta = {'source_sha': SOURCE, 'web_content_sha256': 'c'*64, 'snapshot_manifest_sha256': 'd'*64}
        smoke = {**meta, 'success': True, 'snapshot_url': 'https://evil.example'}
        with self.assertRaises(issue.IssueError):
            issue.open_issue(self.policy, record['tag'], meta, smoke, self.folder)
        self.assertFalse(self.github.issues)

    def test_http_failure_prevents_publication_intent(self):
        record, command = self.ready()
        with patch.object(issue, 'verify_http', side_effect=ValueError('HTTP indisponível')):
            with self.assertRaises(ValueError):
                issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertFalse(self.github.state['candidates'][record['tag']].get('publication'))
        self.assertFalse(self.github.releases)

    def test_repeat_version_after_publication_is_blocked(self):
        record, command = self.ready()
        issue.publish(self.policy, 1, command['id'], self.folder)
        with self.assertRaisesRegex(issue.IssueError, 'Versão'):
            issue.prepare(self.policy, '1.13.0', 'Outra', self.folder)

    def test_commands_are_exact_data_not_shell_or_quotes(self):
        for body in ('/aprovar test-issue-1.13.0-rc.1\n/publicar test-issue-1.13.0-rc.1',
                     '> /aprovar test-issue-1.13.0-rc.1', '/aprovar $(touch /tmp/owned)',
                     '/aprovar v1.13.0-rc.1'):
            self.assertIsNone(issue.parse(body))

    def test_disabled_or_other_ref_is_blocked(self):
        for key, value in (('ISSUE_RELEASE_ENABLED', 'false'), ('GITHUB_REF', 'refs/heads/feature')):
            with patch.dict(os.environ, {key: value}):
                with self.assertRaises(issue.IssueError):
                    issue.context(self.policy, 'prepare')

    def test_unknown_slack_result_is_not_retried(self):
        record = self.candidate()
        with patch.dict(os.environ, {'SLACK_BOT_TOKEN': 'fixture-not-a-real-secret'}), \
             patch.object(issue.slack_notify, 'verify_destination'), \
             patch.object(issue.slack_notify, 'slack_api', side_effect=issue.slack_notify.SlackAPIError('Resposta incerta')) as post:
            with self.assertRaises(issue.slack_notify.SlackAPIError):
                issue.notify(self.policy, record['tag'], self.folder)
            issue.notify(self.policy, record['tag'], self.folder)
            self.assertEqual(post.call_count, 1)
        self.assertEqual(self.github.state['candidates'][record['tag']]['status'], 'awaiting_approval')

    def test_live_comment_changed_after_intent_cannot_resume(self):
        record, command = self.ready()
        original = lab.create_ref_verified
        with patch.object(lab, 'create_ref_verified', side_effect=lab.LabError('Falha antes da tag final')):
            with self.assertRaises(lab.LabError):
                issue.publish(self.policy, 1, command['id'], self.folder)
        self.github.comments[1][0]['body'] = 'Aval retirado'
        with self.assertRaises(issue.IssueError):
            issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertFalse(self.github.releases)

    def test_partial_publication_resumes_same_command_once(self):
        record, command = self.ready()
        with patch.object(lab, 'create_ref_verified', side_effect=lab.LabError('Falha antes da tag final')):
            with self.assertRaises(lab.LabError):
                issue.publish(self.policy, 1, command['id'], self.folder)
        receipt = issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertTrue(receipt['github_release_published'])
        self.assertEqual(len(self.github.releases), 1)

    def test_same_account_duplicate_approvals_still_count_once(self):
        record = self.candidate()
        for _ in range(3):
            self.decide(record, self.vote(record, 'aprovar'))
        stored = self.github.state['candidates'][record['tag']]
        self.assertEqual(len(stored['approvals']), 1)

    def test_unobserved_or_edited_into_approval_cannot_authorize(self):
        record = self.candidate()
        self.vote(record, 'aprovar')  # No matching CREATED event recorded.
        command = self.vote(record, 'publicar')
        self.assertFalse(self.decide(record, command)['publish'])
        with self.assertRaises(issue.IssueError):
            issue.publish(self.policy, 1, command['id'], self.folder)

    def test_preview_and_changelog_hash_changes_are_blocked(self):
        record, command = self.ready()
        self.github.state['candidates'][record['tag']]['report']['commits'][0]['message'] = 'Alterado'
        with self.assertRaisesRegex(issue.IssueError, 'Relatório'):
            issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertFalse(self.github.releases)

    def test_missing_rulesets_block_prepare_before_any_effect(self):
        original = self.github.api
        def api(path, data=None, method='GET', missing=False):
            return [] if '/rulesets?' in path else original(path, data, method, missing)
        with patch.object(lab, 'api', api):
            with self.assertRaisesRegex(issue.IssueError, 'Proteção'):
                issue.prepare(self.policy, '1.13.0', 'Mudança', self.folder)
        self.assertFalse(self.github.effects)

    def test_cas_conflict_stops_cut_before_tags(self):
        original = self.github.api
        def api(path, data=None, method='GET', missing=False):
            if method == 'PUT' and issue.STATE_PATH in path:
                raise lab.LabError('CAS recusado')
            return original(path, data, method, missing)
        with patch.object(lab, 'api', api):
            with self.assertRaises(lab.LabError):
                issue.prepare(self.policy, '1.13.0', 'Mudança', self.folder)
        self.assertFalse(any(kind == 'ref' and key.startswith('tags/test-issue') for kind, key in self.github.effects))

    def test_deleted_command_after_intent_cannot_resume(self):
        record, command = self.ready()
        with patch.object(lab, 'create_ref_verified', side_effect=lab.LabError('Falha antes da tag final')):
            with self.assertRaises(lab.LabError):
                issue.publish(self.policy, 1, command['id'], self.folder)
        self.github.comments[1] = [c for c in self.github.comments[1] if c['id'] != command['id']]
        with self.assertRaises(issue.IssueError):
            issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertFalse(self.github.releases)

    def test_moved_rc_tag_is_blocked(self):
        record, command = self.ready()
        self.github.refs['tags/' + record['tag']] = CORRECTION
        with self.assertRaises(issue.IssueError):
            issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertFalse(self.github.releases)

    def test_approval_requires_recorded_creation_and_same_live_content(self):
        record = self.candidate()
        approval = self.vote(record, 'aprovar')
        event = self.github.event(1, approval)
        self.github.comments[1][0]['body'] = 'Conteúdo editado no mesmo segundo'
        result = issue.decide(self.policy, event, self.folder)
        self.assertEqual(result['state'], 'awaiting_approval')

    def test_issue_creation_lost_response_reconciles_single_issue(self):
        original = self.github.api
        def api(path, data=None, method='GET', missing=False):
            result = original(path, data, method, missing)
            if path.endswith('/issues') and method == 'POST':
                raise lab.LabError('Resposta perdida da criação da ficha')
            return result
        with patch.object(lab, 'api', api):
            with self.assertRaises(lab.LabError):
                self.candidate()
        record = self.candidate()
        self.assertEqual(record['issue_number'], 1)
        self.assertEqual(len(self.github.issues), 1)

    def test_lost_view_patch_repairs_known_body_before_resume(self):
        record, command = self.ready()
        original = self.github.api
        fail = [True]
        def api(path, data=None, method='GET', missing=False):
            if path.endswith('/issues/1') and method == 'PATCH' and fail[0]:
                fail[0] = False
                raise lab.LabError('Falha ao exibir intenção')
            return original(path, data, method, missing)
        with patch.object(lab, 'api', api):
            with self.assertRaises(lab.LabError):
                issue.publish(self.policy, 1, command['id'], self.folder)
        receipt = issue.publish(self.policy, 1, command['id'], self.folder)
        self.assertTrue(receipt['github_release_published'])
        self.assertEqual(len(self.github.releases), 1)


if __name__ == '__main__':
    unittest.main()
