# Validação do cron na main — 14/10/2026

O PR#58 foi integrado à main em14/10/2026 às23:01:29−03, commit cdf5cb558563df2e0eacb7a8582775da37733721. Checks Flutter/contratos passaram; preview foi pulado conforme configuração.

## Condições verificadas

- Repo público, não arquivado, branch padrão main; GitHub Actions habilitado.
- delivery-worker.yml ativo e com schedule válido. A conta autora está ativa.
- DELIVERY_V2_ENABLED habilitada somente para esta validação; POC_SLACK_ENABLED/POC_SLACK_PUBLISH_ENABLED continuam false. POC_PUBLICATION_ENABLED regravado false no Supabase exclusivo.
- Um job condicionado à flag false seria pulado; isso não é prova de que o scheduler criou uma execução.
- Nenhuma execução com event=schedule encontrada antes do teste, inclusive no histórico geral do repositório.

## Ensaio preparado

Controle sintético delivery-a375a1446bcd440bbf3042ff9fec1fc1, versão fictícia99.0.6, scope none. Registrado pela RPC e cancelado na mesma transação antes de qualquer avaliação; nenhuma tag/Release/preview/patch. Manifesto validation_only salvo no GitHub. Histórico revision0 reservado e envelhecido seis minutos para exercitar retomada. Oito tarefas reais pendentes/reservadas aguardam o cron; não foi feito disparo manual nesta fase.

Não é uma nova rodada de release e não comprova preparo completo do app. Mensagens do ensaio devem sair já canceladas, sem botões. O link de Release do template não existe para essa fixture; a evidência válida é o histórico GitHub e os recibos do worker.

## Diagnóstico e mitigação

`gh workflow enable delivery-worker.yml` confirmou o workflow ativo, mas não produziu schedule imediatamente.

[PR#59](https://github.com/israelhudson/flutter_code_push_example/pull/59) integrado na main, commit c6401a449edad9b275ba8dccdd22258fd0ca5328: mantém intervalo de cinco minutos, nos minutos2,7,12,...57 (`2-59/5 * * * *`), evitando início da hora e renovando a definição do cron.

Isso é mitigação diagnóstica; não se conclui que existia erro de sintaxe ou que o início da hora causou a ausência observada. A [documentação GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) admite atraso/descarte sob carga e recomenda outros horários.

## Evidências

Logs, snapshots privados, metadados dos PRs e prints estão em `/Users/israelhudson/Documents/Codex/2026-10-14/cron-validation/`. A leitura do resultado deve verificar event=schedule, head_branch=main, conclusão do job e recibos da tarefa; um run manual verde não substitui esse teste.

## Teste de autorização do receptor

O teste existente `scheduled worker accepts only main and does not authorize manual cancellation` passou isoladamente. Isso confirma o contrato local do receptor, não uma chamada gerada pelo agendador GitHub. Log privado: scheduled-authorization-test.log.

## Resultado observado

O observador consultou event=schedule por12minutos nesta rodada, além das verificações anteriores. Nenhuma execução foi retornada. O filtro da interface GitHub também mostrou zero resultados após o merge59. Não houve run de cron com falha; não houve run de cron observado. A causa permanece desconhecida, portanto não atribuir a ausência a bug do YAML, conta inativa ou indisponibilidade geral sem nova evidência.

A validação remota do cron continua pendente, mesmo com o teste local do receptor aprovado. O próximo diagnóstico deve procurar uma execução realmente agendada ou obter evidência do GitHub sobre o registro/agendamento, preservando o fallback manual e o despertar por callbacks. Não ampliar o Supabase ou introduzir outro scheduler como se isso estivesse aprovado.

Para encerrar a fixture sem tarefas abandonadas, foi disparado o [fallback manual38670154933](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38670154933), identificado como workflow_dispatch. Esse run não será contado como prova do cron.

## Encerramento

Fallback manual concluído com sucesso na main c6401a449edad9b275ba8dccdd22258fd0ca5328. As oito tarefas foram confirmadas e o histórico recebeu os eventos0/1. Zero controles ativos, zero operações pendentes/dispatch, publication_run nulo, somente delivery_control/delivery_outbox no schema público. A fixture cancelada foi preservada para recusar interações antigas.

DELIVERY_V2_ENABLED voltou a false no GitHub. Publicação permaneceu bloqueada; nenhum patch, preview, tag ou Release foi criado. A pendência é comprovar o disparo do cron no GitHub, não repetir os aceites ou a migração do banco.
