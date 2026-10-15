# Cron real na main: recuperação comprovada, prazo não cumprido

Em 15/10/2026, a [execução agendada 38698226773](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38698226773)
concluiu as oito tarefas da fixture cancelada. O evento é `schedule`, a branch é
`main` e o job `drain` executou com sucesso. Não foi um disparo manual nem um job
pulado.

**A execução ocorreu depois da janela combinada.** A recuperação pelo cron está
comprovada; pontualidade, frequência de cinco minutos e encerramento automático
no prazo não estão. Worker e receptor foram pausados ao encerrar esta auditoria;
os controles de publicação continuam desligados.

## O que aconteceu

Todos os horários locais abaixo usam America/Fortaleza (UTC−03).

| Momento | Horário local | UTC | Evidência |
|---|---|---|---|
| PR #60 integrado à main | 14/10, 23:22:36 | 15/10, 02:22:36 | [PR #60](https://github.com/israelhudson/flutter_code_push_example/pull/60), commit `9aff732232421f68f75aa95d5490ca506f66c60d` |
| Início registrado da observação | 14/10, 23:22:00 | 15/10, 02:22:00 | `observation-window.json` privado |
| Fim previsto da observação | 15/10, 01:22:00 | 15/10, 04:22:00 | Mesma janela |
| Run agendado criado | 15/10, 04:21:43 | 15/10, 07:21:43 | Metadados do run |
| Run concluído | 15/10, 04:22:21 | 15/10, 07:22:21 | `success`, com recibos reais |
| Auditoria de encerramento retomada | 15/10, 09:26 | 15/10, 12:26 | Heartbeat recebido neste chat |
| Worker desabilitado no GitHub | 15/10, 09:27:16 | 15/10, 12:27:16 | `DELIVERY_V2_ENABLED=false` |
| Receptor desabilitado no Supabase exclusivo | 15/10, 09:31:46 | 15/10, 12:31:46 | Mesmo controle desligado; digest conferido |

O cron chegou aproximadamente três horas depois do fim previsto. A coleta
registrou ausência de runs às 02:38 e 02:53 UTC; não há registro suficiente para
atribuir uma causa ao intervalo seguinte. Também não há prova de que a pausa
programada ocorreu às 04:22 UTC: ela só foi aplicada na auditoria tardia. Não
atribuir isso a suspensão da máquina, erro de YAML ou carga do GitHub sem evidência.

O [ensaio anterior](../cron-validation/README.md), com outra fixture, continua
registrado como ausência de cron seguida de fallback manual. Seus resultados não
foram reescritos. Nesta observação prolongada, nenhum fallback manual foi necessário
ao encerrar: o cron já havia drenado a fila quando a auditoria foi retomada.

## O que foi comprovado

Fixture: `delivery-91fe34c52e0f4b88812943e29480239f`, versão fictícia `99.0.7`,
escopo `none`. Ela foi cancelada antes da avaliação e já possuía oito tarefas;
nenhuma fixture, tabela ou decisão adicional foi criada neste encerramento.

| Verificação | Resultado |
|---|---|
| Origem da execução | `schedule` na `main`, SHA do merge do PR #60 |
| Job do worker | `drain` executado; etapa de entrega e upload de recibos concluídos |
| Reserva de histórico expirada | Tarefa 215 recuperada na segunda tentativa, com recibo GitHub |
| Oito tarefas existentes | Duas de histórico e seis de canal/DM, todas `done` |
| Histórico permanente | Eventos 0 e 1 encontrados pelo commit imutável; bytes e SHA-256 conferem |
| Controle final | `cancelled`, revisão 1, sem aceites e `publication_run=null` |
| Fila global ao encerrar | Zero operações pendentes, zero operações de dispatch e zero controles ativos |
| Tabelas públicas da aplicação | Somente `delivery_control` e `delivery_outbox` |
| Publicação | Nenhum disparo, tag, Release, preview ou patch produzido por este ensaio |
| Compactação neste run | `removed=0`; não valida uma remoção por retenção |

Os eventos 0 (`pending`) e 1 (`cancelled`) são o histórico da criação e do
cancelamento, respectivamente. A gravação tardia do evento inicial não reabriu
a avaliação: o controle atual permaneceu cancelado. Recibos de canal/DM comprovam
operações confirmadas pelo worker, não leitura das mensagens por pessoas.

## Evidências que ficam no GitHub

- [Run e logs](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38698226773): evento, branch, SHA, steps e artefato `delivery-worker-receipts` (retenção de 90 dias no workflow).
- [Evento 0](https://github.com/israelhudson/flutter_code_push_example/blob/4f1e8291f41b9cedd8f073af9e21bd3e4d866a16/candidates/delivery-91fe34c52e0f4b88812943e29480239f/event-0.json) e [evento 1](https://github.com/israelhudson/flutter_code_push_example/blob/70a77d105b4afddeb6668fda60f269207e7bbb5c/candidates/delivery-91fe34c52e0f4b88812943e29480239f/event-1.json), por commit imutável.
- [Resumo verificável](result.json): identidades do run, horários, oito operações e estado final, sem IDs de DMs nem conteúdo de credenciais.
- [Digests dos prints privados](screenshots.json): integração do PR #60, habilitação inicial, sucesso agendado e worker pausado.

Os logs completos, metadados, artefatos baixados, snapshots do banco e prints
estão preservados em
`/Users/israelhudson/Documents/Codex/2026-10-14/cron-extended/`.
Dados de mensagens/DMs e o snapshot bruto do banco não foram copiados para este
repositório público.

## Encerramento e lições para a Amulets

`DELIVERY_V2_ENABLED=false` foi confirmado no GitHub e no Supabase
`xtvueqciogzkyjkkqxcx`. `POC_SLACK_PUBLISH_ENABLED`, `POC_SLACK_ENABLED`,
`POC_LEGACY_ENABLED` e `POC_PUBLICATION_ENABLED` continuam `false` nos seus
respectivos serviços. O acompanhamento deste ensaio foi encerrado. Amulets,
tags, aceites e outros fluxos foram preservados.

1. **Prazo de ensaio precisa de encerramento confiável.** Um acompanhamento local
   não deve ser a única proteção de uma janela estrita. Antes de repetir uma
   janela com corte obrigatório, definir e testar o bloqueio de prazo na camada
   de execução/receptor e a recuperação de um encerramento perdido. Esta rodada
   apenas registra a lacuna; não adiciona scheduler, tabela ou implementação.
2. **Cron é recuperação, não promessa de latência.** Esta prova confirma uma
   execução real e a retomada de trabalho reservado. Não comprova processamento
   a cada cinco minutos nem explica por que a execução veio tarde. O despertar
   por callback e a reconciliação continuam necessários.
3. **Recibo e estado importam mais que um run verde.** Exigir evento `schedule`,
   job executado, recibos do histórico e fila drenada; um run manual ou pulado
   não substitui essa evidência.
4. **Preservar os limites do ensaio.** Não houve publicação nem nova rodada de
   release. Continuam pendentes a restauração das revisões humanas acordadas,
   teste com pessoas distintas e validações de publicação/distribuição antes da
   adoção na Amulets.
