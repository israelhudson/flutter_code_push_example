# Bots, projetos e canais

**Um app Slack por projeto.** O bot **Amulets Deploy** atende a Amulets; o
**Flutter POC Deploy** atende este repositório, incluindo LAB, Issue e Slack POC.
Os nomes foram organizados em 13/10/2026 (Fortaleza). O código desta migração
precisa passar pelo PR e pela revisão obrigatória da `main` antes de valer para
novas candidatas LAB/Issue. Renomear o app ou cadastrar o secret não ativa esse
código sozinho.

## Mapa de destino

| Projeto | App / usuário do bot | Canal | Receptor das interações |
|---|---|---|---|
| Amulets | **Amulets Deploy**, antes Flutter Deploy LAB; `A0C750DS05D` / `U0C750FTCS3` | `app-deploy`, `C0C5DCFU5HU` | `https://uvfwvplcziehxrkidrxh.supabase.co/functions/v1/slack-approvals` |
| Amulets — testes | **Amulets Deploy**, mesmo app e bot da linha anterior | **`app-deploy-test-amulets`, `C0C8ULVNEBD`**; canal privado criado e bot convidado, roteamento dos novos testes ainda pendente | Mesmo receptor da Amulets; mudar destino de canal não exige trocar a Request URL. |
| `israelhudson/flutter_code_push_example` | **Flutter POC Deploy**, antes Flutter Deploy POC Slack; `A0C8J5ZC9JT` / `U0C8XJ5S0Q6` | `app-deploy-test-isr`, `C0C8DUJB52L` | `https://xtvueqciogzkyjkkqxcx.supabase.co/functions/v1/poc-slack-approvals` |

Workspace: **Amulets**, `T09CYB7AS77`. Israel: `U0BMFQKC001`.
Os IDs, canais e URLs não mudaram com os nomes. O bot da Amulets pode continuar
aparecendo no canal `app-deploy-test-isr` durante a transição. Além dos registros
históricos LAB/Issue, o fluxo **main-test da Amulets** ainda envia a esse canal.
Sua migração para `app-deploy-test-amulets` precisa ser configurada e validada
antes de retirar o bot antigo de `app-deploy-test-isr`. A separação final dos
destinos ainda não está concluída; o receptor da POC já é independente.

O canal novo de teste Amulets tem apenas Israel e Amulets Deploy, conforme a
verificação da criação. O canal da equipe `app-deploy` permanece intacto.

A auditoria somente leitura do backend Amulets confirmou que os cartões Mobile
exigem uma correção coordenada: o registro e uma constraint do banco ainda
fixam o canal antigo; o atualizador do cartão, o modal de ajuste e os avisos
DM/thread também contêm validações desse destino. Trocar só o canal de uma
Action não cobre esses caminhos. As candidatas antigas precisam continuar
vinculadas ao canal e à mensagem originais. Essa migração do backend não faz
parte da alteração LAB/Issue deste PR; nenhuma função ou tabela Amulets foi
modificada nesta auditoria.

A Request URL é configurada por app. Separar somente os canais não isolaria as
interações. A POC usa seu próprio projeto Supabase `xtvueqciogzkyjkkqxcx` e
`POC_SHARED_APP_ROUTING=false`. O `poc-slack-router` antigo não participa deste
arranjo. **Não alterar a Request URL, os secrets ou o backend da Amulets.**

## Onde cada decisão acontece

| Fluxo deste repositório | Bot dos novos avisos | Decisão e publicação |
|---|---|---|
| **LAB ·** | Flutter POC Deploy | Israel e Fabrícia aprovam no GitHub; 2/2 apenas habilita o comando final separado. |
| **Issue ·** | Flutter POC Deploy | Israel aprova na Issue; `/publicar` é outro comando. |
| **Slack -** | Flutter POC Deploy | Cartão exclusivo da POC e estado privado no Supabase. Ensaio solo de Israel em dois papéis; escopo e controles continuam obrigatórios. |

Novos avisos LAB e Issue oferecem links de texto para preview, changelog, Issue
ou execução. Não usam botões interativos direcionados ao receptor Slack POC.
Assim os avisos não exigem ensinar esse receptor a aprovar LAB/Issue nem mudar
seus gates. O backend de cartões Slack POC continua separado dos avisos de
GitHub Actions.

## Credenciais

| Local | Nome | Uso |
|---|---|---|
| Actions deste repositório | `POC_SLACK_BOT_TOKEN` | Token de Flutter POC Deploy. Cadastrado em 13/10/2026, 21:23:34 Fortaleza; novos avisos LAB/Issue usam este secret. |
| Actions deste repositório | `SLACK_BOT_TOKEN` | Mantido temporariamente com o token antigo para registros e ferramentas históricas. Não substituir pelo token novo. |
| Supabase exclusivo da POC | `POC_SLACK_BOT_TOKEN`, `POC_SLACK_SIGNING_SECRET` e identidades `POC_SLACK_*` | App Flutter POC Deploy; cartões e autenticação das interações. |
| Projeto Amulets | Credenciais já existentes | Continuam pertencendo à Amulets; esta migração não as modifica. |

