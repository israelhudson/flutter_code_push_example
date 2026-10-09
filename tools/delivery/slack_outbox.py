"""Durable, optional LAB Slack notices across ephemeral GitHub runners.

Only release-lab/slack-outbox.json in codex/release-lab-state is writable.
Append-only Contents-SHA checkpoints reserve an event before chat.postMessage;
the candidate/approval journal is never modified. An uncertain send is only
reconciled by positive read-only Slack evidence, never by absence or retry.

Official references checked 2026-10-08:
https://docs.slack.dev/reference/methods/conversations.history/
https://docs.slack.dev/reference/methods/chat.postMessage/
https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents
"""
import argparse
import base64
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import uuid
from urllib.parse import quote

import release_lab
import slack_notify
from remote_state import _check_secrets, StateError

REPOSITORY = slack_notify.GITHUB_REPOSITORY
STATE_BRANCH = 'codex/release-lab-state'
STATE_PATH = 'release-lab/slack-outbox.json'
BOT_USER_ID = 'U0C750FTCS3'
APP_ID = 'A0C750DS05D'
SCHEMA = 1
MAX_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 10000
MAX_HISTORY_PAGES = 3
EVENTS = {'candidate_available', 'approval_first', 'approval_second', 'approvals_complete',
          'candidate_rejected', 'candidate_cancelled', 'candidate_failed', 'candidate_superseded',
          'publication_completed', 'publication_partial'}
_SHA40 = re.compile(r'[0-9a-f]{40}\Z')
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_TS = re.compile(r'\d+\.\d+\Z')
_IDENTITY_FIELDS = {'candidate_tag', 'source_sha', 'snapshot_digest', 'run_id', 'run_url'}
_CHECKPOINT_FIELDS = {'at', 'state', 'event_key', 'payload_hash', 'client_msg_id',
                      'channel', 'identity', 'attempt_id', 'receipt'}


class OutboxError(slack_notify.NoticeError):
    pass


def canonical(value):
    return release_lab.canonical(value)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def logical_event_key(identity, event='candidate_available'):
    """One RC/snapshot identity; run and attempt never change the event key."""
    return ':'.join((event, identity['candidate_tag'], identity['source_sha'], identity['snapshot_digest']))


def _identity(value):
    if (not isinstance(value, dict) or set(value) != _IDENTITY_FIELDS
            or not release_lab.TAG.fullmatch(str(value.get('candidate_tag', '')))
            or not _SHA40.fullmatch(str(value.get('source_sha', '')))
            or not _SHA256.fullmatch(str(value.get('snapshot_digest', '')))
            or not re.fullmatch(r'[1-9]\d*', str(value.get('run_id', '')))
            or value.get('run_url') != 'https://github.com/' + REPOSITORY + '/actions/runs/' + str(value['run_id'])):
        raise OutboxError('Identidade congelada do aviso inválida; envio bloqueado.')
    return value


def _content(value):
    """Select the actual visible payload, ignoring server-added block IDs."""
    blocks = value.get('blocks')
    if not isinstance(blocks, list):
        raise OutboxError('Blocos do aviso inválidos; envio bloqueado.')
    selected = []
    for block in blocks:
        if not isinstance(block, dict):
            raise OutboxError('Bloco do aviso inválido; envio bloqueado.')
        selected.append({k: v for k, v in block.items() if k != 'block_id'})
    return {'text': value.get('text'), 'blocks': selected}


