# Auditoria independente do ensaio real no GitHub

Auditor: agente de revisão de segurança, com leituras independentes da API REST
do GitHub e dos snapshots coletados pelo executor. O auditor não aprovou
Environments, não publicou, não alterou código nem fez mutações remotas.
Este documento é seu único arquivo de saída.

## Alcance e limite das evidências

- Reviews confirmam **contas GitHub**, seus IDs, Environment e decisão no run.
- As contas foram operadas em ensaio automatizado autorizado por Israel. Os
  comentários oficiais registram essa condição. **Não demonstram revisão humana
  independente de Israel e Fabrícia**, nem aceite de negócio.
- A promoção deste ensaio cria somente tag estável e Release no GitHub.
  Não equivale a distribuição Android/iOS, loja, Shorebird ou TestFlight.
- O journal pressupõe armazenamento confiável. Sua proteção contra exclusão e
  force push não impede novos commits de um writer/admin malicioso. Os hashes
  detectam divergências no caminho normal; não autenticam um journal forjado por
  quem já possui permissão de escrita.
- A concurrency dos jobs não trava mutações externas por administradores.

## Identidade da candidata inicial

| Campo | Valor verificado |
|---|---|
| RC | `v1.5.0-rc.1` |
| Fonte e ferramentas | `9c4ad37fc415a98ef2a8cfdc5be8d5cf97fe35b0` |
| Run original | [Preparar candidata inicial](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37850467026) |
| Tentativa | `1` |
| Relatório congelado | `8a074cf72f9d5a4a3966112d1e6843a3a9a3235653e71963800f11224f37d2d9` |
| Modo | `github_release_only`; sem distribuição mobile |

## Resultados acumulados

| Caso | Esperado | Observado | Resultado |
|---|---|---|---|
| 0/2 | Dois gates aguardam; sem promoção | Snapshots `rc1-zero-approvals-*`: duas pendências, reviews vazias, sem receipt final/publication; stable e Release ausentes (404) | PASS |
| 1/2 | Israel sozinho não libera autorização/publicação | Consulta REST independente: review `israelhudson`, ID `18661493`; Gate first success; Gate second waiting; somente receipt first; sem job de autorização/promoção iniciado; stable e Release ausentes (404) | PASS |
| Rejeição da RC1 | Segundo gate recusado impede promoção | REST independente: segundo gate failure; autorização e promoção skipped; sem intenção/receipt final; stable e Release ausentes (404) | PASS |
| Correção → RC2 | Fonte nova, RC1 preservada, novos avais 0/2 | PR revisado e CI success; RC2 ativa no merge corrigido, sem recibos prévios; RC1 superseded, tag preservada | PASS |
| Rerun da RC1 | Tentativa 2 não reaproveita aprovações | Preparação failure por rejeição explícita de rerun; avaliação skipped; nenhuma promoção | PASS |
| RC2 pronta com 0/2 | Build/report concluídos não reaproveitam receipt da RC1 | REST independente: reviews vazias, ambos gates waiting e approval_receipts vazio após congelamento do relatório | PASS |
| Conta errada no gate exclusivo | Israel não pode dar o aval destinado à conta Fabrícia | Request ao ID pendente correto recebeu 422/exit1; conta Israel sem permissão de aprovar esse gate; reviews/receipts continuaram vazios | PASS |
| 2/2 sem comando final | Dois avais liberam apenas terceiro gate | REST independente: dois gates success e receipts válidos; AUTORIZAR PUBLICAR waiting; sem intenção/recibo final; stable e Release ausentes | PASS |
| Promoção real da RC2 | Comando final cria stable e Release no mesmo SHA aprovado | REST independente: run success, final pela conta Fabrícia; stable/RC2/SHA iguais; Release publicada e payload coincidente; receipt válido | PASS |

## Conferência independente de 1/2

Leituras REST em 08/10/2026, após o término do Gate first:

- Run original com `status=waiting`, tentativa `1`, ator `israelhudson`.
- Review aprovada exclusiva do Environment `aprovacao-israel`, ID `23819079490`.
- O comentário declara ensaio automatizado por Codex autorizado por Israel e
  ausência de revisão humana independente.
- Job `113563115783`: Gate first, `completed/success`.
- Job `113563115800`: Gate second, `waiting`, sem conclusão.
- O journal mantém RC1 ativa e `status=awaiting_approvals`. `approval_receipts`
  contém somente `first`; não contém `publication` nem `receipt` final.
- SHA de origem e digest de relatório correspondem ao corte. O SHA-256 recalculado
  do relatório em JSON canônico corresponde ao digest congelado.
- GET da referência `tags/v1.5.0` e GET da Release `v1.5.0` retornaram 404.

Nenhuma divergência identificada nesta etapa. Resultados pendentes não devem ser
tratados como PASS antes das respectivas leituras e evidências.

## Conferência independente da rejeição da RC1

