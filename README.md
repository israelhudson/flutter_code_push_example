# flutter_code_push_example

## Esteira atual do laboratório

Use **Actions → LAB - Preparar candidata**, informando versão e título. O fluxo cria a RC, valida o app e publica o preview. **Israel E Fabrícia** aprovam; depois **Israel OU Fabrícia** dá PUBLICAR em uma etapa separada. O recibo final é **SIMULADO**, sem distribuição mobile.

[Passo a passo do fluxo com dois aprovadores](docs/delivery/FLUXO-DOIS-APROVADORES.md). Os workflows anteriores foram arquivados em [workflows-historicos](docs/delivery/workflows-historicos/); seus runs e evidências permanecem preservados.

Prática do uso do code push do Flutter com ShoreBird.

## Ensaiar a esteira agora

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

Os comandos abaixo são o estudo manual de Shorebird. A esteira implementada não
os executa. Um ensaio real exige confirmar app, release-base, destino e autorização
antes de gerar/publicar patches; as duas aprovações liberam um comando final separado.

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

## Laboratório de aprovação de versões no GitHub

[Guia da POC: preview web, aprovação 2/2 e publicação dry-run](docs/delivery/README.md).
Preparar candidata é manual no Actions; PRs e merges não criam RCs por conta própria.
Reviews e merge do registro não publicam. Publicar agora é um workflow separado,
que exige 2/2 real e pode criar somente uma GitHub pre-release de laboratório.
A sessão local usa SQLite; a fila local e os papéis simulados não viram aprovações
do GitHub. A implementação não gera patches Shorebird nem distribui aplicativos.
