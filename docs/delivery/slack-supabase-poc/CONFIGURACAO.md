# Ativar a POC Slack — guia de Israel

O código começa desligado. LAB e Issue continuam com suas regras. Fabrícia não
participa desta alternativa: Israel representa os papéis técnico e de negócio,
identificados no cartão como **ensaio solo**, não como duas pessoas independentes.

## 1. Instalar os workflows

O PR inicial tem base `main` e respeita a revisão já exigida pelo repositório.
Não remover essa regra. Depois de integrar esse PR, criar `slack-main` a partir da
main que contém os workflows. Novas features entram por PR em `slack-main`.
Correções de uma candidata entram por PR em `poc-release/1.0.0`, por exemplo.

Aplicar somente as regras novas:

```bash
python3 tools/delivery/configure_poc_slack.py --output build/poc-rulesets
# Conferir o JSON antes de aplicar.
python3 tools/delivery/configure_poc_slack.py --output build/poc-rulesets --apply
```

`Slack - PRs solo` exige `Slack / Verificar contratos` e zero reviews humanos.
`Slack - tags imutaveis` impede mover/apagar tags `poc-*`. Não altera os rulesets
LAB/Issue. As regras novas não autorizam merge sem checks.

## 2. Projeto Supabase exclusivo

Criado com autorização de Israel: **flutter-code-push-poc**, organização
**iHud Tecnologia**, região São Paulo, ref **xtvueqciogzkyjkkqxcx**.
Plano Free, sem upgrade solicitado. O plano gratuito pode pausar por inatividade.
[Preço e limites oficiais](https://supabase.com/pricing).

URL: `https://xtvueqciogzkyjkkqxcx.supabase.co`.
Aplicar a migration em `supabase/migrations/` e publicar apenas as funções
`poc-control` e `poc-slack-approvals` neste projeto. O router histórico não é
usado pelo app exclusivo. Nunca publicar estas funções no projeto Mobile.
As funções usam autenticação própria: bearer por operação ou assinatura
Slack HMAC. Por isso o verificador JWT do gateway está desligado, não a autenticação.
Nenhuma tabela permite acesso de `anon`/`authenticated`. As RPCs são exclusivas
da credencial de servidor. Não colocar service role no GitHub nem no navegador.

## 3. App exclusivo Flutter POC Deploy

A decisão final foi **um app por projeto**, preservando a Amulets. Usar o app
**Flutter POC Deploy** (`A0C8J5ZC9JT`, bot `U0C8XJ5S0Q6`) somente no canal
`app-deploy-test-isr` (`C0C8DUJB52L`). O nome anterior deste app era
Flutter Deploy POC Slack. O app antigo foi renomeado para Amulets Deploy.

A Request URL do app exclusivo é
`https://xtvueqciogzkyjkkqxcx.supabase.co/functions/v1/poc-slack-approvals`.
Manter **`POC_SHARED_APP_ROUTING=false`**. O `poc-slack-router` foi uma alternativa
anterior; não é a entrada dos cartões nesta organização. A Request URL do app
Amulets permanece
`https://uvfwvplcziehxrkidrxh.supabase.co/functions/v1/slack-approvals`.

O app POC já está instalado com `chat:write` e `groups:read`. A DM/App Home usa
`chat.postMessage` com ID do usuário e guarda o ID D retornado.
[Documentação oficial](https://docs.slack.dev/reference/methods/chat.postMessage/).
Não presumir leitura de histórico: `groups:history` não foi adicionado.

LAB e Issue também migram os **novos** avisos para o app exclusivo, via secret
`POC_SLACK_BOT_TOKEN` no GitHub. A migração foi concluída: o bot Amulets saiu do canal POC e os cartões antigos
ficaram como histórico. Consultar o [inventário e manual dos bots](../BOTS-POR-PROJETO.md).

| Secret no Supabase | Origem |
|---|---|
| `POC_SLACK_APP_ID` | Basic Information, App ID do app escolhido |
| `POC_SLACK_SIGNING_SECRET` | Basic Information, Signing Secret |
| `POC_SLACK_BOT_TOKEN` | OAuth, Bot User OAuth Token do app escolhido |
| `POC_SLACK_BOT_USER_ID` | ID retornado por `auth.test` do token escolhido |
| `POC_REGISTRATION_SECRET` | Aleatório próprio, igual ao secret novo do GitHub |
| `POC_PUBLICATION_SECRET` | Outro aleatório próprio, igual ao secret novo do GitHub |
| `POC_GITHUB_DISPATCH_TOKEN` | Opcional; fine-grained PAT restrito a este repo, Actions write e Contents read, para disparo após 2/2 e consultas autenticadas |
| `POC_SHARED_APP_ROUTING` | `false`, app exclusivo sem encaminhamento |
| `POC_SOURCE_BRANCH` | `slack-main` |
| `POC_ENABLED` | `false` durante configuração; `true` para ensaio |
| `POC_PUBLICATION_ENABLED` | `false` até autorizar prerelease de teste |

Para uma instalação nova, os flags começam desligados. Para coletar os dados
do app exclusivo sem colocá-los no chat, usar o terminal local:

```bash
python3 tools/delivery/configure_poc_slack_app.py
```

O script verifica workspace, scopes e membros do canal antes de gravar os secrets;
as entradas sensíveis ficam ocultas e em arquivo privado fora do repositório.
Ele não manda mensagem e não ativa a publicação.
Não reexecutar a instalação sobre uma POC ativa sem revisar os flags: os valores
iniciais não representam necessariamente a configuração atual.

O token de dispatch é opcional: sem ele, após 2/2 Israel executa manualmente
`Slack - Publicar teste aprovado` com o ID da candidata. A decisão humana é a
aprovação dos papéis; permissões de publicação são verificadas separadamente.
Não configurar PAT de Amulets ou credencial Shorebird nesta etapa.

## 4. GitHub: secrets e variáveis novos

| Tipo | Nome | Valor |
|---|---|---|
| Secret | `POC_REGISTRATION_SECRET` | Mesmo aleatório do backend |
| Secret | `POC_PUBLICATION_SECRET` | Mesmo segundo aleatório do backend |
| Secret | `POC_SLACK_BOT_TOKEN` | Token do app exclusivo, para novos avisos LAB/Issue |
| Variable | `POC_SHARED_APP_ROUTING` | `false`, app exclusivo sem encaminhamento |
| Variable | `POC_SOURCE_BRANCH` | `slack-main` |
| Variable | `POC_SUPABASE_URL` | URL do projeto exclusivo |
| Variable | `POC_SLACK_ENABLED` | `false` inicialmente |
| Variable | `POC_PR_PREVIEW_ENABLED` | `false` inicialmente |
| Variable | `POC_SLACK_PUBLISH_ENABLED` | `false` inicialmente |

`SLACK_BOT_TOKEN` legado foi removido da POC após encerrar as dependências históricas.
Não recriá-lo nem usar credencial Amulets como fallback. O novo secret de
Actions `POC_SLACK_BOT_TOKEN` atende os avisos LAB/Issue com perfil `poc-v1`.
Secrets de publicação, gates e variáveis dos fluxos existentes permanecem separados.
Primeiro ativar backend `POC_ENABLED`, tabela `poc_config.enabled` e os dois
flags GitHub de preparação/preview. A publicação continua desligada.
Para publicar TESTE, ativar **as três permissões**: tabela
`publication_enabled`, backend `POC_PUBLICATION_ENABLED` e GitHub
`POC_SLACK_PUBLISH_ENABLED`, além do flag geral. A candidata precisa ter sido
criada com escopo `github_test`; uma candidata `none` nunca recebe upgrade.

## 5. Percorrer a entrega

1. Fazer PR de feature para `slack-main`; conferir preview e check.
2. Merge; executar **Slack - Preparar candidata** na branch `slack-main`, com
   versão e título legíveis. Começar com escopo `none`.
3. A RC recebe tag `poc-v1.0.0-rc.1`, SHA congelado, preview próprio e changelog.
   O preview de PR pode ter outro SHA; não reaproveitar o link sem prova dos bytes.
4. No cartão, Israel dá aceite técnico e depois de negócio (ou ordem inversa).
   Em 1/2, a DM vai ao papel faltante; no modo solo, ambos pertencem a Israel.
5. Em 2/2, o criador recebe DM. Com escopo `none`, nenhuma tag final/Release é criada.
6. Testar ajuste: informar motivo no modal. A RC fica bloqueada. Corrigir por PR
   em `poc-release/1.0.0`; após merge, preparar novamente a mesma versão.
   Nasce `poc-v1.0.0-rc.2`, outro cartão e zero aceites. Preservar RC1.
7. Em novo ensaio explicitamente habilitado para `github_test`, 2/2 permite uma
   prerelease **TESTE** `poc-v1.0.0`, no mesmo SHA da RC aprovada. Não distribui app.

## 6. Recuperação e rollback

Resposta incerta de Slack/dispatch não recebe retry automático: consultar
`poc_private_notices`, recibos e o destino antes de decidir. Uma execução parcialmente
publicada só é recuperada por **Re-run jobs na mesma execução GitHub**; um novo
Run não toma sua intenção. Se já publicada, repetir consulta retorna o recibo
sem criar tag/Release de novo. Falha no aviso posterior não desfaz um aceite salvo.

Para parar: desligar flags GitHub, backend e `poc_config.enabled`. Preservar
histórico, tags, cartões e recibos. Não apagar o projeto como rollback de entrega.

**Limite do ensaio:** se o projeto Free pausar por inatividade, os cartões da
POC podem parar de responder. O receptor Amulets continua independente; não
trocar sua URL para contornar uma falha da POC. Definir com Samuel
disponibilidade, monitoramento e hospedagem antes da adoção na Amulets.