def validate_notice(notice):
    if (not isinstance(notice, dict) or notice.get('dry_run') is not True
            or not isinstance(notice.get('simulation'), bool)
            or notice.get('event') not in EVENTS):
        raise OutboxError('Aviso precisa declarar evento candidato e laboratório sem distribuição.')
    identity = _identity(notice.get('identity'))
    if notice.get('event_key') != logical_event_key(identity, notice['event']):
        raise OutboxError('Chave do aviso diverge da identidade congelada.')
    payload = notice.get('payload')
    fields = {'channel', 'text', 'blocks', 'mrkdwn', 'parse', 'link_names',
              'unfurl_links', 'unfurl_media', 'client_msg_id'}
    if (not isinstance(payload, dict) or set(payload) != fields
            or payload.get('channel') != slack_notify.CHANNEL_ID
            or payload.get('mrkdwn') is not False or payload.get('parse') != 'none'
            or any(payload.get(k) is not False for k in ('link_names', 'unfurl_links', 'unfurl_media'))
            or payload.get('client_msg_id') != str(uuid.uuid5(uuid.NAMESPACE_URL,
                                      slack_notify.CHANNEL_ID + ':' + notice['event_key']))
            or not isinstance(payload.get('text'), str) or not payload['text']
            or len(payload['text']) > 4000 or len(canonical(notice).encode()) > 100000):
        raise OutboxError('Payload do aviso fora do canal/modo autorizado.')
    # Keep this adapter noninteractive. The frozen renderer owns the plain
    # text and repository links; actions, buttons and arbitrary mention parsing
    # cannot enter through a notice JSON supplied to the CLI.
    content = _content(payload)
    for block in content['blocks']:
        text = block.get('text')
        if (set(block) != {'type', 'text'} or block.get('type') != 'section'
                or not isinstance(text, dict) or text.get('type') not in ('plain_text', 'mrkdwn')
                or not isinstance(text.get('text'), str) or len(text['text']) > 3000):
            raise OutboxError('Aviso não pode conter controles interativos.')
        if text['type'] == 'mrkdwn':
            if set(text) != {'type', 'text', 'verbatim'} or text.get('verbatim') is not True:
                raise OutboxError('Link do aviso precisa ser literal e explícito.')
            match = re.fullmatch(r'<(https://[^<>|]+)\|([^<>|]+)>', text['text'])
            if match is None:
                raise OutboxError('Link do aviso fora do GitHub autorizado.')
            preview_url = ('https://israelhudson.github.io/flutter_code_push_example/snapshots/'
                           + identity['source_sha'] + '/')
            if match[1] not in (identity['run_url'], preview_url):
                raise OutboxError('Link do aviso diverge do preview/run congelado.')
        elif set(text) - {'type', 'text', 'emoji'}:
            raise OutboxError('Texto do aviso contém campos não autorizados.')
    try:
        _check_secrets(notice)
    except StateError:
        raise OutboxError('Aviso contém credencial; nenhum conteúdo foi persistido.') from None
    return {'event_key': notice['event_key'], 'payload_hash': digest(payload),
            'client_msg_id': payload['client_msg_id'], 'channel': slack_notify.CHANNEL_ID,
            'identity': dict(identity)}


def _same(first, second):
    # The evaluation run is frozen candidate provenance; the delivery worker's
    # retry does not replace it. The logical key omits attempts while the full
    # descriptor still rejects changing this immutable source identity.
    return (all(first[k] == second[k] for k in ('event_key', 'payload_hash', 'client_msg_id', 'channel'))
            and first['identity'] == second['identity'])


def _receipt(value):
    if (not isinstance(value, dict) or set(value) != {'channel', 'ts', 'bot_user_id', 'app_id', 'reconciled'}
            or value.get('channel') != slack_notify.CHANNEL_ID
            or not isinstance(value.get('ts'), str) or not _TS.fullmatch(value['ts'])
            or value.get('bot_user_id') != BOT_USER_ID or value.get('app_id') != APP_ID
            or not isinstance(value.get('reconciled'), bool)):
        raise OutboxError('Recibo remoto Slack inválido; reenvio bloqueado.')
    return value


def _project(document):
    if (not isinstance(document, dict) or set(document) != {'schema', 'repository', 'branch', 'events'}
            or document.get('schema') != SCHEMA or document.get('repository') != REPOSITORY
            or document.get('branch') != STATE_BRANCH or not isinstance(document.get('events'), list)
            or len(document['events']) > MAX_EVENTS):
        raise OutboxError('Journal Slack desconhecido; não sobrescrever.')
    result = {}
    for checkpoint in document['events']:
        if (not isinstance(checkpoint, dict) or set(checkpoint) - _CHECKPOINT_FIELDS
                or not _CHECKPOINT_FIELDS - {'receipt'} <= set(checkpoint)
                or checkpoint.get('state') not in ('unknown', 'sent')
                or not _SHA256.fullmatch(str(checkpoint.get('payload_hash', '')))
                or checkpoint.get('channel') != slack_notify.CHANNEL_ID):
            raise OutboxError('Checkpoint Slack inválido; não presumir outbox vazia.')
        _identity(checkpoint['identity'])
        event = str(checkpoint['event_key']).split(':')[0]
        if event not in EVENTS or checkpoint['event_key'] != logical_event_key(checkpoint['identity'], event):
            raise OutboxError('Checkpoint de outra identidade; reenvio bloqueado.')
        try:
            uuid.UUID(checkpoint['attempt_id'])
            expected_client = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                  slack_notify.CHANNEL_ID + ':' + checkpoint['event_key']))
            if checkpoint['client_msg_id'] != expected_client:
                raise ValueError()
            datetime.fromisoformat(checkpoint['at'])
            _check_secrets(checkpoint)
        except (ValueError, TypeError, StateError):
            raise OutboxError('Metadados de checkpoint inválidos; envio bloqueado.') from None
        previous = result.get(checkpoint['event_key'])
        if checkpoint['state'] == 'unknown':
            if previous is not None or 'receipt' in checkpoint:
                raise OutboxError('Reserva Slack duplicada; journal bloqueado.')
        else:
            _receipt(checkpoint.get('receipt'))
            if (previous is None or previous['state'] != 'unknown' or not _same(previous, checkpoint)
                    or previous['attempt_id'] != checkpoint['attempt_id']):
                raise OutboxError('Transição Slack não é append-only; journal bloqueado.')
        result[checkpoint['event_key']] = checkpoint
    return result


