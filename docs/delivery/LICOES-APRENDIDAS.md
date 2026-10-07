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

## Registro GitHub autorizado: ainda pendente

O owner autorizou o registro pessoal da versão 1.1.0+2 / `entrega-0100-rc.1`. Nesta baseline essa fase está **planejada e autorizada, sem publicação confirmada**. FakePublisher concluído não cria GitHub Release nem comprova distribuição.

O caminho histórico de duas reviews reais permanece separado: sua política verifica duas identidades nomeadas no commit do PR. Papéis simulados não satisfazem esse gate. A autorização do owner para registro LAB pessoal deve ter política explícita, sem relaxar silenciosamente o caminho histórico ou a futura política da Amulets.

A [documentação GitHub de Create a release](https://docs.github.com/en/rest/releases/releases#create-a-release), API 2026-03-10, exige escrita de workflows quando o alvo altera `.github/workflows/` em relação à branch padrão. `GITHUB_TOKEN` não recebe essa permissão; erros podem ser 403/404. Isso foi documentação consultada, não criação executada.

Plano do coordenador: produzir `tag-spec.json`; o owner criar tag anotada no SHA exato com autenticação existente; o CI conferir a tag preexistente. Não mover a RC para a main mais recente. Revalidar API, token, anotação, SHA, manifesto, proteção e recibo da Release antes de registrar sucesso.

## Propostas para discutir na Amulets

| Proposta | Evidência | Próxima validação antes de aplicar |
|---|---|---|
| Congelar fonte e toolchain por candidata | Mesma fonte/hash nos sete comandos. | Conferir versionamento, flavor, entrypoint, bases e artifacts assinados da empresa. |
| Separar avais do comando final | 1/2 não publicou; 2/2 só autorizou. | Definir pessoas reais, owner, revogação, nova RC e critério de validação pelo usuário. |
| Recuperar por destino e chave | iOS reconciliado pelo recibo original; mobile não repetiu. | Verificar APIs autoritativas Shorebird/lojas e efeito incerto sob autorização própria. |
| Persistir intenção e confirmação | Estado/journal/outbox avançaram juntos. | Ensaiar conflito, resposta perdida, recuperação sem reset, retenção e armazenamento. |
| Confirmar conteúdo e conservar previews | Hashes ao vivo e snapshot anterior preservados. | Decidir hospedagem/acesso e verificar conteúdo no ambiente aprovado. |
| Separar corredores de prova | Web, XCArchive unsigned e recibos fictícios têm limites explícitos. | Confirmar base real, compatibilidade final, loja/testers e dispositivo; seguir a [referência 004](../../referencias/docs/004-shorebird-patch-e-elegibilidade.md). |
| Logs acionáveis sem segredos | JSONL com ação, fonte, resultado e validação seguinte. | Definir acesso, retenção e campos autorizados com a equipe. |

Nenhuma proposta foi aplicada na Amulets. Build, patch Shorebird, envio à loja, disponibilidade para testers e validação em Production continuam sendo resultados distintos.

## Continuidade do log

Cada linha contém `timestamp_utc`, `recorded_at_utc`, `event_timestamp_utc`, `timestamp_basis`, `historical_backfill`, `action`, `source_evidence`, `result`, `scope`, `lesson` e `next_validation`. `scope.actual` descreve ações executadas; `scope.simulated` descreve fixtures, papéis e efeitos fictícios.

Acrescentar eventos ao fim, sem apagar histórico. Eventos novos usam `historical_backfill=false` e hora UTC observada. Quando uma conclusão mudar, acrescentar correção referenciando a anterior. Registrar falhas/cancelamentos. Não copiar tokens, bancos SQLite, credenciais ou dados de participantes/canais privados.
