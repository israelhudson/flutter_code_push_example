# Patch Android local após a entrega aprovada

Este adaptador registra a execução local autorizada da POC. Ele **não executa `shorebird patch`, promoção, rollback ou publicação em loja**. A Release no GitHub deve estar concluída com dois avais e comando final antes da intenção mobile. A conta executora é conferida diretamente por `gh api user`: deve ser `User` e estar em `policy.operators`. Variáveis locais `GITHUB_ACTOR` não autenticam ninguém. Na política atual, Israel prepara RCs e executa o adaptador; Israel e Fabrícia aprovam, e qualquer um dos dois pode dar o comando final. Os operadores do Amulets ainda dependem de decisão de governança com Samuel.

## O que fica congelado e o que é acrescentado

A tag identifica a entrega e o SHA aprovado. Android mantém sua própria base `1.1.0+2`; iOS e web não herdam o número do patch Android. O plano `mobile_execution_plan` faz parte do relatório aprovado: app, plataforma, release ID do provedor, versão/revisão Flutter, geração em `staging`, promoção para `stable` e validação obrigatória no dispositivo.

O plano não contém um número futuro de patch. O SHA Git original da base é desconhecido (`base_git_sha: null`); isso permanece explícito. A consulta ao provedor confirma a base e sua toolchain. O relatório aprovado, a intenção GitHub e o recibo original GitHub permanecem byte a byte preservados.

`record.mobile_delivery` é separado e contém intenção, executor verificado, estados, recibo e anexo. Somente depois de geração, execução em staging e confirmação stable, o corpo da Release recebe uma seção determinística. O corpo anterior deve permanecer prefixo byte-exato. Slack deve ler o resultado mobile confirmado desse recibo sem reescrever o conteúdo/hash de mensagens históricas.

## Preparar o checkout e os arquivos

Execute no checkout isolado da POC, exatamente no SHA da RC aprovada. Não use o checkout Amulets. Confira `shorebird.yaml` e o app `bc6a30bd-0768-4326-8885-8be69c59aed2`. O bridge recusa HEAD diferente, alterações rastreadas, código/assets não rastreados e `pubspec_overrides.yaml` local escondido por ignore. Logs brutos ficam somente em `build/` privado; o bridge guarda hashes e dados permitidos, nunca stdout bruto, conta Shorebird/e-mail, tokens ou URLs assinadas.

Nos comandos abaixo, `TAG`, `SHA`, `INTENT` e `N` são placeholders que devem vir da candidata/recibo. `N` **sempre vem do servidor**, nunca de previsão. `OUT` é uma pasta de evidências privada por rodada. Os arquivos de consulta devem ser capturados pelo bridge; não montar manualmente um wrapper em torno de JSON de outra base.

```bash
python3 tools/delivery/shorebird_delivery.py capture-provider \
  --target delivery/shorebird-lab-target.json --kind release \
  --output OUT/release-info.json
python3 tools/delivery/shorebird_delivery.py capture-provider \
  --target delivery/shorebird-lab-target.json --kind list \
  --output OUT/patches-before.json
```

Faça dry-run no SHA aprovado, sem `latest` nem bypass nativo/assets, e salve stdout/stderr e exit code. Esse comando não envia patch:

```bash
shorebird patch android --release-version 1.1.0+2 --track staging --dry-run --json
```

O sucesso do dry-run não prova upload; o servidor pode fazer verificações adicionais. `MaterialIcons-Regular.otf` também é asset: adicionar um ícone apenas em Dart altera a fonte reduzida. Nesta rodada, a comparação de assets falhou por ícones novos, foi corrigida conservando os ícones da base e passou sem ignorar o alerta.

Transforme os logs privados e o AAB produzido em prova de operador local:

