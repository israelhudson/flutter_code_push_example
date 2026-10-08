# Validar a promoção: cenários, logs e lições para Amulets

O objetivo é testar o ciclo **candidata → dois avais → comando final → tag
estável e Release no GitHub**, incluindo rejeição, correção e recuperação.
A distribuição de app ou patch mobile continua fora deste ensaio. O
[guia operacional](FLUXO-DOIS-APROVADORES.md) explica cada etapa.

**PASS exige evidência da execução correspondente.** Implementar um bloqueio,
escrever um teste ou ter uma execução antiga verde não basta para declarar um
novo cenário aprovado. `PENDENTE` significa que falta executar ou anexar a prova;
não significa que o cenário falhou. Falhas observadas ficam nos logs, com a
correção e sua validação posterior.

## O que cada tipo de prova demonstra

| Evidência | Demonstra | Não demonstra |
|---|---|---|
| Teste unitário local | Regra isolada com entradas conhecidas | API GitHub, identidade humana ou distribuição |
| Ensaio offline integrado | Helpers reais e Git temporário real, com API/reviews/HTTP controlados | PR remoto revisado, Pages publicado ou aprovação humana independente |
| Run Actions real | Jobs, permissões, artefatos e estados no GitHub | Objeto publicado correto sem leitura posterior |
| Review de Environment | Conta autenticada, Environment, decisão e run | Quem operou a conta ou qualidade/independência da revisão |
| GET de tag e Release | Tag no commit esperado e Release com estado/conteúdo conferidos | Build na loja, testers recebendo ou clientes atualizados |
| Ensaio mobile futuro | Resultado do adaptador na plataforma e base exatas | Resultado de outra plataforma ou release-base |

Automação de ensaio pode operar contas com autorização explícita do usuário.
Registre-a como **review de teste pela conta autorizada**; não a descreva como
revisão independente feita por Fabrícia ou aceite de negócio da Amulets. O recibo
usa `account_review_verified=true` e `review_independence_verified=false` para
manter essa distinção.

## Histórico já observado

Em 8 de outubro de 2026, o primeiro ensaio percorreu preparação, analyze, testes,
preview confirmado por HTTP, changelog, dois gates e comando final. O
[run do ensaio inicial](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37845381675)
registrou reviews das contas `israelhudson` e `fahnassau30`, com comando final de
`fahnassau30`. Seu recibo declara `result_simulated=true`,
`distribution_performed=false` e `patch_generated=false`.

Isso comprova o ciclo de aprovação **do modo simulado**. Não criou tag estável ou
Release e não autoriza reaproveitar esses avais em modo real. O
[passo a passo histórico com prints e logs](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-two-reviewers-run/PASSO-A-PASSO.md)
permanece preservado; o efeito final e os nomes das etapas mudam nesta versão.

## Resultados do ensaio real de 8 de outubro