Nenhum token deve ir para código, chat, prints, logs ou artefatos. Conferir o nome
do secret e a identidade por `auth.test` sem exibir seu valor. Os workflows
passam os dois tokens apenas às etapas de aviso; o registro congelado escolhe
o token correto. Não há fallback para o bot antigo quando falta o token novo.

## Como a migração preserva as candidatas

Um corte novo grava **`notification_profile: poc-v1`** antes dos efeitos de
preparação. Esse perfil fica ligado ao registro e ao relatório/plano congelado.
Registros históricos sem o campo continuam no perfil `legacy`; uma preparação
parcial mantém o perfil original. Uma candidata não troca de bot por mudança de
variável ou por reexecução. Perfil desconhecido ou divergente bloqueia o aviso.

O journal LAB novo é `release-lab/slack-outbox-poc.json`; o histórico continua em
`release-lab/slack-outbox.json`. A separação evita reinterpretar os payloads ou
recibos anteriores. As notificações Issue mantêm a identidade do perfil no seu
estado. Recibo de envio não é aprovação nem autorização de publicação.

Os jobs LAB usam o `tooling_sha` congelado. Ferramentas antigas continuam com seu
contrato antigo e não passam a entender o novo token por receber um secret.
Não editar `tooling_sha`, relatório, digest, avais, tags ou registro antigo para
forçar a migração. Correções para uma release branch antiga precisam entrar por
PR conforme o fluxo já existente antes de criar uma nova RC.

## Sequência de ativação

1. Conferir os nomes, IDs e URLs do mapa. O app POC deve ser membro de
   `app-deploy-test-isr`; Amulets Deploy deve participar de
   `app-deploy-test-amulets`. Manter o canal da equipe `app-deploy` intacto.
2. Cadastrar `POC_SLACK_BOT_TOKEN` neste repositório e preservar o secret antigo.
   Esta configuração já foi aplicada; falta integrar e validar o código do PR.
3. Revisar o PR: contratos locais, validação dos workflows e CI precisam passar.
   A revisão humana e o merge protegido da `main` são mantidos.
4. Criar uma candidata nova pelos workflows habituais LAB/Issue. Conferir o
   perfil `poc-v1`, o autor `U0C8XJ5S0Q6`, canal `C0C8DUJB52L`, links corretos e
   recibo `sent` com `channel`/`ts`. Conferir também uma repetição sem duplicata.
5. Confirmar que as decisões continuam nos lugares do quadro acima. O ensaio
   deve incluir aprovação incompleta, comando final separado e aviso opcional
   com erro sem interromper a entrega.
6. Migrar os avisos **main-test da Amulets** para `app-deploy-test-amulets` e
   comprovar um novo aviso ali com o bot Amulets Deploy. Esse ajuste pertence ao
   fluxo Amulets e não é produzido pelo merge deste PR na POC.
7. Inventariar candidatas históricas, cortes parciais, publicações parciais e
   avisos pendentes/incertos. Somente após encerrar essas dependências, incluindo
   a migração main-test da Amulets, remover o
   bot Amulets Deploy do canal de teste e retirar a credencial legada deste
   repositório. Guardar o inventário e a decisão junto das evidências.

O último passo não deve ser feito apenas porque um novo cartão funcionou.
Reexecuções com ferramentas congeladas antigas ainda podem precisar do token e
da participação antiga. Sem eles, devem falhar fechadas no aviso; não reenviar
automaticamente pelo bot novo.

## Falha, envio incerto e recuperação

- **Secret ausente, identidade ou destino errado:** manter o aviso bloqueado e
  corrigir a configuração; não usar token de outro projeto como fallback.
- **`sent`:** reaproveitar o recibo original. Não postar a mensagem novamente.
- **`unknown`:** o POST pode ter chegado ao Slack. Não limpar o journal, não
  trocar de bot e não fazer retry cego. Registrar identidade, canal, evento e
  recibos para reconciliação com prova positiva.
- **Sem `groups:history`:** o app POC tem `chat:write` e `groups:read`; enviar e
  conferir o destino não prova capacidade de ler histórico. A busca automática
  de um envio incerto pode permanecer bloqueada por falta dessa permissão.
  Não ampliar escopos ou inventar um recibo para resolver a incerteza.
- **Rollback de código:** preservar os registros `poc-v1`, os dois journals e
  suas credenciais. Um rollback não converte candidatas novas em `legacy`.
  Investigar o worker de aviso e preparar correção compatível, mantendo a
  candidata/decisão original. A disponibilidade do Slack não altera os gates.

## Provas e limites

Os logs privados de organização ficam em
`/Users/israelhudson/Documents/Codex/2026-10-13/slack-supabase-poc/bot-organization/`.
Eles registram a configuração aplicada sem credenciais. Artefatos de cada Run
guardam payload, identidade, resultado e recibos sanitizados. As jornadas antigas
documentadas em [Slack automático](SLACK-AUTOMATICO.md) são evidência do bot
histórico, não validação automática do novo remetente.

Testes locais usam dados sintéticos e não contam como cliques humanos ou envios
reais. A ativação LAB/Issue no bot novo exige a rodada posterior ao merge. Um
aviso, preview ou GitHub Release não comprova distribuição mobile.
