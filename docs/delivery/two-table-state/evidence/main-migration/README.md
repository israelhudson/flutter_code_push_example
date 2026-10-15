# Integração na main e aposentadoria do banco legado

14/10/2026, Fortaleza. Projeto exclusivo `xtvueqciogzkyjkkqxcx`.

A automação v2 passa a usar `main` pela política e `DELIVERY_SOURCE_BRANCH`. Isso não muda a origem do código de RC2: a correção continua na branch da release. O PR também integra os incrementos anteriores de `slack-main`, conciliando as proteções e a documentação atuais da main.

## Receptor e teste manual

Receptor `poc-slack-approvals` atualizado com roteamento `delivery_*`. Publicação bloqueada no backend (`POC_PUBLICATION_ENABLED=false`) e GitHub (`POC_SLACK_PUBLISH_ENABLED=false`). Controle de teste com escopo `none`. Nenhuma Release/tag/preview/patch criada.

Os primeiros aceites reais desta rodada foram registrados via Slack às 22:26:16 (negócio) e 22:26:18 (técnico). O agente repetiu ambos via Computer Use às 22:26:45 e 22:27:06; HTTP 200, revisão permaneceu 2, sem duplicar decisões. A mesma conta exerce dois papéis: não comprova dois revisores distintos.

O webhook e banco são reais. A drenagem de mensagens usa handler local com SQL/Slack reais e fixtures de autorização/histórico GitHub. O log `delivery_worker_wakeup_pending` é esperado enquanto o worker não estiver instalado na main. Não confundir essa prova com cron/dispatch validado ponta a ponta.

## Duas tabelas

Destino final: somente `delivery_control` e `delivery_outbox` em `public`. Tabelas internas de Auth/Storage do Supabase não fazem parte do domínio da aplicação e não devem ser apagadas.

Backup privado das oito tabelas restaurado localmente: 67 registros e sete funções sem divergência. A remoção foi ensaiada nesse banco restaurado; somente as duas tabelas novas permaneceram. `legacy-history.json` preserva no GitHub o histórico mínimo, sem payloads/identidades privadas. O backup completo privado permanece disponível e seu hash está registrado.

Os preparos/publicações antigos são bloqueados por `POC_LEGACY_ENABLED=false`; o receptor legado passa a devolver resposta informativa sem consultar tabelas quando `POC_LEGACY_RETIRED=true`. O endpoint antigo de controle responde 410. LAB e Issue permanecem documentados e seus fluxos GitHub não são removidos; não dependem das tabelas `poc_*` para estado de suas aprovações.

A migration de aposentadoria recusa candidata ativa, aviso pendente, publicação não reconciliada ou configuração antiga habilitada. Não usa CASCADE. Nenhuma alteração no projeto/bot da Amulets.

## Após o merge (sem publicação)

1. Confirmar checks e integrar o PR na main; a abertura não equivale a merge.
2. Implantar `delivery-control`, criar/verificar ruleset da branch `codex/delivery-history`.
3. Habilitar worker/preparo v2 de maneira controlada na main, mantendo publicação bloqueada.
4. Validar callback → wakeup → GitHub journal → atualização de DMs com a execução real. Só então considerar esse percurso comprovado.

Logs/prints privados: `Documents/Codex/2026-10-14/delivery-manual-validation`.
