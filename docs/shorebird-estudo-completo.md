# Shorebird — Estudo Completo e Comparação com o `amulets-mobile`

> **Como este documento foi produzido**
> A parte de fundamentos vem da POC deste repositório, **validada em dispositivo real**.
> A parte do `amulets-mobile` vem de uma auditoria automatizada de 7 dimensões, onde cada
> achado foi **verificado de forma adversarial** contra o arquivo real (233 confirmados,
> 8 corrigidos, 1 refutado). Nenhum comando `shorebird` foi executado no `amulets-mobile` —
> a análise foi **somente leitura**.

**Legenda de confiança usada no texto:**

| Marca | Significado |
|---|---|
| 🧪 | Validado na prática, nesta POC, em device/emulador real |
| ✅ | Verificado no código do `amulets-mobile`, com evidência em arquivo |
| 📖 | Documentação oficial do Shorebird |
| ⚠️ | Risco / armadilha |

---

## Sumário executivo

O `amulets-mobile` tem uma **automação de release madura** — muito além da nossa POC — mas
usa o Shorebird de forma **passiva e arriscada**:

**O que o amulets faz melhor que a POC:**
- Pipeline de CI que decide sozinho entre patch OTA e release de loja ✅
- Manifesto declarativo de patches (`shorebird-patches.json`) + script validado com teste ✅
- Flavors configurados nas três camadas (Gradle, Xcode, `shorebird.yaml` com 3 `app_id`) ✅
- Versionamento automatizado com `cider` + assinatura via secrets em CI ✅

