# Falhas, bloqueios e prevenção para a próxima rodada

Auditoria dos arquivos preservados do laboratório de **8 de outubro de 2026**.
O objetivo é evitar repetir erros de configuração, teste e coleta, mantendo os
bloqueios que protegem a publicação. Esta auditoria não disparou Actions, não
repetiu aprovações nem alterou tags, Releases ou código.

**A promoção real da RC2 terminou com oito jobs verdes e a Release `v1.5.0`
publicada no mesmo commit aprovado.** As quatro conclusões vermelhas de
execução desta rodada foram negativas esperadas: rejeição da RC1, segunda
tentativa da RC1, versão já usada e versão antiga. A recusa HTTP 422 da conta
incorreta foi outro negativo esperado, sem criar review. Isso não significa que
todas as falhas anteriores do histórico sejam esperadas.

Também ocorreram erros evitáveis: comparação rígida de defaults seguros da API,
uma expectativa incorreta de fixture e duas assertions do coletor HTTP. A
auditoria encontrou uma lacuna de rechecagem de proteções e a corrigiu antes da
promoção. A exportação parcial de logs e um nome prematuro de snapshot exigiram
tratamento explícito na documentação. Cada caso aparece abaixo com seu limite.

Provas terminais: [run concluído](rc2-verified-result-run.json),
[oito jobs](rc2-verified-result-jobs.json), [estado/recibo](rc2-verified-result-state.json),
[Release conferida por GET](rc2-verified-result-stable-release.json) e
[Release no GitHub](https://github.com/israelhudson/flutter_code_push_example/releases/tag/v1.5.0).
O [relatório completo](PASSO-A-PASSO-E-LICOES.md) explica o percurso; a
[matriz](MATRIZ-RESULTADOS.json) separa **9/9 cenários offline PASS** de
**15/20 verificações/subcasos remotos PASS**, com cinco pendentes no serviço real.

## Como ler uma execução vermelha

| Classificação | Quando usar | Consequência |
|---|---|---|
| Negativo esperado — PASS | O roteiro pediu uma ação inválida e a automação recusou antes dos efeitos proibidos | Preservar o bloqueio; não tentar transformar essa execução em publicação verde |
| Erro real corrigido | Código, configuração ou teste contrariou o comportamento esperado | Guardar falha original, correção e prova posterior |
| Limite de coleta tratado | A exportação não trouxe todos os logs, mas outras fontes comprovam o estado | Informar exatamente o que falta; não declarar coleta completa |
| Refinamento pendente | O resultado protegido está correto, mas a representação do estado precisa melhorar | Registrar a pendência sem dizer que já foi implementada |
| Não auditado | Falta o conjunto de logs/estado da tentativa para estabelecer a causa | Não atribuir uma causa pelo ícone vermelho ou pelo título do run |

Um `failure` do GitHub descreve a conclusão daquela execução. O resultado do
**teste** depende de comparar o que deveria acontecer com o que aconteceu e
conferir a ausência dos efeitos proibidos. Um erro em um coletor também não
altera automaticamente o resultado do workflow que ele observa.

## Bloqueios esperados observados no GitHub

| Caso | Resultado observado | O que preservar na próxima rodada | Evidência |
|---|---|---|---|
| RC1 rejeitada pela conta Fabrícia | Attempt 1: review `rejected`, gate da conta falhou; autorização final e promoção `skipped`; sem estável/Release | Motivo explícito, attempt original e ausência dos efeitos; corrigir por PR e criar outra RC | [Review](rc1-rejected-reviews.json), [jobs](rc1-rejected-jobs.json), [estado](rc1-rejected-state.json), [estável ausente](rc1-rejected-stable-ref.json), [Release ausente](rc1-rejected-stable-release.json) |
| Rerun da RC1 | Attempt 2 recusou o corte com “Reexecução não reaproveita avais”; avaliação `skipped` | Usar rerun apenas no cenário negativo. No caminho normal, preparar nova RC com novos avais | [Run attempt 2](rc1-rerun-run.json), [jobs](rc1-rerun-jobs.json), [log](rc1-rerun-attempt2.log), [estado](rc1-rerun-state.json) |
| Israel tentou aprovar gate exclusivo Fabrícia | API retornou HTTP 422; nenhum aval criado; dois gates continuaram aguardando | Identificar conta e Environment antes da ação normal; testar a conta errada somente como negativo declarado | [Resposta original](rc2-wrong-account-response.json), [avaliação corrigida](rc2-wrong-account-assessment.json), [reviews vazias](rc2-wrong-account-blocked-reviews.json), [jobs](rc2-wrong-account-blocked-jobs.json) |
| Preparar `1.5.0` depois de publicada | Corte falhou; avaliação `skipped`; nenhuma nova candidata; journal, estável e Release iguais ao baseline concluído | Selecionar uma versão maior no caminho normal; conservar tentativa de versão igual somente no roteiro negativo | [Avaliação](same-version-blocked-assessment.json), [log](same-version-blocked.log), [run](same-version-blocked-run.json) |
| Preparar `1.4.0` depois de `1.5.0` | Mesma recusa antes de alterar o estado ou o catálogo | Conferir versão numericamente, comparando com catálogo e reservas; não apagar tags para reutilizar versão | [Avaliação](old-version-blocked-assessment.json), [log](old-version-blocked.log), [run](old-version-blocked-run.json) |

Os estados 0/2, 1/2 e 2/2 antes de PUBLICAR são **esperas corretas**, não falhas.
Dois avais habilitam o terceiro gate; não substituem o comando final. O clique
nativo **Approve and deploy** em um gate de aval libera seu job de registro; o
nome do botão não muda as dependências do fluxo. [Prova do terceiro gate
pendente após dois avais](rc2-two-approvals-awaiting-final-pending.json).

## Erros evitáveis e correções comprovadas

### F-01 — configuração recusou defaults seguros da API

**Classificação: erro real de compatibilidade da validação, corrigido.**
A primeira tentativa terminou `FAILED_CLOSED` com “Ruleset diverge; revisar
antes de alterar”. O snapshot mostra a regra de PR com campos retornados pelo
servidor que a especificação não incluía: `required_reviewers=[]` e
`require_extra_approval_for_unattributed_changes=true`. A comparação rígida
interpretou essa normalização segura como divergência.

**Correção feita:** `ruleset_matches` passou a normalizar somente esses dois
valores seguros conhecidos. Reviewer extra e `false` para a aprovação adicional
continuam sendo divergências. Cinco testes de configuração passaram e o retry
concluiu com os revisores esperados. Não houve bypass nem sobrescrita da regra
divergente. A tentativa inicial já tinha produzido a proteção de tags estáveis;
por isso a retomada precisava ler o estado real, não presumir “nenhum efeito”.

**Prevenção pré-rodada:** comparar GET com a política efetiva, aceitar apenas a
lista explícita de defaults seguros e verificar idempotência. Se houver outra
divergência, parar para revisão; não recriar ou apagar regras às cegas.

**Limite:** prova local da normalização e retry real deste repositório; não
garante suporte ou permissões em um repositório privado da Amulets.

Provas: [primeira tentativa](../2026-10-08-real-promotion-activation/first-attempt.json),
[regras retornadas](../2026-10-08-real-promotion-activation/rulesets-after-first-attempt.json),
[configuração do retry](../2026-10-08-real-promotion-activation/retry/configuration.json)
e [cinco testes](../2026-10-08-real-promotion-offline-v3/configuration-tests.log).

### F-02 — proteções eram verificadas antes da espera, sem reconferência suficiente

**Classificação: lacuna real de código encontrada na revisão, corrigida antes
da promoção; não foi uma falha remota de publicação observada.** A revisão
identificou que uma proteção poderia mudar durante a espera pelas aprovações.
O preflight original não comprovava que as regras continuavam vigentes no
momento dos efeitos externos.

**Correção feita:** `finish_real` reconfere proteções antes de salvar a intenção
e `live_intent` reconfere antes dos efeitos. VAL-09 prova offline que ausência de
proteções antes da intenção produz zero efeitos; retirada depois da tag bloqueia
a Release, preservando a tag já criada.

**Prevenção pré-rodada:** manter essa verificação no ponto de publicação e na
retomada, além do preflight. Conferir o helper efetivamente congelado para o run
com o helper validado. Um check manual inicial não substitui a rechecagem depois
da espera humana.

**Limite:** a retirada de proteções foi simulada offline; não removemos regras
reais para provocar falha remota. Esse subcaso segue pendente na matriz.

Provas: [registro da revisão/correção](../2026-10-08-real-promotion-workflows/security-review.json),
[VAL-09](../2026-10-08-real-promotion-offline-v3/VAL-09/result.json),
[resumo offline final](../2026-10-08-real-promotion-offline-v3/summary.json)
e [hashes congelados/matriz](MATRIZ-RESULTADOS.json).

### F-03 — fixture contou uma tag RC histórica de outro namespace

**Classificação: erro real da expectativa do teste, corrigido.** O teste de
resposta perdida no corte esperava somente `tags/v1.4.0-rc.1`, mas filtrava todas
as refs contendo `-rc.`. A fixture conservava também
`tags/entrega-0100-rc.1`. O log documenta a assertion com as duas refs; isso não
é prova de criação duplicada da mesma RC nem de um erro real do GitHub.

**Correção feita:** a expectativa passou a filtrar o namespace `tags/v` da
esteira nova, preservando a tag histórica da fixture. O log original FAIL e o
log final PASS permanecem em arquivos separados. A suíte final de promoção tem
24 testes verdes.

**Prevenção pré-rodada:** definir baseline e namespace de cada assertion;
comparar a diferença antes/depois quando o caso verifica novos objetos. Não
apagar histórico para fazer o teste passar. Inspecionar as fixtures herdadas
antes de usar contagens globais de tags.

**Limite:** erro local de teste; não foi falha de Action da promoção real.

Provas: [log original com assertion](../2026-10-08-real-promotion-offline-v2/unit-tests.log),
[log corrigido](../2026-10-08-real-promotion-offline-v2/unit-tests-final.log)
e [suíte final](../2026-10-08-real-promotion-offline-v3/unit-tests.log).

### F-04 — coletor interpretou incorretamente a resposta HTTP 422

**Classificação: dois erros reais de assertion da coleta, corrigidos.** O
coletor inicialmente procurou o código HTTP apenas no stderr; o código estava
no corpo JSON oficial. Depois, comparou o `status` textual `"422"` com um número.
Os erros eram da avaliação da resposta já preservada, não da recusa do GitHub.

**Correção feita:** ler o JSON da resposta e normalizar o código com `int` antes
da assertion. A requisição negativa **não foi repetida**. GETs posteriores
confirmaram nenhuma review criada, os dois gates esperando e ausência de
estável/Release naquele momento.

**Prevenção pré-rodada:** testar o coletor com respostas preservadas; guardar
stdout, stderr e exit code separadamente; validar schema/tipos antes das
assertions. Corrigir o parser usando o arquivo original em vez de repetir uma
ação que pode ter efeitos.

**Limite:** a correção documentada é do coletor deste ensaio; não comprova
tolerância a todos os formatos futuros da API.

Provas: [resposta original](rc2-wrong-account-response.json),
[correções declaradas e avaliação PASS](rc2-wrong-account-assessment.json),
[reviews](rc2-wrong-account-blocked-reviews.json) e
[pendências](rc2-wrong-account-blocked-pending.json).

### F-05 — exportação agregada de logs terminou com conteúdo parcial

**Classificação: limite real de coleta, tratado sem afirmar coleta completa.**
O comando de exportação da RC1 rejeitada devolveu exit code 1 com
`log not found` para o job rejeitado, que não executou as etapas do helper.
Mesmo assim, produziu **391.589 bytes** de conteúdo. Isso não demonstra um
segundo erro no workflow nem falha de publicação.

**Tratamento feito:** preservar os bytes, stderr e exit code. Usar reviews,
run/jobs e GETs de objetos para comprovar rejeição e ausência de efeitos. A
ferramenta de exportação não foi modificada; a limitação continua explícita.

**Prevenção pré-rodada:** exportar por tentativa, manter metadados de coleta e
listar jobs sem logs em vez de descartar todo o arquivo quando o exit code é
não zero. Sempre guardar a tentativa original antes de rerun; o link geral do
run passa a mostrar a tentativa mais recente.

**Limite:** não afirmar que todos os logs de todos os jobs foram coletados.

Provas: [metadados da coleta](rc1-log-collection.json),
[conteúdo preservado](rc1-rejected-attempt1.log),
[review oficial](rc1-rejected-reviews.json) e [jobs](rc1-rejected-jobs.json).

### F-06 — nome do snapshot sugeriu conclusão antes da prova terminal

**Classificação: erro de nomenclatura da coleta, corrigido na interpretação.**
A família `rc2-promotion-completed-*` foi coletada com o run ainda
`in_progress`, a intenção em `tag_verified` e sem Release ou recibo terminal.
O nome foi mais forte que o estado observado.

**Tratamento feito:** conservar esses arquivos como transição intermediária e
usar `rc2-verified-result-*` como prova terminal: run `completed/success`,
Release GET e recibo `completed`. O intervalo tag → Release foi uma transição
normal entre APIs, não uma recuperação de falha parcial.

**Prevenção pré-rodada:** nomear capturas pelo estado observado e usar um
manifesto com run/attempt/status/conclusion. Só declarar publicação concluída
depois de conferir GET e recibo. Não derivar PASS do nome de arquivo, print ou
tag isolada.

**Limite:** nenhum timeout ou recovery real foi comprovado nesse intervalo.

Provas: [run intermediário](rc2-promotion-completed-run.json),
[estado intermediário](rc2-promotion-completed-state.json),
[run terminal](rc2-verified-result-run.json),
[estado/recibo terminal](rc2-verified-result-state.json) e
[Release terminal](rc2-verified-result-stable-release.json).

## Refinamentos que permanecem pendentes

| Refinamento | Motivo evidenciado | Situação e cuidado |
|---|---|---|
| Conciliar rejeição/cancelamento com o journal | O gate rejeitado não executou o helper; journal da RC1 ainda mostrou `awaiting_approvals`, enquanto review/run comprovavam rejeição | Pendente para uma visão consolidada. RC2 marcou a anterior como supersedida; não apresentar só o journal como estado completo |
| Resumo próprio de testes negativos | As recusas corretas permanecem vermelhas na tela Actions nativa | Proposta futura: roteiro/orquestrador registra expectativa, observado e PASS do teste. Pode terminar verde quando a recusa esperada e ausência de efeitos forem comprovadas; manter a Action de publicação recusando ações inválidas |
| Recuperação, conflito, deriva, writers e preview falho no serviço real | A suíte offline cobriu os casos, mas o serviço real não recebeu todas essas falhas controladas | Cinco verificações/subcasos remotos pendentes na matriz; não contar o happy path como prova desses negativos |
| Escopo de token para fonte congelada com workflows | Auditoria registra possível exigência de permissão Workflows write se a default branch avançar | Prova remota aplicável pendente. Falhar fechado; não deslocar a tag aprovada, ampliar permissão sem decisão ou usar rerun como contorno |
| Revisão humana independente | As contas do ensaio foram operadas por automação autorizada | Este teste comprova contas/gates, não aceite independente de duas pessoas |
| Mobile e integração Amulets | GitHub Release e preview web não distribuem app; versão do catálogo e pubspec são distintas | Adaptadores, versões/builds, release-base, credenciais, testers/dispositivos e política do time precisam de aceites próprios |

## Checklist da próxima simulação

Este é um roteiro de prevenção recomendado, **não um novo workflow já
implementado**. Não exige repetir os testes verdes desta rodada sem uma
mudança, nova falha ou dúvida relevante.

1. **Fixar escopo e expectativa antes de disparar.** Identificar modo simulado
   ou GitHub-only real, fonte/ferramentas, operador e resultado esperado. Uma
   simulação pode não criar a Release; o ensaio desta rodada criou a Release
   real, com mobile fora do escopo. Rotular cada negativo, por exemplo
   “Teste negativo esperado — versão já publicada”.
2. **Conferir baseline sem modificar o catálogo.** Ler versão estável, versões
   reservadas, candidata ativa e intenção parcial. Usar versão maior no caminho
   normal; uma publicação parcial precisa de reconciliação, não de outra RC.
3. **Conferir política, identidades e proteções.** GET de rulesets/Environments,
   defaults seguros conhecidos, checks e pessoas elegíveis. Identificar a conta
   aberta antes da aprovação. Não presumir que o Safari ou a sessão de API usa
   a conta pretendida.
4. **Validar fixtures e coletores antes do serviço real.** Namespace e baseline
   das refs, JSON/status string ou número, casos sem log e nomes de transição.
   Reutilizar arquivos preservados para corrigir parsers, sem repetir ações
   remotas. Se a implementação mudou, executar checks apropriados no novo
   snapshot; o PASS antigo continua sendo prova apenas do snapshot antigo.
5. **Percorrer o caminho normal até cada ponto de controle.** Preview/changelog
   prontos → 0/2 → 1/2 → 2/2 ainda esperando PUBLICAR → comando separado → GET
   da estável/Release e recibo. Respeitar o lock de mutação e não competir com
   outra preparação/promoção. O gate humano não precisa manter esse lock.
6. **Rodar negativos declarados e verificar efeitos.** Para cada recusa, salvar
   esperado, observado, run/attempt, log/review e comparação de estado/objetos.
   Não considerar qualquer erro PASS: a mensagem e a ausência dos efeitos
   proibidos devem corresponder ao cenário.
7. **Fechar a rodada com rastreabilidade.** Guardar falha original e correção em
   arquivos novos, listar coleta parcial e pendências, conferir objetos finais
   e separar teste local, comportamento real de conta e aceite humano. Um
   relatório consolidado deve mostrar “bloqueio esperado”, “erro corrigido” ou
   “pendente”, sem depender da cor de Actions.

## Histórico anterior: não generalizar esta auditoria

Esta leitura cobre a rodada de promoção real e seus arquivos locais
`2026-10-08-real-promotion-*`. **Não foi feita uma auditoria completa de todos os
Actions vermelhos anteriores do repositório.** O histórico de previews,
publicações e versões antigas exige o conjunto da tentativa correspondente:
run/attempt/jobs, logs disponíveis, inputs, SHA e efeitos externos.

Não atribuir falhas históricas a token, Pages, Flutter, upload ou aprovação sem
esses dados. O changelog citar um PR de correção é um ponto de investigação,
não substitui o log causal da execução. Na próxima investigação, registrar
“não auditado” até reunir essa prova; os registros anteriores devem permanecer
preservados.

As referências locais **005 — acordo V4 histórico** e **004 — elegibilidade
Shorebird**, do checkout original, foram lidas antes desta análise. Elas
sustentam snapshot preservado, novos avais na correção e limite web/mobile. A
[fonte de planejamento V4](https://amulets-esteira-distribuicao-v4.israeldev.chatgpt.site/#comparacao)
e o texto histórico do primeiro ensaio simulado não mudam o resultado
GitHub-only real comprovado nesta rodada.
