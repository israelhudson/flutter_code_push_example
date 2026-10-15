# Rodada com preview, aceites manuais e Android em staging

Alvo da rodada: **1.15.5**. O texto do aplicativo identifica essa entrega, para
comparar o preview com o Android. Israel recebe duas DMs e decide manualmente
como responsável técnico e de negócio. São dois papéis, não duas pessoas.

## Preparar pela main

```bash
gh workflow run delivery-prepare.yml \
  --repo israelhudson/flutter_code_push_example --ref main \
  -f version=1.15.5 \
  -f title="Preview e teste Android em staging" \
  -f scope=github -f validation_mode=full -f patch_mode=android_staging
```

O comando é o roteiro, não uma prova de que a rodada terminou. O preparo congela
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

Para a Amulets, investigar em separado o uso de tracks a partir da main/release
real, bases por plataforma, configuração dos aparelhos de QA e bloqueios contra
promoção automática. Um track isola distribuição de patches; não escolhe backend,
branch Git ou público de TestFlight. A investigação foi solicitada no chat
“FORK-Planejar esteira de distribuição (2)”, sem autorização para execução remota.

Fontes: [Shorebird — staging](https://docs.shorebird.dev/code-push/guides/staging-patches/),
[Slack — respostas no canal](https://docs.slack.dev/reference/methods/chat.postMessage/),
[Slack — canais silenciados](https://slack.com/help/articles/204411433-Mute-channels-and-direct-messages).
