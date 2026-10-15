# Versões e publicação

A Release se chama **Versão X.Y.Z**. O cartão usa a mesma tabela e é atualizado no lugar, mantendo sua mensagem e os aceites. O nome do bot e os identificadores técnicos `poc-*` permanecem por compatibilidade; a apresentação deixa de usar o prefixo “POC Slack”. Isso não amplia a autorização para distribuir aplicativos.

| Destino | Fonte da identidade | Resultado exibido |
|---|---|---|
| GitHub | Tag final e Release conferidas na API | Release publicada |
| Web | metadata.json, manifesto e hashes do preview congelado | Preview validado; não comprova produção |
| Android | Recibo anexado à Release, vinculado à candidata e ao SHA | Base + build (patch N), track e confirmação de execução |
| iOS | Recibo específico de iOS, vinculado à mesma candidata | Base + build (patch N); sem recibo, Não validada |

No Android, base + build correspondem a versionName + versionCode. No iOS, correspondem à versão e ao build do aplicativo. O número de patch Shorebird é separado, por plataforma e base: nunca copiar o patch Android para iOS. Usar `1.1.0+2 (patch 4)` evita confundir patch com build.

## Evidência da 1.15.1

- GitHub: `poc-v1.15.1`; preservar também `poc-v1.15.1-rc.1`.
- Web: `1.1.0+2`, preview existente, sem comprovar produção.
- Android: `1.1.0+2 (patch 4)`, staging, execução comprovada anteriormente em emulador.
- iOS: não validado; nenhum número inventado.

O recibo é um resultado observado no momento registrado. Exibir a tabela não executa Shorebird, não altera tracks e não comprova instalação atual em todos os dispositivos.

## Validação sem novos artefatos de aplicação

`scope=github_test` permite a publicação da Release GitHub. `validation_mode=controls_only` pula build e preview. Nenhum deles publica patches.

Para corrigir uma Release já aprovada, usar `finalize_existing=true` no workflow de publicação, sem preparar outra candidata. Não alterar o escopo ou modo de validação congelados na candidata antiga: a operação apenas relê evidências existentes. Nos testes de novas candidatas, usar `github_test` + `controls_only`.

A correção exige candidata publicada, identidade das tags preservada, descrição conhecida e credencial exclusiva de publicação. Grava recibos de apresentação, atualização da Release e atualização do cartão. Uma repetição não recria a Release: confere o estado e atualiza a mesma mensagem. Falha no Slack pode ser recuperada sem repetir a publicação GitHub.

## Integridade

Recibos devem coincidir em candidata, versão, RC, tag final, SHA e digest do relatório. O hash do arquivo precisa coincidir com o anexo GitHub. Dados divergentes bloqueiam a atualização. Ausência de recibo exibe “Não validada”, nunca sucesso.

O relatório aprovado e seu digest, os aceites, os anexos, as tags e o recibo original de publicação não são reescritos. LAB, Issue e Amulets não recebem mudanças de credenciais ou de roteamento nesta atualização.
