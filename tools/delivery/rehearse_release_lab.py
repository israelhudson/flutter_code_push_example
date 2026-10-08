"""Offline rehearsals of the production helper; never calls GitHub or approves humans.

Each run uses a disposable real Git repository, synthetic REST responses, and
explicit synthetic reviewer fixtures. Logs prove local behavior, not a live
GitHub review, Pages deploy, store upload, or Shorebird publication.
"""
import argparse
import base64
from contextlib import ExitStack, redirect_stdout
import copy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import release_lab as lab


ISRAEL = {'id': 18661493, 'login': 'israelhudson'}
FABRICIA = {'id': 339824994, 'login': 'fahnassau30'}
ENV_IDS = {'aprovacao-israel': 101, 'aprovacao-fahnassau30': 102,
           'autorizar-publicacao': 103}


def offline_policy():
    return {'schema': 1, 'repository': lab.REPOSITORY,
            'operators': [copy.deepcopy(ISRAEL)],
            'approvers': [dict(ISRAEL, role='first', environment='aprovacao-israel'),
                          dict(FABRICIA, role='second', environment='aprovacao-fahnassau30')],
            'publishers': [copy.deepcopy(ISRAEL), copy.deepcopy(FABRICIA)],
            'final_environment': 'autorizar-publicacao',
            'state_branch': 'codex/release-lab-state',
            'changelog_initial_tag': 'entrega-0100-rc.1',
            'mobile_bases': {'android': None, 'ios': None},
            'publication_mode': 'github_release_only',
            'result_simulated': False, 'distribution_performed': False}


def synthetic_review(person, environment, state='approved'):
    return {'state': state, 'user': dict(person, type='User'),
            'comment': 'OFFLINE fixture; no human decision submitted',
            'environments': [{'id': ENV_IDS[environment], 'name': environment}]}


