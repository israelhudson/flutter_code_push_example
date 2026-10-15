# Rodada com preview, aceites manuais e Android em staging

Rodada concluída: **1.15.5**, em **15/10/2026**. O texto do aplicativo identifica essa entrega, para
comparar o preview com o Android. Israel recebe duas DMs e decide manualmente
como responsável técnico e de negócio. São dois papéis, não duas pessoas.

## Preparação usada na rodada 1.15.5

O comando abaixo registra a preparação histórica. **Não o reexecute para criar
outra entrega 1.15.5**: essa versão já foi publicada e deve continuar preservada.
Para novas versões, usar [os nomes oficiais](NOMES-OFICIAIS.md), escolhidos pela
esteira; o formulário continua recebendo a versão sem `v` e sem sufixo RC.

```bash
gh workflow run delivery-prepare.yml \
  --repo israelhudson/flutter_code_push_example --ref main \
  -f version=1.15.5 \
  -f title="Preview e teste Android em staging" \
  -f scope=github -f validation_mode=full -f patch_mode=android_staging
```

O comando isolado não comprova conclusão; as provas reais estão no
[resultado abaixo](#resultado-real-da-1155). O preparo congela
o código e o plano Android, cria a tag/prerelease, testa e publica o preview,
confere seus hashes e entrega o cartão de acompanhamento e as duas DMs.
`controls_only` ou `scope=none` são recusados quando `patch_mode=android_staging`.
Os modos anteriores continuam disponíveis com `patch_mode=none`.

Depois dos dois aceites, o worker confirma o histórico e dispara a publicação
GitHub. Essa execução não contém uma credencial Shorebird. Ela cria a tag final
no código aprovado e preserva a tag candidata. O cartão diferencia a Release
GitHub publicada do patch Android ainda pendente.

## Android é uma etapa local explícita

O operador segue [a ponte staging](ANDROID-STAGING.md), no checkout limpo do SHA
aprovado. O executável verifica o histórico de decisões e a execução GitHub real,
faz dry-run e reserva uma tentativa antes do upload. Usa somente a base Android
`1.1.0+2` do app deste repositório e `--track staging`. O número do patch é lido do
provedor; não é escolhido antecipadamente.

Depois do recibo real anexado à Release:

```bash
gh workflow run delivery-worker.yml \
  --repo israelhudson/flutter_code_push_example --ref main \
  -f refresh_candidate=ID_REAL_DA_CANDIDATA
```

O worker confere o anexo e seus hashes, atualiza somente o corpo conhecido da
Release e os cartões. Edição manual divergente bloqueia a atualização automática.
Não muda tags, aceites, manifesto ou o recibo original de publicação. O PATCH do
GitHub não oferece compare-and-swap: operadores devem evitar edição concorrente.

## Novidades no Slack

O cartão original do canal e as DMs continuam sendo editados no mesmo lugar.
Avisos curtos na thread, também exibidos no canal, sinalizam início/fim da
publicação GitHub, rejeição/cancelamento e o primeiro recibo Android staging
confirmado. Cada aviso tem tarefa e recibo próprios na outbox existente.
Não há `@channel`, `@here` ou aviso a cada job. Atualizar a tabela novamente não
deve repetir o aviso do mesmo resultado.

Esses avisos criam mensagens novas; não podem sobrepor as preferências pessoais
de um canal silenciado. Enviar ao Slack não comprova que o destinatário leu.

## Limites que devem aparecer no resultado

- Preview Web é uma visualização do código congelado, não deploy Web de produção.
- Patch confirmado em staging não comprova execução após reinício no Android.
- Não há promoção para stable, patch iOS ou upload em lojas nesta rodada.
- Uma resposta perdida não autoriza repetir upload: reconciliar a mesma intenção.
- O projeto e o bot da Amulets não são alterados por este ensaio.

Guardar logs privados, hashes, recibos, prints do preview, GitHub e Slack por
marco. Só registrar sucesso quando existir a evidência correspondente.

## Resultado real da 1.15.5

O [PR #64](https://github.com/israelhudson/flutter_code_push_example/pull/64)
entrou na `main`, commit `2b2ea070fcb7c9cad71c3f63bdd252765285ba78`. Esta rodada
foi preparada antes da mudança de nomes; suas referências continuam
**`poc-release/1.15.5`**, **`poc-v1.15.5-rc.1`** e **`poc-v1.15.5`**.
Não foram renomeadas para representar o padrão novo.

| Etapa | Evidência real | Resultado |
|---|---|---|
| Preparação e Web | [Run 38784099405](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38784099405) | Preview do SHA aprovado publicado e conferido por hashes. |
| Avaliação | [Histórico da candidata](https://github.com/israelhudson/flutter_code_push_example/tree/codex/delivery-history/candidates/delivery-b9b75f1922de4a8b8461dfbea819fdf5) | Israel deu manualmente os dois aceites nas DMs; manifesto e eventos foram preservados. |
| Publicação GitHub | [Run 38785467883](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38785467883) | Disparo automático depois dos aceites; Release final publicada no mesmo SHA da RC. |
| Android local | [Recibo anexado](https://github.com/israelhudson/flutter_code_push_example/releases/download/poc-v1.15.5/platform-receipt-android.json) | Base `1.1.0+2`, patch `5`, ID `722743`, confirmado em staging pelos três hashes do AAB. |
| Atualização GitHub/Slack | [Run 38786116974](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38786116974) | Tabela e cartão atualizados; um único aviso Android, três marcos no total. |

A [Release final](https://github.com/israelhudson/flutter_code_push_example/releases/tag/poc-v1.15.5)
mostra **`1.1.0+2 (patch 5)`** e **“Patch em staging; execução em dispositivo não comprovada”**.
O mesmo cartão do canal e as duas DMs foram atualizados no lugar. Não houve
menção coletiva. Os patches `1`, `2` e `3` em stable mantiveram seus dados,
artefatos e tracks; o patch `4` anterior também foi preservado.

O refresh conservou o ID da Release, as duas tags e os eventos `0` a `4`,
acrescentando o evento Android sem reescrever decisões. A outbox terminou sem
pendências e o banco manteve três tabelas de aplicação. Os controles de execução
e publicação foram pausados depois da conferência; a rodada não deixou uma
publicação permanentemente liberada.

**Limites da prova:** dois papéis solo não são duas pessoas independentes;
upload em staging não é execução no dispositivo; a ponte Android foi local,
não um job mobile em CI. Não houve promoção stable, publicação iOS, envio a
lojas, deploy Web de produção ou alteração na Amulets.

Logs brutos, capturas completas e snapshots privados foram guardados fora do
repositório. Este resumo aponta somente para runs, histórico e recibo de
resultado, sem copiar credenciais ou payloads privados. A alteração dos nomes
para próximas versões não executa uma nova rodada nem modifica esta prova.

## Antes de aplicar na Amulets

Para a Amulets, investigar em separado o uso de tracks a partir da main/release
real, bases por plataforma, configuração dos aparelhos de QA e bloqueios contra
promoção automática. Um track isola distribuição de patches; não escolhe backend,
branch Git ou público de TestFlight. A investigação foi solicitada no chat
“FORK-Planejar esteira de distribuição (2)”, sem autorização para execução remota.

Fontes: [Shorebird — staging](https://docs.shorebird.dev/code-push/guides/staging-patches/),
[Slack — respostas no canal](https://docs.slack.dev/reference/methods/chat.postMessage/),
[Slack — canais silenciados](https://slack.com/help/articles/204411433-Mute-channels-and-direct-messages).