O run original terminou `completed/failure`. A API oficial de approvals retornou
review `rejected` da conta `fahnassau30`, ID `339824994`, exclusiva do Environment
`aprovacao-fahnassau30`. O comentário identifica teste automatizado autorizado,
motiva a correção da mensagem inicial e exige RC2 com novos avais.

- Gate first manteve `success` e seu recibo histórico.
- Gate second `113563115800` terminou `failure`.
- AUTORIZAR PUBLICAR `113564492241`: `skipped`.
- PROMOVER `113564492381`: `skipped`.
- Snapshots `rc1-rejected-*` não contêm intenção de publicação nem receipt final.
- O auditor repetiu GETs de stable e Release: ambos 404, sem publicação.

**Semântica do estado:** a rejeição é registrada no histórico oficial de reviews
e na conclusão dos jobs; o journal mantém `awaiting_approvals` e somente o receipt
`first`. Portanto esse status isolado não descreve a rejeição. Na criação da RC2,
o journal deverá marcar RC1 `superseded`, mantendo o registro histórico. Não houve
tentativa de reaproveitar o receipt para publicar a RC1 rejeitada.

## Correção revisada, RC2 e rejeição de rerun

O auditor leu o PR [identificar laboratório na candidata corrigida](https://github.com/israelhudson/flutter_code_push_example/pull/15)
e seus arquivos/reviews/checks via REST. O diff alterou somente a mensagem inicial
para português e a expectativa correspondente no widget test. Não alterou
workflows ou política. A conta `fahnassau30`, ID `339824994`, aprovou o HEAD exato
`4d3043f4cb5ce32abc98438067df2627599e02b5`, com comentário que identifica revisão
automatizada por Codex. O check obrigatório terminou `SUCCESS`; o merge entrou
em `release/1.5.0` como `b8763ec5adc5e24ce34f474a66a079b48a9ffa0f`.

Consulta independente posterior do journal e das tags confirmou:

- Nova candidata ativa `v1.5.0-rc.2`, no SHA desse merge corrigido.
- Novo run [avaliar candidata corrigida](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37851607911), tentativa `1`.
- No corte da RC2, `approval_receipts` ausente/vazio; sem `publication` ou receipt.
- RC1 `superseded`, com seu relatório e receipt first preservados no histórico.
- Tag `v1.5.0-rc.1` mantém o SHA original; tag RC2 aponta ao SHA novo.

O run da RC1 foi deliberadamente reexecutado. Na tentativa `2`, o job de
preparação terminou `failure` e a avaliação foi `skipped`. O log de tentativa 2,
`rc1-rerun-attempt2.log`, registra o bloqueio explícito de reexecução antes de
cortar outra candidata. A leitura REST confirmou a tentativa e os resultados.
Esse resultado comprova o bloqueio de **rerun**; não deve ser descrito como uma
tentativa de publicação da RC antiga que chegou ao job final.

## RC2 pronta para os novos avais

Nova leitura independente confirmou o run da RC2 em `waiting`, tentativa `1`,
após build e Pages/report terminarem `success`. As reviews REST estavam vazias;
ambos os gates exclusivos estavam `waiting`. O journal manteve os recibos da RC2
vazios e sem intenção final. **Nenhum aval da RC1 foi transportado.**

| Campo congelado antes dos avais | Valor verificado |
|---|---|
| Candidata | `v1.5.0-rc.2` |
| Fonte | `b8763ec5adc5e24ce34f474a66a079b48a9ffa0f` |
| Run | `37851607911` |
| Relatório | `f322ac38d3d87747dc7a29642a19d9892476bcb642a34f9602ddc910a9624334` |
| Preview confirmado | [Snapshot corrigido](https://israelhudson.github.io/flutter_code_push_example/snapshots/b8763ec5adc5e24ce34f474a66a079b48a9ffa0f/) |
| Destino estável | `v1.5.0` |
| Modo | `github_release_only` |
| Simulado / distribuição | `false` / `false` |

O SHA-256 independente do relatório canônico corresponde ao digest congelado.
Os campos fonte, RC e digest de política correspondem ao registro da candidata;
o relatório registra confirmação HTTP do snapshot novo, e o changelog inclui o
merge da correção e seu commit de implementação.

## Tentativa de conta errada no gate exclusivo

O executor tentou aprovar `aprovacao-fahnassau30` pela conta Israel. O auditor
conferiu request, resposta e snapshots imediatamente posteriores:

- Request destinado ao Environment `23819080337`, que realmente estava pendente.
- A leitura de pending deployments para Israel mostrava `current_user_can_approve=false`
  no gate da Fabrícia e `true` apenas no gate Israel.
- O revisor exclusivo do Environment solicitado era `fahnassau30`.
- Resposta do GitHub: **HTTP 422**, com `exit_code=1`. Não foi HTTP 403.
- Após o erro, reviews oficiais ainda vazias; receipts da RC2 vazios; ambos gates
  `waiting`; nenhuma intenção de publicação/recibo final; stable e Release 404.

O status foi extraído do JSON oficial em `stdout` (`"status":"422"`), e não de
uma suposição sobre o texto de stderr. O coletor inicialmente procurou somente
stderr e depois normalizou o status string para inteiro; a resposta original foi
preservada e a requisição não foi repetida. Essas correções são de coleta/assertion,
não defeitos na regra de autorização. O resultado funcional negativo é PASS.

## Dois novos avais ainda não promovem a RC2

O auditor consultou reviews, jobs e journal via REST quando o terceiro gate estava
pendente. As contas `israelhudson`/`18661493` e `fahnassau30`/`339824994` haviam
aprovado somente seus Environments exclusivos na avaliação RC2. Ambos os jobs
Gate first/second terminaram `success`.

Os dois receipts coincidem em RC, SHA, digest do relatório, run e tentativa:
`v1.5.0-rc.2`, `b8763ec5adc5e24ce34f474a66a079b48a9ffa0f`,
`f322ac38d3d87747dc7a29642a19d9892476bcb642a34f9602ddc910a9624334`,
run `37851607911`, tentativa `1`. Seus campos review coincidem com as decisões
oficiais, incluindo comentários de ensaio automatizado autorizado.

O job **AUTORIZAR PUBLICAR** estava `waiting`; **PROMOVER** ainda não tinha sido
iniciado. O journal não tinha `publication` nem receipt final. Os snapshots
`rc2-two-approvals-awaiting-final-*` mostram stable e Release ausentes e somente
Environment `autorizar-publicacao` pendente, com as duas contas como revisores
alternativos. Isso comprova que 2/2 libera apenas o comando final separado.

## Promoção real da RC2 concluída

O auditor consultou novamente run, jobs, reviews, journal, três referências de
tag e a Release. O run da RC2 terminou `completed/success`, tentativa `1`.
AUTORIZAR PUBLICAR e PROMOVER terminaram `success`, depois dos dois gates.
A terceira review aprovada foi da conta `fahnassau30`, ID `339824994`, exclusiva
de `autorizar-publicacao`, e identifica explicitamente o comando de ensaio
autorizado para criar stable e Release GitHub sem distribuição mobile.

| Objeto final | Resultado da leitura independente |
|---|---|
| RC1 preservada | `v1.5.0-rc.1` → `9c4ad37fc415a98ef2a8cfdc5be8d5cf97fe35b0` |
| RC2 preservada | `v1.5.0-rc.2` → `b8763ec5adc5e24ce34f474a66a079b48a9ffa0f` |
| Stable nova | `v1.5.0` → **mesmo SHA da RC2 aprovada** |
| Release | [1.5.0 — Laboratório corrigido](https://github.com/israelhudson/flutter_code_push_example/releases/tag/v1.5.0) |
| ID da Release | `407306454` |
| Publicação | `2026-10-08T22:16:37Z`, equivalente a 19:16 de Fortaleza |
| Draft / prerelease | `false` / `false` |
| target_commitish | SHA da RC2 aprovada |
| Payload canônico | `87a0d06699d01056e9360b89178de1e90b778b24a71258a331639e64741edca1` |

As verificações executadas pelo auditor passaram:

1. Identidade e digest da intenção coincidem com RC2, stable, fonte, relatório,
   política, run original e digest das decisões oficiais.
2. GET da Release corresponde exatamente a tag, target, nome, corpo, draft e
   prerelease da intenção; possui data de publicação, ID positivo e URL esperada.
3. `github_release` da API, da intenção e do receipt são iguais.
4. As três decisões no receipt correspondem a contas, IDs, Environments, estado
   e comentários retornados pelo endpoint oficial de approvals do mesmo run.
5. Status da candidata e da intenção é `completed`; `last_stable_version=1.5.0`
   e `last_stable_source_sha` corresponde ao SHA publicado.
6. Após a publicação, a leitura independente dos rulesets/Environments confirmou
   definições exigidas ativas, sem bypass e revisores exclusivos/alternativos
   corretos. Isso é uma fotografia da configuração, não garantia permanente
   contra alteração futura por administradores.

Sequência do journal da RC2: preparação → avaliação → relatório congelado →
primeiro aval → segundo aval → intenção de publicação → tag verificada → Release
verificada → conclusão. A intenção precede os efeitos externos e o receipt final.

O receipt registra corretamente `account_review_verified=true`,
`review_independence_verified=false`, `result_simulated=false`,
`distribution_performed=false` e `patch_generated=false`. Portanto a tag e a
Release GitHub são reais; não houve distribuição do aplicativo nem comprovação
de revisão humana independente. Não houve recuperação nesta promoção:
`recovery_authorizations` está vazio. Os testes de falha parcial/recuperação
continuam evidência offline, sem PASS remoto inferido deste caminho feliz.

**Conclusão desta auditoria:** nove estados/casos da tabela acima foram
verificados, incluindo rejeição, correção, novos avais e promoção real. Não foi
identificada divergência ou publicação sem os dois avais mais comando final.
