# Bots Slack — inventário e manual de operação

**Um app por projeto; canais separados para POC e Amulets.**
Estado documentado: encerramento da migração em 13/10/2026 (Fortaleza).
Base: recibos de execução e inventário final, não uma nova auditoria online.

## 1. Identificar o bot certo

| Projeto | App e usuário do bot | Canal |
|---|---|---|
| POC `israelhudson/flutter_code_push_example` — LAB, Issue e Slack | **Flutter POC Deploy**, app `A0C8J5ZC9JT`, usuário `U0C8XJ5S0Q6` | **app-deploy-test-isr**, `C0C8DUJB52L` |
| Amulets — testes | **Amulets Deploy**, app `A0C750DS05D`, usuário `U0C750FTCS3` | **app-deploy-test-amulets**, `C0C8ULVNEBD` |
| Amulets — equipe | Mesmo app Amulets Deploy | **app-deploy**, `C0C5DCFU5HU` |

Workspace: **Amulets**, `T09CYB7AS77`. Israel: `U0BMFQKC001`.
O app POC pode aparecer com o nome anterior **Flutter Deploy POC Slack**;
Amulets Deploy se chamava **Flutter Deploy LAB**. Confirmar os IDs evita confundir
um nome em cache com outro app. Dois canais não equivalem a dois bots: a
separação inclui app, token, Signing Secret e receptor.

