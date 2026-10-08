# Lições aprendidas — laboratório de entrega

Baseline reconstruída em 07/10/2026 a partir de runs, logs e evidências locais. O [log JSONL](evidencias/2026-10-07.jsonl) identifica os eventos reconstruídos com `historical_backfill=true`; não foi produzido em tempo real. A hora original é usada quando existe na fonte. Quando falta, o registro usa a hora da reconstrução e declara essa ausência.

**Resultado verificado:** a POC pessoal compilou web, Android e iOS; preservou a RC entre runners; passou por 0/2, 1/2, 2/2, publicação fictícia parcial, reconciliação, retomada e consulta final. Pages também foi publicado e conferido por HTTP e pelo navegador. Isso não aplica mudanças na Amulets nem valida distribuição mobile de produção.

## Identidade e limites

| Camada | O que foi real | Limite |
|---|---|---|
| Operação | GitHub autenticou Israel no repositório pessoal; eventos e estado sobreviveram entre runs. | Ian, Samuel e Vinícius foram papéis simulados por um único operador. |
| Builds | Flutter 3.44.1, revisão `924134a44c189315be2148659913dda1671cbe99`; web, Android e iOS passaram. | Android AAB de laboratório; iOS XCArchive sem assinatura, sem IPA instalável. Nenhum upload de loja. |
| Preview | Pages, integridade HTTP e interação do botão web observados. | Preview não comprova engine Shorebird ou OTA mobile. |
| Publicação | FakePublisher preservou três recibos e produção **simulada** na revisão 1. | `distribution_performed=false`; nenhum patch, TestFlight, Play ou distribuição a testers. |
| Avisos | Todos os resultados do ensaio informaram `not_configured`. | Nenhuma mensagem Slack enviada; instalação do bot não está comprovada aqui. |
| Amulets | Referências e arquitetura foram lidas; lições abaixo são propostas. | Nenhum build, alteração, CI, deploy ou validação de Production da empresa integra este ensaio. |

Fonte fixa: `08ce07d615905e33f0572f9264808683cab53349`. Candidata: `entrega-0100-rc.1`, versão `1.1.0+2`. Manifesto: `28a15ae28f273bd13742dfbec2191d907769db53de6d5b3550a35070823acaeb`. As ferramentas dos sete comandos vieram de `5fee5a3aea2aa3a4c176916e52cdb70514b7affc`; a aplicação continuou na fonte fixa.

## Incidentes e correções

