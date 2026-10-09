# Configuração Slack do laboratório

**Use o bot `Flutter Deploy LAB` já instalado. A conexão real foi validada.**
O secret `SLACK_BOT_TOKEN` já existe no GitHub. Os avisos da candidata foram
integrados pela PR #19 e comprovados na jornada 1.7.0, com cinco avisos reais.
A jornada 1.8.0 está em correção após rejeição da RC1; seguir o
[manual de operação](SLACK-AUTOMATICO.md).

## O que está comprovado

Em **08/10/2026, às 22:19:46 (Fortaleza)**, a
[execução 37869235129](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37869235129)
enviou uma mensagem real. O adaptador conferiu a identidade do bot, o canal
privado e seus membros; a API confirmou `channel`/`ts`, e uma leitura
independente confirmou a mensagem visível e seu autor.

| Item | Identidade observada |
| --- | --- |
| App | `Flutter Deploy LAB` — `A0C750DS05D` |
| Usuário do bot | `U0C750FTCS3` |
| Canal privado | `app-deploy-test-isr` — `C0C8DUJB52L` |
| Participante humano | Israel — `U0BMFQKC001` |
| Membros permitidos neste LAB | Israel e o próprio bot |
| Recibo | `state=sent`, `duplicate=false`, `ts=1791508786.825199` |
| Credencial no GitHub | Secret de Actions `SLACK_BOT_TOKEN` |

A prova está no
[resultado sanitizado](https://github.com/israelhudson/flutter_code_push_example/blob/0ea138a7878652e797c68b84c118bcbc046f0e24/docs/delivery/evidencias/2026-10-08-slack-connection/RESULTADO.md)
e no
[recibo](https://github.com/israelhudson/flutter_code_push_example/blob/0ea138a7878652e797c68b84c118bcbc046f0e24/docs/delivery/evidencias/2026-10-08-slack-connection/receipt.json).
O workflow de conexão permanece na branch `codex/slack-connection-test` como
prova isolada; a automação da candidata tem implementação e ensaio próprios.

`simulation=true`/`dry_run=true` no teste descrevem o ensaio e a ausência de
distribuição do aplicativo. **O envio ao Slack foi real.** Nenhuma candidata,
tag, aprovação ou Release foi alterada pelo teste de conexão.

## Permissões e credencial

O bot precisa participar do canal privado. Para este fluxo, conferir no app
existente os escopos de bot pertinentes:

| Escopo | Finalidade |
| --- | --- |
| `chat:write` | Enviar com `chat.postMessage` |
| `groups:read` | Conferir o canal privado e sua lista de membros |
| `groups:history` | Ler o histórico do canal para reconciliar um envio incerto |

Esses requisitos vêm dos métodos oficiais
[chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/),
[conversations.info](https://docs.slack.dev/reference/methods/conversations.info/),
[conversations.members](https://docs.slack.dev/reference/methods/conversations.members/)
e [conversations.history](https://docs.slack.dev/reference/methods/conversations.history/).
O teste real prova as permissões usadas no envio e na verificação de destino;
a recuperação automática pelo histórico ainda precisa de sua própria prova.

O runner recebe o token explicitamente somente na etapa de comunicação.
Para manutenção ou rotação, usar
[Settings → Secrets and variables → Actions](https://github.com/israelhudson/flutter_code_push_example/settings/secrets/actions)
e atualizar `SLACK_BOT_TOKEN` diretamente. Conferir a presença pelo **nome**;
guardar o valor apenas no secret. Não copiar token para chat, código, arquivo,
print, artefato ou log.
[Guia oficial de secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets?tool=webui).

## Conferir o conteúdo sem enviar

Com o relatório real da candidata, executar na raiz do projeto:

```bash
python3 tools/delivery/slack_preview.py \
  --report CAMINHO/report.json \
  --policy delivery/release-lab-policy.json \
  --output build/slack-preview
```

O gerador cria `slack-message.json`, `slack-preview.md` e
`slack-preview-metadata.json`. Ele lê a comunicação congelada; não lê
credenciais nem envia mensagens. Criar ou rotacionar o secret não transforma
essa ilustração em remetente.

O conteúdo informa a candidata, as mudanças ou o fallback identificado, o
preview e a execução correta no GitHub. Aprovações e comando final continuam
autenticados no GitHub: **2/2 habilita somente o comando final separado.**

## Verificações restantes

1. Concluir a jornada 1.8.0 com correção, RC2 e novas decisões, sem herdar avais.
2. Confirmar mensagem, identidade, texto congelado, links e recibo no canal fixo.
3. Confirmar que secret ausente, erro ou demora do Slack produz aviso opcional
   e permite que os gates e a publicação sigam.
4. Reexecutar o mesmo evento com o estado persistente; conferir que um envio
   confirmado é reaproveitado e que `unknown` não causa reenvio automático.
5. Conferir 1/2, 2/2 e uma RC nova: os avisos apontam às decisões da mesma
   candidata e nunca transportam avais da RC anterior.

## Limites e adaptação para a Amulets

A política de membros Israel + bot é deliberadamente restrita ao laboratório.
Para a Amulets, acordar com Samuel o canal, o app, as contas, as permissões e
os papéis antes de adaptar a validação de destino. A proposta usa Samuel **E**
Vinícius para os avais e Samuel **OU** Vinícius para o comando final. Um aviso
no Slack não comprova distribuição mobile, disponibilidade para testers ou
publicação em Production.

O Incoming Webhook citado no manual anterior continua sendo uma alternativa
para outros fluxos; este laboratório já utiliza o bot e `SLACK_BOT_TOKEN`.
O webhook não retorna `ts` e não é a credencial deste remetente.
[Limites oficiais do webhook](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/).

Fontes oficiais consultadas em **08/10/2026 (Fortaleza)**. Identidades e recibo
acima são evidência da execução indicada; não são uma garantia de que a
configuração nunca mudará.
