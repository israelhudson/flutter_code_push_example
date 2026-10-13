"""Collect credentials locally; validate the separate bot before installing disabled settings."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlencode

PROJECT = 'xtvueqciogzkyjkkqxcx'
TEAM = 'T09CYB7AS77'
CHANNEL = 'C0C8DUJB52L'
USER = 'U0BMFQKC001'
OLD_BOT = 'U0C750FTCS3'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def slack(token, method, payload):
    req = Request('https://slack.com/api/' + method + '?' + urlencode(payload),
                  headers={'Authorization': 'Bearer ' + token}, method='GET')
    with build_opener(NoRedirect()).open(req, timeout=15) as response:
        scopes = {x.strip() for x in response.headers.get('x-oauth-scopes', '').split(',')}
        result = json.load(response)
    if not result.get('ok'):
        raise ValueError('Slack validation refused. Check app scopes and private-channel membership.')
    return result, scopes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shared-app', action='store_true', help='Existing LAB app through the verified router; never edit its old backend.')
    args = parser.parse_args()
    app = input('App ID do novo app exclusivo: ').strip()
    if not re.fullmatch(r'A[A-Z0-9]+', app):
        raise ValueError('App ID inválido.')
    token = getpass.getpass('Bot User OAuth Token do novo app (oculto): ').strip()
    signing = getpass.getpass('Signing Secret do novo app (oculto): ').strip()
    if not token.startswith('xoxb-') or len(signing) < 16 or '\n' in signing:
        raise ValueError('Credenciais inválidas.')
    bot, scopes = slack(token, 'auth.test', {})
    if bot.get('team_id') != TEAM or (bot.get('user_id') == OLD_BOT and not args.shared_app):
        raise ValueError('Workspace incorreto ou bot LAB compartilhado. Criar app exclusivo.')
    if args.shared_app and (bot.get('user_id') != OLD_BOT or app != 'A0C750DS05D'):
        raise ValueError('O modo compartilhado exige o app LAB confirmado.')
    if not {'chat:write', 'groups:read'} <= scopes:
        raise ValueError('Scopes insuficientes; conferir manifest e reinstalar o novo app.')
    members, cursor = [], ''
    for _ in range(20):
        data, _ = slack(token, 'conversations.members', {'channel': CHANNEL, 'limit': 200, **({'cursor': cursor} if cursor else {})})
        members.extend(data.get('members', []))
        cursor = data.get('response_metadata', {}).get('next_cursor', '')
        if not cursor:
            break
    if cursor or bot.get('user_id') not in members or USER not in members:
        raise ValueError('Adicione o novo bot no app-deploy-test-isr antes de configurar.')
    print('Bot exclusivo e Israel confirmados no canal de teste; nenhuma mensagem enviada.')
    print('Será configurado somente o projeto ' + PROJECT + ', com flags desligadas.')
    if input('Digite CONFIGURAR para instalar as credenciais: ').strip() != 'CONFIGURAR':
        print('Cancelado sem alterações.')
        return
    private = Path.home() / '.codex/private/slack-supabase-poc'
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private, 0o700)
    target = private / 'slack-app-secrets.env'
    values = {'POC_SLACK_APP_ID': app, 'POC_SLACK_BOT_TOKEN': token,
              'POC_SLACK_SIGNING_SECRET': signing, 'POC_SLACK_BOT_USER_ID': bot['user_id'],
              'POC_ENABLED': 'false', 'POC_PUBLICATION_ENABLED': 'false', 'POC_SOURCE_BRANCH': 'slack-main',
              'POC_SHARED_APP_ROUTING': 'true' if args.shared_app else 'false'}
    target.write_text(''.join(k + '=' + v + '\n' for k, v in values.items()))
    os.chmod(target, 0o600)
    result = subprocess.run(['supabase', 'secrets', 'set', '--project-ref', PROJECT,
                             '--env-file', str(target)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('CLI não confirmou configuração. Não ativar as flags.')
    print('Credenciais instaladas; preparação/publicação continuam desligadas. Consulte CONFIGURACAO.md.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        # Never print provider bodies, headers, tokens, or subprocess arguments.
        print('Configuração não concluída. Confira app, scopes, convite e autenticação do CLI.')
        raise SystemExit(1) from None
