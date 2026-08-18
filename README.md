# flutter_code_push_example

Prática do uso do code push do Flutter com ShoreBird.

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

O app verifica por patches novos ao abrir e aplica automaticamente no próximo restart — sem
passar pela loja.

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