class SlackJournalStore:
    """Contents-SHA CAS in a separate file preserves release-lab/state.json."""
    def __init__(self, api=release_lab.api):
        self.api = api

    def read(self):
        path = release_lab.endpoint('contents/' + STATE_PATH)
        response = self.api(path + '?ref=' + quote(STATE_BRANCH, safe=''), missing=True)
        if response is None:
            # Verify the expected branch exists. Missing file may bootstrap;
            # missing branch/authentication must never look like empty state.
            branch = self.api(release_lab.endpoint('git/ref/heads/' + STATE_BRANCH))
            if (not isinstance(branch, dict) or branch.get('ref') != 'refs/heads/' + STATE_BRANCH
                    or not _SHA40.fullmatch(str(branch.get('object', {}).get('sha', '')))):
                raise OutboxError('Branch durável ausente; envio bloqueado.')
            return {'schema': SCHEMA, 'repository': REPOSITORY, 'branch': STATE_BRANCH, 'events': []}, None
        try:
            encoded = re.sub(r'\s', '', response['content'])
            raw = base64.b64decode(encoded, validate=True)
            if response.get('encoding') != 'base64' or len(raw) > MAX_BYTES:
                raise ValueError()
            blob_sha = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if response.get('sha') != blob_sha:
                raise ValueError()
            document = json.loads(raw)
        except (KeyError, TypeError, ValueError, UnicodeDecodeError):
            raise OutboxError('Bytes do journal Slack inválidos; envio bloqueado.') from None
        _project(document)
        return document, response['sha']

    def get(self, descriptor):
        document, _ = self.read()
        prior = _project(document).get(descriptor['event_key'])
        if prior is not None and not _same(prior, descriptor):
            raise OutboxError('Chave já usada com outro conteúdo; envio bloqueado.')
        return prior

    def append(self, descriptor, state, attempt_id, receipt=None):
        for _ in range(3):
            document, old_sha = self.read()
            prior = _project(document).get(descriptor['event_key'])
            if prior is not None and not _same(prior, descriptor):
                raise OutboxError('Chave já usada com outro conteúdo; envio bloqueado.')
            if state == 'unknown' and prior is not None:
                raise OutboxError('Evento já reservado; resultado unknown/sent precisa ser reconciliado.')
            if state == 'sent':
                _receipt(receipt)
                if prior is None or prior['attempt_id'] != attempt_id:
                    raise OutboxError('Confirmação sem reserva remota própria; envio bloqueado.')
                if prior['state'] == 'sent':
                    if prior['receipt'] != receipt:
                        raise OutboxError('Recibo confirmado divergente; journal preservado.')
                    return prior
            checkpoint = {**descriptor, 'state': state, 'at': now(), 'attempt_id': attempt_id}
            if receipt is not None:
                checkpoint['receipt'] = receipt
            document['events'].append(checkpoint)
            _project(document)
            content = (canonical(document) + '\n').encode()
            if len(content) > MAX_BYTES:
                raise OutboxError('Journal Slack excede limite; envio bloqueado.')
            data = {'branch': STATE_BRANCH, 'message': 'lab: Slack ' + state,
                    'content': base64.b64encode(content).decode()}
            if old_sha:
                data['sha'] = old_sha
            try:
                self.api(release_lab.endpoint('contents/' + STATE_PATH), data, 'PUT')
                return checkpoint
            except release_lab.LabError:
                # A failed HTTP reply could hide a successful commit. Never
                # repeat external effects; an exact own checkpoint can be
                # acknowledged, other reservations block the current writer.
                current = self.get(descriptor)
                if current == checkpoint:
                    return current
                if current is not None:
                    raise OutboxError('Checkpoint concorrente/incerto; envio bloqueado.') from None
                # Different events may race the CAS. Re-read and append only
                # this journal entry; chat.postMessage has not run here.
        raise OutboxError('Checkpoint durável não confirmado; envio bloqueado.')


