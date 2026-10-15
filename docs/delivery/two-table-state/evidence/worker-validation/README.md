# Concorrência e DMs — 14/10/2026

## Limites do ensaio

Somente o projeto Supabase exclusivo `xtvueqciogzkyjkkqxcx` e o bot Flutter Deploy POC Slack foram usados. O escopo do controle fictício foi `none`; a função de transporte recusou qualquer dispatch GitHub. Não foram criadas tags, Releases, previews ou patches. Flags remotas, Edge Functions e workflows não foram ativados.

## Concorrência real

Quatro cenários passaram, com chamadas SQL em processos independentes contra o PostgreSQL remoto:

- Aceite duplicado: uma revisão, sem duplicar a decisão.
- Rejeição primeiro: avaliação rejeitada e aceite posterior recusado.
- Segundo aceite primeiro: avaliação aprovada e rejeição posterior recusada.
- Dois workers: tarefas diferentes reservadas, sem dupla posse.

As chamadas de decisão sobrepostas foram mantidas concorrentes com uma transação aberta por cinco segundos. Esse ensaio não substitui teste de carga nem cobre todas as ordens possíveis de bloqueio. Os controles fictícios de concorrência foram removidos; não houve tarefa de dispatch.

## DMs e worker

O harness executa `deliveryControlHandler` do código real, contra SQL remoto e Slack real. O bot é validado por `auth.test`. A autorização do run GitHub e os recibos de histórico são **fixtures**: não constitui prova do worker em GitHub Actions, journal GitHub, cron ou webhook publicado.

Enviadas duas DMs distintas para Israel (modo solo): aceite técnico e aceite de negócio. O canal recebe acompanhamento sem botões. Prefixo visível identifica teste sem release. As mensagens apontam ao PR #53; não a uma Release inexistente.

A atualização usa `chat.update` e preserva as identidades das mensagens. Os aceites do harness são decisões sintéticas, não decisões humanas.

## Incidente de clique manual durante o ensaio

O usuário clicou nos cartões. Logs remotos registraram três `POST 403` no receptor `poc-slack-approvals`, em 22:20:06, 22:20:09 e 22:20:25, horário de Fortaleza.

Inspeção do código efetivamente publicado: versão 13, entrypoint `Deno.serve(slackHandler(runtime()))`. Esse receptor legado aceita ações `poc_*` e canal legado; não roteia `delivery_*` das DMs. Os cliques foram recusados. O código novo estava somente no harness, não na Edge Function publicada.

Lição: não apresentar cartões de ensaio como prontos para cliques manuais antes de verificar o receptor publicado. Aviso textual “não clicar” não basta como experiência de uso. Próximo teste manual requer receptor compatível e worker real preparados, com publicação bloqueada por escopo e flags, antes de enviar botões.

## O que ainda não está validado

- Clique manual assinado chegando ao handler v2 publicado.
- Despertar do workflow real e cron de recuperação.
- Persistência e verificação dos eventos reais na branch protegida de histórico.
- Concorrência de cancelamento/compactação com todas as etapas de envio.

Não considerar o fluxo pronto para ativação a partir apenas deste ensaio.

## Artefatos

`concurrency.json` contém resumo sanitizado. Logs completos, recibos Slack e prints ficam no diretório privado `Documents/Codex/2026-10-14/delivery-worker-validation`. Nenhuma credencial foi incluída no repositório. Scripts de reprodução: `verify_delivery_concurrency.py` e `verify_delivery_dm_worker.ts`, ambos em `tools/delivery`.
