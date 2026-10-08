# Ensaio remoto: candidata, rejeição, correção e promoção no GitHub

Este relatório registra o laboratório de 8 de outubro de 2026 e as lições para
aplicar à Amulets. O destino deste ensaio é **tag estável e Release no GitHub**.
Android, iOS, Shorebird, lojas e distribuição para testers não são executados.

**Estado do relatório: ensaio remoto em andamento.** A implementação foi
integrada e passou na CI; a RC1 passou na avaliação e foi rejeitada pela conta
Fabrícia depois do aval de Israel. Os bloqueios 0/2, 1/2 e rejeição foram
confirmados. Um PR de correção está em CI. Merge da
correção, RC2, novos avais e promoção final permanecem PENDENTE até seus logs,
reviews, objetos GitHub e recibo confirmarem os resultados. Os testes offline
são registrados separadamente e não são apresentados como distribuição real.

## A diferença entre aprovação, comando e publicação

```mermaid
flowchart TD
  PR[PR técnico + checks + review elegível] --> Main[Main revisada]
  Main --> Cut[Operador informa versão e título]
  Cut --> RC[Branch release + tag RC imutável]
  RC --> Eval[Analyze + testes + build web]
  Eval --> Preview[Preview HTTP confirmado + changelog congelado]
  Preview --> A[Conta Israel: registrar aval]
  Preview --> B[Conta Fabrícia: registrar aval]
  A --> Both[Dois jobs e recibos válidos: 2 de 2]
  B --> Both
  Both --> Command[Conta Israel OU Fabrícia: autorizar PUBLICAR]
  Command --> Recheck[Reconferir RC, relatório, reviews e proteções]
  Recheck --> Intent[Salvar intenção antes de efeitos externos]
  Intent --> Stable[Tag estável no mesmo commit da RC]
  Stable --> Release[Release real no GitHub + conferência por GET]
  Release --> Receipt[Recibo: GitHub publicado, mobile não distribuído]
  B --> Reject[Rejeição: publicação bloqueada]
  Reject --> Fix[PR para release + revisão técnica]
  Fix --> RC2[RC2: novo preview, novos avais e novo comando]
  RC2 --> Eval
```

| Etapa | Quem pode agir | O que a ação produz |
|---|---|---|
| Preparar candidata | Operador autorizado Israel | Fonte/tag/versão/título congelados; não é aprovação |
| Review de código | Conta técnica elegível, diferente do autor | Review do PR; não é aval da entrega |
| Registrar aprovação Israel | Conta `israelhudson` | Um aval da candidata e evidência validada |
| Registrar aprovação Fabrícia | Conta `fahnassau30` | O outro aval da mesma candidata |
| Autorizar PUBLICAR | Israel OU Fabrícia, depois de 2/2 | Comando final separado; não altera a fonte aprovada |
| Promover | Automação confiável depois do comando | Nova tag estável + Release GitHub no commit da RC |
| Recuperar | Operador autorizado e nova autorização final | Completar efeitos ausentes da intenção original |

O botão **Approve and deploy** é da interface nativa GitHub. No Environment de
uma conta ele libera somente o job que registra seu aval. Uma conta aprovar não
publica a versão; a outra conta e o comando final continuam necessários. O
número no botão conta os Environments selecionados, não quantos avais faltam.

Uma lista de reviewers em um único Environment funciona como OU. Por isso os
dois primeiros Environments são separados e exclusivos; o terceiro contém os
dois usuários e funciona como OU, depois de ambos os primeiros jobs concluírem.

## Quem operou o ensaio e o que as reviews provam

O usuário autorizou Codex a executar ações de **ensaio** pela conta Fabrícia
aberta no Safari. A revisão da implementação foi enviada nessa sessão como
review automatizada, com comentário explícito sobre o teste. As etapas futuras
operadas pelo agente precisam manter a mesma identificação honesta.

O GitHub verifica uma conta autenticada. Isso **não comprova que a Fabrícia
pessoalmente revisou o produto**, nem uma avaliação independente feita por duas
pessoas. O recibo de promoção usa `account_review_verified=true`,
`approval_evidence_kind=github_account_review` e
`review_independence_verified=false`. Este relatório não converte um teste de
contas em aceite humano de negócio.

