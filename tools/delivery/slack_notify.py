"""Private laboratory Slack notices; approvals remain exclusively in GitHub.

Default operation only renders JSON. --send explicitly uses SLACK_BOT_TOKEN
from the environment; no credentials are written to the outbox or printed.

Primary references (consulted 2026-10-07):
https://docs.slack.dev/reference/methods/chat.postMessage/
https://docs.slack.dev/reference/methods/conversations.info/
https://docs.slack.dev/reference/methods/conversations.members/
https://docs.slack.dev/reference/methods/auth.test/

The local outbox prevents repeating a known/uncertain attempt only while the
same database is retained. client_msg_id is supplementary, not an exactly-once
guarantee. An uncertain result must be reconciled manually; this adapter has no
automatic retry, approval callback, invitation or alternate-channel fallback.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

CHANNEL_ID = 'C0C8DUJB52L'
CHANNEL_NAME = 'app-deploy-test-isr'
ISRAEL_ID = 'U0BMFQKC001'
GITHUB_REPOSITORY = 'israelhudson/flutter_code_push_example'
EVENTS = ('candidate', 'approval', 'publication', 'lab')
DEFAULT_OUTBOX = Path('build/delivery/slack-outbox.sqlite3')
_LABELS = {'candidate': 'Candidata preparada', 'approval': 'Estado de aprovação',
           'publication': 'Estado de publicação', 'lab': 'Ensaio do laboratório'}
_METHODS = {'auth.test', 'conversations.info', 'conversations.members', 'chat.postMessage'}


class NoticeError(ValueError):
    pass


class SlackAPIError(NoticeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    # Do not forward a bearer token to a redirected host.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


request_url = build_opener(NoRedirect()).open


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _text(value, field, maximum, multiline=False):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(c) < 32 and not (multiline and c == '\n') for c in value)
            or '\x7f' in value):
        raise NoticeError(f'{field} inválido.')
    return value.strip()


def github_url(value):
    value = _text(value, 'URL GitHub', 1200)
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.netloc != 'github.com'
            or not parsed.path.startswith('/' + GITHUB_REPOSITORY + '/')
            or parsed.query or parsed.fragment or any(c in value for c in '<>| \\')):
        raise NoticeError('Use um link HTTPS deste repositório no GitHub, sem query ou fragmento.')
    return value


def render_notice(event, status, candidate, source_sha, url, simulation=None,
                  dry_run=True, idempotency_key=None):
    if event not in EVENTS:
        raise NoticeError('Evento inválido.')
    status = _text(status, 'Status', 1400, multiline=True)
    candidate = _text(candidate, 'Candidata', 160)
    if not re.fullmatch(r'[0-9a-f]{40}', source_sha or ''):
        raise NoticeError('Informe o SHA completo do snapshot.')
    url = github_url(url)
    simulation = event == 'lab' if simulation is None else simulation
    if not isinstance(simulation, bool) or dry_run is not True:
        raise NoticeError('Esta POC exige dry_run=true e simulation booleano.')
    if event == 'lab' and not simulation:
        raise NoticeError('Evento lab precisa declarar simulation=true.')
    logical = {'event': event, 'status': status, 'candidate': candidate,
               'source_sha': source_sha, 'url': url, 'simulation': simulation,
               'dry_run': dry_run, 'channel': CHANNEL_ID}
    event_key = (_text(idempotency_key, 'Chave de idempotência', 240)
                 if idempotency_key is not None else hashlib.sha256(canonical(logical).encode()).hexdigest())
    body = (f'LABORATÓRIO · {_LABELS[event]}\n'
            f'Candidata: {candidate}\nStatus: {status}\nSnapshot: {source_sha}\n'
            f'simulation={str(simulation).lower()} · dry_run=true (distribuição do app)\n'
            'Aprovações e comando final ficam no GitHub. Este aviso não aprova nem publica.')
    payload = {'channel': CHANNEL_ID, 'text': body + '\n' + url,
               'blocks': [{'type': 'section', 'text': {'type': 'plain_text', 'text': body, 'emoji': False}},
                          {'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'<{url}|Abrir no GitHub>',
                                                       'verbatim': True}}],
               'mrkdwn': False, 'parse': 'none', 'link_names': False,
               'unfurl_links': False, 'unfurl_media': False,
               'client_msg_id': str(uuid.uuid5(uuid.NAMESPACE_URL, CHANNEL_ID + ':' + event_key))}
    return {'event_key': event_key, 'simulation': simulation, 'dry_run': True, 'payload': payload}


def slack_api(method, data, token):
    if method not in _METHODS:
        raise SlackAPIError('Método Slack fora do escopo de avisos.')
    write = method == 'chat.postMessage'
    url = 'https://slack.com/api/' + method
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}
    if write:
        headers['Content-Type'] = 'application/json; charset=utf-8'
        request = Request(url, data=canonical(data).encode(), headers=headers, method='POST')
    else:
        request = Request(url + ('?' + urlencode(data) if data else ''), headers=headers, method='GET')
    try:
        with request_url(request, timeout=10) as response:
            result = json.loads(response.read(1024 * 1024))
    except HTTPError as error:
        raise SlackAPIError(f'Slack {method}: HTTP {error.code}; sem retry automático.') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise SlackAPIError(f'Slack {method}: resposta não confirmada; sem retry automático.') from None
    if not isinstance(result, dict) or result.get('ok') is not True:
        code = result.get('error', 'invalid_response') if isinstance(result, dict) else 'invalid_response'
        code = code if isinstance(code, str) and re.fullmatch(r'[a-z0-9_]{1,80}', code) else 'invalid_response'
        raise SlackAPIError(f'Slack {method}: {code}; sem retry automático.')
    return result


def verify_destination(token, api=slack_api):
    auth = api('auth.test', {}, token)
    bot_user = auth.get('user_id')
    if (not auth.get('bot_id') or not isinstance(bot_user, str)
            or not re.fullmatch(r'[UW][A-Z0-9]+', bot_user) or bot_user == ISRAEL_ID):
        raise NoticeError('O token precisa identificar o próprio bot, sem representar Israel.')
    channel = api('conversations.info', {'channel': CHANNEL_ID}, token).get('channel', {})
    if (not isinstance(channel, dict) or channel.get('id') != CHANNEL_ID or channel.get('name') != CHANNEL_NAME
            or channel.get('is_private') is not True or channel.get('is_archived') is not False
            or channel.get('is_im') or channel.get('is_mpim')
            or channel.get('is_shared') or channel.get('is_ext_shared')
            or channel.get('is_pending_ext_shared') or channel.get('is_org_shared')):
        raise NoticeError('Destino não corresponde ao canal privado de laboratório autorizado.')
    members, seen_cursors = set(), set()
    cursor = ''
    for _ in range(100):
        args = {'channel': CHANNEL_ID, 'limit': 200}
        if cursor:
            args['cursor'] = cursor
        response = api('conversations.members', args, token)
        batch = response.get('members')
        if not isinstance(batch, list) or not all(isinstance(m, str) for m in batch):
            raise NoticeError('Lista de membros inválida; envio bloqueado.')
        members.update(batch)
        if members - {ISRAEL_ID, bot_user}:
            raise NoticeError('Canal contém outros membros; envio bloqueado.')
        metadata = response.get('response_metadata', {})
        next_cursor = metadata.get('next_cursor', '') if isinstance(metadata, dict) else None
        if not isinstance(next_cursor, str):
            raise NoticeError('Cursor de membros inválido; envio bloqueado.')
        cursor = next_cursor.strip()
        if not cursor:
            break
        if cursor in seen_cursors:
            raise NoticeError('Paginação de membros repetida; envio bloqueado.')
        seen_cursors.add(cursor)
    else:
        raise NoticeError('Paginação incompleta; envio bloqueado.')
    if members != {ISRAEL_ID, bot_user}:
        raise NoticeError('O canal precisa conter somente Israel e o próprio bot.')
    return bot_user


def _open_outbox(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS notices ('
               'event_key TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, '
               'client_msg_id TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN (\'unknown\',\'sent\')), '
               'slack_ts TEXT, created_at TEXT NOT NULL, sent_at TEXT)')
    db.commit()
    return db


def _prior(db, key, payload_hash):
    row = db.execute('SELECT payload_hash, state, slack_ts, client_msg_id FROM notices '
                     'WHERE event_key=?', (key,)).fetchone()
    if row is None:
        return None
    if row[0] != payload_hash:
        raise NoticeError('Chave já usada com outro conteúdo; envio bloqueado.')
    if row[1] != 'sent':
        raise NoticeError('Resultado unknown: confira o Slack e reconcilie a outbox; reenvio automático bloqueado.')
    return {'state': 'sent', 'duplicate': True, 'channel': CHANNEL_ID,
            'ts': row[2], 'client_msg_id': row[3]}


def send_notice(notice, outbox=DEFAULT_OUTBOX, api=slack_api, checkpoint=None):
    payload = notice['payload']
    if payload.get('channel') != CHANNEL_ID or notice.get('dry_run') is not True:
        raise NoticeError('Aviso fora do destino/modo autorizado.')
    key = _text(notice['event_key'], 'Chave de idempotência', 240)
    payload_hash = hashlib.sha256(canonical(payload).encode()).hexdigest()
    with closing(_open_outbox(outbox)) as db:
        prior = _prior(db, key, payload_hash)
        if prior:
            return prior
        token = os.environ.get('SLACK_BOT_TOKEN')
        if not token or any(c.isspace() for c in token):
            raise NoticeError('SLACK_BOT_TOKEN ausente ou inválido; nenhuma mensagem enviada.')
        verify_destination(token, api)
        # Commit uncertainty before the write. A concurrent invocation/crash
        # cannot automatically send this key again, even if the reply is lost.
        db.execute('BEGIN IMMEDIATE')
        prior = _prior(db, key, payload_hash)
        if prior:
            db.rollback()
            return prior
        db.execute('INSERT INTO notices(event_key,payload_hash,client_msg_id,state,created_at) '
                   'VALUES (?,?,?,\'unknown\',?)',
                   (key, payload_hash, payload['client_msg_id'], datetime.now(timezone.utc).isoformat()))
        db.commit()
        # Ephemeral runners must persist uncertainty remotely before the POST.
        # If this checkpoint fails, no external message has been attempted.
        if checkpoint is not None:
            checkpoint('unknown')
        result = api('chat.postMessage', payload, token)
        if (not isinstance(result, dict) or result.get('ok') is not True
                or result.get('channel') != CHANNEL_ID
                or not isinstance(result.get('ts'), str)
                or not re.fullmatch(r'\d+\.\d+', result['ts'])):
            raise NoticeError('Envio sem confirmação exata do canal/ts; outbox permanece unknown.')
        db.execute('UPDATE notices SET state=\'sent\',slack_ts=?,sent_at=? WHERE event_key=?',
                   (result['ts'], datetime.now(timezone.utc).isoformat(), key))
        db.commit()
        if checkpoint is not None:
            checkpoint('sent')
        return {'state': 'sent', 'duplicate': False, 'channel': CHANNEL_ID,
                'ts': result['ts'], 'client_msg_id': payload['client_msg_id']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', choices=EVENTS, required=True)
    parser.add_argument('--status', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--simulation', action='store_true', default=None)
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Sempre verdadeiro nesta POC; refere-se à distribuição do app, não ao aviso.')
    parser.add_argument('--idempotency-key')
    parser.add_argument('--outbox', type=Path, default=DEFAULT_OUTBOX,
                        help='SQLite persistente. Preserve o arquivo entre runs; unknown bloqueia repetição.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--render-only', action='store_true', help='Padrão: só JSON local, sem rede ou outbox.')
    mode.add_argument('--send', action='store_true', help='Envia aviso ao canal fixo após verificação.')
    args = parser.parse_args(argv)
    try:
        notice = render_notice(args.event, args.status, args.candidate, args.source_sha,
                               args.url, args.simulation, args.dry_run, args.idempotency_key)
        result = send_notice(notice, args.outbox) if args.send else notice
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (NoticeError, sqlite3.Error, OSError) as error:
        # NoticeError messages are sanitized. Do not print network exceptions,
        # raw API bodies, headers, token or user-supplied content in errors.
        message = str(error) if isinstance(error, NoticeError) else 'Outbox indisponível; envio bloqueado.'
        print(message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
