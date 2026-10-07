# [001] Curso Flutter NV2 — [03] Firebase Remote Config

| Campo | Valor |
|-------|-------|
| **Fonte** | https://youtu.be/YqSS2mCIR8c |
| **Autor/Canal** | Deivid Willyan \| Flutter |
| **Publicado em** | 2022-02-25 |
| **Duração** | 29min50s |
| **Adicionado em** | 2026-08-18 |
| **Tema** | Firebase Remote Config, feature toggle, rollout gradual |
| **Transcrição** | [001-transcricao-bruta.md](001-transcricao-bruta.md) (ASR, não revisada) |
| **Relacionadas** | [002](002-remote-config-package-of-the-week.md) (visão oficial) · [003](003-feature-flags-arquitetura.md) (teoria e trade-offs) |

## Por que está aqui

Remote Config e Shorebird resolvem problemas **diferentes e complementares** de
entrega contínua em Flutter. Este projeto já usa Shorebird (code push); Remote
Config é a outra metade. Ver [Aplicação neste projeto](#aplicação-neste-projeto).

**Referência principal do tema, apesar da idade.** O vídeo é de fev/2022 (Flutter
2.10, pacote 2.0) e a API mudou. Isso **não** desqualifica a fonte: o valor dela é
didático — o autor explica *por que* cada decisão existe, não só como chamar o
método. O raciocínio do `getValueOrDefault` (zero-value vs. ausência), o argumento
de encapsulamento do `CustomVisibilityRC` e as duas pegadinhas do console
(rascunho, cache) continuam corretos e não têm equivalente na doc oficial, que
mostra a chamada sem explicar a consequência.

**Como ler:**

| O que | Validade | Onde conferir |
|---|---|---|
| Arquitetura, raciocínio, casos de uso | 🟢 vale hoje | [Fonte verificada](#fonte-verificada) |
| Assinaturas de API, versões, nomes | 🔴 conferir antes de usar | [🔻 Divergências](#-divergências-entre-a-aula-20-e-a-api-atual-656) |

## Fonte verificada

Conteúdo extraído da transcrição automática. Timestamps apontam para o vídeo.

> ⚠️ **Contexto de versão:** `firebase_remote_config` **2.0** em **Flutter 2.10**
> (fev/2022); atual é **6.5.6**. A arquitetura ensinada continua válida — os
> detalhes de API não. Divergências marcadas com 🔻 em [Complemento](#complemento).

### A tese da aula

> "Essa feature é pouco conhecida se for comparar com outras do Firebase, muito
> pouco utilizada também — e mal utilizada. O pessoal não explora todo o poder dela." — [00:00]

O argumento central: Remote Config permite **ligar e desligar componentes do app
remotamente, sem deploy** [07:18]. Se uma funcionalidade nova apresenta bug, você
não sobe versão nova — desliga a chave.

### Arquitetura proposta: wrapper + singleton

O autor **não usa `FirebaseRemoteConfig` direto pelo app**. Ele cria uma pasta
`remote_config/` com uma classe `CustomRemoteConfig` [01:34]:

- **Singleton via factory constructor + variável estática** [01:34–02:22]. Uma
  única instância do início ao fim da aplicação. A factory retorna a instância já
  criada em vez de fabricar uma nova.
- Motivo declarado do "Custom" no nome: sinalizar que é implementação própria, não
  a do Firebase.

Reconstrução da classe (⚠️ **inferida da narração em áudio**, não é o código literal da tela):

```dart
class CustomRemoteConfig {
  static CustomRemoteConfig? _instance;
  late FirebaseRemoteConfig _remoteConfig;

  factory CustomRemoteConfig() => _instance ??= CustomRemoteConfig._();
  CustomRemoteConfig._();
  // ...
}
```

### Os três métodos

**1. `initialize()` → `Future<void>`** [02:22–04:50]

Recupera `FirebaseRemoteConfig.instance` e aplica as configurações iniciais:

| Parâmetro | Valor do autor | Justificativa dada |
|---|---|---|
| `fetchTimeout` | **10 segundos** | "caso o Firebase não me responda com a velocidade que eu espero, aborta e volta" [03:59] |
| `minimumFetchInterval` | **1 hora** | funciona como cache local — dentro de 1h não consulta o servidor [03:59] |

**2. `forceFetch()`** [04:50–05:39]

Reaplica as settings com `minimumFetchInterval: Duration.zero` (mantendo o timeout
de 10s) e chama `fetchAndActivate()`. É o **bypass do cache**.

Tratamento de erro [05:39]: `try/catch` com dois ramos — `PlatformException` (falha
na integração nativa do Firebase) e um catch genérico, ambos com rethrow.

**3. `getValueOrDefault(String key, dynamic defaultValue)`** [06:27–09:45]

O método mais importante da aula. Faz `switch` no `defaultValue.runtimeType`,
ramificando para `getString` / `getInt` / `getBool` / `getDouble`.

> **A pegadinha que o método existe para resolver:** Remote Config **nunca retorna
> null** para chave inexistente. Retorna o zero-value do tipo — `""`, `0`, `false`,
> `0.0` [08:57]. Sem esse wrapper você não distingue "chave ausente" de "valor
> legitimamente falso/vazio".

Por isso o método compara o retorno com o zero-value: se for diferente, devolve o
valor do servidor; se for igual, devolve o default in-app.

O próprio autor admite a limitação: *"esse cara é para fins didáticos, valeria
algumas validações a mais"* [08:08]. Ele reconhece que um valor legítimo igual ao
zero-value (ex.: `false` publicado de propósito) cai no default — o método não
separa os dois casos.

### O widget de toggle: `CustomVisibilityRC`

[18:42–21:15] Um `StatelessWidget` com três parâmetros **obrigatórios** (`required`):

| Parâmetro | Tipo | Papel |
|---|---|---|
| `child` | `Widget` | o que será exibido ou escondido |
| chave | `String` | a chave no Remote Config |
| `defaultValue` | `dynamic` | fallback quando a chave não existe |

Retorna um `Visibility` cujo `visible` vem de `CustomRemoteConfig().getValueOrDefault(...)`.

**A razão declarada** [21:15] — e é o melhor argumento da aula:

> "Eu concentro tudo em um único lugar. Todas as nossas chamadas do Custom Remote
> Config. Dessa forma, onde eu vou utilizar o toggle de visibilidade eu não preciso
> expor a minha camada de Remote Config."

### Prática: default `false` (fail-closed)

[23:42] Ao criar `showContainer`, ele deixa o default in-app como `false`:

> "Sempre que eu não tenho uma chave, ou não estou ligando um produto, eu não quero
> que ele seja exibido."

Chave ausente ⇒ feature escondida. Você só *habilita* indo ao console — nunca o contrário.

### O ciclo no console (com duas pegadinhas)

[13:47–16:16] Ao criar um parâmetro no console, o autor demonstra dois pontos onde
o app "não atualiza" e a causa não é óbvia:

1. **Rascunho ≠ publicado.** O parâmetro criado fica como rascunho. Hot reload, hot
   restart e até `forceFetch` não veem nada até você clicar em **Publicar alterações**.
2. **Publicado ≠ visível.** Depois de publicar, o valor vale imediatamente — mas só
   para *novos* fetches. O app rodando continua no cache de 1h. [15:24]

> "Ele nunca busca no Firebase imediatamente — depende do tempo do seu cache." [15:24]

Demonstração: publica `isActiveBlue = true`, faz hot restart, **nada muda**. Só ao
apertar o botão que chama `forceFetch()` a AppBar vira azul [17:04].

### Quando forçar o fetch

[17:04–17:53] O autor deixa explícito que isso é **regra de negócio**, e sugere:

- toda vez que o app abre;
- toda vez que o app navega para uma determinada rota;
- **ao receber um push notification** — o push com argumentos dispara a atualização
  do Remote Config. Ele marca como ideia a desenvolver em aula futura.

### O que Remote Config faz além do toggle

[26:08–29:24] Fechamento da aula, tudo configurado no console:

- **Testes A/B** ("experimentos") — exemplo dado: botão azul converte mais que o
  vermelho? Firebase segmenta os usuários e entrega um dashboard de conversão.
- **Personalizações** — Firebase usa ML para decidir qual valor entregar a cada segmento.
- **Condições** — ativar só para Android; só para um idioma; só para um país/região
  (Brasil sim, EUA não); só para um público-alvo (ex.: "todo mundo que fez compra").
- **Rollout por percentil** — o caso de uso que ele mais defende: *"quando estou
  lançando uma feature nova e não consegui testar toda a qualidade, mas quero
  lançar em ondas"*. Solta para 5%, depois 10%, 15%, 20%, até 100% [27:46].
- **Agendamento por data/hora** — exemplo: Black Friday. Deixa o app pré-configurado
  para, na data, trocar tema, cores e promoções automaticamente [28:34].
- **Installation ID** — ativar ou não para uma instalação específica [29:24].

## Complemento

Documentação oficial atual — usar como referência de implementação, já que a aula
é de 2022.

**Fontes:** [Firebase — Get started on Flutter](https://firebase.google.com/docs/remote-config/flutter/get-started) · [pub.dev — firebase_remote_config](https://pub.dev/packages/firebase_remote_config)

### 🔻 Divergências entre a aula (2.0) e a API atual (6.5.6)

**Real-time updates existem agora.** Toda a mecânica de `forceFetch()` da aula foi
concebida sem essa API. Hoje dá para ouvir mudanças por stream:

```dart
remoteConfig.onConfigUpdated.listen((event) async {
  await remoteConfig.activate();
  // usar os novos valores aqui
});
```

O `listen` só notifica — **quem aplica os valores é o `activate()`**. Esquecer isso
é o bug clássico: o stream dispara e a UI não muda.

Isso não aposenta o `forceFetch()` — ele continua útil para os gatilhos manuais que
o autor lista (abrir o app, entrar numa rota). Mas o caso "quero refletir agora, sem
o usuário apertar nada" hoje se resolve pelo stream, não por bypass de cache.

**`firebase_analytics` é dependência prática.** A doc oficial manda instalar junto,
porque a segmentação por audiência e o A/B testing — justamente os recursos do
fechamento da aula — dependem dele.

```bash
flutter pub add firebase_remote_config
flutter pub add firebase_analytics
```

**Plataformas suportadas em 6.5.6:** Android, iOS, macOS, web e Windows.

**Throttling em desenvolvimento:** a doc recomenda baixar `minimumFetchInterval`
para ~5 minutos durante o desenvolvimento, e nunca levar isso para produção — com
milhares de usuários de teste a quota estoura. É uma alternativa mais simples ao
`forceFetch()` da aula para o dia a dia de dev.

**Confirmado pela doc:** o comportamento de zero-value que o autor descreve em
[08:57] está correto — não existe retorno nulo. `setDefaults` é obrigatório na
prática, não opcional.

## Aplicação neste projeto

`flutter_code_push_example` já usa **Shorebird** (`shorebird.yaml`, `app_id:
bc6a30bd-…`, `auto_update` no default). Os dois mecanismos não competem:

| | Shorebird (code push) | Remote Config |
|---|---|---|
| **Entrega** | Código Dart novo (patch) | Valores de configuração |
| **Serve para** | Corrigir bug, mudar lógica | Ligar/desligar feature já embarcada |
| **Latência** | Gerar e publicar patch | Imediato (console) — respeitado o cache |
| **Rollback** | Novo patch | Trocar o valor de volta |
| **Rollout gradual** | Não nativo | Percentil nativo (5% → 100%) |
| **Limite** | Não muda código nativo nem dependências | Não introduz código que não existe no app |

O padrão que combina os dois — e que o rollout por percentil de [27:46] torna
concreto: **Shorebird entrega o código da feature nova já desligada; Remote Config
liga ela gradualmente**. Se der problema, o kill switch é um toggle no console, sem
esperar build nem propagação de patch.

O `CustomVisibilityRC` da aula é a peça que falta para isso funcionar: sem ele, cada
call site conheceria a camada de Remote Config.

Nada de Remote Config foi implementado aqui ainda — o projeto tem só
`lib/features/home/home_page.dart` com a UI de checagem de update do Shorebird.

## Confrontos com as outras referências

Adicionadas depois desta. Onde elas corrigem ou completam a aula:

- **JSON blob.** A [002] mostra que Remote Config aceita `string`, `boolean`, `number`
  **e JSON blob**. O `getValueOrDefault` daqui cobre só os quatro primitivos — é a
  lacuna mais concreta desta implementação.
- **O `minimumFetchInterval` tem nome na literatura.** O que a aula chama de "cache" é
  o padrão que a [003 › 09:18](003-feature-flags-arquitetura.md#onde-armazenar-as-flags--a-tabela-de-trade-offs)
  recomenda explicitamente para flags em banco: como flags mudam raramente, cachear
  agressivamente dá velocidade de código com flexibilidade de banco. A 1h do autor não
  é limitação — é o design correto.
- **O percentil deixa de ser caixa-preta.** A aula usa o rollout do console sem explicar
  o mecanismo. A [003 › 15:32](003-feature-flags-arquitetura.md#o-algoritmo-de-rollout-por-porcentagem)
  mostra que é hash determinístico de `feature + userId` — ou seja, o usuário em 10%
  **não perde a feature ao reabrir o app**. Isso é o que justifica confiar no percentil.
- **Falta o custo de manutenção.** A aula vende a feature sem citar o preço. A
  [003 › 05:10](003-feature-flags-arquitetura.md#os-4-contras--e-eles-são-levados-a-sério)
  é enfática: flag sem data de remoção vira dívida técnica. Só kill switch é permanente.

## Pendências

- [x] ~~Capturar a transcrição real do vídeo~~ — feito em 2026-08-18 via `yt-dlp`
- [x] ~~Confrontar o que o autor ensina com a API atual~~ — ver 🔻 em [Complemento](#complemento)
- [ ] Reescrever `CustomRemoteConfig` para a API 6.5.6 usando `onConfigUpdated`, e
      avaliar se `forceFetch()` ainda se justifica no design
- [ ] Resolver a limitação do `getValueOrDefault` que o próprio autor admite em [08:08]
      (valor legítimo igual ao zero-value cai no default)
- [ ] Decidir se este projeto implementa Remote Config de fato ou fica como estudo comparativo