def _restore_sqlite(path, checkpoint):
    with closing(slack_notify._open_outbox(path)) as db:
        previous = db.execute('SELECT payload_hash,state,slack_ts,client_msg_id FROM notices WHERE event_key=?',
                              (checkpoint['event_key'],)).fetchone()
        if previous and (previous[0] != checkpoint['payload_hash'] or previous[3] != checkpoint['client_msg_id']):
            raise OutboxError('Cache local diverge do checkpoint remoto; envio bloqueado.')
        if previous and previous[1] == 'sent' and checkpoint['state'] == 'unknown':
            # Local sent is useful diagnostic evidence but remote unknown is
            # authoritative after a lost sent checkpoint; require Slack proof.
            return
        receipt = checkpoint.get('receipt', {})
        db.execute('INSERT INTO notices(event_key,payload_hash,client_msg_id,state,slack_ts,created_at,sent_at) '
                   'VALUES (?,?,?,?,?,?,?) ON CONFLICT(event_key) DO UPDATE SET '
                   'state=excluded.state,slack_ts=excluded.slack_ts,sent_at=excluded.sent_at',
                   (checkpoint['event_key'], checkpoint['payload_hash'], checkpoint['client_msg_id'],
                    checkpoint['state'], receipt.get('ts'), checkpoint['at'],
                    checkpoint['at'] if checkpoint['state'] == 'sent' else None))
        db.commit()


def _exact_bot_api(api):
    member_pages = 0

    def checked(method, data, token):
        nonlocal member_pages
        if method == 'conversations.members':
            member_pages += 1
            if member_pages > 3:
                raise OutboxError('Paginação de membros excede orçamento; envio bloqueado.')
        response = api(method, data, token)
        if not isinstance(response, dict) or response.get('ok') is not True:
            raise OutboxError('Resposta Slack inválida; nenhuma confirmação segura.')
        if method == 'auth.test' and (response.get('user_id') != BOT_USER_ID
                    or response.get('app_id', APP_ID) != APP_ID):
            raise OutboxError('Token não identifica o bot LAB autorizado; nenhuma mensagem enviada.')
        return response
    return checked


def _history_receipt(notice, checkpoint, token, api):
    cursor, seen = '', set()
    matches = []
    for _ in range(MAX_HISTORY_PAGES):
        arguments = {'channel': slack_notify.CHANNEL_ID, 'limit': 100}
        if cursor:
            arguments['cursor'] = cursor
        response = api('conversations.history', arguments, token)
        messages = response.get('messages')
        if not isinstance(messages, list):
            raise OutboxError('Histórico Slack inválido; resultado unknown permanece bloqueado.')
        for message in messages:
            if not isinstance(message, dict) or message.get('client_msg_id') != checkpoint['client_msg_id']:
                continue
            profile = message.get('bot_profile', {})
            if (message.get('user') != BOT_USER_ID or not isinstance(profile, dict)
                    or message.get('app_id', profile.get('app_id')) != APP_ID
                    or not message.get('bot_id')
                    or message.get('channel', slack_notify.CHANNEL_ID) != slack_notify.CHANNEL_ID
                    or not isinstance(message.get('ts'), str) or not _TS.fullmatch(message['ts'])
                    or digest(_content(message)) != digest(_content(notice['payload']))):
                raise OutboxError('Mensagem com client_msg_id possui identidade/conteúdo divergente; bloqueado.')
            matches.append(message)
        if len(matches) > 1:
            raise OutboxError('Mais de uma mensagem para o evento; reconciliação manual necessária.')
        metadata = response.get('response_metadata', {})
        cursor = metadata.get('next_cursor', '') if isinstance(metadata, dict) else None
        if not isinstance(cursor, str) or cursor in seen and cursor:
            raise OutboxError('Paginação Slack inválida; resultado unknown bloqueado.')
        if not cursor:
            break
        seen.add(cursor)
    if matches:
        # Positive proof establishes existence. A bounded history scan is not
        # an exactly-once/retention guarantee or proof about unread pages.
        return {'channel': slack_notify.CHANNEL_ID, 'ts': matches[0]['ts'],
                'bot_user_id': BOT_USER_ID, 'app_id': APP_ID, 'reconciled': True}
    raise OutboxError('Resultado unknown sem prova positiva no Slack; reconciliação manual necessária, sem reenvio.')