```bash
python3 tools/delivery/shorebird_delivery.py command-proof \
  --target delivery/shorebird-lab-target.json --source-sha SHA --dry-run \
  --exit-code 0 --stdout OUT/dry-run.stdout.log --stderr OUT/dry-run.stderr.log \
  --aab build/app/outputs/bundle/release/app-release.aab \
  --output OUT/dry-run-proof.json
python3 tools/delivery/shorebird_delivery.py plan --candidate-tag TAG \
  --release-info OUT/release-info.json --patches-before OUT/patches-before.json \
  --dry-run-proof OUT/dry-run-proof.json --output OUT/mobile-intent.json
```

O resultado de `plan` contém `intent.intent_id`. Ele não autoriza repetir upload. Antes de executar o CLI uma única vez:

```bash
python3 tools/delivery/shorebird_delivery.py begin-upload \
  --candidate-tag TAG --intent-id INTENT --output OUT/before-upload.json
```

O estado remoto é gravado como `upload_response_unknown` antes da execução externa. Se esse comando ou o upload perderem a resposta, consultar e reconciliar; não executar outro upload automaticamente.

## Gerar, confirmar staging e vincular o código

Depois do checkpoint e da autorização desta entrega, o operador executa uma vez e salva os logs/exit code:

```bash
shorebird patch android --release-version 1.1.0+2 --track staging --json
```

O CLI instalado não emite um envelope JSON final com o número. Consulte novamente a lista:

```bash
python3 tools/delivery/shorebird_delivery.py capture-provider \
  --target delivery/shorebird-lab-target.json --kind list \
  --output OUT/patches-after.json
```

Exija exatamente um novo par ID/número, com todo o histórico anterior preservado. Zero ou vários novos patches deixam o resultado não confirmado. Para o `N` confirmado, consulte `info` e capture o AAB final da geração:

```bash
python3 tools/delivery/shorebird_delivery.py capture-provider \
  --target delivery/shorebird-lab-target.json --kind info --patch-number N \
  --output OUT/staging-info.json
python3 tools/delivery/shorebird_delivery.py command-proof \
  --target delivery/shorebird-lab-target.json --source-sha SHA --intent-id INTENT \
  --exit-code 0 --stdout OUT/generation.stdout.log --stderr OUT/generation.stderr.log \
  --aab build/app/outputs/bundle/release/app-release.aab \
  --output OUT/generation-proof.json
python3 tools/delivery/shorebird_delivery.py record-receipt --candidate-tag TAG \
  --patches-after OUT/patches-after.json --staging-info OUT/staging-info.json \
  --generation-proof OUT/generation-proof.json --output OUT/staging-receipt.json
```

O bridge exige os três SHA-256 dos `libapp.so` completos do AAB final: `arm`, `aarch64` e `x86_64`. Esses hashes devem coincidir com `patches info.artifacts[].hash`; o hash do arquivo de diff não substitui essa prova. O patch observado em outra geração/código é recusado mesmo se seu número parecer correto. A base e os comandos são explícitos; a CLI não fornece `app_id`/`release_id` dentro do patch JSON. O wrapper captura esses parâmetros da consulta, portanto é evidência de operador/CLI e não atestado independente de SHA Git pelo provedor. Não alterar os arquivos de prova.

## Validar no dispositivo antes de stable

Use o emulador dedicado `LAB_Shorebird_POC_API35`, serial `emulator-5558`, ou outro Android autorizado. Instale o preview da base exata no track de staging:

```bash
shorebird preview --app-id bc6a30bd-0768-4326-8885-8be69c59aed2 \
  --platform android --release-version 1.1.0+2 --device-id emulator-5558 --track staging
```

`preview` fica em log stream. Observe o download, encerre somente a sessão do preview quando houver prova suficiente, feche/reabra o app e confirme o patch `N` em execução. Download ou upload não prova que o patch foi executado. Guarde screenshot, logs do SDK e PIDs distintos antes/depois do cold restart.

O arquivo `OUT/device-proof.json` exige estes campos exatos, sem extras. Os hashes são dos arquivos reais; PIDs e número observado devem ser medidos:

```json
{
  "schema": 1,
  "intent_id": "INTENT",
  "source_sha": "SHA",
  "target": {
    "app_id": "bc6a30bd-0768-4326-8885-8be69c59aed2",
    "platform": "android",
    "release_version": "1.1.0+2",
    "provider_release_id": 776887,
    "flutter_revision": "c2515c46c7fca511e39735a615f0f12f3dca6230"
  },
  "track": "staging",
  "patch_number": 0,
  "observed_patch_number": 0,
  "cold_restart": true,
  "device": "emulator-5558",
  "pid_before": 0,
  "pid_after": 0,
  "screenshot_sha256": "SHA256",
  "sdk_log_sha256": "SHA256"
}
```

Os zeros e strings acima são placeholders inválidos; substituir por valores comprovados. Grave a prova no journal **antes** de promover:

```bash
python3 tools/delivery/shorebird_delivery.py record-receipt --candidate-tag TAG \
  --patches-after OUT/patches-after.json --staging-info OUT/staging-info.json \
  --generation-proof OUT/generation-proof.json --device-proof OUT/device-proof.json \
  --output OUT/device-receipt.json
```

## Confirmar stable e acrescentar o changelog

Depois da prova de staging, o operador pode mover somente o patch confirmado da POC para stable. Não usar `latest`, nem aplicar isso ao Amulets:

```bash
shorebird patches set-track --app-id bc6a30bd-0768-4326-8885-8be69c59aed2 \
  --release 1.1.0+2 --patch N --track stable --json
python3 tools/delivery/shorebird_delivery.py capture-provider \
  --target delivery/shorebird-lab-target.json --kind info --patch-number N \
  --output OUT/stable-info.json
python3 tools/delivery/shorebird_delivery.py record-receipt --candidate-tag TAG \
  --patches-after OUT/patches-after.json --staging-info OUT/staging-info.json \
  --generation-proof OUT/generation-proof.json --device-proof OUT/device-proof.json \
  --stable-info OUT/stable-info.json --output OUT/stable-receipt.json
python3 tools/delivery/shorebird_delivery.py append-release --candidate-tag TAG \
  --output OUT/release-extension-proof.json
```

O bridge só permite acrescentar o body esperado à Release original. Divergência de tag, SHA, ID, título, status ou body bloqueia a operação. Reserva de anexo e estado desconhecido são persistidos antes de PATCH; GET confirma depois. A resposta perdida não gera outro PATCH. A autoridade vem do resultado CAS da reserva, não de uma leitura anterior: outro writer ou resposta CAS perdida bloqueiam novo efeito.

GitHub Release PATCH **não oferece CAS**. GET antes/depois detecta alterações observadas, mas não impede edição manual no intervalo GET→PATCH. Durante o anexo, serialize operadores e evite editar manualmente a Release. Esse limite permanece documentado; o bridge não afirma atomicidade global. Uma nova RC também é bloqueada enquanto houver intenção mobile incompleta, para manter a reconciliação possível.

## Leituras e lições para o Amulets

- Tag RC e estável identificam entrega e preservam histórico; o número do patch pertence a app/plataforma/base.
- Aprovar e dar comando final autorizam a entrega específica; não autorizam repetir upload após falha ambígua.
- Compare assets reais: novos ícones podem alterar fonte mesmo sem modificar `assets/`.
- Distinga staging gerado, patch executado após cold restart, stable confirmado e distribuição em loja.
- Logs de conta/autenticação e URLs assinadas são privados. Compartilhe somente cópias saneadas e prova com allowlist.
- O Amulets precisa decidir operadores de RC, executores mobile, concorrência por base, credenciais CI, dispositivos de validação e tratamento de PATCH sem CAS antes de adotar esse adaptador.

Fontes: [Shorebird — Create a Patch](https://docs.shorebird.dev/code-push/patch/), [Staging Patches](https://docs.shorebird.dev/code-push/guides/staging-patches/), source/ajuda da CLI `1.6.116`, referência `004-shorebird-patch-e-elegibilidade.md` deste projeto.
