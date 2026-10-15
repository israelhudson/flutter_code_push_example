# flutter_code_push_example

## Esteira oficial de entrega

O fluxo oficial deste projeto usa a **`main`**, os workflows
[`delivery-prepare.yml`](.github/workflows/delivery-prepare.yml),
[`delivery-publish.yml`](.github/workflows/delivery-publish.yml) e
[`delivery-worker.yml`](.github/workflows/delivery-worker.yml). O canal Slack
acompanha a entrega; os aceites técnico e de negócio são feitos em DMs.
Com escopo e controles habilitados, os dois aceites disparam a publicação GitHub
automaticamente. O modo solo atual usa Israel nos dois papéis; não equivale a
duas pessoas independentes.

Para **novas versões**, a branch é `release/X.Y.Z`, a tag candidata é
`vX.Y.Z-rc.N` e a tag final é `vX.Y.Z`. A mudança de nomes não dispara uma
release, não cria aceites e não renomeia tags ou branches históricas.
As referências antigas `poc-v...` e `poc-release/...` permanecem preservadas.
Não misturar os dois formatos para a mesma versão.

[Guia do fluxo oficial](docs/delivery/two-table-state/README.md) ·
[Nomes de branches e tags, RC1 e RC2](docs/delivery/two-table-state/NOMES-OFICIAIS.md) ·
[Resultado real da rodada 1.15.5](docs/delivery/two-table-state/RODADA-PREVIEW-STAGING.md).

A rodada **1.15.5** comprovou preview Web, dois aceites manuais, Release GitHub
automática e **Android `1.1.0+2`, patch `5` em staging**, com a tabela e o cartão
Slack atualizados. Os patches stable anteriores foram preservados. A etapa
Android foi executada localmente após a Release GitHub, não em CI, e não
comprovou execução em dispositivo. iOS, stable, lojas e Amulets não foram
publicados nessa rodada. Os controles de execução/publicação foram pausados ao
encerrar a janela; uma nova rodada exige habilitação autorizada.

## LAB: outro fluxo, preservado

Use **Actions → LAB · Criar candidata**, informando versão e título. O fluxo cria a RC, valida o app e publica o preview. **Israel E Fabrícia** aprovam; depois **Israel OU Fabrícia** autoriza PUBLICAR em uma etapa separada. A promoção cria **uma nova tag estável e uma Release real no GitHub, no mesmo commit da RC aprovada**, preservando as tags candidatas. Não distribui o app nem gera patch mobile.

[Passo a passo do fluxo com dois aprovadores](docs/delivery/FLUXO-DOIS-APROVADORES.md) · [Cenários, logs, evidências e lições para Amulets](docs/delivery/VALIDACAO-E-PROMOCAO.md). A matriz distingue implementação, testes locais e validação remota. O primeiro ensaio tinha resultado final simulado; novas permissões de publicação exigem nova RC e novos avais.

Os workflows anteriores foram arquivados em [workflows-historicos](docs/delivery/workflows-historicos/); seus runs e evidências permanecem preservados. Para uma promoção parcial, use **LAB · Recuperar publicação** com a tag RC original, após conferir o diagnóstico e obter nova autorização final.

Prática do uso do code push do Flutter com ShoreBird.

## Simulação local histórica

```bash
python3 tools/delivery/lab.py demo --folder build/delivery-lab/meu-primeiro-ensaio
```

Israel representa os papéis de desenvolvedor, Ian/Yan, Samuel e Vinícius.
O cenário local percorre 0/2 → 1/2 → 2/2, comando final separado, snapshots e
recuperação de falha parcial, com recibos falsos e sem distribuição.

[Guia passo a passo do laboratório](docs/delivery/LABORATORIO.md) ·
[Plano e critérios de aceite](docs/plano-evolucao-esteira.md) ·
[GitHub nativo e ativação futura](docs/delivery/README.md).

## Setup

### Pré-requisitos

- Flutter no canal `stable` (projeto validado com Flutter `3.44.1`);
- Dart SDK compatível com `^3.12.1` (incluído no Flutter);
- Git;
- Para Android: Android Studio, Android SDK e um emulador ou dispositivo físico;
- Para iOS/macOS: macOS com Xcode instalado e configurado.

Valide a instalação do Flutter com:

```bash
flutter doctor
flutter doctor --android-licenses
```

O comando `flutter doctor` deve indicar que o Flutter e a plataforma escolhida estão configurados corretamente.

### Instalação

Na raiz do projeto, instale as dependências:

```bash
flutter pub get
```

Se o Flutter SDK estiver instalado em um caminho diferente do padrão, configure-o no arquivo `android/local.properties`:

```properties
flutter.sdk=/caminho/para/flutter
sdk.dir=/caminho/para/android-sdk
```

Esse arquivo é específico da máquina e não deve ser commitado.

### Executando o projeto

Liste os dispositivos disponíveis e execute o aplicativo:

```bash
flutter devices
flutter run
```

Para escolher uma plataforma explicitamente:

```bash
flutter run -d android
flutter run -d ios
flutter run -d chrome
```

Para validar o projeto:

```bash
flutter analyze
flutter test
```

### Estrutura do projeto

```text
lib/
├── app/
│   └── app.dart                 # MaterialApp e configuração do app
├── core/
│   └── theme/
│       └── app_theme.dart       # Cores e tema visual
├── features/
│   └── home/
│       └── home_page.dart       # Tela inicial
└── main.dart                    # Ponto de entrada
```

### Shorebird

Este projeto é um exemplo de atualização de código com Shorebird (code push para Android; iOS
também é suportado pelo Shorebird, mas requer dispositivo físico — veja a nota abaixo).

Os comandos abaixo são o estudo manual de Shorebird. O fluxo LAB não os executa.
No fluxo oficial, os jobs GitHub também não executam o upload Shorebird: a
[ponte Android local](docs/delivery/two-table-state/ANDROID-STAGING.md) permite
uma tentativa em staging depois dos dois aceites e da Release GitHub, quando
esse plano foi congelado antes da avaliação. App, base, código, destino e
autorização são reconferidos; geração, execução em dispositivo e promoção para
stable são provas distintas.

#### 1. Instalar a CLI e autenticar

```bash
curl --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/shorebirdtech/install/main/install.sh -sSf | bash
shorebird doctor
shorebird login
```

O instalador adiciona `~/.shorebird/bin` ao `PATH`. Feche e reabra o terminal (ou exporte
manualmente) para o comando `shorebird` ficar disponível.

#### 2. Inicializar o app no Shorebird

Já feito neste repositório (`shorebird init`), o que gerou o [`shorebird.yaml`](shorebird.yaml)
com o `app_id` do projeto (não é segredo, pode ficar versionado) e adicionou a dependência
`shorebird_code_push` ao `pubspec.yaml`.

#### 3. Gerar uma release

Releases são a versão "base" do app, publicadas com o Shorebird em vez do `flutter build`:

```bash
shorebird release android
```

#### 4. Publicar um patch (a atualização OTA)

Depois de alterar código Dart, publique a mudança como patch para uma release já existente:

```bash
shorebird patch android --release-version=<versão da release, ex: 1.0.0+1>
```

O app verifica e baixa patches pelo `UpdateService` ao abrir/retomar e também
pelo botão manual. O download do engine está configurado com `auto_update: false`;
o código do app controla a operação e informa quando é preciso fechar e reabrir
o aplicativo. O patch baixado passa a valer no próximo **cold start**.

#### 5. Testar

```bash
# instala a release mais recente em um dispositivo/emulador conectado
shorebird preview --device-id <device-id>
```

A tela inicial ([home_page.dart](lib/features/home/home_page.dart)) mostra o número do patch
atual e tem botões para verificar/baixar atualizações manualmente via `ShorebirdUpdater`.

> **Nota sobre simuladores/emuladores:** o emulador Android é totalmente suportado para testar
> patches. **O simulador iOS não é suportado** — o engine iOS do Shorebird usa um interpretador
> feito para rodar em dispositivos físicos `arm64`, então validar code push no iOS exige um
> iPhone físico (uma conta Apple grátis já é suficiente para instalar via Xcode em uso local).

Mais informações:

- [Documentação do Flutter](https://docs.flutter.dev/)
- [Instalação do Flutter](https://docs.flutter.dev/get-started/install)
- [Documentação do Shorebird](https://docs.shorebird.dev/)

## Histórico do laboratório de aprovação de versões

[Guia anterior da POC: preview web, aprovação 2/2 e publicação dry-run](docs/delivery/README.md).
A sessão local histórica usa SQLite; a fila local e os papéis simulados não viram
aprovações do GitHub. O [fluxo LAB](docs/delivery/FLUXO-DOIS-APROVADORES.md)
continua documentado como outro caminho: preparação manual, dois avais,
comando separado e promoção GitHub-only. O fluxo oficial atual está no início
deste README e possui suas próprias DMs, automação e ponte Android opcional.
PRs, merges e a mudança dos nomes das tags não iniciam uma candidata por conta
própria; o preparo continua sendo um Run workflow autorizado, pela interface
ou CLI.