def send_frozen_notice(notice, output_dir, *, store=None, slack_api=slack_notify.slack_api):
    """Return only selected safe metadata; failures never block the LAB gates."""
    descriptor = validate_notice(notice)
    folder = Path(output_dir)
    if folder.is_symlink():
        raise OutboxError('Diretório de saída inválido; envio bloqueado.')
    folder.mkdir(parents=True, exist_ok=True)
    sqlite_path = folder / 'slack-outbox.sqlite3'
    if sqlite_path.is_symlink() or (folder / 'slack-receipt.json').is_symlink():
        raise OutboxError('Arquivo de saída inválido; envio bloqueado.')
    result = {**descriptor, 'state': 'blocked', 'duplicate': False,
              'notification_optional': True, 'distribution_performed': False}
    token = os.environ.get('SLACK_BOT_TOKEN')
    if (not token or not re.fullmatch(r'xoxb-[A-Za-z0-9-]+', token)
            or len(token) > 1000):
        result.update(state='skipped', reason='slack_secret_absent_or_invalid')
    else:
        store = SlackJournalStore() if store is None else store
        api = _exact_bot_api(slack_api)
        try:
            prior = store.get(descriptor)
            if prior is not None:
                _restore_sqlite(sqlite_path, prior)
                if prior['state'] == 'sent':
                    result.update(state='sent', duplicate=True, receipt=prior['receipt'])
                else:
                    slack_notify.verify_destination(token, api)
                    receipt = _history_receipt(notice, prior, token, api)
                    checkpoint = store.append(descriptor, 'sent', prior['attempt_id'], receipt)
                    _restore_sqlite(sqlite_path, checkpoint)
                    result.update(state='sent', duplicate=True, receipt=receipt)
            else:
                attempt_id = str(uuid.uuid4())

                def checkpoint(state):
                    receipt = None
                    if state == 'sent':
                        with closing(slack_notify._open_outbox(sqlite_path)) as db:
                            row = db.execute('SELECT state,slack_ts FROM notices WHERE event_key=?',
                                             (descriptor['event_key'],)).fetchone()
                        if not row or row[0] != 'sent' or not _TS.fullmatch(str(row[1])):
                            raise OutboxError('Recibo SQLite incompleto; checkpoint sent bloqueado.')
                        receipt = {'channel': slack_notify.CHANNEL_ID, 'ts': row[1],
                                   'bot_user_id': BOT_USER_ID, 'app_id': APP_ID, 'reconciled': False}
                    store.append(descriptor, state, attempt_id, receipt)

                sent = slack_notify.send_notice(notice, sqlite_path, api, checkpoint)
                if sent.get('duplicate'):
                    raise OutboxError('Cache local sem confirmação remota; reconciliação necessária.')
                result.update(state='sent', receipt={'channel': sent['channel'], 'ts': sent['ts'],
                              'bot_user_id': BOT_USER_ID, 'app_id': APP_ID, 'reconciled': False})
        except (slack_notify.NoticeError, release_lab.LabError, sqlite3.Error, OSError, ValueError):
            # API responses/exception strings never enter artifacts or stdout.
            result.update(state='blocked', reason='notification_unconfirmed_or_unsafe')
    (folder / 'slack-receipt.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notice', required=True)
    parser.add_argument('--output-dir', required=True)
    arguments = parser.parse_args(argv)
    try:
        path = Path(arguments.notice)
        if path.is_symlink() or path.stat().st_size > 100000:
            raise OutboxError('Arquivo de aviso inválido.')
        result = send_frozen_notice(json.loads(path.read_text()), arguments.output_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0  # Optional notification cannot approve or fail a LAB gate.
    except (OutboxError, OSError, ValueError, KeyError):
        print(json.dumps({'state': 'blocked', 'notification_optional': True,
                          'reason': 'invalid_frozen_notice_or_output'}))
        return 0


if __name__ == '__main__':
    sys.exit(main())
