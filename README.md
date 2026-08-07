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

Este projeto é um exemplo de atualização de código com Shorebird. Para trabalhar com code push, instale a CLI do [Shorebird](https://shorebird.dev/) e siga a documentação oficial para configurar o projeto e autenticar a conta.

Mais informações:

- [Documentação do Flutter](https://docs.flutter.dev/)
- [Instalação do Flutter](https://docs.flutter.dev/get-started/install)
- [Documentação do Shorebird](https://docs.shorebird.dev/)