A [execução da RC2](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37851607911) terminou com sucesso: a [Release estável v1.5.0](https://github.com/israelhudson/flutter_code_push_example/releases/tag/v1.5.0) e sua tag apontam ao mesmo commit aprovado de `v1.5.0-rc.2`. RC1 foi rejeitada, a correção passou por PR para a release e RC2 exigiu novos avais. Ambos os gates e o comando final foram executados em ensaio automatizado autorizado por Israel; não constituem revisão humana independente.

Os [resultados completos e atualizados](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-live/PASSO-A-PASSO-E-LICOES.md), a [matriz por cenário e subcaso](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-live/MATRIZ-RESULTADOS.json) e a [auditoria independente](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-live/LIVE-SECURITY-AUDIT.md) guardam prints, reviews, logs, GETs e recibos. A matriz abaixo registra o alcance de cada família; variantes offline não passam a ser provas remotas.

## Matriz de pelo menos cinco cenários

Os nove IDs correspondem ao ensaio `tools/delivery/rehearse_release_lab.py`.
A coluna offline usa helpers reais, Git temporário real e API/reviews/HTTP
fixtures. As colunas são independentes: PASS offline não vira PASS remoto.

| ID | Cenário | Observável esperado | Offline | GitHub com promoção real |
|---|---|---|---|---|
| VAL-01 | Feliz: 0/2 → 1/2 → 2/2 → comando | 0/2 e 1/2 bloqueiam; 2/2 libera só comando; terceiro aval promove o mesmo commit | PASS | PASS — [recibo, GETs e run](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-live/rc2-verified-result-state.json) |
| VAL-02 | RC1 negada → correção → RC2 | RC1 preservada, RC2 sem avais antigos, estável no commit corrigido de RC2 | PASS | Ciclo comprovado; integração na main e evidência do PR na [matriz atualizada](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-live/MATRIZ-RESULTADOS.json) |
| VAL-03 | Deriva de fonte, relatório ou política | Identidade divergente bloqueia; nada de trocar fonte ou destino silenciosamente | PASS | PENDENTE |
| VAL-04 | Conflito de tag estável | Tag divergente preservada; nenhum overwrite | PASS | PENDENTE |
| VAL-05 | Falha parcial e resposta API perdida | Intenção persistida; recuperação autorizada completa só o ausente e verifica por GET | PASS | PENDENTE |
| VAL-06 | Versão antiga, ator inválido, bot, rerun | Entrada recusada antes de efeitos de promoção | PASS | Parcial — conta errada e rerun comprovados; demais variantes na matriz atualizada |
| VAL-07 | Dois writers concorrentes no diário | CAS retry preserva os dois avais e um evento por papel | PASS | PENDENTE |
| VAL-08 | Preview não confirmado | Sem relatório aprovado, sem gate válido e sem promoção | PASS | PENDENTE |
| VAL-09 | Proteções removidas após as reviews ou entre efeitos | Sem proteção antes da intenção, nada publica; após a tag, Release/recibo bloqueiam sem apagar a tag | PASS | PENDENTE |

Atualize para PASS somente com caminho ou link de evidência. Se um cenário tiver
subcasos obrigatórios, registre cada um e exija que todos passem no mesmo escopo.
A separação dos locks e runners também precisa da conferência descrita abaixo;
VAL-07 offline sozinho não prova scheduling real do GitHub.

**Evidência final dos nove PASS locais:** [summary.json da terceira rodada](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-offline-v3/summary.json).
Cada pasta de cenário guarda `result.json`, `trace.jsonl`, snapshots de diário,
refs/Releases e histórico dos commits temporários. O relatório declara
`real_network=false`, `real_human_reviews=false`, `real_pages_validation=false`
e `real_github_release=false`. Os roteiros seguintes incluem verificações remotas
e subcasos adicionais; a tabela não os declara todos executados no GitHub.

A terceira rodada verifica o helper com SHA-256
`082492a7083f8b5df6ebdf18b042092834cec449c89ef12b4c769c4c87b8abcf`.
Os [24 testes finais da promoção](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-offline-v3/unit-tests.log)
passaram em 21,941 segundos, e os [cinco testes de configuração](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-offline-v3/configuration-tests.log)
passaram em 0,023 segundos. A [primeira rodada](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-offline/summary.json)
e a [segunda rodada](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-offline-v2/summary.json)
ficam preservadas como histórico. Na segunda rodada,
[unit-tests.log](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-offline-v2/unit-tests.log)
preserva uma falha inicial de fixture que contava uma tag RC legada; o namespace
foi corrigido para `v...` e os [22 testes daquela rodada passaram](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-offline-v2/unit-tests-final.log).
Não remova os logs de falha. Evidências ficam na branch de estado, fora da `main`;
a documentação usa seus links e não inclui os snapshots no PR de código.

## VAL-01 — dois avais e comando separado

1. Prepare candidata com versão disponível e título legível; guarde RC, commit,
   identidade do relatório, modo de publicação e preview.
2. Com zero avais, confirme que a autorização final não iniciou.
3. Registre só um aval e aguarde seu job. A outra conta continua obrigatória;
   o job que registra a review não pode criar tag estável ou Release.
4. Registre o segundo aval. A promoção ainda aguarda comando final separado.
5. Dê o comando final. Leia tag estável e Release por GET: commit, título, corpo,
   `draft=false` e `prerelease=false` precisam ser os aprovados.
6. Leia o recibo: mesma candidata/fonte, três decisões, publicador,
   `result_simulated=false` e `distribution_performed=false`.

O resultado é um registro real no catálogo GitHub. Não há comando Shorebird,
build mobile, credencial de loja ou entrega aos clientes. A ordem dos primeiros
avais é livre; AND continua obrigatório independentemente de quem começa.

## VAL-02 — RC1 rejeitada, correção e RC2

| Passo | Ação | Evidência |
|---|---|---|
| 1 | Preparar RC1 | Tag, commit, relatório e preview |
| 2 | Rejeitar um gate com motivo | Review `rejected`, publicação não inicia |
| 3 | Corrigir a partir da branch release | Diff e teste/reprodução do problema |
| 4 | PR para release com review técnico elegível | PR, check verde e merge; autor não aprova o próprio PR |
| 5 | Preparar RC2 | Nova tag no commit corrigido; RC1 continua existindo |
| 6 | Tentar usar evidência da RC1 | Bloqueio; RC2 começa sem os avais anteriores |
| 7 | Obter novos avais para RC2 | Duas contas, mesma RC2/relatório/preview |
| 8 | Dar novo comando final | Estável e Release no commit exato da RC2 |
| 9 | Outro PR leva a correção à main | Features novas da main preservadas, correção integrada |

O ensaio offline usa commits Git temporários para comprovar comparações entre
RCs; não inventa PR ou review técnico remoto. Para PASS GitHub, anexe os dois PRs
e as reviews, identificando operadores e automação de teste. Se falta um revisor
técnico elegível, esse trecho remoto fica PENDENTE; não reduza a proteção para
concluir o teste. Uma main que avançou não muda o commit da release aprovada.

## VAL-03 — identidade divergente ou RC supersedida

O VAL-03 local cobre relatório, tag RC e branch release divergentes e alteração
da política de release-base. VAL-02 cobre superseding da RC anterior. Complete
remotamente, quando aplicável, a verificação do preview e de mudança sim → real.
Todos precisam falhar fechado, sem usar main atual ou destino “latest”.
Guarde diário antes/depois, erro da reconferência e ausência de efeitos externos.
Não mova tags protegidas remotas para gerar deriva; fixtures e Git temporário
validam essas entradas sem danificar o catálogo.

## VAL-04 — colisão de tag ou Release

Teste tag estável em outro commit e Release com conteúdo/identidade divergentes.
A operação não pode atualizar ou apagar o objeto existente. Quando a mesma
operação legítima já produziu os objetos corretos, recuperação reconhece a
identidade e não cria duplicatas. Registre objetos antes/depois e chamadas API.
Testes remotos usam versão reservada de LAB, nunca a entrega em revisão de alguém.

## VAL-05 — limites de falha e recuperação

Teste intenção salva antes da tag; tag criada sem Release; POST concluído cuja
resposta se perdeu; objetos corretos com falha ao salvar o recibo. Nenhum POST
isolado conclui a promoção sem confirmação por GET.

A preparação recusa outro corte enquanto existe promoção parcial. Uma nova
execução de **LAB - Recuperar promoção** na main resolve internamente o relatório
e exige nova autorização final. Reconferem-se dois avais e comando originais,
sem trocar fonte, título, modo ou destino. O recibo preserva publicador original
e acrescenta `recovery_authorizations`, com a conta da autorização nova.

A intenção registra estágios `intent_recorded`, `tag_verified`,
`release_verified`, `failed` e `completed`. Guarde o estado parcial e a exceção;
não apague tags nem use rerun para contornar o bloqueio. Em corte parcial, a
reconciliação de preparação exige mesma versão e título; não se reaproveitam avais.

Falha de API controlada offline comprova o algoritmo, não uma recuperação real.
Não provoque indisponibilidade remota ou remova artefatos para forçar um PASS.
Uma recuperação GitHub só recebe PASS com incidente/falha controlada registrada.

## VAL-06 — autorização e repetição inválidas

Subcasos: versão antiga/inválida; operador fora da política; bot como revisor;
Environment/reviewer trocado; review ambígua; rerun; tag sem registro confiável.
Entradas inválidas são recusadas antes de promoção. Cancelamento, rejeição,
job ignorado ou falho não equivalem a aval. Registre erro, chamadas externas e
a ausência de criação/alteração de tag ou Release.

## VAL-07 — gravações concorrentes e scheduling

O ensaio intercalado salva a review `second` entre a leitura e a gravação de
`first`. O retry CAS precisa preservar os dois recibos e um evento por papel.
Isso cobre disputa de diário, mas não comprova os locks do Actions.

Confira os YAMLs e, quando possível, o comportamento remoto:

- Corte, promoção e recuperação usam `release-lab-mutation` nos jobs curtos de
  efeitos. Uma RC não pode ser substituída entre a última conferência e as APIs.
- Jobs de aprovação/autorização não adquirem esse lock durante espera humana;
  outra candidata pode ser preparada enquanto ainda existe espera de review.
- `cancel-in-progress=false` preserva uma promoção já em execução. Um job ainda
  pendente pode ser substituído pela fila do GitHub; isso não vira sucesso no
  diário. Diagnostique o run antes de repetir a operação.
- Concurrency do Pages cobre export/deploy, sem abranger os avais nem trocar a
  identidade do snapshot.

A concurrency group não trava operações manuais fora do workflow. Proteções de
branch/tag e reconferência continuam obrigatórias. Não presuma que runs serão
publicados na ordem em que foram disparados.

## VAL-08 — avaliação incompleta e runner privilegiado

O cenário offline injeta confirmação de preview malsucedida: o relatório não
pode abrir um caminho válido de aprovação/publicação. O mesmo princípio vale
para falha de analyze/test/build e HTTP 200 com bytes de fonte divergente.

App e dependências compilam no runner readonly. O runner novo de Pages executa
só ferramentas confiáveis e valida bytes; recusa `.git`, symlinks, snapshots
extras e metadata/fingerprint divergentes. Promoção e recuperação também usam
runners novos. Review do YAML e testes de comportamento conferem essas fronteiras;
um run real precisa confirmar o caminho executado.

## VAL-09 — reconferir as proteções depois da espera

O check inicial não basta: um administrador pode mudar rulesets enquanto as
reviews aguardam. O primeiro subcaso retira as proteções depois de 2/2 e do
comando final, antes de gravar a intenção; a operação precisa recusar a promoção
sem criar tag estável ou Release. O segundo retira as proteções depois da tag;
a tag fica preservada, a intenção registra falha e nenhuma Release ou recibo de
conclusão é produzido. A recuperação também precisa reconferir essas regras.

O PASS offline valida essas transições com API controlada. Não desative regras
remotas da candidata real para repetir esse teste. Proteções são consultadas
novamente em `finish_real` e nas conferências de intenção antes de cada efeito.
Os registros Git protegidos contra reescrita/exclusão pressupõem escritores e
administradores confiáveis: não bloqueiam um commit malicioso em fast-forward
nem substituem um log externo resistente à adulteração.

## Configuração e permissões: limites ainda relevantes

Na configuração remota, a primeira tentativa foi recusada de forma segura pela
diferença entre o payload proposto e campos padrão devolvidos pelo servidor.
O validador foi refinado para aceitar os defaults seguros `required_reviewers=[]`
e `extra_approval=true`, mantendo bloqueio para regras incompatíveis. A repetição
concluiu e a regra **LAB - tags estaveis imutaveis** ficou ativa. Isso valida a
configuração; não comprova que uma Release foi publicada.

O token de publicação pode ser recusado ao criar uma tag no commit aprovado que
contém workflows, sobretudo se a main avançar e for necessária a autorização
**Workflows write**. `contents: write` e testes offline não provam essa permissão.
O fluxo falha fechado e conserva a evidência, sem trocar para o commit atual,
apagar arquivos ou repetir jobs para contornar a recusa. Essa limitação precisa
de validação e, se necessário, credencial de GitHub App com escopo apropriado;
ela não está resolvida por rerun ou pela recuperação idempotente.

## Executar e preservar os registros

O ensaio offline não usa credenciais GitHub, dispara Actions, aprova Environments,
publica no Pages ou cria objetos remotos.

```bash
python3 tools/delivery/rehearse_release_lab.py --help
python3 tools/delivery/rehearse_release_lab.py --output docs/delivery/evidencias/meu-novo-ensaio
python3 -m unittest discover -s tests/delivery -v
```

Confira argumentos, branch e checkout antes de rodar. As validações do app
continuam `flutter analyze` e `flutter test`. `actionlint` confere os YAMLs;
sintaxe válida não comprova Environments ou rulesets remotos.
Escolha uma pasta nova e vazia para cada execução; o ensaio recusa sobrescrever
evidência. As pastas da primeira e segunda rodadas permanecem preservadas.

Cada cenário guarda ID, escopo, resultado, RC/commit/relatório/modo, iniciador,
reviews oficiais e operador do ensaio, jobs, objetos antes/depois, chamadas API,
logs, recibos, prints, causa de falha, correção e lição. Para o caminho remoto,
anexe run, PRs, reviews técnicas, preview e GETs de tag/Release.

Artefatos do Actions duram 90 dias. Preserve logs/recibos antes da expiração;
use arquivos novos para cada estado, sem sobrescrever capturas históricas. Não
publique tokens, cookies, webhooks ou dados privados da Amulets neste LAB público.

### Registro desta implementação

- **Ensaio offline:** PASS, 9/9, em
  [summary.json final, terceira rodada](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-offline-v3/summary.json).
- **Testes locais de promoção:** PASS, 24/24, em
  [unit-tests.log](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-offline-v3/unit-tests.log).
- **Testes locais de configuração:** PASS, 5/5, em
  [configuration-tests.log](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-offline-v3/configuration-tests.log).
- **Workflows:** PASS no `actionlint` 1.7.12 para os quatro YAMLs; runner build
  readonly, gates sem lock de mutação e promoção/recuperação sob lock curto comum.
  [Log final da validação estática](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-workflows/actionlint-final.json).
- **CI da implementação:** PENDENTE de logs do snapshot final.
- **Promoção real GitHub-only:** PENDENTE de nova candidata e novos avais no modo
  real, depois da validação dos cenários.
- **Distribuição mobile:** fora deste ensaio; sem patch, upload ou testers.

Atualize resultados com evidências concretas. O ensaio simulado anterior permanece
histórico; não o converta em resultado de promoção real.

## Lições para Amulets

| Lição | Motivo/evidência | Aplicação |
|---|---|---|
| Uma lista de reviewers é OR | Um único aval libera um Environment | Dois gates obrigatórios e terceiro OR |
| Botão nativo pode confundir | “Approve and deploy” aparece também no registro de aval | Nomes claros e tabela dos efeitos junto ao relatório |
| Job de aval precisa executar | Primeiro clique validou conta e gravou evidência | Explicar que job rodando não é publicação |
| 2/2 não é comando de publicar | Run aguardou terceiro Environment depois dos dois avais | Decisão final separada e auditável |
| Recibo simulado não promove tag | Primeiro ensaio concluiu mantendo só RC | Definir efeito final e conferir tag/Release por GET |
| Mudar modo exige novas reviews | Resultado antes aprovado era simulado | Congelar modo/destino no relatório e criar nova RC |
| RC rejeitada preserva aprendizado | Fonte e motivo explicam a RC seguinte | Manter tags/reviews; estável é uma nova tag |
| Tag e Release não são transação única | São chamadas API diferentes | Intenção persistida e recuperação idempotente autorizada |
| Espera humana não deve segurar lock | Um revisor pode demorar | Separar autorização e efeitos; lock curto compartilhado |
| Build não deve herdar publicação | Compilação executa código de app/dependência | Runner readonly e runner novo para efeitos |
| Proteções podem mudar durante a revisão | VAL-09 retirou regras após reviews e entre tag/Release | Revalidar depois da espera e antes de cada efeito, preservando parcial |
| Diário pressupõe escritores confiáveis | Fast-forward e não exclusão não impedem escrita maliciosa autorizada | Restringir quem escreve; para maior garantia, usar armazenamento externo apropriado |
| Defaults da API precisam de interpretação explícita | Primeira configuração recusou diferenças; retry aceitou somente defaults seguros | Validar regras incompatíveis sem rejeitar uma resposta segura do servidor |
| Token readonly/write não prova permissão de workflows | Tag em commit congelado pode exigir Workflows write | Ensaiar escopo da credencial; não mudar commit aprovado nem contornar com rerun |
| Conta não prova revisão independente | Teste autorizado pode operar a conta | Registrar operador/automação; aceite de negócio humano |
| GitHub não equivale a distribuição | Release, loja, Shorebird e testers são estados diferentes | Recibo por adaptador/plataforma, base e destino exatos |

Confirme plano GitHub do repositório privado, revisores técnicos, contas, preparador
e publicador antes de migrar. LAB público não comprova disponibilidade dos gates
na Amulets privada. Não copie contas/credenciais do LAB. O desenho de Samuel E
Vinícius para avais, e Samuel OU Vinícius para comando, precisa de acesso e aceite.

Antes de publicar mobile, faça aceite separado: base/destino Android e iOS,
credenciais, build assinado, patch/store elegível, disponibilidade a testers e
resultado no dispositivo. Promoção GitHub aprovada não conclui esse aceite.

Fontes: [reviewers e disponibilidade](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments),
[concurrency e fila](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency),
[reviews do run](https://docs.github.com/en/rest/actions/workflow-runs#get-the-review-history-for-a-workflow-run)
e [referência Shorebird](../../referencias/docs/004-shorebird-patch-e-elegibilidade.md).