| Evidência | O que ocorreu | Lição e próxima validação |
|---|---|---|
| [Pages 37692481698](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37692481698), [PR5](https://github.com/israelhudson/flutter_code_push_example/pull/5) | `flutter --version --machine` falhou com JSONDecodeError. O PR5 identificou inicialização/banner na primeira chamada de um SDK recém-clonado. | Inicializar o SDK antes de ler JSON estrito, mantendo versão/revisão exatas. Confirmar em runner novo e em todos os callers. |
| [Pages 37693008451](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37693008451), [PR6](https://github.com/israelhudson/flutter_code_push_example/pull/6) | A compilação terminou, mas o empacotamento recusou arquivo oculto. O PR6 identificou `.last_build_id` como marcador interno. | Excluir somente o marcador conhecido; manter bloqueio para outros ocultos. Compilar não equivale a publicar. |
| [Manual 37693054775](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37693054775) | O primeiro dispatch manual terminou `cancelled`. | Guardar cancelamentos; um run criado não prova publicação. Exigir conclusão e conferência HTTP. |
| [PR6](https://github.com/israelhudson/flutter_code_push_example/pull/6), [CI 37694271502](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37694271502) | A revisão reforçou a âncora do manifesto completo, incluindo entrada e metadata. Adulteração não pode ser aceita só por recalcular o manifesto público. O PR relatou 18 testes locais de Pages; o log CI confirmou 152 testes offline e verificações Flutter. | Ancorar identidade na saída confiável do build e manter casos de adulteração. Testes não substituem verificação ao vivo. |

Os 18 testes locais são evidência histórica relatada no PR6, não uma nova execução feita para escrever este documento.

## Sequência persistente

| Operação | Run | Resultado |
|---|---|---|
| Inicializar | [37692514365](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37692514365) | Seed explícito de laboratório, revisão 0. |
| Revisão técnica | [37692640138](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37692640138) | Papel Ian simulado; 0 avais. |
| Preparar | [37693065273](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37693065273) | Três builds reais passaram; RC em 0/2. |
| Papel Samuel | [37693945716](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37693945716) | Restaurou a RC e salvou 1/2. |
| Papel Vinícius | [37694080929](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37694080929) | Restaurou 1/2 e salvou 2/2, sem publicar. |
| Publish `ios-after` | [37694192406](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37694192406) | Android confirmado, iOS desconhecido após efeito fictício, web pendente; estado parcial. |
| Reconcile | [37694305502](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37694305502) | Consultou journal preservado e confirmou o recibo iOS original. |
| Publish `none` | [37694415878](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37694415878) | Concluiu o restante e avançou produção simulada para revisão 1. |
| Status final | [37694535864](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37694535864) | Novo runner restaurou 2/2, três sucessos e os mesmos recibos. |

Recibos Android/iOS mantiveram os horários originais de 22:08:43 UTC; somente web recebeu novo recibo na retomada, às 22:10:43 UTC. Fonte e manifesto permaneceram iguais. A inspeção Git Data confirmou sete commits consecutivos em `codex/delivery-state`, cada um com o snapshot anterior como parent. Head conferido: `b90cf65c3a47d507ee40649001176d663269b350`.

Banco, journal e outbox são preservados juntos. A concorrência dos workflows complementa a conferência de revisão; não substitui essa garantia. Não reinicializar seed/banco como recuperação de incerteza. Fontes locais: `build/operational-evidence/remote-sequence/sequence.json`, `remote-chain-and-identity.json`, JSONs dos runs e artifacts. O log versionável registra resumos e caminhos, sem copiar bancos ou eventos brutos.

## Pages e experiência observada

A [publicação automática 37694532640](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37694532640) publicou a fonte `0fc06c8f2b79a83bd8bcf135b24fcd02ef1bd928`. A [execução manual 37694569901](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37694569901), disparada pelo botão do GitHub, usou as ferramentas dessa main e publicou a aplicação `08ce07d...`. Ambas concluíram com confirmação HTTP.

O [snapshot manual](https://israelhudson.github.io/flutter_code_push_example/snapshots/08ce07d615905e33f0572f9264808683cab53349/) abriu a versão 1.1.0+2. O botão **Verificar atualização agora** respondeu **Serviço de atualização indisponível no momento.**, sem erros no console observado. Esse comportamento web não prova nem reprova atualização mobile.

Após a segunda publicação, o primeiro snapshot conservou:

- hash web: `888c623ea3e63e9ccce64c25f26002a9a60d8cc8e2283f61884c2d560cfd7635`;
- hash do manifesto completo: `870cd05b631ada3c7a314f4e0dee99e452f3470dde0af5d3c9ae4c25fd37c807`.

Foram conferidos mapa de arquivos, metadata, entrada, bootstrap e JavaScript. Os headers da raiz mostraram `cache-control: max-age=600`: o redirect pode ficar guardado por dez minutos. Para validar uma candidata, usar o endereço confirmado por SHA. Pages usa base URL própria, portanto seus bytes/hash podem diferir do ZIP de preview do CI; fonte e SDK comuns não provam igualdade de bytes.

Fontes locais: `pages-validation.json`, `pages-first-snapshot-preserved.json`, `pages-root-headers.txt` e `pages-manual-browser.jpg`, em `build/operational-evidence/`.

## Registro GitHub concluído pela retomada manual do usuário

O registro pessoal da versão 1.1.0+2 / `entrega-0100-rc.1` está **publicado como GitHub pre-release de laboratório**. Plano e tag passaram; a primeira tentativa falhou no upload; a correção foi integrada pelo [PR8](https://github.com/israelhudson/flutter_code_push_example/pull/8), após [CI 37703315084](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37703315084) com sucesso; então o usuário executou manualmente a retomada. Esse registro real no GitHub é separado dos recibos FakePublisher e não comprova distribuição mobile. As próximas execuções manuais continuam reservadas a Israel.

| Etapa real | Evidência | Resultado conferido |
|---|---|---|
| Plano | [Run 37702713050](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37702713050), [eventos](evidencias/2026-10-07-release-plan-37702713050.jsonl) | Owner autenticado, candidata/fonte/preview conferidos e `plan_ready`; `published=false`. |
| Bootstrap da tag | [Eventos](evidencias/2026-10-07-tag-entrega-0100-rc.1.jsonl) | Objeto e ref anotada criados e confirmados, sem mover a fonte: tag `entrega-0100-rc.1`, objeto `4650c3c985d1e47f6211bdd1cc47a193ed0c31a2`, commit `08ce07d615905e33f0572f9264808683cab53349`. |
| Tentativa de publish | [Run 37702829375](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37702829375), [eventos completos](evidencias/2026-10-07-release-publish-failed-37702829375.jsonl) | Draft `406248758` criado; upload do primeiro asset, `candidate.json`, ficou incerto. Resultado `failed`, `published=false`; nenhuma tentativa automática de repetir. |
| Retomada manual pelo usuário | [Run 37704202085](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37704202085), [eventos](evidencias/2026-10-07-release-published-37704202085.jsonl) | `SUCCESS`, mesma Release `406248758`, quatro assets confirmados e `published=true`; publicação às `2026-10-07T23:47:41Z`. |

Identidade do registro: `765134435bdb2ecc8eedd008f62c0907f21e4ecc945a24bb03b59e9189403a40`. O checkpoint da tentativa falha preservou `operation=upload_asset`, `asset=candidate.json`, `release_id=406248758` e `status=uncertain`; naquele momento, a leitura remota confirmou draft sem assets. Esse log histórico continua com `http_status=null`, sem inventar código HTTP ou causa técnica.

A retomada usou as ferramentas em `0817b4fbf84204b24a20858925fa414a1dcac54a`, mantendo a fonte `08ce07d...`, o manifesto e a tag originais. Resultado e checkpoint novos confirmam `published=true`; a API confirmou `draft=false`, `prerelease=true` e data de publicação. Os assets `candidate.json`, `receipt.json`, `preview.zip` e `checksums.sha256` foram baixados e conferidos pelo coordenador: tamanhos e SHA-256 iguais ao plano, bytes iguais aos artifacts congelados, digest da candidata igual ao manifesto e checksums válidos. O recibo mantém **2 papéis simulados, 0 reviews reais e `distribution_performed=false`**.

**Correção e prova local:** o coordenador confirmou 14 testes do publicador após adicionar `Content-Length: len(data)` em bytes. O teste [test_real_gh_stdin_upload_requires_explicit_byte_length_and_preserves_bytes](../../tests/delivery/test_github_lab_release.py) usa o binário `gh` real 2.101.0, localhost e autenticação sintética: o comando antigo transmitiu stdin sem tamanho explícito e o servidor de teste respondeu 411; o corrigido transmitiu os bytes UTF-8 exatos, sem transferência chunked, e recebeu 201. Tamanho, metadata e digest foram conferidos. São resultados do servidor **local**, não códigos HTTP observados no run remoto anterior; aquele `http_status` continua desconhecido.

A [documentação de upload de assets](https://docs.github.com/en/rest/releases/assets?apiVersion=2026-03-10#upload-a-release-asset) exige `Content-Length` e corpo binário. O [código do gh 2.101.0](https://github.com/cli/cli/blob/v2.101.0/pkg/cmd/api/http.go) trata esse header definindo o tamanho da requisição. Essa leitura e o teste local fundamentaram a correção; a confirmação remota veio depois, da execução manual e da verificação dos assets.

**Fase encerrada:** abra a [pre-release confirmada](https://github.com/israelhudson/flutter_code_push_example/releases/tag/entrega-0100-rc.1) para consultar os quatro assets. Não há outro publish pendente para esta RC. A recuperação retomou o draft existente, conservou a identidade e confirmou a publicação; não criou outra tag nem escolheu latest/main. Uma futura RC segue o processo geral de nova preparação e novos avais, quando houver outra mudança a entregar.

Lição para a Amulets, ainda proposta: diferenciar um draft remoto criado, um asset confirmado e uma Release publicada. Um teste offline de argumentos CLI não comprova que o endpoint recebeu bytes válidos. Preservar erro, checkpoint e identidade permitiu recuperar sem duplicar o registro. A retomada foi feita pelo usuário; nenhum ajuste desta etapa foi aplicado na empresa.

O caminho histórico de duas reviews reais permanece separado: sua política verifica duas identidades nomeadas no commit do PR. Papéis simulados não satisfazem esse gate. A autorização do owner para registro LAB pessoal deve ter política explícita, sem relaxar silenciosamente o caminho histórico ou a futura política da Amulets.

A [documentação GitHub de Create a release](https://docs.github.com/en/rest/releases/releases#create-a-release), API 2026-03-10, exige escrita de workflows quando o alvo altera `.github/workflows/` em relação à branch padrão. `GITHUB_TOKEN` não recebe essa permissão; erros podem ser 403/404. A restrição foi consultada e o bootstrap autenticado pelo owner passou; não houve tentativa de criar essa tag com `GITHUB_TOKEN`. Isso não comprova upload ou publicação concluídos.

O processo separou `tag-spec.json`, bootstrap autenticado pelo owner e validação da tag preexistente. A conclusão foi registrada somente após a retomada e as verificações de identidade, assets e recibo, conservando a tentativa falha como histórico.

## Promoção com revisão real do proprietário

O controle atribui a Israel a revisão da candidata congelada, usando
a [issue #10](https://github.com/israelhudson/flutter_code_push_example/issues/10)
do próprio repositório. A decisão precisa ser um comentário novo da
conta real `israelhudson`, com `APROVAR PRODUCAO`, candidata e hash completos.
Uma nova decisão `REVOGAR PRODUCAO` retira o aceite antes da promoção. O plano
é consultivo; o comando manual `promote` exige a aprovação atual e revalida
fonte, tag e assets antes de mudar a pre-release existente para release estável.

A [regra oficial de reviews GitHub](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews)
impede que o autor aprove seu próprio PR. Os [required reviewers de environments
nos planos Free, Pro e Team ficam disponíveis apenas em repositórios públicos](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).
A issue registra uma decisão real de publicação do proprietário para o
laboratório privado; não substitui uma revisão de código independente nem
altera a política histórica de Samuel e Vinícius.

Promover conserva a Release `406248758`, a tag `entrega-0100-rc.1`, a versão
`1.1.0+2`, a fonte `08ce07d...`, o manifesto e os quatro assets publicados.
Somente o registro GitHub passa a estável, com nome e notas de promoção; não há
rebuild, criação de ref, novo upload, alteração de estado do core ou distribuição
mobile. O recibo original conserva **2 papéis simulados e 0 reviews reais de PR**;
os eventos de promoção distinguem a revisão real de Israel desse histórico.

**Promoção confirmada:** Israel publicou o
[comentário de aprovação 6049452293](https://github.com/israelhudson/flutter_code_push_example/issues/10#issuecomment-6049452293)
às `2026-10-08T00:14:05Z` (21:14:05 de 07/10/2026 em Fortaleza). Depois autorizou
o Codex a executar os controles manuais pelo navegador e capturar as telas.
O agente executou o [plano 37707108627](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37707108627)
e a [promoção 37707227938](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37707227938),
ambos com `SUCCESS`. O plano confirmou o aceite e `promoted=false`; a promoção
confirmou `promoted=true` após a única mutação `promote_release`.
A confirmação da promoção foi às `2026-10-08T00:21:19.318614Z`, 21:21:19 de
07/10/2026 em Fortaleza.

A implementação foi integrada no [PR11](https://github.com/israelhudson/flutter_code_push_example/pull/11),
commit `989fe3443ad16df0c67ff0068d6efb3f458c8ace`, após
[CI 37706794267](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37706794267)
com 199 testes e verificações Flutter de análise, testes e build web passando.
Essas verificações foram seguidas pela execução real e pela leitura da API.

A conferência final às `2026-10-08T00:22:46Z` confirmou `draft=false`,
`prerelease=false`, nome **[LAB · ESTÁVEL] 1.1.0+2 · entrega-0100-rc.1** e os
mesmos IDs/digests dos quatro assets. Fonte, árvore, tag anotada e estado do
core continuaram iguais. A tela mostra **Latest** e seis assets porque o
GitHub acrescenta dois arquivos automáticos de código-fonte aos quatro
uploads originais; não houve novos uploads durante a promoção.

O [log curado](evidencias/2026-10-07-promotion.jsonl), os
[eventos do plano](evidencias/2026-10-07-promotion-plan-37707108627.jsonl), os
[eventos da promoção](evidencias/2026-10-07-promotion-promoted-37707227938.jsonl)
e o [passo a passo com prints](PASSO-A-PASSO-PROMOCAO.md) conservam aprovação,
execução delegada e resultado. Os registros da preparação sem aceite, da
publicação anterior e de sua falha permanecem como histórico.

O gate consulta a lista atual de comentários: a API não reconstrói comandos
apagados. Uma edição posterior de Israel bloqueia a aprovação antiga, mas uma
decisão excluída deixa de ser observável. No laboratório, o proprietário preserva
o histórico e revoga por comentário novo; ele decide a execução do comando final.
Para uma política independente na Amulets, avaliar proteção nativa e registros
de decisão que conservem alterações e exclusões, conforme o plano da empresa.

Lição proposta para a Amulets: registrar separadamente quem revisou o código,
quem autorizou a promoção e quem executou o comando; vincular cada decisão à
candidata e aos seus bytes, conferir revogações e preservar a identidade na
promoção. A equipe precisa escolher pessoas e proteção adequadas ao plano e à
política da empresa. Nenhuma dessas regras foi aplicada na Amulets.

## Propostas para discutir na Amulets

| Proposta | Evidência | Próxima validação antes de aplicar |
|---|---|---|
| Congelar fonte e toolchain por candidata | Mesma fonte/hash nos sete comandos. | Conferir versionamento, flavor, entrypoint, bases e artifacts assinados da empresa. |
| Separar avais do comando final | 1/2 não publicou; 2/2 só autorizou. | Definir pessoas reais, owner, revogação, nova RC e critério de validação pelo usuário. |
| Separar review de PR, aceite de promoção e execução | Aceite real de Israel na issue #10; plano e promoção executados pelo Codex sob autorização expressa; mesma candidata/hash confirmados na API. | Escolher revisores independentes e proteção compatível com a política e o plano GitHub da empresa. |
| Recuperar por destino e chave | iOS reconciliado pelo recibo original; mobile não repetiu. | Verificar APIs autoritativas Shorebird/lojas e efeito incerto sob autorização própria. |
| Persistir intenção e confirmação | Estado/journal/outbox avançaram juntos. | Ensaiar conflito, resposta perdida, recuperação sem reset, retenção e armazenamento. |
| Confirmar conteúdo e conservar previews | Hashes ao vivo e snapshot anterior preservados. | Decidir hospedagem/acesso e verificar conteúdo no ambiente aprovado. |
| Separar corredores de prova | Web, XCArchive unsigned e recibos fictícios têm limites explícitos. | Confirmar base real, compatibilidade final, loja/testers e dispositivo; seguir o [guia oficial de patches Shorebird](https://docs.shorebird.dev/code-push/patch/). |
| Logs acionáveis sem segredos | JSONL com ação, fonte, resultado e validação seguinte. | Definir acesso, retenção e campos autorizados com a equipe. |

Nenhuma proposta foi aplicada na Amulets. Build, patch Shorebird, envio à loja, disponibilidade para testers e validação em Production continuam sendo resultados distintos.

## Continuidade do log

Cada linha contém `timestamp_utc`, `recorded_at_utc`, `event_timestamp_utc`, `timestamp_basis`, `historical_backfill`, `action`, `source_evidence`, `result`, `scope`, `lesson` e `next_validation`. `scope.actual` descreve ações executadas; `scope.simulated` descreve fixtures, papéis e efeitos fictícios.

Acrescentar eventos ao fim, sem apagar histórico. Eventos novos usam `historical_backfill=false` e hora UTC observada. Quando uma conclusão mudar, acrescentar correção referenciando a anterior. Registrar falhas/cancelamentos. As cópias allowlisted dos eventos originais de plano/tag/publish usam o schema do emissor (`at`, `event`); sua origem e a cópia posterior estão descritas no [índice de evidências](evidencias/README.md). Não copiar tokens, bancos SQLite, credenciais ou dados de participantes/canais privados.
