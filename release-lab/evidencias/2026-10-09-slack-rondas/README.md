# Evidências dos dois ensaios com Slack

Em 9 de outubro de 2026 UTC, o laboratório concluiu duas jornadas reais no GitHub: **B, 1.7.0 feliz**, com RC1, dois avais e comando final; e **A, 1.8.0**, com RC1 recusada, correção por PR, RC2 com novos avais, publicação estável e retorno da correção à main. Foram confirmadas três tags RC, duas Releases estáveis e 13 avisos reais do bot Slack. A publicação ficou limitada à tag e Release GitHub; o web serviu como preview. Nenhum app mobile ou patch Shorebird foi distribuído.

## Resultado e identidades

| Jornada | Candidata e source | Resultado |
| --- | --- | --- |
| B feliz | v1.7.0-rc.1 → 22b29663d85724ba619600766c78ff38cd3456ec | [v1.7.0](https://github.com/israelhudson/flutter_code_push_example/releases/tag/v1.7.0), Release 407416169, publicada 01:46:39Z; draft=false e prerelease=false |
| A recusa | v1.8.0-rc.1 → 22b29663d85724ba619600766c78ff38cd3456ec | Review oficial de Fabrícia recusada; run cancelada operacionalmente, sem promoção; candidata depois superseded, tag preservada |
| A correção | v1.8.0-rc.2 → c8d8f337ee390755bcff795d558f8c6f6f19c35b | [v1.8.0](https://github.com/israelhudson/flutter_code_push_example/releases/tag/v1.8.0), Release 407429740, publicada 02:17:15Z; draft=false e prerelease=false |

As cinco tags foram consultadas novamente: RC1 1.7, stable 1.7 e RC1 1.8 mantêm source 22b29663; RC2 1.8 e stable 1.8 apontam para c8d8f337. Os diretórios históricos 01–04 conservam os nomes do mapeamento inicial. O usuário promoveu 1.7 antes da recusa planejada; [scenario-mapping-change.json](scenario-mapping-change.json) registra a troca de papéis. Não foi alterada uma candidata promovida.

Os registros de 1.7 mostram decisões manuais do usuário nas duas contas e comando final. A recusa de 1.8, as revisões dos PRs e os novos avais/comando final da RC2 foram operados pelo **Codex LAB**, autorizado por Israel, na conta Israel via IAB e na conta Fabrícia (`fahnassau30`) via Safari. Os comentários declaram esse caráter. Os dois logins e reviews são reais, mas não estabelecem aceite humano independente. Os novos recibos trazem `review_independence_verified:false`, `distribution_performed:false` e `publication_mode:github_release_only`. `result_simulated:false` qualifica a publicação GitHub real, sem ampliá-la para mobile.

## Correção e retorno

[PR19](https://github.com/israelhudson/flutter_code_push_example/pull/19) integrou os avisos Slack à main 22b29663 em 01:39:53Z, com review de Fabrícia no head exato e CI com 384 testes. A recusa da RC1 revelou que seu gate ficou vermelho, mas o outro gate permaneceu esperando. Israel cancelou a execução via CLI para encerrá-la; o observer consolidou a recusa a partir da review oficial. **A recusa foi esperada, mas o fechamento manual foi necessário.** Não houve aval de Israel nem promoção dessa RC.

[PR21](https://github.com/israelhudson/flutter_code_push_example/pull/21) corrigiu o fechamento das esperas após recusa oficial e os recibos concorrentes Slack. Foi integrado como fbcf012 em 02:05:16Z, com review exata de Fabrícia e CI com 404 testes. [PR20](https://github.com/israelhudson/flutter_code_push_example/pull/20) trocou o título para “Laboratório de entregas”, incorporou essa main confiável e foi integrado em release/1.8.0 como c8d8f337 em 02:08:04Z, com nova review exata e CI com 404 testes. Antes da RC2, foram confirmados **36 blobs iguais** em `.github/` inteira, `delivery/release-lab-policy.json`, `deploy/` e `tools/delivery/`: [prova](13-pr20-release-correction-merged/trusted-tooling-comparison-actual-merge.json). O fechamento novo após recusa tem testes locais e CI; **a nova via de recusa não foi reexercitada remotamente**.

RC2 nasceu em 02:09:06.010762Z com source c8d8f337, tooling fbcf012 e base 22b29663. Seu [preview](https://israelhudson.github.io/flutter_code_push_example/snapshots/c8d8f337ee390755bcff795d558f8c6f6f19c35b/) passou na verificação HTTP dos seis arquivos pelo workflow. Hash web: `00063b7f8fa10405f43fce2f458a42d4ff0d762898e11ef5a8725a4569675069`; manifest: `55bbe8d17dab9d2a6e798160dba682e1662d8e935c327d78f6dc93b536412853`. O executor root confirmou visualmente o título corrigido, a alternância manual dos temas e o retorno para claro no reload. As capturas autorizadas estão em [screenshots](screenshots).

[PR22](https://github.com/israelhudson/flutter_code_push_example/pull/22) foi revisado por Fabrícia em 02:18:57Z (review 5464978904, head c8d8f337) e integrado à main cf6d6fa90e228ec10cc6d0d7a204da756d784514 em 02:19:08Z, **depois da promoção**. A main tem c8d8f337 como pai direto e toda a árvore igual à release, tree `337e9cd9a1d6298b20ba60d939a9078eb81f7ca1`: [prova](21-pr22-backmerge-final/backmerge-proof.json).

## Novos avais e relatório congelado

As capturas fixas da RC2 demonstram 0/2, [1/2](17-a18-rc2-first-approval/state.snapshot.json) e [2/2](18-a18-rc2-two-of-two-before-final/state.snapshot.json), sem herança da RC1:

| Progresso | Commit da branch de estado | Estado |
| --- | --- | --- |
| 0/2 | 8bf2c4d7e5537345c26aba217087ae8b9291adf2 | awaiting_approvals |
| 1/2 Israel | a034949681d3ed8a6a0ef004d1feae15a8a75ff8 | awaiting_approvals; recibo final ausente |
| 2/2 Israel + Fabrícia | a532ff55c2277ef0eee9a5fb4d5bf2aaf5027ad9 | awaiting_publish_authorization; recibo final ausente |
| Publicada | 77ace317c3812a81f2ca9f8fc2c02b46e60ce1a9 | completed, publication.status=completed, receipt presente |

Os recibos dos dois avais e do comando final vinculam run 37873174277, RC2/source c8d8f337 e report digest `1ed870ac2e509ac9c10b3b6dc4b09d201cf4fd7cdb7e4099805180a56f9bd71e`. Uma série de GETs não é uma transação atômica: na etapa 18, o estado fixo ainda aguardava o comando final, enquanto a resposta de jobs lida posteriormente já o exibia concluído. `captured_at` é o fim da coleta. `publication_intent` nulo no estado terminal não prova ausência de publicação: os campos finais são `publication` e `receipt`, junto às consultas de tag e Release.

O texto de comunicação da RC2 ficou **commits_fallback**, motivo `ai_not_configured`. Os PR20 e 21 foram coletados como contexto, mas suas seções literais somaram 744 + 1 + 741 = **1486 caracteres**, acima do limite 1400; o resultado agregado ficou vazio. O diagnóstico foi reproduzido com o código lido no tooling exato fbcf012, recalculando o mesmo digest: [diagnóstico](18-a18-rc2-two-of-two-before-final/communication-diagnostic/diagnostic.json). Nenhum resumo IA foi selecionado. Relatórios e fontes foram preservados sem revisão.

Na 1.7, o PR18 histórico congelado ainda descrevia Slack inativo; aquele texto não comprova o estado atual da integração. Para 1.8 RC1, o delta foi vazio e o texto selecionado foi “Sem commits adicionais desde a base registrada.”; PR18 não foi reutilizado.

## Slack confirmado

Canal C0C8DUJB52L, bot U0C750FTCS3, app A0C750DS05D. Os **13 recibos sent** da outbox foram corroborados por leitura independente do conector Slack, incluindo candidata, run e source. Este coletor apenas leu o canal. O horário da mensagem derivado de TS pode diferir alguns instantes da gravação do recibo `at`; [audit-current.json](audit-current.json) conserva ambos.

| Candidata | Evento | Mensagem real |
| --- | --- | --- |
| v1.7.0-rc.1 | candidate_available | [1791510213.021329](https://app.slack.com/archives/C0C8DUJB52L/p1791510213021329) |
| v1.7.0-rc.1 | approval_first | [1791510292.512419](https://app.slack.com/archives/C0C8DUJB52L/p1791510292512419) |
| v1.7.0-rc.1 | approval_second | [1791510318.577539](https://app.slack.com/archives/C0C8DUJB52L/p1791510318577539) |
| v1.7.0-rc.1 | approvals_complete | [1791510321.511589](https://app.slack.com/archives/C0C8DUJB52L/p1791510321511589) |
| v1.7.0-rc.1 | publication_completed | [1791510418.960699](https://app.slack.com/archives/C0C8DUJB52L/p1791510418960699) |
| v1.8.0-rc.1 | candidate_available | [1791510649.910329](https://app.slack.com/archives/C0C8DUJB52L/p1791510649910329) |
| v1.8.0-rc.1 | candidate_rejected | [1791510851.085829](https://app.slack.com/archives/C0C8DUJB52L/p1791510851085829) |
| v1.8.0-rc.1 | candidate_superseded | [1791511959.743739](https://app.slack.com/archives/C0C8DUJB52L/p1791511959743739) |
| v1.8.0-rc.2 | candidate_available | [1791511965.619999](https://app.slack.com/archives/C0C8DUJB52L/p1791511965619999) |
| v1.8.0-rc.2 | approval_first | [1791512050.620989](https://app.slack.com/archives/C0C8DUJB52L/p1791512050620989) |
| v1.8.0-rc.2 | approval_second | [1791512135.408919](https://app.slack.com/archives/C0C8DUJB52L/p1791512135408919) |
| v1.8.0-rc.2 | approvals_complete | [1791512139.599129](https://app.slack.com/archives/C0C8DUJB52L/p1791512139599129) |
| v1.8.0-rc.2 | publication_completed | [1791512253.460609](https://app.slack.com/archives/C0C8DUJB52L/p1791512253460609) |

## Logs e verificação

Foram coletadas 10 execuções, 49 logs reais de jobs, **1.966.637 bytes e 19.725 linhas**. Contagem: `len(raw_bytes.splitlines())`; inclui quebras de retorno de carro, não somente newline. Somente consultas de logs com status `collected` entram no total. Respostas de erro JSON com extensão `.log` não entram como logs. stdout e stderr originais, inclusive vazios, foram preservados byte a byte.

| Run | Conclusão GitHub | Coleta | Logs reais | Bytes | Linhas |
| --- | --- | --- | ---: | ---: | ---: |
| [37870620819](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37870620819) | success | complete | 1 | 136166 | 1088 |
| [37870868223](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37870868223) | success | complete | 16 | 487633 | 5323 |
| [37871436136](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37871436136) | cancelled | partial | 7 | 301731 | 3213 |
| [37871443874](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37871443874) | success | complete | 2 | 40937 | 455 |
| [37871944797](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37871944797) | success | complete | 2 | 40989 | 456 |
| [37872583739](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37872583739) | success | complete | 1 | 140396 | 1106 |
| [37872899430](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37872899430) | success | complete | 1 | 140503 | 1107 |
| [37873174277](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37873174277) | success | complete | 16 | 496717 | 5414 |
| [37873380596](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37873380596) | success | complete | 1 | 140610 | 1108 |
| [37873895168](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37873895168) | success | complete | 2 | 40955 | 455 |

PR19: 384 testes localmente (234.162s) e na CI (27.240s). PR21: 404 na CI (35.587s); PR20: 404 (35.801s); PR22: 404 (31.280s). Os checks incluíram Flutter analyze e Flutter test. Logs de CI preservam o checkout de merge do PR; as reviews estavam ligadas aos heads originais. Essas identidades estão separadas nas fontes.

Suítes locais posteriores permanecem separadas: **13 guard** (8.088s), **22 state** (15.143s) e **70 outbox** (6.086s). Outra rodada de 13 guard (11.535s) também foi preservada. Não foram somadas nem rotuladas como suíte integral local de 404 testes. O preflight de segurança está em [local-final/security-rc2-preflight](local-final/security-rc2-preflight).

Quatro consultas de logs da RC1 cancelada retornaram 404: jobs 113630935243, 113630935257, 113631748299 e 113631748455. Eram gates/promote/final sem runner e sem passos. A coleta dessa run é **partial**, com 7 logs reais, 5 jobs skipped e 860 bytes de JSON de erro + 52 bytes de stderr. Essas respostas foram guardadas sem inventar logs: [collection-summary](runs/37871436136-rejected-final/collection-summary.json).

Uma coleta HTTP local adicional do preview 1.7 ultrapassou 60 segundos: [registro](02-a-rc1-preview-http/capture-summary.json). Esse timeout permanece separado da verificação HTTP bem-sucedida pelo workflow.

## Lições e preservação

1. Recusa oficial, cancelamento operacional e falha técnica têm fontes e efeitos distintos. A rejeição esperada não torna a execução inteira verde.
2. Nova RC exige novo código, novo relatório, dois novos avais e comando final separado. Tags anteriores permanecem imutáveis.
3. O texto resumido dos PRs deve caber junto no limite 1400. O fallback congelado continua sendo evidência; fontes antigas não atestam comportamento atual.
4. Confirmação Slack depende de mensagem real e recibo e continua separada da realização da publicação.
5. Entrega/tag 1.8.0 não altera automaticamente pubspec 1.1.0+2. Identidades de web, app mobile e patch Shorebird permanecem próprias.
6. Evidência GitHub/web não atesta distribuição mobile nem aceite humano independente.

[timeline.json](timeline.json) organiza os marcos com fontes e URLs. [matrix-lessons.json](matrix-lessons.json) separa resultado, limites e lições. [manifest.json](manifest.json) e [SHA256SUMS](SHA256SUMS) registram tamanho e hash dos bytes. As fontes brutas em 00–21 e runs são históricas: estados intermediários e 404 esperados não serão reescritos.

O pacote é apensado apenas em `release-lab/evidencias/2026-10-09-slack-rondas/` da branch existente `codex/release-lab-state`, com commit descendente do HEAD atual e CAS sem force. O readback final confere cada blob e preserva todos os arquivos anteriores, em especial state e outbox.