No fluxo da Amulets, revisores técnicos e aprovadores da candidata são papéis
separados. Fabrícia não se torna revisora técnica por padrão; neste LAB, o uso de
sua conta para a review de ensaio foi autorizado especificamente. O autor de um
PR não pode aprová-lo; o branch protegido e o check obrigatório permanecem ativos.

## Objetos e evidências principais

| Objeto | Identidade ou evidência |
|---|---|
| Implementação | [PR da promoção GitHub-only](https://github.com/israelhudson/flutter_code_push_example/pull/14) |
| Código integrado | `9c4ad37fc415a98ef2a8cfdc5be8d5cf97fe35b0` |
| CI da implementação | [Run com Flutter analyze/test e 273 testes da esteira](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37850097988) |
| Log da CI | [implementation-ci.log](implementation-ci.log) |
| Review técnica de ensaio | [implementation-pr-before-merge.json](implementation-pr-before-merge.json) e [print](01-revisao-tecnica-automatizada.jpg) |
| Primeira candidata real | `v1.5.0-rc.1`, branch `release/1.5.0` |
| Título | Ensaio de rejeição, correção e promoção no GitHub |
| Avaliação RC1 | [Run da primeira candidata](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37850467026) |
| Correção para release | [PR: identificar laboratório na candidata corrigida](https://github.com/israelhudson/flutter_code_push_example/pull/15) |
| CI da correção | [Run da correção proposta](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37851354969) |
| Preview RC1 | [Snapshot verificado](https://israelhudson.github.io/flutter_code_push_example/snapshots/9c4ad37fc415a98ef2a8cfdc5be8d5cf97fe35b0/) |
| Diário das observações | [actions.jsonl](actions.jsonl) |
| Fonte de estado/recibo | Branch `codex/release-lab-state`, `release-lab/state.json` |
| Testes offline finais | [9 cenários e suas limitações](../2026-10-08-real-promotion-offline-v3/summary.json) |
| Testes de promoção/configuração | [24 testes](../2026-10-08-real-promotion-offline-v3/unit-tests.log) e [5 testes](../2026-10-08-real-promotion-offline-v3/configuration-tests.log) |
| YAML final | [actionlint-final.json](../2026-10-08-real-promotion-workflows/actionlint-final.json) |

Os links relativos deste relatório apontam a evidências na mesma branch de
estado, fora da main. Os snapshots de teste não são adicionados ao PR de código.
Todos os horários mencionados em texto usam Fortaleza; os JSONs e logs preservam
os timestamps originais para comparação e auditoria.

## Passo 1 — integrar a implementação e conferir a CI

**PASS observado.** A implementação passou em Flutter analyze, Flutter test e
273 testes Python de contratos/bloqueios, e foi integrada pelo PR após review
registrada pela conta autorizada. O log registra `Ran 273 tests` e `OK`.

A CI confirma os checks desse snapshot. Não cria uma candidata nem publica a
Release. Sua review de ensaio não equivale a análise humana independente. O
print e o JSON preservam a origem da decisão e as proteções do PR.

## Passo 2 — preparar RC1 no modo GitHub-only

**PASS para o corte e a avaliação.** Às 18h58,
o operador iniciou a preparação de `1.5.0` com título legível. O corte criou a
branch release e a RC imutável no commit integrado, sem exigir hashes no formulário.

Na observação registrada logo após o corte:

- O run estava `in_progress`; corte e preflight concluíram com sucesso.
- O build web estava em andamento; relatório/preview ainda não estavam congelados.
- `publication_mode=github_release_only`, `status=evaluating` e nenhum recibo final.
- Não havia reviews nem tag estável/Release `v1.5.0`; os GETs registraram 404.

Provas: [run](rc1-preparing-run.json), [jobs](rc1-preparing-jobs.json),
[estado](rc1-preparing-state.json), [reviews](rc1-preparing-reviews.json),
[tags RC](rc1-preparing-rc-refs.json), [estável ausente](rc1-preparing-stable-ref.json)
e [Release ausente](rc1-preparing-stable-release.json).

A ausência de reviews enquanto o build ainda roda não comprova sozinha o gate
0/2. Esse bloqueio deve ser observado **depois** de preview e relatório prontos,
com os dois jobs de aprovação efetivamente aguardando.

Na observação seguinte, às 19h02, analyze/test, build e publicação/HTTP do preview
concluíram com sucesso. O diário registrou `awaiting_approvals` e um relatório
congelado com `result_simulated=false`; os dois gates estavam `waiting`, as
reviews estavam vazias e a tag estável/Release continuavam ausentes. Assim o
bloqueio 0/2 foi observado depois da avaliação, não presumido durante o build.

Provas dessa transição: [jobs](rc1-zero-approvals-jobs.json),
[estado e relatório](rc1-zero-approvals-state.json), [reviews](rc1-zero-approvals-reviews.json),
[gates pendentes](rc1-zero-approvals-pending.json),
[estável ausente](rc1-zero-approvals-stable-ref.json) e
[Release ausente](rc1-zero-approvals-stable-release.json).

[Print do estado com zero aprovações](02-rc1-zero-aprovacoes.jpg).

O relatório distingue versão do catálogo GitHub (`1.5.0`) de versão atual do
pubspec (`1.1.0+2`). Este LAB não constrói nem distribui mobile. Antes de migrar,
defina uma regra explícita de alinhamento entre versão da entrega e versão/build
do app; uma tag GitHub não altera automaticamente o pubspec ou a release-base.

## Passo 3 — provar 0/2 e 1/2 antes de rejeitar RC1

**PASS para 0/2, 1/2 e rejeição.** O roteiro executado é:

1. Após preview/changelog, registrar 0/2: ambos os gates aguardam, autorização
   final e promoção não iniciaram e não há estável/Release.
2. Aprovar somente Israel e esperar o job de registro terminar.
3. Registrar 1/2: diário contém apenas um recibo, Fabrícia continua obrigatória,
   final não inicia e catálogo permanece sem a versão estável.
4. Rejeitar o gate Fabrícia com comentário de ensaio e motivo da correção.
5. Registrar a rejeição: review oficial `rejected`, job final/promoção não
   executados, nenhum recibo de conclusão ou versão estável.

Os jobs de registro conferem reviewer ID/login, Environment e relatório da RC.
Rodar esse job é necessário para guardar a decisão; não é um novo build ou deploy.

Na observação 1/2, o gate Israel concluiu com sucesso e o diário contém somente
o recibo `first`, correspondente à conta `israelhudson`. A review traz comentário
explícito de ensaio automatizado autorizado. Fabrícia continuava aguardando;
autorização final/promoção não iniciaram, não havia recibo final e tag/Release
estáveis continuavam ausentes. Isso confirma o efeito do primeiro clique.

Provas: [pedido do aval de ensaio](rc1-israel-approval-request.json),
[reviews](rc1-one-approval-reviews.json), [jobs](rc1-one-approval-jobs.json),
[estado com um receipt](rc1-one-approval-state.json),
[pendências](rc1-one-approval-pending.json),
[estável ausente](rc1-one-approval-stable-ref.json) e
[Release ausente](rc1-one-approval-stable-release.json).

[Print com um aval e Publicar bloqueado](03-rc1-um-aval-publicar-bloqueado.jpg).

A conta Fabrícia rejeitou o gate da RC1, com comentário explícito de automação
de ensaio. O run encerrou com `completed/failure`; a autorização final e o job
de promoção foram `skipped`. O diário não recebeu recibo de conclusão, e tag
estável/Release continuam ausentes. O receipt Israel permanece como história;
sozinho ele não autoriza entrega nem deve ser transferido à RC2.

O journal local da execução rejeitada ainda mostra `awaiting_approvals`: o job
do Environment rejeitado não chegou a executar o helper que grava decisões.
Portanto, a prova da rejeição é o histórico oficial de reviews e o estado do
run/job, não somente o campo resumido do journal. A preparação da RC seguinte
deverá marcar a antiga como supersedida. Para uma interface Amulets, reconcilie
essas fontes para não exibir uma candidata rejeitada como revisão saudável em espera.

Provas: [review de rejeição](rc1-rejected-reviews.json),
[jobs após rejeição](rc1-rejected-jobs.json), [estado](rc1-rejected-state.json),
[estável ausente](rc1-rejected-stable-ref.json),
[Release ausente](rc1-rejected-stable-release.json) e
[print da RC1 rejeitada](04-rc1-rejeitada-sem-promocao.jpg).

## Passo 4 — corrigir por PR na release e criar RC2

**PR aberto; CI, review e merge PENDENTE.** A correção de ensaio altera a mensagem do app e seu teste, com branch
baseada na `release/1.5.0`. Ela precisa passar em CI e em review técnica por
conta elegível antes do merge. Não há push direto à release.

O PR **identificar laboratório na candidata corrigida** propõe trocar o título
visível por **Laboratório de atualizações**, junto da expectativa no widget
test. O commit proposto é `4d3043f4cb5ce32abc98438067df2627599e02b5`.
Essa mudança visível permite distinguir o preview da RC2 do primeiro candidato;
abrir o PR não significa que a correção já foi integrada.

Depois do merge:

1. Preparar novamente versão `1.5.0`, com título atualizado.
2. Conferir que `v1.5.0-rc.2` aponta ao commit corrigido da release.
3. Confirmar que RC1 continua no commit original e não foi renomeada/apagada.
4. Confirmar RC1 supersedida e RC2 sem recibos de aprovação anteriores.
5. Conferir novo preview, changelog acumulado e relatório no modo real.
6. Validar que aprovações/relatório da RC1 não autorizam RC2.

O ensaio precisa preservar o PR, diff, check, review, merge commit, tags e estado.
A correção deve também entrar na main por outro PR revisado; features novas da
main não devem ser importadas para essa release.

## Passo 5 — novos avais, comando separado e promoção

**PENDENTE.** Israel e Fabrícia dão novos avais para RC2. Ambos os jobs de registro
precisam concluir com sucesso. Com 2/2, o run abre somente a autorização final;
a versão não publica automaticamente.

Uma das duas contas autoriza PUBLICAR na mesma execução. O job de efeitos, em
runner novo, reconfere identidade e proteções e salva a intenção antes de chamar
as APIs de tag/Release. Cria **`v1.5.0` no commit de RC2**, preservando RC1 e RC2.
A Release deve ser não draft, não prerelease, com título/changelog aprovados.

O PASS remoto exige GETs de tag/Release, recibo e jobs concluídos. O recibo precisa
mostrar commit/report/RC, os dois avais, comando final, `result_simulated=false`,
`github_release_published=true` e `distribution_performed=false`. Um POST bem
sucedido ou uma tela com tag não bastam para afirmar esse resultado.

## Matriz: local, remoto e pendências separados

| Cenário/subcaso | Offline | Remoto até a observação atual | Prova exigida |
|---|---|---|---|
| CI do snapshot integrado | Testes complementares PASS | PASS: analyze/test + 273 contratos | Log CI e run |
| Corte RC1 | PASS em fixtures | PASS: branch/RC preparadas | Fonte, refs, journal e run |
| VAL-01: 0/2 bloqueia | PASS | PASS | Dois gates aguardando, final sem início, reviews vazias e ausência de estável/Release |
| VAL-01: 1/2 bloqueia | PASS | PASS | Um receipt, outro gate pendente, sem estável/Release ou início final |
| VAL-01: 2/2 exige comando | PASS | PENDENTE na RC2 | Dois receipts/jobs e terceiro Environment pendente |
| VAL-01: comando promove | PASS | PENDENTE na RC2 | Stable/Release GET, recibo e jobs |
| VAL-02: rejeição RC1 | PASS sintético | PASS | Review rejeitada, final/promoção skipped e ausência de estável/Release |
| VAL-02: correção PR release | Git temporário PASS; sem PR remoto | PENDENTE | PR, CI, review e merge |
| VAL-02: RC2 não herda avais | PASS | PENDENTE | Nova fonte/report e zero receipts de RC2 |
| VAL-02: correção também main | Roteiro; não comprovado pelo fixture | PENDENTE | Outro PR revisado |
| VAL-03: deriva de fonte/report/política | PASS | PENDENTE; não provocar deriva de tag protegida real | Bloqueio e nenhum efeito |
| VAL-04: tag conflitante | PASS | PENDENTE; catálogo real não adulterado | Objeto preservado sem overwrite |
| VAL-05: parcial/POST resposta perdida/recovery | PASS | PENDENTE; nenhuma falha remota forçada | Intent, fresh gate e GET idempotente |
| VAL-06: versão/ator/bot/rerun inválidos | PASS | PENDENTE | Recusa antes de promoção |
| VAL-07: writers intercalados CAS | PASS | PENDENTE de disputa controlada real | Dois receipts preservados sem eventos duplicados |
| VAL-08: preview falha | PASS | PENDENTE de falha real controlada | Não abrir caminho válido de publicação |
| VAL-09: proteções removidas após reviews/entre efeitos | PASS | Não provocar remoção no catálogo real; PENDENTE remoto | Antes intent zero efeitos; depois tag sem Release/recibo |
| Aplicativo/patch entregue | Fora do escopo | Não executado | Aceite mobile separado futuro |

PASS offline usa helper real + Git temporário + APIs/reviews/HTTP fixtures.
Nenhum dos nove cenários locais efetuou network, Pages, review humana ou Release
real. A integração remota prova serviço/permissões e conta autenticada, sem
comprovar independência humana. Um cenário não concluído permanece PENDENTE.

## Logs e prints a preservar

`actions.jsonl` registra operador, estado do run e existência dos efeitos por
observação. Cada etapa também precisa salvar:

- run/jobs/reviews/pending deployments, sem esconder cancelamentos ou rejeições;
- journal, identidade RC/report, refs candidatas/estável e Release GET;
- logs completos da CI/avaliação/gates/promoção ou recuperação;
- PRs e reviews técnicas de release/main, diff e merges;
- screenshots da seleção de Environment, primeira aprovação, rejeição, novos
  gates, comando final e Release resultante, com legenda do operador do ensaio;
- falhas e correções em arquivos novos, sem sobrescrever a evidência anterior.

Artefatos Actions duram 90 dias. Exporte o que precisa permanecer consultável.
Não copie tokens, cookies, webhooks, segredos ou dados privados Amulets para este
LAB público. Os registros longos ficam na branch de estado; a main contém guias,
helpers e testes, sem centenas de snapshots de execução.

## Lições aprendidas e riscos para migrar

| Lição | Evidência/motivo | Aplicação à Amulets |
|---|---|---|
| Aprovação de candidata é AND; final é OR | Gates separados verificam contas e jobs | Samuel E Vinícius aprovam; um deles manda publicar, após confirmar política |
| Label nativo pode confundir | Botão Approve and deploy também aparece no registro de aval | Nomear efeito da etapa e mostrar o que o clique fará |
| Job de aval não é publicação | Helper valida e grava receipt; job final só após ambos | Explicar estado visível por ação, não só por runner rodando |
| Gate rejeitado não executa o helper | Run RC1 falhou e review rejeitou, mas journal manteve awaiting_approvals | Conciliar run/reviews e journal ao mostrar estados de rejeição/cancelamento |
| Mudança RC exige novos avais | VAL-02 local preserva RC1 e promove commit corrigido RC2 | Nova fonte, report e preview; jamais reutilizar antigas decisões |
| RC não é renomeada para estável | Tag estável é outro ref no mesmo commit aprovado | Preservar candidatas rejeitadas e o histórico de porquês |
| Tag/Release são efeitos separados | VAL-05 reconciliou resposta perdida e parcial | Persistir intent; GET exato; recovery fresh sem duplicar |
| Proteções podem mudar durante a espera | Auditoria P2 e VAL-09 cobrem retirada após reviews/entre tag e Release | Rechecagem após espera e antes dos efeitos, sem confiar só no preflight |
| Defaults seguros API precisam de validação explícita | Configuração primeira tentativa recusou defaults; retry aceitou []/extra_approval true seguros | Falhar fechado para drift inseguro sem rejeitar normalização segura |
| Ruleset estável cobre namespace novo | Regra LAB - tags estaveis imutaveis ativa | Proteger estáveis e RCs; regra antiga entrega-* não cobre v* |
| Conta real não é review humana independente | Ensaio usa automação autorizada Safari fahnassau30 | Rotular operador/evidence kind; aceite de negócio separado |
| Journal pressupõe writers/admins confiáveis | Fast-forward/não exclusão não bloqueia commit malicioso autorizado | Restringir writers ou usar evidência externa resistente à adulteração |
| Token precisa provar escopo para commit congelado | Tag em commit com workflows pode exigir Workflows write se main avançar | Ensaiar token/App e falhar fechado; não trocar commit aprovado/rerun |
| Wait humano não pode segurar lock | Autorização semlock; effects sob release-lab-mutation | Separar gate e publicação, preservando corte/promoção serializados |
| Build deve ser readonly | Runner novo para Pages e promoção não executa o app com write/OIDC | Isolar artefato e validar identidade/staticbytes |
| Preview web não valida mobile | Bases Android/iOS null no LAB | Target bloqueado até base/toolchain/artefato/dispositivo reais |
| Versão GitHub e versão do app são campos distintos | Report RC1 registra entrega 1.5.0 e pubspec 1.1.0+2 | Definir alinhamento versão/build/release-base antes do adaptador mobile |

Na Amulets privada, confira primeiro plano e disponibilidade de Required
reviewers; o LAB público não prova suporte no privado Team. Confirme responsáveis,
contas, revisores técnicos elegíveis, domínio de preview privado e permissões de
publicação. Preserve separação de CI, aceite de produto, comando e distribuição.

## Falhas registradas até aqui

- A validação de configuração recusou inicialmente campos padrão seguros do
  servidor. Foi refinada para os defaults específicos seguros; o retry concluiu.
  Não se habilitou bypass para fazer a configuração passar.
- A auditoria identificou a lacuna P2 de verificar proteções só antes da espera.
  `finish_real` e `live_intent` passaram a consultá-las novamente; VAL-09 local
  confirma bloqueio antes intent e entre tag/Release.
- Rodadas offline anteriores e falha de fixture de tag legada permanecem nos
  logs históricos, com testes finais verdes. Eles não foram apagados para
  apresentar uma execução sem incidentes.
- Ao exportar o log do run rejeitado, a ferramenta devolveu exit code 1 apesar
  de produzir conteúdo de log. Os bytes coletados devem ser preservados junto
  do stderr; a conclusão/reviews/jobs oficiais permanecem a prova do resultado.
  Não é correto apagar o log parcial nem deduzir uma falha de publicação apenas
  do exit code da ferramenta de exportação.
- Restrição potencial de GITHUB_TOKEN/Workflows write em commit congelado ainda
  exige prova remota aplicável. A automação falha fechado, não resolve por rerun
  nem apontando a tag para outra main.

**Nenhuma falha remota de promoção foi estabelecida nessas observações.**
O build concluiu e o fluxo aguarda reviews; isso não é sucesso final. Este trecho
será atualizado se houver incidentes observados, preservando seus logs.

## Antes de chamar a esteira de validada para produção mobile

Este ensaio pode comprovar promoção GitHub-only e os bloqueios com contas reais.
Ainda são aceites separados: release-base Android/iOS exata, compatibilidade
nativa/assets/dependências/toolchain, build assinado, credential/target correto,
adaptador Shorebird/store, upload, disponibilidade a testers, instalação e uso
no dispositivo, monitoramento/rollback. GitHub Release não confirma nenhum
 desses resultados automaticamente.

Consulte o [guia do fluxo implementado](https://github.com/israelhudson/flutter_code_push_example/blob/main/docs/delivery/FLUXO-DOIS-APROVADORES.md)
e a [matriz técnica com escopos](https://github.com/israelhudson/flutter_code_push_example/blob/main/docs/delivery/VALIDACAO-E-PROMOCAO.md).
