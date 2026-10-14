# RC2: preservar preview quando Flutter regenera a versão do cache

## Incidente

Run [38493768059](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38493768059)
criou `poc-v1.14.0-rc.2` no SHA `e36098f65e99592f85870c566591678d20cb2759`,
o mesmo código da RC1. Testes e build passaram; importação do preview bloqueou
bytes divergentes antes do registro da candidata e do envio ao Slack.

Comparação dos artefatos RC1/RC2: o único arquivo do app diferente era
`flutter_bootstrap.js`, apenas o valor numérico `serviceWorkerVersion`:
`1599534818` e `806451507`. O hash do app mudou como consequência;
inputs, fingerprints e todos os demais arquivos do app permaneceram iguais.

## Correção limitada ao fluxo Slack

O importador conserva seu comportamento estrito por padrão. O workflow Slack
pode passar `--allow-flutter-cache-version`: exige identidades de fonte/build
iguais e presentes, a mesma lista de arquivos, exatamente um campo numérico de
versão em cada bootstrap, igualdade byte a byte após neutralizar apenas esse
campo para comparação e todos os outros arquivos iguais, incluindo o worker.
Qualquer outra divergência bloqueia. Nenhum arquivo é normalizado no disco.

O preview existente, seu wrapper, hashes e manifesto são reutilizados intactos.
`reuse_evidence` no artefato `poc-web-proof` registra os dois hashes e a causa.
A verificação HTTP e o registro da candidata usam os hashes do preview preservado.
Não sobrescrever preview nem mover/apagar tags para recuperar essa falha.

## Retomada

Integrar o PR de ferramentas na `slack-main`, mantendo o código da release branch.
Executar novamente preparação `1.14.0`, título `otimizacao`, escopo `github_test`.
Como a tentativa anterior não registrou RC2 no backend, o planejamento volta a
RC2 e verifica a tag já existente no mesmo SHA. Não reexecutar workflow antigo
esperando que ele carregue código novo. Se existir candidata registrada ou envio
incerto, reconciliar antes de iniciar nova preparação.

## Validação e limites

Testes cobrem reutilização sem alteração de bytes/manifesto, opt-in obrigatório,
loader/worker alterados, inputs divergentes, campo duplicado, worker ou identidade
ausentes. O ensaio local com os artefatos reais preservou o snapshot original.
Logs privados: diretório `rc2-38493768059` dentro de
`/Users/israelhudson/Documents/Codex/2026-10-13/slack-supabase-poc/`.
O resultado da nova execução deve ser registrado ali após concluir.
Essa recuperação não aprova nem publica automaticamente a candidata.

## Compatibilidade explícita das ferramentas

A retomada 38494853447 encontrou também a proteção que compara as ferramentas
atuais às congeladas na fonte. Uma recuperação aprovada usa
`delivery/poc-preview-recovery.json`: vincula exclusivamente RC2, escopo, SHA e
objetos Git exatos de fonte/ferramentas (.github, deploy, tools/delivery, política
e supabase). Qualquer nova alteração nesses objetos invalida o registro; outras
RCs não recebem exceção. O backend deve ser idêntico nos dois lados. O registro
é lido do HEAD confiável e copiado para `tooling-recovery.json` no artefato.
Não editar a fonte ou mover tags para satisfazer essa comparação.