[Canal POC](https://app.slack.com/client/T09CYB7AS77/C0C8DUJB52L) ·
[Canal de testes Amulets](https://app.slack.com/client/T09CYB7AS77/C0C8ULVNEBD)

## 2. Receptores e isolamento

| App | Request URL das interações | Projeto Supabase |
|---|---|---|
| Flutter POC Deploy | `https://xtvueqciogzkyjkkqxcx.supabase.co/functions/v1/poc-slack-approvals` | `xtvueqciogzkyjkkqxcx` |
| Amulets Deploy | `https://uvfwvplcziehxrkidrxh.supabase.co/functions/v1/slack-approvals` | `uvfwvplcziehxrkidrxh` |

POC: `POC_SHARED_APP_ROUTING=false`. O antigo `poc-slack-router` não é a entrada
ativa. Não direcionar o app Amulets ao receptor POC para resolver uma falha.
A Request URL é por app; alterá-la afeta todos os seus cartões interativos.
A indisponibilidade do backend POC não deve redirecionar decisões ao backend
Amulets. O workspace e o Slack continuam sendo dependências compartilhadas.

## 3. O que chamamos de cartão

É uma **mensagem estruturada no Slack**: versão, estado, resumo, preview e links.
Alguns cartões têm botões que registram decisões; outros só apontam ao GitHub.
Não é uma Issue nem a Release em si. Receber a mensagem não significa aprovar
ou publicar. O recibo de envio identifica `channel` e `ts` da mensagem.

| Fluxo POC | Onde aprovar | O que publica |
|---|---|---|
| LAB | GitHub, Israel e Fabrícia | Depois dos dois avais, comando final separado no GitHub |
| Issue | Comentário na Issue | `/publicar` separado da aprovação |
| Slack | Botões **Aceite técnico** e **Aceite de negócio** do bot POC | Com 2/2, escopo `github_test` e controles ativos, o backend pode disparar a publicação; sem token de dispatch, usar o workflow manual |

LAB/Issue enviam avisos e links pelo bot POC, sem transferir suas decisões ao
receptor Slack. No ensaio Slack, Israel exerce ambos os papéis; **não representa
duas pessoas independentes**. Fabrícia não precisa de Slack para LAB/Issue.
O fluxo Slack não herda o comando `/publicar` da alternativa Issue.

## 4. Credenciais e controles

| Local | Nome | Responsabilidade |
|---|---|---|
| GitHub POC | `POC_SLACK_BOT_TOKEN` | Avisos novos LAB/Issue pelo bot POC |
| Supabase POC | `POC_SLACK_BOT_TOKEN` | Criar/atualizar cartões e avisos Slack POC |
| Supabase POC | `POC_SLACK_SIGNING_SECRET` | Verificar assinatura Slack sobre o corpo original |
| Supabase POC | `POC_SLACK_APP_ID`, `POC_SLACK_BOT_USER_ID` | Identidade esperada do app/bot |
| GitHub e backend POC | `POC_REGISTRATION_SECRET` | Autenticação da preparação |
| GitHub e backend POC | `POC_PUBLICATION_SECRET` | Autenticação da publicação |
| Supabase POC | `POC_GITHUB_DISPATCH_TOKEN` | Disparo opcional do workflow após aceites válidos |
| Amulets | Credenciais próprias existentes | Continuam no projeto Amulets |

**`SLACK_BOT_TOKEN` legado foi removido do repositório POC.** O token Amulets não
foi revogado; ainda atende seu projeto. Não restaurar esse secret como fallback.
Os valores nunca devem aparecer em código, prints, chat ou logs.

Preparação: flags gerais GitHub `POC_SLACK_ENABLED`, backend `POC_ENABLED` e
`tabela poc_config.enabled`; branch `POC_SOURCE_BRANCH=slack-main`.
Publicação exige, além disso, **três controles**: GitHub
`POC_SLACK_PUBLISH_ENABLED`, backend `POC_PUBLICATION_ENABLED` e
`poc_config.publication_enabled`. A candidata deve nascer com `github_test`.
Não promover o escopo congelado `none` de uma candidata existente.
Flags são mutáveis: consultar o estado antes de cada rodada; este documento não
é prova de que continuam ligados.

Escopos do bot POC: `chat:write` e `groups:read`. Não possui `groups:history`.
Enviar mensagens e consultar membros não prova capacidade de ler o histórico.
Não ampliar permissões automaticamente para contornar uma falha.

## 5. Roteiro Slack para 1.14.0 / RC2

1. Conferir se a RC2 já existe e se há cartão ativo. Nesse caso, continuar nele;
   não preparar outra candidata apenas para recuperar seu link.
2. Se RC1 está em ajuste, integrar a correção por PR na release branch
   `poc-release/1.14.0`, conforme o corte existente. Preservar RC1 e seus recibos.
3. Abrir [Slack - Preparar candidata](https://github.com/israelhudson/flutter_code_push_example/actions/workflows/poc-slack-prepare.yml).
   Selecionar **slack-main**, versão **1.14.0** (sem RC), título da alteração e
   escopo **github_test**. O sistema determina a próxima RC; não digitar RC2 na versão.
4. Aguardar checks, preview e changelog da candidata. No canal POC, confirmar
   autor POC, tag esperada `poc-v1.14.0-rc.2`, código e escopo antes de aprovar.
5. Israel registra **Aceite técnico** e **Aceite de negócio**. Um aceite mantém
   a publicação bloqueada; ajuste bloqueia a candidata e a próxima RC começa sem avais.
6. Após 2/2, acompanhar o dispatch. Sem token configurado, executar
   [Slack - Publicar teste aprovado](https://github.com/israelhudson/flutter_code_push_example/actions/workflows/poc-slack-publish.yml)
   na branch `slack-main`, usando o ID exato da candidata. Se o dispatch ficar
   incerto, reconciliar antes de iniciar outro Run.
7. Confirmar Run, recibo e prerelease **TESTE** `poc-v1.14.0`, no SHA da RC.
   Isso não distribui aplicativo, patch Shorebird ou versão de loja.

Este roteiro não afirma que RC2 existe ou que foi publicada: consultar o estado
real antes de iniciá-lo. Mais detalhes em [Configuração](slack-supabase-poc/CONFIGURACAO.md).

## 6. Encerramento dos cartões antigos

A migração foi concluída, não está aguardando retirada do bot:

- Novos LAB/Issue usam `notification_profile: poc-v1` e bot POC.
- Main-test e cartões novos Amulets foram direcionados ao canal Amulets de testes.
- Ensaios LAB/Issue pendentes foram encerrados; não houve publicação nesses testes.
- Três cartões interativos antigos receberam rótulo **HISTÓRICO — ENSAIO ENCERRADO**,
  preservando mensagem/timestamp e texto, com botões de decisão retirados.
- Receptor Amulets verifica assinatura e bloqueia callbacks do canal POC retirado
  antes de decisões no banco, atualização da mensagem ou dispatch; inclui modais antigos.
- Amulets Deploy foi removido somente do canal POC. Instalação e credenciais
  Amulets continuam intactas. O inventário final confirma apenas o bot POC nesse canal.

Tags, votos, registros e recibos anteriores permanecem. O journal LAB novo é
`release-lab/slack-outbox-poc.json`; o legado é `release-lab/slack-outbox.json`.
Não reescrever `tooling_sha`, digests ou perfil de uma candidata para forçar outro bot.
Ferramentas congeladas antigas podem falhar no aviso sem a credencial legada;
isso é bloqueio deliberado. Cartão histórico não é ponto de retomada de entrega.

## 7. Evidências e limites

| Verificação | Evidência / resultado |
|---|---|
| LAB, envio pelo bot POC | [Cartão](https://amuletsworkspace.slack.com/archives/C0C8DUJB52L/p1791939197944389); [Run 38492251489](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38492251489), cancelado intencionalmente antes dos avais |
| Issue, envio pelo bot POC | [Cartão](https://amuletsworkspace.slack.com/archives/C0C8DUJB52L/p1791939140598999); [Issue 37](https://github.com/israelhudson/flutter_code_push_example/issues/37), rejeitada e encerrada |
| Repetição LAB após retirada | [Run 38492813433](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38492813433), sucesso sem duplicação |
| Novo cartão Amulets | [Mensagem no canal novo](https://amuletsworkspace.slack.com/archives/C0C8ULVNEBD/p1791938642302169), ensaio sem publicação |
| Migração POC | [PR 36](https://github.com/israelhudson/flutter_code_push_example/pull/36), integrado |
| Proteção dos cartões aposentados | [Backend PR 2](https://github.com/amuletslabs/amulets-release-lab/pull/2), integrado e implantado; 38 testes locais e CI |

Logs privados: `/Users/israelhudson/Documents/Codex/2026-10-13/slack-supabase-poc/bot-retirement/`.
Arquivos principais: `LEIA-ME.md`, `membership-after.json`, `poc-only-bot.png`,
`archived-cards.json`, `stale-modal-blocked.json`, `lab-after-removal.log`,
`issue-repeat.log` e `lab-final-jobs.json`.
Preparação e ativação anteriores: diretório irmão `bot-organization/`.
Esses caminhos são locais; não estarão disponíveis a quem clonar o repositório.

O teste remoto de modal antigo foi **sintético e assinado**, não clique humano.
O download agregado do LAB encontrou um job cancelado sem log; estados dos jobs
foram preservados e logs dos workers guardados separadamente. Nenhum desses
ensaios comprova publicação mobile. Não copiar histórico privado inteiro para
um repositório público; compartilhar somente evidência sanitizada necessária.

## 8. Manutenção e recuperação

- Antes de trocar token: conferir `auth.test`, app, workspace, usuário e canal;
  atualizar somente os consumidores do projeto correspondente e testar envio e interação.
- Antes de mudar Request URL: inventariar cartões ativos e modais abertos;
  testar o receptor e manter um plano de retorno ao receptor do mesmo projeto.
- Aviso `sent`: reutilizar recibo, sem novo envio. `unknown`/`uncertain`: conferir
  Slack, journal e Run antes de repetir; não apagar reserva para forçar retry.
- Botão sem resposta: conferir app, canal, assinatura, receptor e estado da RC.
  Uma falha de aviso não apaga automaticamente um aceite já salvo.
- Publicação parcial: seguir recuperação na mesma execução descrita no manual;
  não criar outro Run para assumir uma intenção em andamento.
- Para conter incidente POC: desligar preparação/publicação pelos controles POC,
  preservar registros e corrigir o próprio receptor. Não tocar nos secrets Amulets.
- Antes de remover outro bot: zerar dependências ativas, arquivar controles antigos,
  validar novo envio e repetição, remover, validar novamente e guardar os recibos.

Responsável operacional desta POC: Israel. Definir com Samuel os responsáveis,
aprovadores, rotação de credenciais, disponibilidade e retenção antes de transportar
esse modelo para a esteira oficial Amulets.
