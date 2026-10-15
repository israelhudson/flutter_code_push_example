# Android staging após os dois aceites v2

Esta ponte **local** usa somente o histórico v2 em `codex/delivery-history`.
Não usa o journal LAB, não cria tabelas e não aprova por ninguém. Os dois aceites
continuam manuais, pelas DMs. O ensaio solo permite Israel nos dois papéis;
isso comprova duas decisões de papel, não independência entre duas pessoas.

## O que a candidata autoriza

O manifesto precisa congelar, antes dos aceites:

```json
{
  "schema": "delivery-android-staging-v1",
  "target": "conteúdo completo de delivery/shorebird-lab-target.json",
  "execution": "local_operator_after_github_publication",
  "track": "staging",
  "stable_authorized": false
}
```

No JSON real, `target` é o objeto completo, não a string ilustrativa acima.
Embora o arquivo histórico do alvo cite `promotion_track: stable`, o envelope
v2 autoriza **somente staging**. O executável não possui comando de promoção.

Alvo exclusivo: Android, app `bc6a30bd-0768-4326-8885-8be69c59aed2`,
base `1.1.0+2`, release do provedor `776887`, Flutter `3.44.9`, revisão
`c2515c46c7fca511e39735a615f0f12f3dca6230`. Não usar esse alvo na Amulets.
O número do patch vem do servidor depois do upload; não é previsto no plano.

## Executar uma vez

Após os aceites e a Release GitHub final, use um checkout isolado e limpo,
exatamente no `source_sha` da candidata. A conta real de `gh api user` precisa
ser `israelhudson`, ID `18661493`. Variáveis como `GITHUB_ACTOR` não autorizam.
Os comandos leem manifesto e eventos em um commit imutável, os dois aceites,
a execução bem-sucedida de `delivery-publish.yml` na `main`, a Release final
e as tags RC/final no mesmo código. Qualquer divergência bloqueia o upload.

Nos comandos, substitua `ID` pelo `delivery-...` real e `PASTA_PRIVADA` por uma
pasta nova, fora de qualquer checkout. São comandos locais; não disparam jobs.

```bash
python3 tools/delivery/delivery_android_staging.py readiness \
  --candidate ID --output PASTA_PRIVADA

python3 tools/delivery/delivery_android_staging.py dry-run \
  --candidate ID --output PASTA_PRIVADA

python3 tools/delivery/delivery_android_staging.py upload \
  --candidate ID --output PASTA_PRIVADA
```

`readiness` não envia patch. `dry-run` compila e valida sem upload nem bypass
de assets/nativo. `upload` reconfere os logs e o AAB desse dry-run, consulta a
lista anterior e grava primeiro uma intenção **create-only** no GitHub.
Só uma reserva cuja resposta e bytes foram confirmados permite executar:

```bash
shorebird patch android --release-version 1.1.0+2 --track staging --json
```

Não execute esse comando novamente por conta própria após a ponte. Ela já o
executa uma vez. Depois, exige um único patch novo e os três hashes de
`libapp.so` do AAB iguais aos retornados pelo provedor. Só então registra:

- `candidates/ID/android-staging-intent.json`: tentativa, plano, autorização,
  dry-run e lista anterior; nunca substituída.
- `candidates/ID/android-staging-receipt.json`: resultado confirmado,
  sem stdout bruto; nunca substituído.
- Asset `platform-receipt-android.json` na Release final: mesmo resultado,
  consumido pela tabela de versões. Um asset diferente nunca é sobrescrito.

## Falha, resposta perdida e recuperação

Uma intenção existente impede **qualquer novo upload da mesma candidata**.
Se caiu a rede, o processo ou o anexo, preserve a mesma pasta e use:

```bash
python3 tools/delivery/delivery_android_staging.py reconcile \
  --candidate ID --output PASTA_PRIVADA
```

Esse comando nunca chama `shorebird patch`. Exige prova local de geração
concluída, o mesmo código/intenção e os hashes dos três artefatos; o simples
aparecimento de um número novo não basta. Zero ou vários patches novos,
hashes diferentes ou prova perdida permanecem **não confirmados**. Se o CLI
não concluiu com sucesso ou perdeu a resposta antes de salvar essa prova,
a recuperação exige investigação; a ponte não fabrica sucesso nem reenvia.

Outra intenção v2 sem recibo bloqueia um novo upload da base. O operador
também precisa impedir comandos Shorebird concorrentes fora desta ponte:
ela não impõe um lock global ao provedor. Uma intenção sem resultado pode
continuar bloqueando até investigação; não apague registros para contornar.

## O que o recibo não afirma

`uploaded: true` significa patch confirmado em **staging**. Dispositivo,
cold restart, `stable`, lojas e iOS não ficam comprovados. Neste primeiro
adaptador, `device_validation` é explicitamente falso. A tabela informa
“execução em dispositivo não comprovada”. Validar dispositivo e promover
stable são próximos escopos, com autorização e provas próprias.

O provedor não atesta um SHA Git: o vínculo é evidência do operador, CLI e AAB,
checado contra os hashes do provedor. Logs brutos ficam somente na pasta
privada com permissão restrita; o journal e o asset usam campos permitidos.
O script não edita o corpo da Release nem as mensagens Slack: o fluxo de
apresentação consome o asset e atualiza esses modelos separadamente.

## Verificação

```bash
python3 -m unittest discover -s tests/delivery \
  -p 'test_poc_delivery_android_staging.py' -v
```

Os testes são offline e usam dados sintéticos para autorização, rejeição,
dois papéis solo, SHA/tags divergentes, repetição, resposta perdida e hashes.
Eles não comprovam geração real. A rodada real precisa guardar seus próprios
logs, recibos e prints, preservando as tags e os aceites anteriores.
