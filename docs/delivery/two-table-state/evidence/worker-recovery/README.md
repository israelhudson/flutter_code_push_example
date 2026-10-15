# Recuperação, rejeição e RC2 — 14/10/2026

## Correções implementadas

[PR #57](https://github.com/israelhudson/flutter_code_push_example/pull/57), integrado na main em `eddbd06aee7ceea91e64352d8fe1f0461f72e79e`:

1. Validação da origem v2 reconhece CI de push na main ou na branch exata da release. O workflow de contratos passou a executar também em push na main. Legado mantém slack-main.
2. Reserva expirada em working volta à fila; antes de delivery_begin nenhum efeito externo foi iniciado. Depois de effect, Slack/dispatch ficam uncertain e exigem reconciliação. Histórico pode ser refeito porque compara bytes em caminho imutável.
3. Repetir a mesma negação pela conta/papel/DM originais confirma a decisão sem incrementar revisão ou enfileirar outro evento. Outra pessoa/papel continua recusada.

A migration `20261015014626_recover_delivery_before_effect.sql` foi aplicada somente no Supabase exclusivo após backup das duas funções afetadas. Nenhuma tabela nova. Publicação permaneceu false no GitHub e no backend, e os controles de ensaio usam scope none.

## Validação

- 55 testes Deno, com SQL real PGlite, e 33 testes Python passaram.
- [CI do PR: contratos](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38667629846), [Flutter e demais contratos](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38667629856).
- [Push da main](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38667812318) passou. checked_source executado contra esse mesmo SHA aprovou, sem criar refs.
- Negação real por Computer Use: controle delivery-b1db80bb8a0e4d97b273c566b4561b8b, versão fictícia 99.0.5 RC1, revisão1/status rejected. Repetição assinada de transporte retornou HTTP200 e manteve revisão1. Aceite posterior retornou HTTP503 sem alterar estado. Os callbacks assinados produzidos pelo script são testes de transporte, não decisões humanas.
- RC2 delivery-19e1ba7f70c648c980c9241d4a1551ac: anterior=RC1 rejeitada, revisão0, status pending e aceites nulos. Novo manifesto e mensagens; nada herdado.

## Preparação dos testes de interrupção

O ensaio registra controles via RPC e manifestos GitHub explicitamente validation_only. Não é um preparo completo de release, não corrige o app nem cria tags/Release/preview/patch. As interrupções são injetadas reservando tarefas reais e envelhecendo somente as leases da fixture. Não se apresenta isso como queda espontânea de runner.

Na RC2, o histórico e o cartão do canal foram reservados antes do envio; o envio técnico entrou em effect controladamente, sem chamar Slack. Assim é possível confirmar que o worker recupera os primeiros e não repete o efeito incerto. O roteiro privado registrou também um erro inicial de ordem na reserva da fixture: ao expirar o histórico cedo demais, delivery_take o recuperou imediatamente. Corrigido o roteiro; isso não foi falha do worker.

Duas rodadas preliminares 99.0.3 e 99.0.4 receberam os dois aceites antes do teste de negação; foram encerradas por cancelamento. Após Israel confirmar que deixaria os cliques ao agente, a rodada99.0.5 comprovou a rejeição. Não contar as rodadas preliminares como rejeições.

## Evidências privadas

`/Users/israelhudson/Documents/Codex/2026-10-14/worker-recovery-rc2/` contém snapshots completos, backup das funções, logs de Actions, roteiro de ensaio e prints. Não publicar payloads, credenciais ou screenshots com a barra lateral privada no repositório público.

## Limites para a Amulets

Continuam necessários: duas contas reais, responsáveis e regras humanas de revisão, preparo completo com preview e publicação idempotente quando autorizados, e procedimento de reconciliação para resultados incertos. O formulário de ensaio ainda exibe link de Release inexistente quando o controle foi inserido só para testar worker; aprimorar sua identificação visual antes de demonstração desse caso.

## Recuperação agendada versus manual

O workflow estava ativo na branch padrão main e a flag habilitada. Entre01:50 e01:56UTC não apareceu execução com event=schedule. O teste continua sem prova do cron; isso não significa que a fila tenha perdido dados. A documentação do GitHub informa que execuções agendadas podem atrasar: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule. O fallback manual foi disparado na main em [38668295362](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38668295362).

## Resultado da recuperação e dos aceites

[Fallback manual38668295362](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38668295362) concluiu com sucesso: histórico revision0 com recibo GitHub confirmado, mensagem de canal enviada, envio técnico permaneceu uncertain com attempts1/sem recibo. Nenhum reenvio cego ocorreu.

Somente a tarefa técnica da fixture foi reconciliada pelo operador, pois o roteiro chamou delivery_begin sem chamar Slack (prova controlada de ausência de efeito). O [worker38668362877](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38668362877) enviou a DM técnica. Isso não comprova reconciliação genérica de resposta perdida em um envio real.

Na RC2, o agente clicou primeiro em Aceite de negócio pela UI: revisão1/status pending. Depois clicou Aceite técnico: revisão2/status approved. Repetição assinada do aceite de negócio retornou HTTP200 e manteve revisão2. [Worker38668383851](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38668383851) e [worker38668428543](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38668428543) confirmaram histórico e atualização das mensagens. As três revisões usam o mesmo ts por mensagem; não criaram outro cartão a cada aceite.

O GitHub cancelou execuções pendentes substituídas por outro despertar devido ao grupo de concorrência; a fila persistente foi drenada pela execução seguinte. Não interpretar esses cancelamentos como perda de decisão.

## Encerramento confirmado

[Worker38668486223](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38668486223) cancelou a RC2, gravou o evento final e retirou seus botões. RC1 permaneceu rejeitada. Nenhum controle ativo; todas as operações confirmadas; nenhuma operação dispatch; publication_run nulo. Exatamente delivery_control/delivery_outbox no schema público. Controles terminais são preservados para bloquear callbacks antigos; não há nova tabela de histórico.

A flag DELIVERY_V2_ENABLED no GitHub voltou a false ao final. Preparos/cron pausados, publicação bloqueada. O cron não teve execução observada nesta rodada e continua pendente de validação remota; o fallback manual e o despertar por callbacks foram comprovados. Não declarar o agendamento aprovado por inferência.