**O que a POC tem e o amulets não tem:**
- Controle manual do update (`auto_update: false`) 🧪
- Detecção de patch pronto e **aviso ao usuário para reiniciar** 🧪
- O amulets **removeu isso de propósito** (commit `26a3c29`, "remove UpdaterWidget to allow
  silent OTA updates") ✅

**Os 3 problemas mais graves encontrados:**
1. 🔴 O bump de versão **nunca chega na `main`** (job de CI sempre pulado por semântica do
   GitHub Actions) → o manifesto está congelado em `1.46.0+63` desde junho, e **todo merge
   empilha mais um patch sobre a mesma release**.
2. 🔴 Trocar a **URL da API de produção não gera diff** (o `config.production.json` é
   gitignored) → a trava que deveria forçar release de loja **nunca dispara**, e a mudança
   de endpoint sai silenciosamente por patch OTA.
3. 🔴 **Não existe nenhuma documentação** de hotfix, rollback ou resposta a bug crítico —
   e nenhum mecanismo de bloqueio/versão mínima no app.

---

# Parte 1 — Fundamentos (validados na POC)

## 1.1 Release vs Patch

| | Release | Patch |
|---|---|---|
| O que é | O app completo (código Dart + nativo + assets) | Só o **diff do código Dart** |
| Tamanho 🧪 | 47 MB (AAB da POC) | **3,6 KB** (patch 1) / 6,7 KB (patch 2) |
| Como chega | Loja (Play/App Store), com revisão | Servidor Shorebird, direto, **sem revisão** |
| Comando | `shorebird release android` | `shorebird patch android` |

Um patch **só existe em cima de uma release**. A release é o livro impresso; o patch é a
errata que você grampeia depois.

## 1.2 O que um patch NÃO consegue fazer

Isto é o coração da segurança do processo:

- ❌ **Código nativo** (Kotlin/Swift, plugins novos, versão de plugin)
- ❌ **Assets** (imagens, fontes, JSON em `assets/`)
- ❌ **Permissões, ícone, nome do app, `AndroidManifest`, `Info.plist`**
- ❌ **`shorebird.yaml`** — ele é um *asset*, então mudá-lo exige release nova 🧪
- ✅ **Só código Dart** compilado no snapshot AOT

📖 O CLI **detecta e bloqueia** essas mudanças por padrão. Existem duas flags para
desligar as travas:

```
--allow-native-diffs    # NOTE: this is not recommended... can cause your app to crash
--allow-asset-diffs     # NOTE: this is not recommended... can cause your app to behave unexpectedly
```

O texto entre aspas é literal da ajuda do CLI. **Guarde essa informação — o amulets usa as
duas** (ver §3.4).

## 1.3 O patch só aplica em cold restart

📖🧪 Confirmado na doc e na prática. O fluxo real é de **dois launches**:

```
Launch 1:  app abre → verifica → baixa o patch em background → CONTINUA rodando o código antigo
           (fecha o app de verdade — force-stop, não só background)
Launch 2:  app abre → carrega o patch → código novo em execução
```

**Evidência da POC** 🧪 — o mesmo processo (PID `3738`) antes e depois de voltar do
background, com o patch já baixado mas a tela ainda mostrando o conteúdo antigo:

```
pid antes: 3738   →   [HOME] → [reabrir]   →   pid depois: 3738
tela: "Patch: nenhum (release base)"  ← patch baixado, MAS NÃO aplicado
```

Só após `am force-stop` + abrir de novo (PID novo `3854`) a tela virou `Patch: 1`.

**O que NÃO conta como restart:** hot reload, mandar para background e voltar, ou chamar
`runApp()` de novo. A VM do Dart já está carregada com o código antigo.

⚠️ `SystemNavigator.pop()` **não serve** — encerra a Activity mas não o processo.

## 1.4 Limites por plataforma

| Plataforma | Testar patch | Fechar+reabrir sozinho |
|---|---|---|
| Android (emulador ou físico) | ✅ Suportado 🧪 | ✅ Possível (`AlarmManager` + `exit(0)`; pacotes `restart_app`, `terminate_restart`) |
| iOS **dispositivo físico** | ✅ Suportado | ❌ Apple proíbe encerrar o app programaticamente |
| iOS **simulador** | ❌ **Não suportado** | — |
| Web | ❌ Shorebird não atua | — |

📖 O simulador iOS não funciona porque o engine iOS do Shorebird usa um interpretador feito
para dispositivos físicos `arm64`. Criar um `FlutterEngine` novo **não** é restart de
processo e **não aplica o patch** — é exatamente o que a
[issue #2350](https://github.com/shorebirdtech/shorebird/issues/2350) pede, ainda em aberto.

## 1.5 A API Dart, na íntegra

O pacote `shorebird_code_push` expõe **apenas isto**:

```dart
bool get isAvailable                                   // false fora de build Shorebird
Future<Patch?> readCurrentPatch()                      // patch rodando agora
Future<Patch?> readNextPatch()                         // patch que valerá no próximo boot
Future<UpdateStatus> checkForUpdate({UpdateTrack? track})
Future<void> update({UpdateTrack? track})

enum UpdateStatus { upToDate, outdated, restartRequired, unavailable }
class Patch { final int number; }                      // SÓ o número
```

⚠️ **Não existe** API para listar todos os patches, ler descrição/changelog de um patch, nem
escolher instalar um patch específico. `update()` sempre traz o mais recente do track.

---

# Parte 2 — O arsenal completo do Shorebird

## 2.1 Comandos

```bash
shorebird release <plataforma>     # publica a versão base
shorebird patch <plataforma>       # publica um patch
shorebird preview                  # instala uma release num device
shorebird releases list|info|get-apks
shorebird patches  list|info|promote|set-track
shorebird doctor / upgrade / login / account whoami
```

⚠️ `shorebird preview` **não termina sozinho** — fica preso transmitindo `logcat`, igual ao
`flutter run`. Confirme com `adb shell pidof <package>` e mate o comando 🧪.

## 2.2 Os dois eixos de isolamento (a resposta para "testar em dev sem afetar produção")

Esta é a pergunta central, e a resposta tem **dois mecanismos independentes e combináveis**:

### Eixo 1 — Flavors (separação total, por `app_id`)

📖 Cada flavor vira um **app separado** no Shorebird, com `app_id` próprio:

```yaml
# shorebird.yaml
app_id: <id-do-app-sem-flavor>
flavors:
  development: <id-dev>
  staging:     <id-stg>
  production:  <id-prod>
```

```bash
shorebird release android --flavor development
shorebird patch   android --flavor development   # NUNCA chega em produção
```

O servidor roteia o patch **somente** para a release daquele flavor. É isolamento físico:
não existe caminho pelo qual um patch de dev atinja um usuário de produção.

### Eixo 2 — Tracks (subconjuntos dentro do mesmo app)

📖 Track é um canal de distribuição. `stable` é embutido; qualquer outro nome (`beta`,
`staging`, `qa-time-x`, até 128 caracteres) é criado sob demanda ao publicar:

```bash
shorebird patch android --track=staging     # só quem estiver inscrito nesse track recebe
shorebird patch android                     # sem flag = stable (produção)
```

No app, a inscrição é feita em código (**exige `auto_update: false`**):

```dart
final track = user.isTester ? UpdateTrack.beta : UpdateTrack.stable;
await updater.update(track: track);
// nome customizado:
await updater.update(track: UpdateTrack.custom('qa-interno'));
```

Se não houver patch no track pedido, o device **continua na release base** — não há fallback
automático para `stable`.

**Promoção sem rebuild** (validou em staging → manda para produção):

```bash
shorebird patches promote   --release-version 1.46.0+63 --patch-number 7
shorebird patches set-track --release 1.46.0+63 --patch 7 --track stable
```

### Qual usar?

| Situação | Mecanismo |
|---|---|
| Ambiente inteiro separado (API dev, base de dados dev) | **Flavor** |
| Mesma build de produção, mas validar com o time antes de liberar geral | **Track** |
| Rollout gradual (5% → 25% → 100%) | **Track** + bucketing no app |

## 2.3 Rollback — desfazer um patch ruim

📖 Este é o botão de pânico, e vale ouro num incidente:

```bash
shorebird patches set-track --release-version 1.46.0+63 --patch-number 7 --track stable
```

Ou no console: release → menu ⋮ na linha do patch → **Rollback**.

**O que acontece:** o patch é **desinstalado remotamente** dos devices. Quem já tinha o
patch 7 é rebaixado para o patch 6 (ou para a release base, se não houver anterior). O
servidor devolve a lista de patches revertidos na próxima checagem e o device os apaga.

**Requisito:** Flutter ≥ 3.27.4.
⚠️ Se a cota mensal de instalações de patch estourar, o device cai na **release base**.

## 2.4 Rollout percentual

📖 Não é nativo — é um padrão que você monta: publica no track `beta`, guarda um número
1–100 por device, busca a porcentagem atual de um backend (Firestore, Remote Config, sua
API) e escolhe `beta` ou `stable` em runtime.

---

# Parte 3 — Como o `amulets-mobile` está hoje (auditoria)

## 3.1 Configuração Shorebird ✅

```yaml
# shorebird.yaml (as ÚNICAS linhas não-comentadas)
app_id: 0bc81b98-2725-4c5d-8e53-dee27aef9f0a
flavors:
  development: 0bc81b98-2725-4c5d-8e53-dee27aef9f0a   # ⚠️ IGUAL ao app_id raiz
  production:  8e59f735-9614-490e-96e5-cb8951d6459c
  staging:     b31be804-08df-42ed-919e-b1a3df829df4
```

- `shorebird_code_push: ^2.0.6` ✅ (a POC usa `^2.0.7`)
- `shorebird.yaml` declarado em `flutter: assets:` ✅ — a armadilha clássica está evitada
- ⚠️ **`auto_update` não está declarado** — só existe comentado. Portanto vale o **default
  (ligado)**: o Shorebird baixa patches sozinho no launch.
- ⚠️ **`app_id` raiz == `app_id` de `development`.** Qualquer comando sem `--flavor` atinge
  o app de **desenvolvimento**.

## 3.2 O Shorebird no runtime Dart ✅

**Existe exatamente um uso vivo**, e ele é passivo:

```dart
// lib/apps/mobile_application.dart:126
ShorebirdUpdater().readCurrentPatch()   // → só vira tag do Sentry
```

⚠️ E provavelmente **é inócuo**: `Sentry.configureScope()` roda na linha 128, mas
`SentryFlutter.init()` só na linha 166 do mesmo método — configura escopo num hub ainda não
inicializado. Além disso, envia a string literal `'null'` quando não há patch.

**Código morto:** `lib/core/updater/updater_service.dart` e `updater_widget.dart` existem
(bottom sheet "Update your application" + `Restart.restartApp`), mas **não são montados em
lugar nenhum**. O commit `26a3c29` (23/fev/2026) removeu o `UpdaterWidget` da árvore com a
mensagem *"remove UpdaterWidget to allow silent OTA updates via Shorebird"* — foi **decisão
deliberada do time** pela atualização silenciosa.

### Resposta direta: existe bloqueio de versão forçando fechar/reabrir?

**Não. Zero.** ✅ A auditoria não encontrou:

- ❌ force update / versão mínima / `update_required` / `426 Upgrade Required`
- ❌ Firebase Remote Config, `in_app_update`, `upgrader`
- ❌ qualquer `showDialog`, `barrierDismissible: false` ou bottom sheet não-dispensável
- ❌ qualquer tela que peça para reiniciar

`package_info_plus` existe, mas só para **exibir** "1.46.0 (63)" na tela de conta — não
alimenta nenhuma comparação. O tratamento global de erro (`SessionEnvironmentMixin`) reage a
401/403/500 fazendo **logout**, não pedido de atualização.

## 3.3 Ambientes e endpoints ✅ — o ponto mais delicado

A config chega **exclusivamente** por `--dart-define-from-file`, lida em um único arquivo
(`lib/core/config/app_config.dart`) via `const String.fromEnvironment`.

Chaves: `AMULETS_API_URL`, `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE` (obrigatórias) e
`AMULETS_BANNERS_URL` (opcional, hoje não lida por nenhum Dart).

⚠️ **Não há separação real de ambientes:**

- `config.development.json` aponta para a **mesma API de produção**
  (`mobile-bff-api.amulets.io`)
- `config.staging.json` **não existe** — o `AGENTS.md` manda rodar staging com o config de
  development
- `config.production.json` **não está no repo** (gitignored, materializado no CI a partir de
  secret)
- **Não existe `enum Flavor`/`Environment` em Dart** — flavor é 100% build-time
- Os 4 entrypoints (`main.dart`, `main_development.dart`, `main_staging.dart`,
  `main_production.dart`) são **byte-idênticos e nunca usados** (nada passa `--target`)

### 🔴 A consequência crítica

A base URL é uma **constante de compilação inlinada no snapshot AOT** — exatamente a região
que um patch Shorebird substitui. E o `shorebird patch` aceita `--dart-define-from-file`.

**Logo: um patch OTA pode trocar a URL da API de produção, sem passar por loja.**

Pior: como `config.production.json` é gitignored, **rotacionar o endpoint não gera diff
nenhum**. O guard de "caminhos sensíveis" do CI (que deveria forçar modo `store`) lista
`config.production.json`, mas **nunca dispara para ele** — o arquivo não existe no
versionamento. A troca de URL de produção sai silenciosamente como patch.

## 3.4 O pipeline de release ✅

Dois workflows. O `deploy-main.yaml` é o release de verdade, e escolhe entre dois modos:

| Modo | Quando | O que faz |
|---|---|---|
| **patch** (default) | merge normal na `main` | `cider bump patch` + `shorebird patch` em matriz android/ios |
| **store** | label `release/store` **ou** mudança em `android/`, `ios/`, `assets/`, `pubspec.yaml`, `pubspec.lock`, `shorebird.yaml`, `config.production.json` | `cider bump minor` + `shorebird release` + Play `internal` + TestFlight |

Se o manifesto estiver vazio → cai para `store`. **Nunca se patcheia `latest`** (regra
explícita no `AGENTS.md`).

**O manifesto** (`shorebird-patches.json`) — invenção do repo, não é padrão Shorebird:

```json
{ "patches": [
  {"platform": "android", "releaseVersion": "1.46.0+63"},
  {"platform": "ios",     "releaseVersion": "1.46.0+63"}
]}
```

Lido por `scripts/resolve-shorebird-patches.sh` (validação com `jq`, subcomandos
`count/list/json/validate/run`, **com teste em Dart** ✅) e pelo CI, que o transforma em
matriz de jobs paralelos.

⚠️ **Todos os comandos fixam `--flavor production`.** Os `app_id` de `development` e
`staging` existem no `shorebird.yaml` mas **nunca recebem release nem patch** — estão órfãos.

⚠️ **O CI e o script publicam com `--allow-asset-diffs --allow-native-diffs`** — desligando
as duas travas de segurança do Shorebird. O `make patch-target` (manual) não usa as flags,
então o caminho **automatizado é o mais permissivo dos dois**.

⚠️ O job de patch do CI **reimplementa o comando inline** em vez de chamar o script — os
dois podem divergir sem ninguém perceber.

---

# Parte 4 — Comparação lado a lado

| Aspecto | POC (`flutter_code_push_example`) | `amulets-mobile` | Quem está melhor |
|---|---|---|---|
| `auto_update` | `false` — controle manual 🧪 | default (ligado) ✅ | **POC** — controle explícito |
| Uso do SDK em runtime | `UpdateService` completo (check → download → avisa) 🧪 | só `readCurrentPatch()` p/ Sentry (provavelmente inócuo) ✅ | **POC** |
| Aviso ao usuário | Bottom sheet 40%, dispensável, reaparece ao voltar do background 🧪 | **nenhum** (removido de propósito) ✅ | **POC** |
| Flavors | nenhum (app único) | 3 flavors nas 3 camadas ✅ | **amulets** |
| `app_id` por ambiente | 1 | 3 (mas 2 órfãos) ✅ | **amulets** |
| Tracks | não usa | **não usa** | empate (ambos só `stable`) |
| CI/CD | nenhum | pipeline completo com 2 modos ✅ | **amulets** |
| Versionamento | manual | `cider` automatizado ✅ (⚠️ mas quebrado, §5.1) | **amulets** (na intenção) |
| Assinatura | debug keys | secrets + keychain temporário ✅ | **amulets** |
| Travas de diff | padrão (ligadas) | **desligadas** ✅ | **POC** |
| Doc de rollback/hotfix | este documento | **nenhuma** ✅ | **POC** |
| Testado em device real | Samsung S23 + emulador 🧪 | — | **POC** |

**Resumo honesto:** o amulets ganha em **infraestrutura**, a POC ganha em **uso correto e
seguro do Shorebird**. As duas metades se complementam — é exatamente isso que a Parte 6
propõe juntar.

---

# Parte 5 — Riscos encontrados, por severidade

## 5.1 🔴 CRÍTICO — o bump de versão nunca chega na `main`

**Causa raiz** ✅: o job `persist_version` declara `needs` em `deploy_patch_setup`,
`deploy_patch` **e** `deploy_store` ao mesmo tempo. Esses caminhos são **mutuamente
exclusivos** (no modo patch, `deploy_store` é pulado; no modo store, os de patch são
pulados). Como o `if` do job **não usa** `always()` / `!cancelled()`, uma dependência pulada
**pula o job dependente** — sempre.

**Sintoma observável** ✅: `origin/main` continua em `1.46.0+63`, CHANGELOG parado em
2026-06-08, e **nenhum commit do `amulets-release-bot` no histórico**.

**Consequência em cadeia:** o manifesto está congelado em `1.46.0+63` desde junho. Como
ninguém o edita, **todo merge na `main` dispara um patch real contra a mesma release**,
empilhando patches indefinidamente sobre uma base cada vez mais antiga.

**Correção:**
```yaml
persist_version:
  needs: [deploy_patch_setup, deploy_patch, deploy_store]
  if: ${{ !cancelled() && !failure() && ... }}   # <- a status-check function é obrigatória
```

## 5.2 🔴 CRÍTICO — mudança de endpoint de produção escapa por patch

Já detalhado em §3.3. O guard de caminhos sensíveis lista `config.production.json`, mas o
arquivo é gitignored → **nunca gera diff** → **nunca força modo `store`**.

**Correção sugerida:** versionar um `config.production.checksum` (hash do arquivo real) ou
adicionar um passo no CI que compare o secret atual com o do último release e force `store`
quando `AMULETS_API_URL` mudar.

## 5.3 🔴 ALTO — `--allow-native-diffs` desliga a trava certa

O próprio CLI diz: *"Native code changes cannot be included in a patch and attempting to do
so can cause your app to crash or behave unexpectedly."* O CI usa a flag **sempre**.

**Correção:** remover `--allow-native-diffs` do CI. Se um patch falhar por causa dela, é
**sinal correto** de que o caso exige release de loja.

## 5.4 🟠 MÉDIO — patch é construído a partir do pubspec NÃO bumpado

✅ `deploy_patch_setup` (que roda `make bump-patch`) e `deploy_patch` (que gera o patch) são
jobs **paralelos**, e o de patch faz checkout limpo. A versão que o CHANGELOG anuncia nunca
corresponde à que o usuário tem instalada.

## 5.5 🟠 MÉDIO — `applicationId` idêntico nos 3 flavors (Android)

✅ Os três `productFlavors` declaram `applicationIdSuffix ""` → todos são
`io.amulets.wallet`. **Não dá para ter dev e produção lado a lado no mesmo aparelho.** A
única diferença real é o texto do label (os ícones por flavor são inertes — o manifest
aponta para `@mipmap/launcher_icon`, que só existe em `src/main`).

No iOS está **correto**: `io.amulets.wallet` / `.dev` / `.stg`.

## 5.6 🟠 MÉDIO — problemas de projeto Xcode

- ✅ `Runner.xcscheme` (iOS e macOS) aponta para configurations `Debug`/`Profile`/`Release`
  que **não existem** → qualquer comando sem `--flavor` quebra (o makefile mascara isso
  sempre passando `--flavor production`)
- ✅ Todas as 9 configurations usam `CODE_SIGN_IDENTITY = "Apple Development"`, **inclusive
  Release-production** — só o `sed` do CI corrige. Um `make ios` local produz build de
  release com identidade de desenvolvimento
- ✅ macOS production **sem `PRODUCT_BUNDLE_IDENTIFIER`** → herda `com.example.myApp`

## 5.7 🟡 BAIXO — outros

- ✅ `minifyEnabled true` sem nenhuma regra `keep` própria (nenhum `.pro` no projeto) —
  risco para o SDK nativo do Sumsub e para reflexão
- ✅ Um merge que altera **só** `shorebird-patches.json` dispara deploy em modo patch (o
  arquivo não está nem na exclusão do preflight nem nos caminhos sensíveis)
- ✅ Seleção de modo por label é frágil: sem PR associado, cai em `response.data[0]`; se a
  API falhar, é só um warning e segue em modo patch
- ✅ Nada valida os configs contra `config.schema.json` — o schema é decorativo

---

# Parte 6 — Playbooks operacionais

## 6.1 Testar um patch em desenvolvimento sem tocar produção

**Opção A — por flavor (isolamento total, já configurado no amulets):**

```bash
# 1. Precisa existir uma release daquele flavor (hoje NÃO existe no amulets)
shorebird release android --flavor development -- --dart-define-from-file=config.development.json

# 2. Instalar num device
shorebird preview --flavor development --release-version <versao>

# 3. Patch — vai SÓ para o app_id de development
shorebird patch android --flavor development --release-version <versao> \
  -- --dart-define-from-file=config.development.json
```

⚠️ Pré-requisito no amulets: dar `applicationIdSuffix` real aos flavors Android (§5.5),
senão dev e prod colidem no mesmo device.

**Opção B — por track (mesma build de produção, público restrito):**

```bash
shorebird patch android --flavor production --track=staging --release-version 1.46.0+63
```

Exige no app: `auto_update: false` + escolher o track em runtime.

```bash
# validou? promove sem rebuildar:
shorebird patches promote --release-version 1.46.0+63 --patch-number <n>
```

## 6.2 Publicar um hotfix de bug crítico

```bash
# 1. Confirmar que a correção é SÓ Dart (sem nativo, sem asset)
git diff --stat main...HEAD    # nada em android/ ios/ assets/ pubspec*

# 2. Descobrir a release que os usuários realmente têm
shorebird releases list --flavor production

# 3. Validar primeiro num track restrito
shorebird patch android --flavor production --track=staging --release-version <REAL>

# 4. Testar em device físico: instalar, fechar de VERDADE, reabrir

# 5. Promover para todos
shorebird patches promote --release-version <REAL> --patch-number <n>

# 6. Confirmar
shorebird patches list --release-version <REAL>
```

⚠️ **Passo 2 é onde o amulets erra hoje**: o manifesto está fixo em `1.46.0+63`. Sempre
confirme com `shorebird releases list` qual é a release realmente publicada na loja.

## 6.3 O patch quebrou produção — rollback

```bash
# volta os usuários para o patch anterior (ou para a release base)
shorebird patches set-track --release-version <REAL> --patch-number <RUIM> --track stable
```

Os devices apagam o patch ruim na próxima checagem e voltam ao último estado bom **no
próximo cold start**. Requer Flutter ≥ 3.27.4.

⚠️ O usuário **não volta instantaneamente** — ele precisa reabrir o app. É por isso que o
aviso de reinício (§6.4) tem valor real num incidente.

## 6.4 Mudança de contrato de backend (URLs/headers) com segurança

Este era seu cenário original, e é o mais perigoso:

**Não acople a virada do backend ao rollout do patch.** A adoção é gradual e assíncrona —
cada usuário recebe no próximo cold start dele, que pode levar dias.

**Sequência correta:**
1. Backend passa a aceitar **os dois contratos** (`/v1` e `/v2` convivendo)
2. Publica o patch com o cliente novo
3. Acompanha a adoção no console do Shorebird
4. Só então aposenta o `/v1`

**Se não der para manter compatibilidade**, você precisa de um *gate de versão* — que o
amulets **não tem**: backend responde `426 Upgrade Required` para clientes velhos, o app
intercepta globalmente, dispara `update()` e bloqueia a tela pedindo o restart.

---

# Parte 7 — Recomendações priorizadas para o `amulets-mobile`

| # | Ação | Severidade | Esforço |
|---|---|---|---|
| 1 | Corrigir o `if` do `persist_version` (§5.1) — sem isso o versionamento inteiro é fictício | 🔴 | baixo |
| 2 | Remover `--allow-native-diffs` do CI e do script (§5.3) | 🔴 | baixo |
| 3 | Fechar o furo do guard de `config.production.json` (§5.2) | 🔴 | médio |
| 4 | Automatizar o `shorebird-patches.json` a partir de `shorebird releases list`, em vez de manutenção manual | 🔴 | médio |
| 5 | Documentar hotfix + rollback (pode partir das Partes 6.2/6.3 deste doc) | 🔴 | baixo |
| 6 | Dar `applicationIdSuffix` real aos flavors Android (§5.5) | 🟠 | baixo |
| 7 | Adotar tracks (`staging`) para validar patch antes de `stable` | 🟠 | médio |
| 8 | Corrigir os schemes `Runner` e a assinatura no pbxproj (§5.6) | 🟠 | médio |
| 9 | Decidir sobre `lib/core/updater/`: deletar de vez, **ou** ressuscitar com `auto_update: false` + aviso de restart (portar da POC) | 🟠 | médio |
| 10 | Criar `config.staging.json` com endpoint próprio, e um endpoint de dev de verdade | 🟠 | médio |
| 11 | Validar configs contra `config.schema.json` no CI | 🟡 | baixo |
| 12 | Adicionar regras `keep` de ProGuard (§5.7) | 🟡 | médio |

### Sobre o item 9 — vale ressuscitar o aviso de restart?

O time removeu deliberadamente. **Para o dia a dia, silencioso está certo** — o cold start
acontece naturalmente e incomodar o usuário não acelera nada.

**Mas num incidente crítico isso vira um problema:** você publica a correção e não tem
nenhuma forma de dizer ao usuário que ele precisa reabrir o app. Ele pode ficar horas com o
bug já corrigido no disco dele.

**Meio-termo recomendado:** manter o comportamento silencioso por padrão, e acionar o aviso
**apenas quando o patch for marcado como crítico** (uma flag vinda do backend ou um track
dedicado). Assim você tem o botão de emergência sem irritar ninguém no fluxo normal.

A implementação de referência está nesta POC:
- `lib/features/update/update_service.dart` — wrapper do SDK com resultado tipado
- `lib/features/update/update_prompt.dart` — checagem no launch e ao voltar do background
- `lib/features/update/widgets/update_available_sheet.dart` — bottom sheet 40%, dispensável

---

# Apêndice A — Referência rápida de comandos

```bash
# Diagnóstico
shorebird doctor
shorebird account whoami
shorebird releases list [--flavor <f>] [--platform android]
shorebird patches list --release-version <v>

# Publicar
shorebird release android --flavor <f> -- --dart-define-from-file=config.<env>.json
shorebird patch  android --flavor <f> --release-version <v> --track=staging \
  -- --dart-define-from-file=config.<env>.json

# Promover / reverter
shorebird patches promote   --release-version <v> --patch-number <n>
shorebird patches set-track --release <v> --patch <n> --track <track>

# Instalar para testar
shorebird preview --device-id <id> --release-version <v> [--flavor <f>]
```

⚠️ Tudo depois de `--` é repassado ao `flutter build`.
⚠️ `shorebird preview` não encerra sozinho — mate-o após confirmar com `adb shell pidof`.

# Apêndice B — Estado atual da POC

```
app_id:   bc6a30bd-0768-4326-8885-8be69c59aed2
releases: 1.1.0+2 (android: active) — patch #1 track stable
          1.0.0+1 (android: active) — patches #1, #2
flavors:  nenhum      auto_update: false      Flutter 3.44.9
validado: Samsung S23 (Android 16) + emulador Pixel 7 (Android 15)
```

# Apêndice C — Fontes

**Documentação oficial**
- [Overview](https://docs.shorebird.dev/code-push/) · [FAQ](https://docs.shorebird.dev/code-push/faq/)
- [Tracks](https://docs.shorebird.dev/code-push/tracks/) · [Testing Patches](https://docs.shorebird.dev/code-push/guides/testing-patches/)
- [Roll back a Patch](https://docs.shorebird.dev/code-push/rollback/)
- [Update Strategies](https://docs.shorebird.dev/code-push/update-strategies/)
- [Percentage-Based Rollouts](https://docs.shorebird.dev/code-push/guides/percentage-based-rollouts/)
- [Android Flavors](https://docs.shorebird.dev/code-push/guides/flavors/android/)
- [Issue #2350 — patch sem restart](https://github.com/shorebirdtech/shorebird/issues/2350)
- [`shorebird_code_push` no pub.dev](https://pub.dev/packages/shorebird_code_push)

**Arquivos-chave auditados no `amulets-mobile`** (somente leitura)
`shorebird.yaml` · `shorebird-patches.json` · `.github/workflows/deploy-main.yaml` ·
`scripts/resolve-shorebird-patches.sh` · `makefile` · `android/app/build.gradle` ·
`ios/Runner.xcodeproj/project.pbxproj` · `lib/core/updater/` ·
`lib/apps/mobile_application.dart` · `lib/core/config/app_config.dart` ·
`config.development.json` · `config.schema.json` · `AGENTS.md` · `README.md` · `CHANGELOG.md`