class OfflineWorld:
    """API emulator fails on unknown endpoints, so no real-network fallback exists."""
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.temporary_git = tempfile.TemporaryDirectory(prefix='release-lab-offline-git-')
        self.repo = Path(self.temporary_git.name)
        self.repo.mkdir(exist_ok=True)
        self.calls, self.events, self.releases = [], [], []
        self.refs, self.runs, self.failures = {}, {}, []
        self.state, self.state_revision = None, 0
        self.policy = offline_policy()
        self.sequence = 0
        self.operation_sequence = 0
        self.run_id = '9001'
        self.env = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                    'GITHUB_REPOSITORY': lab.REPOSITORY,
                    'GITHUB_ACTOR': ISRAEL['login'], 'GITHUB_ACTOR_ID': str(ISRAEL['id']),
                    'GITHUB_TRIGGERING_ACTOR': ISRAEL['login'],
                    'GITHUB_RUN_ID': self.run_id, 'GITHUB_RUN_ATTEMPT': '1',
                    'GITHUB_REF': 'refs/heads/main', 'GITHUB_OUTPUT': '', 'GITHUB_STEP_SUMMARY': ''}
        self.local_git('init', '--initial-branch=main')
        self.local_git('config', 'user.name', 'Offline Fixture')
        self.local_git('config', 'user.email', 'fixture@example.invalid')
        for path in ('.github/workflows/trusted.yml', 'deploy/trusted.txt',
                     'tools/delivery/release_lab.py', 'delivery/release-lab-policy.json'):
            destination = self.repo / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text('trusted local fixture\n')
        (self.repo / 'lib').mkdir()
        (self.repo / 'lib/main.dart').write_text('void main() {}\n')
        self.baseline = self.commit('fixture baseline')
        (self.repo / 'lib/main.dart').write_text('void main() { print("candidate"); }\n')
        self.source = self.commit('feat: offline candidata')
        self.refs = {'heads/main': self.source, 'tags/entrega-0100-rc.1': self.baseline}
        self.local_git('update-ref', 'refs/tags/entrega-0100-rc.1', self.baseline)
        self.set_run(self.run_id)
        self.emit('scope', mode='offline', human_reviews='synthetic fixtures',
                  real_network=False, real_distribution=False, real_git=True)

    def local_git(self, *args):
        result = subprocess.run(['git', '-C', str(self.repo), *args],
                                text=True, capture_output=True, check=True, timeout=20)
        return result.stdout.strip()

    def close(self):
        history = self.local_git('log', '--all', '--format=%H %s').splitlines()
        (self.folder / 'git-history.json').write_text(json.dumps(history, indent=2) + '\n')
        self.temporary_git.cleanup()

    def git(self, *args):
        if args[0] == 'fetch':
            return ''  # All objects already exist in the disposable local repo.
        return self.local_git(*args)

    def commit(self, message):
        self.local_git('add', '.')
        self.local_git('commit', '-m', message)
        return self.local_git('rev-parse', 'HEAD')

    def correct_release(self, version='1.4.0'):
        (self.repo / 'lib/main.dart').write_text('void main() { print("corrected RC"); }\n')
        source = self.commit('fix: corrigir candidata recusada offline')
        self.refs['heads/release/' + version] = source
        self.local_git('update-ref', 'refs/heads/release/' + version, source)
        self.emit('fixture_correction', source_sha=source,
                  note='Local commit fixture; this is not proof of a reviewed remote PR.')
        return source

    def set_run(self, run_id, reviews=None, jobs=None, actor=None, attempt=1):
        self.run_id = str(run_id)
        self.env['GITHUB_RUN_ID'] = self.run_id
        self.runs[self.run_id] = {'id': int(run_id), 'run_attempt': attempt,
                                 'actor': copy.deepcopy(actor or ISRAEL),
                                 'reviews': copy.deepcopy(reviews or []),
                                 'jobs': copy.deepcopy(jobs or [])}

    def emit(self, event, **values):
        value = {'sequence': len(self.events) + 1, 'event': event, **values}
        self.events.append(value)
        with (self.folder / 'trace.jsonl').open('a') as stream:
            stream.write(lab.canonical(value) + '\n')

    def inject_failure(self, prefix, *, method='POST', after=False, count=1):
        self.failures.append({'prefix': prefix, 'method': method,
                              'after': after, 'remaining': count})

    def failure(self, path, method, after):
        for failure in self.failures:
            if (failure['remaining'] and failure['method'] == method
                    and failure['after'] == after and path.startswith(failure['prefix'])):
                failure['remaining'] -= 1
                self.emit('injected_failure', endpoint=path, method=method,
                          after_effect=after, message='Offline timeout / response lost')
                raise lab.LabError('Offline injected timeout / response lost')

    def api(self, path, data=None, method='GET', missing=False):
        prefix = lab.endpoint('')
        if not path.startswith(prefix):
            raise AssertionError('Offline emulator cannot leave the LAB repository')
        path = path[len(prefix):]
        self.calls.append({'path': path, 'method': method, 'data': copy.deepcopy(data)})
        self.emit('api', endpoint=path, method=method,
                  request_sha=lab.digest(data) if data is not None else None)
        self.failure(path, method, False)
        result = self.route(path, data, method, missing)
        self.failure(path, method, True)
        return copy.deepcopy(result)

    def route(self, path, data, method, missing):
        parsed = urlsplit(path)
        route = unquote(parsed.path)
        if route == 'contents/' + lab.STATE_PATH:
            if method == 'GET':
                if self.state is None:
                    return None if missing else self.not_found(route)
                return {'sha': str(self.state_revision),
                        'content': base64.b64encode(lab.canonical(self.state).encode()).decode()}
            if method == 'PUT':
                if data.get('sha') != (str(self.state_revision) if self.state is not None else None):
                    raise lab.LabError('Offline journal CAS conflict')
                self.state = json.loads(base64.b64decode(data['content']))
                self.state_revision += 1
                return {'content': {'sha': str(self.state_revision)}}
        if route.startswith('environments/'):
            name = route.split('/')[1]
            if route.endswith('/deployment-branch-policies'):
                return {'branch_policies': [{'name': 'main', 'type': 'branch'},
                                           {'name': 'v*-rc.*', 'type': 'tag'}]}
            people = self.policy['publishers'] if name == self.policy['final_environment'] else [
                p for p in self.policy['approvers'] if p['environment'] == name]
            return {'id': ENV_IDS[name], 'can_admins_bypass': False,
                    'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True},
                    'protection_rules': [{'type': 'required_reviewers', 'prevent_self_review': False,
                                          'reviewers': [{'type': 'User', 'reviewer': p} for p in people]}]}
        rules = self.rulesets()
        if route == 'rulesets':
            return [{'id': r['id'], 'name': r['name']} for r in rules]
        if route.startswith('rulesets/'):
            return next(r for r in rules if r['id'] == int(route.split('/')[-1]))
        if route == 'commits/main':
            return {'sha': self.refs['heads/main']}
        if route.startswith('git/ref/'):
            ref = route[8:]
            if ref not in self.refs:
                return None if missing else self.not_found(route)
            return {'ref': 'refs/' + ref, 'object': {'type': 'commit', 'sha': self.refs[ref]}}
        if route.startswith('git/matching-refs/'):
            prefix = route[18:]
            return [{'ref': 'refs/' + ref, 'object': {'type': 'commit', 'sha': sha}}
                    for ref, sha in sorted(self.refs.items()) if ref.startswith(prefix)]
        if route == 'git/refs' and method == 'POST':
            ref = data['ref'][5:]
            if ref in self.refs:
                raise lab.LabError('Offline existing ref cannot be overwritten')
            self.refs[ref] = data['sha']
            self.local_git('update-ref', data['ref'], data['sha'])
            return {'ref': data['ref'], 'object': {'type': 'commit', 'sha': data['sha']}}
        if route.startswith('actions/runs/'):
            bits = route.split('/')
            run = self.runs[bits[2]]
            if len(bits) == 3:
                return {k: v for k, v in run.items() if k not in ('reviews', 'jobs')}
            if bits[3] == 'approvals':
                return run['reviews']
            if bits[3] == 'jobs':
                return {'jobs': run['jobs']}
        if route == 'releases' and method == 'GET':
            return self.releases
        if route.startswith('releases/tags/') and method == 'GET':
            tag = route[len('releases/tags/'):]
            found = next((r for r in self.releases if r['tag_name'] == tag), None)
            return found if found is not None or missing else self.not_found(route)
        if route == 'releases' and method == 'POST':
            if any(r['tag_name'] == data['tag_name'] for r in self.releases):
                raise lab.LabError('Offline duplicate Release forbidden')
            value = {**copy.deepcopy(data), 'id': len(self.releases) + 100,
                     'published_at': '2026-10-08T21:00:00Z',
                     'html_url': 'https://github.com/' + lab.REPOSITORY + '/releases/tag/' + data['tag_name']}
            self.releases.append(value)
            return value
        raise AssertionError('Unsupported offline endpoint: ' + method + ' ' + path)

    @staticmethod
    def not_found(path):
        raise lab.LabError('Offline fixture HTTP 404: ' + path)

    def rulesets(self):
        definitions = [
            ('LAB - novas RCs imutaveis', 'tag', ['refs/tags/v*-rc.*'], ['update', 'deletion']),
            ('LAB - tags estaveis imutaveis', 'tag', ['refs/tags/v*'], ['update', 'deletion']),
            ('LAB - journal append-only', 'branch', ['refs/heads/' + self.policy['state_branch']], ['non_fast_forward', 'deletion']),
            ('LAB - main e release revisadas', 'branch', ['refs/heads/main', 'refs/heads/release/**'],
             ['pull_request', 'required_status_checks', 'non_fast_forward', 'deletion'])]
        return [{'id': index + 1, 'name': name, 'target': target, 'enforcement': 'active',
                 'bypass_actors': [], 'conditions': {'ref_name': {
                     'include': patterns,
                     'exclude': ['refs/tags/v*-rc.*'] if name == 'LAB - tags estaveis imutaveis' else []}},
                 'rules': [{'type': kind, **({'parameters': {'required_approving_review_count': 1}}
                                             if kind == 'pull_request' else
                                            {'parameters': {'required_status_checks': [{'context': 'Flutter analyze e test'}]}}
                                             if kind == 'required_status_checks' else {})} for kind in kinds]}
                for index, (name, target, patterns, kinds) in enumerate(definitions)]

    def snapshot(self, label):
        self.sequence += 1
        value = {'scope': 'offline', 'state': self.state, 'refs': self.refs,
                 'releases': self.releases, 'runs': self.runs}
        (self.folder / f'{self.sequence:02}-{label}.json').write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + '\n')

    def invoke(self, operation, **kwargs):
        self.operation_sequence += 1
        destination = self.folder / f'{self.operation_sequence:02}-{operation}-output'
        stdout = io.StringIO()
        self.emit('operation_started', operation=operation, scope='offline',
                  context={key: self.env[key] for key in ('GITHUB_ACTOR', 'GITHUB_ACTOR_ID',
                           'GITHUB_TRIGGERING_ACTOR', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_REF')})
        with ExitStack() as stack:
            stack.enter_context(patch.object(lab, 'ROOT', self.repo))
            stack.enter_context(patch.object(lab, 'api', side_effect=self.api))
            stack.enter_context(patch.object(lab, 'git', side_effect=self.git))
            stack.enter_context(patch.dict(lab.os.environ, self.env))
            stack.enter_context(patch.object(lab.time, 'sleep'))
            stack.enter_context(redirect_stdout(stdout))
            try:
                lab.validate_policy(self.policy)
                lab.validate_context(self.policy, operation, self.env)
                function = getattr(lab, operation)
                function(self.policy, folder=destination, **kwargs)
            except Exception as error:
                self.emit('operation_failed', operation=operation,
                          exception=type(error).__name__, reason=str(error),
                          stdout=stdout.getvalue())
                self.snapshot(operation + '-blocked')
                raise
        self.emit('operation_succeeded', operation=operation, stdout=stdout.getvalue())
        self.snapshot(operation + '-success')
        return destination

    def prepare(self, version='1.4.0'):
        self.env['GITHUB_REF'] = 'refs/heads/main'
        self.invoke('prepare', version=version, title='Ensaio offline ' + version)
        return self.state['active']

    def freeze_report(self, tag=None):
        tag = tag or self.state['active']
        self.invoke('preflight', tag=tag)
        source = self.state['candidates'][tag]['source_sha']
        smoke = {'success': True, 'source_sha': source,
                 'web_content_sha256': 'c' * 64, 'snapshot_manifest_sha256': 'd' * 64,
                 'snapshot_url': 'https://israelhudson.github.io/flutter_code_push_example/snapshots/' + source + '/'}
        metadata = {**smoke, 'source_build_inputs': {'flutter': 'offline fixture'}, 'version': '1.4.0+1'}
        smoke_path, metadata_path = self.folder / 'fixture-smoke.json', self.folder / 'fixture-metadata.json'
        smoke_path.write_text(json.dumps(smoke))
        metadata_path.write_text(json.dumps(metadata))
        self.invoke('report', tag=tag, smoke_path=smoke_path, metadata_path=metadata_path)
        self.emit('report_scope', preview='Synthetic HTTP-success fixture; no live Pages evidence')
        return self.state['candidates'][tag]['report_digest']

    def approve(self, role, tag=None):
        tag = tag or self.state['active']
        person = next(p for p in self.policy['approvers'] if p['role'] == role)
        self.runs[self.run_id]['reviews'].append(synthetic_review(person, person['environment']))
        self.invoke('approval', tag=tag, role=role,
                    report_digest=self.state['candidates'][tag]['report_digest'])
        self.runs[self.run_id]['jobs'].append({'name': 'Avaliar a mesma candidata / Gate ' + role,
                                              'conclusion': 'success'})
        self.emit('synthetic_approval', role=role, account=person['login'], human_decision=False)

    def authorize(self, person=None):
        person = person or FABRICIA
        self.runs[self.run_id]['reviews'].append(synthetic_review(person, self.policy['final_environment']))
        self.emit('synthetic_final_command', account=person['login'], human_decision=False)

    def finish(self, tag=None):
        tag = tag or self.state['active']
        return self.invoke('finish', tag=tag, report_digest=self.state['candidates'][tag]['report_digest'])

    def assert_no_publication(self):
        assert not any(lab.VERSION.fullmatch(ref[6:]) for ref in self.refs if ref.startswith('tags/v'))
        assert self.releases == []
        if self.state:
            assert not any(record.get('receipt') for record in self.state['candidates'].values())


def expect_blocked(world, operation, *args, **kwargs):
    try:
        operation(*args, **kwargs)
    except lab.LabError as error:
        world.emit('expected_block_observed', reason=str(error))
        return str(error)
    raise AssertionError('Operation unexpectedly succeeded instead of remaining blocked')


def scenario_happy(world):
    tag = world.prepare()
    world.freeze_report(tag)
    expect_blocked(world, world.finish, tag)
    world.assert_no_publication()
    world.approve('first', tag)
    expect_blocked(world, world.finish, tag)
    world.assert_no_publication()
    world.approve('second', tag)
    expect_blocked(world, world.finish, tag)
    world.assert_no_publication()
    world.authorize()
    folder = world.finish(tag)
    receipt = json.loads((folder / 'receipt.json').read_text())
    assert world.refs['tags/v1.4.0'] == world.refs['tags/' + tag]
    assert len(world.releases) == 1 and world.releases[0]['tag_name'] == 'v1.4.0'
    assert not world.releases[0]['draft'] and not world.releases[0]['prerelease']
    assert receipt['distribution_performed'] is False
    world.emit('assertions_passed', approvals_required=2, final_command_required=True,
               stable_commit_matches_rc=True, mobile_distributed=False)


def scenario_rc_correction(world):
    first = world.prepare()
    world.freeze_report(first)
    world.approve('first', first)
    world.runs[world.run_id]['reviews'].append(synthetic_review(FABRICIA, 'aprovacao-fahnassau30', 'rejected'))
    expect_blocked(world, world.finish, first)
    original = world.refs['tags/' + first]
    corrected = world.correct_release()
    world.set_run('9002')
    second = world.prepare()
    assert second == 'v1.4.0-rc.2'
    assert world.refs['tags/' + first] == original and corrected != original
    assert world.state['candidates'][first]['status'] == 'superseded'
    assert not world.state['candidates'][second].get('approval_receipts')
    world.freeze_report(second)
    expect_blocked(world, world.finish, first)
    expect_blocked(world, world.finish, second)
    world.approve('first', second)
    world.approve('second', second)
    world.authorize(ISRAEL)
    world.finish(second)
    assert world.refs['tags/v1.4.0'] == corrected
    assert world.refs['tags/' + first] == original
    world.emit('assertions_passed', rc1_preserved=True, rc2_approvals_started_at_zero=True,
               stable_from_corrected_rc2=True, remote_pr_exercised=False)


def scenario_frozen_identity(world):
    tag = world.prepare()
    world.freeze_report(tag)
    world.approve('first', tag)
    world.approve('second', tag)
    world.authorize()
    record = world.state['candidates'][tag]
    report = copy.deepcopy(record['report'])
    record['report']['title'] = 'changed after review'
    expect_blocked(world, world.finish, tag)
    record['report'] = report
    original = world.refs['tags/' + tag]
    world.refs['tags/' + tag] = world.baseline
    expect_blocked(world, world.finish, tag)
    world.refs['tags/' + tag] = original
    world.refs['heads/release/1.4.0'] = world.baseline
    expect_blocked(world, world.finish, tag)
    world.refs['heads/release/1.4.0'] = original
    world.policy['mobile_bases']['android'] = {'source_sha': world.baseline, 'release_version': '1.3.0+1'}
    expect_blocked(world, world.finish, tag)
    world.assert_no_publication()
    world.emit('assertions_passed', changed_report_blocked=True, moved_tag_blocked=True,
               release_branch_drift_blocked=True, changed_mobile_base_policy_blocked=True)


def scenario_conflict(world):
    tag = world.prepare()
    world.freeze_report(tag)
    world.approve('first', tag)
    world.approve('second', tag)
    world.authorize()
    world.refs['tags/v1.4.0'] = world.baseline
    expect_blocked(world, world.finish, tag)
    assert world.refs['tags/v1.4.0'] == world.baseline
    assert not world.releases
    assert not world.state['candidates'][tag].get('receipt')
    assert not any(c['method'] in ('PATCH', 'DELETE') for c in world.calls)
    world.emit('assertions_passed', conflicting_tag_not_overwritten=True, receipt_absent=True)


def scenario_partial_recovery(world):
    tag = world.prepare()
    world.freeze_report(tag)
    world.approve('first', tag)
    world.approve('second', tag)
    world.authorize()
    world.inject_failure('git/refs', after=True)
    world.inject_failure('releases', after=False)
    try:
        world.finish(tag)
    except lab.LabError:
        pass
    assert world.refs['tags/v1.4.0'] == world.source
    # A timeout may be reconciled within finish; if Release creation failed, a
    # fresh recovery run must prove a new final decision instead of using rerun.
    if not world.state['candidates'][tag].get('receipt'):
        world.set_run('9003')
        world.env['GITHUB_REF'] = 'refs/heads/main'
        world.authorize(ISRAEL)
        world.inject_failure('releases', after=True)
        world.invoke('recover', tag=tag, report_digest=world.state['candidates'][tag]['report_digest'])
    assert len(world.releases) == 1
    assert world.state['candidates'][tag].get('receipt')
    assert world.refs['tags/v1.4.0'] == world.refs['tags/' + tag]
    assert not any(c['method'] in ('PATCH', 'DELETE') for c in world.calls)
    world.emit('assertions_passed', lost_tag_response_reconciled=True,
               lost_release_response_reconciled=True, exactly_one_release=True,
               receipt_after_verified_effects=True)


def scenario_version_and_identity(world):
    scenario_happy(world)
    stable_refs, releases = copy.deepcopy(world.refs), copy.deepcopy(world.releases)
    for version in ('1.4.0', '1.3.9'):
        expect_blocked(world, world.prepare, version)
        assert world.refs == stable_refs and world.releases == releases
    for change in ({'GITHUB_RUN_ATTEMPT': '2'}, {'GITHUB_ACTOR_ID': '7'},
                   {'GITHUB_TRIGGERING_ACTOR': FABRICIA['login']}):
        prior = dict(world.env)
        world.env.update(change)
        expect_blocked(world, world.prepare, '1.5.0')
        assert world.refs == stable_refs and world.releases == releases
        world.env = prior
    world.set_run('9010')
    tag = world.prepare('1.5.0')
    world.freeze_report(tag)
    world.runs[world.run_id]['reviews'].append(synthetic_review(ISRAEL, 'aprovacao-israel'))
    world.runs[world.run_id]['reviews'][0]['user']['type'] = 'Bot'
    expect_blocked(world, world.invoke, 'approval', tag=tag, role='first',
                   report_digest=world.state['candidates'][tag]['report_digest'])
    assert world.refs['tags/v1.4.0'] == stable_refs['tags/v1.4.0']
    assert len(world.releases) == 1
    world.emit('assertions_passed', old_version_blocked=True, completed_version_blocked=True,
               rerun_blocked=True, wrong_actor_blocked=True, bot_review_blocked=True)


def scenario_concurrent_journal(world):
    tag = world.prepare()
    report_digest = world.freeze_report(tag)
    for role in ('first', 'second'):
        person = next(p for p in world.policy['approvers'] if p['role'] == role)
        world.runs[world.run_id]['reviews'].append(synthetic_review(person, person['environment']))
    original_route = world.route
    raced = False

    def route(path, data, method, missing):
        nonlocal raced
        if path == 'contents/' + lab.STATE_PATH and method == 'PUT' and not raced:
            raced = True
            world.emit('interleaved_writer', note='Second gate writes after first gate read, before first CAS write')
            world.invoke('approval', tag=tag, role='second', report_digest=report_digest)
        return original_route(path, data, method, missing)

    with patch.object(world, 'route', side_effect=route):
        world.invoke('approval', tag=tag, role='first', report_digest=report_digest)
    receipts = world.state['candidates'][tag]['approval_receipts']
    assert set(receipts) == {'first', 'second'}
    actions = [event['action'] for event in world.state['events']]
    assert actions.count('approval_first') == actions.count('approval_second') == 1
    world.runs[world.run_id]['jobs'] = [{'name': 'Gate ' + role, 'conclusion': 'success'}
                                      for role in ('first', 'second')]
    world.authorize()
    world.finish(tag)
    assert len(world.releases) == 1
    world.emit('assertions_passed', stale_journal_write_retried=True,
               both_approval_receipts_preserved=True, exactly_one_event_per_role=True)


def scenario_failed_preview(world):
    tag = world.prepare()
    world.invoke('preflight', tag=tag)
    record = world.state['candidates'][tag]
    smoke_path, metadata_path = world.folder / 'failed-smoke.json', world.folder / 'failed-metadata.json'
    smoke_path.write_text(json.dumps({'success': False, 'source_sha': record['source_sha']}))
    metadata_path.write_text(json.dumps({'source_sha': record['source_sha']}))
    expect_blocked(world, world.invoke, 'report', tag=tag,
                   smoke_path=smoke_path, metadata_path=metadata_path)
    assert not world.state['candidates'][tag].get('report_digest')
    world.runs[world.run_id]['reviews'].append(synthetic_review(ISRAEL, 'aprovacao-israel'))
    expect_blocked(world, world.invoke, 'approval', tag=tag, role='first', report_digest='e' * 64)
    expect_blocked(world, world.invoke, 'finish', tag=tag, report_digest='e' * 64)
    world.assert_no_publication()
    world.emit('assertions_passed', failed_preview_prevents_frozen_report=True,
               cannot_register_approval_without_report=True, cannot_publish_without_report=True)


def scenario_protection_drift(world):
    tag = world.prepare()
    world.freeze_report(tag)
    world.approve('first', tag)
    world.approve('second', tag)
    world.authorize()
    with patch.object(world, 'rulesets', return_value=[]):
        world.emit('fixture_rules_removed', phase='after reviews, before publication intent')
        expect_blocked(world, world.finish, tag)
    world.assert_no_publication()
    assert not world.state['candidates'][tag].get('publication')
    original_route, original_rulesets = world.route, world.rulesets
    stable_created = False

    def route(path, data, method, missing):
        nonlocal stable_created
        result = original_route(path, data, method, missing)
        if (path == 'git/refs' and method == 'POST'
                and data['ref'] == 'refs/tags/v1.4.0'):
            stable_created = True
            world.emit('fixture_rules_removed', phase='after stable creation, before Release effect')
        return result

    with patch.object(world, 'route', side_effect=route), \
            patch.object(world, 'rulesets', side_effect=lambda: [] if stable_created else original_rulesets()):
        expect_blocked(world, world.finish, tag)
    assert stable_created and world.refs['tags/v1.4.0'] == world.source
    assert world.releases == []
    assert not world.state['candidates'][tag].get('receipt')
    assert world.state['candidates'][tag]['publication']['status'] == 'failed'
    assert not any(call['method'] in ('PATCH', 'DELETE') for call in world.calls)
    world.emit('assertions_passed', missing_rules_prevent_intent=True,
               missing_rules_after_stable_prevent_release=True,
               stable_and_partial_intent_preserved=True, receipt_absent=True)


SCENARIOS = [
    ('VAL-01', '0/2, 1/2 e 2/2 sem PUBLICAR bloqueiam; terceiro comando promove', scenario_happy),
    ('VAL-02', 'RC1 negada, código corrigido e RC2 sem herdar avais', scenario_rc_correction),
    ('VAL-03', 'Relatório, tag, ramo ou release-base alterados bloqueiam avais antigos', scenario_frozen_identity),
    ('VAL-04', 'Tag estável conflitante preservada sem sobrescrita', scenario_conflict),
    ('VAL-05', 'Falha parcial e resposta perdida: reconciliação sem Release duplicada', scenario_partial_recovery),
    ('VAL-06', 'Versão antiga/concluída, iniciador errado, rerun e bot bloqueados', scenario_version_and_identity),
    ('VAL-07', 'Dois writers intercalados preservam ambos os avais por retry CAS', scenario_concurrent_journal),
    ('VAL-08', 'Preview reprovado bloqueia relatório, registro do aval e publicação', scenario_failed_preview),
    ('VAL-09', 'Proteções removidas após reviews ou após stable bloqueiam o próximo efeito', scenario_protection_drift)]


LESSONS = [
    {'scenario': 'VAL-01', 'lesson': 'Two approval receipts do not replace the separate final publication decision.'},
    {'scenario': 'VAL-02', 'lesson': 'A corrected commit requires a new RC tag and fresh reviews; keep rejected RC refs for audit.'},
    {'scenario': 'VAL-03', 'lesson': 'Bind reviews to code, frozen report and policy; a review count alone cannot authorize promotion.'},
    {'scenario': 'VAL-04', 'lesson': 'An existing stable ref reserves its version; never adopt, move or delete a conflicting ref.'},
    {'scenario': 'VAL-05', 'lesson': 'Persist publication intent before effects, then GET the exact tag and Release after lost responses; do not repeat a blind POST.'},
    {'scenario': 'VAL-06', 'lesson': 'Compare versions numerically and distinguish the original operator, real account identity and run attempt.'},
    {'scenario': 'VAL-07', 'lesson': 'A journal writer must recompute from fresh state after a CAS conflict, preserving the other approver receipt.'},
    {'scenario': 'VAL-08', 'lesson': 'An unsuccessful preview cannot become a reviewable frozen report or a publication authorization.'},
    {'scenario': 'VAL-09', 'lesson': 'Recheck effective protections after human waiting and before each external effect; preserve an already-created stable tag if protections disappear.'},
    {'scenario': 'all', 'lesson': 'Offline fixtures prove helper behavior only; repeat human reviews, permissions and GitHub publication checks on the real service.'}]


def run_scenarios(folder):
    folder = Path(folder)
    if folder.exists() and any(folder.iterdir()):
        raise ValueError('Use a new empty output directory; previous evidence must not be overwritten or mixed.')
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for identifier, description, scenario in SCENARIOS:
        world = OfflineWorld(folder / identifier)
        result = {'scenario': identifier, 'description': description,
                  'scope': 'offline helper + synthetic GitHub API/reviews + real disposable Git',
                  'expected': 'All assertions pass; no real external action', 'status': 'FAIL'}
        try:
            scenario(world)
            result.update(status='PASS', obtained='All explicit state/ref/receipt assertions passed')
        except Exception as error:
            result['obtained'] = type(error).__name__ + ': ' + str(error)
            world.emit('scenario_failed', reason=result['obtained'])
        world.snapshot('final')
        (world.folder / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
        world.close()
        results.append(result)
    report = {'schema': 1, 'executed_at': datetime.now(timezone.utc).isoformat(),
              'mode': 'offline', 'real_network': False, 'real_human_reviews': False,
              'real_pages_validation': False, 'real_github_release': False,
              'helper_sha256': lab.hashlib.sha256(Path(lab.__file__).read_bytes()).hexdigest(),
              'results': results, 'passed': sum(r['status'] == 'PASS' for r in results),
              'total': len(results),
              'lessons_learned': LESSONS,
              'limitations': ['Synthetic reviews are not human E2E evidence.',
                              'Local correction is not a remote reviewed PR.',
                              'Preview HTTP success is fixture input, not a live Pages check.',
                              'Offline API cannot prove real GitHub permissions or UI behavior.',
                              'No mobile build, Shorebird patch, store or tester distribution.']}
    (folder / 'summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = run_scenarios(args.output)
    print(json.dumps({'mode': 'offline', 'passed': report['passed'], 'total': report['total'],
                      'summary': str(Path(args.output) / 'summary.json')}, ensure_ascii=False))
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
