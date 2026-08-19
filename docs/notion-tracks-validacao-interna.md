# Item para o Notion — "Shorebird Manual explicativo"

> Conteúdo pronto para colar. A parte longa vai dentro de um bloco **Alternar (toggle)**
> no Notion — digite `/alternar`, cole o título, e cole o corpo dentro dele.
>
> **API verificada** contra `shorebird_code_push 2.0.7` instalado localmente e contra a
> saída real de `shorebird patches promote --help` / `set-track --help`.

---

## Pergunta

**Como validar um patch com uma equipe interna antes de liberá-lo para todos os usuários, sem criar uma build nova?**

**R:** Utilizando Tracks — enviando o patch para um canal específico (ex.: `beta`) antes do canal `stable`.

---

## ▸ Resposta detalhada (bloco alternar)

### 1. O que é uma Track?

Uma **Track** é um canal de distribuição lógico que funciona **dentro do mesmo aplicativo**. Por padrão, todo app do Shorebird já tem o canal **`stable`** (produção) embutido.

Você pode criar canais adicionais dinamicamente no momento da publicação — `beta`, `staging`, `qa-team`, com nomes de até 128 caracteres. O servidor do Shorebird roteia o patch apenas para os dispositivos que pedirem aquele canal.

---

### 2. O fluxo de trabalho na prática

#### Passo A — Publicar o patch numa Track específica

```bash
shorebird patch android --track=beta
```

Nesse momento, nenhum usuário comum recebe a atualização.

#### Passo B — Fazer o app pedir aquela Track

Para que os aparelhos da equipe interna busquem patches no canal `beta`, o app precisa escolher o canal em tempo de execução.

**1. Desativar a atualização automática.** No `shorebird.yaml`, declare `auto_update: false`. Se ficar no padrão — que é o caso do Amulets hoje — o app baixa sozinho qualquer patch do canal `stable`.

```yaml
auto_update: false
```

**2. Escolher o canal em código.** Exponha uma configuração oculta (menu de desenvolvedor, ou chave de admin no perfil) que define o canal do aparelho:

```dart
import 'package:shorebird_code_push/shorebird_code_push.dart';

final updater = ShorebirdUpdater();

// Constantes prontas: stable, beta, staging
final status = await updater.checkForUpdate(track: UpdateTrack.beta);

if (status == UpdateStatus.outdated) {
  await updater.update(track: UpdateTrack.beta);
}

// Canal com nome livre:
await updater.update(track: UpdateTrack('qa-amulets'));
```

> ⚠️ **Ponto que engana:** o SDK **não guarda** o canal do aparelho. Não existe
> "inscrição" persistente — o track é passado **em cada chamada**. Quem precisa
> persistir a escolha do testador é o seu app (SharedPreferences, Hive, o que usar)
> e repassá-la em toda chamada de `checkForUpdate` e `update`.

Um aparelho que não passar nenhum track continua no `stable`. E se não houver patch publicado no canal pedido, o app segue rodando a release base normalmente — **não há fallback automático** para o `stable`.

#### Passo C — Promoção sem rebuild

Depois que o QA validar o patch no canal `beta`, você promove **o mesmo patch** para produção:

```bash
# promove direto para stable
shorebird patches promote --release-version 1.46.0+63 --patch-number 7

# ou move para qualquer track pelo nome
shorebird patches set-track --release 1.46.0+63 --patch 7 --track stable
```

> Repare que os dois comandos usam nomes de flag diferentes para a mesma coisa:
> `promote` usa `--release-version` / `--patch-number`, e `set-track` usa
> `--release` / `--patch`. Não é erro de digitação — é assim no CLI.

**Por que isso é seguro:** você **não gera uma build nova**. O snapshot AOT exato que foi testado no aparelho dos testadores é o mesmo que vai para todos os usuários — sem risco de divergência de compilação.

---

### 3. Tracks vs. Flavors — quando usar cada um

| Situação | Mecanismo | O que faz na prática |
| --- | --- | --- |
| Ambiente inteiramente separado: banco de teste, chaves de API distintas, URL de desenvolvimento | **Flavors** | Cria **apps fisicamente diferentes** no aparelho, com `app_id` e bundle/applicationId próprios — dá para ter Dev e Produção instalados lado a lado |
| Mesma build de produção, mas validar uma alteração de Dart com um grupo restrito antes de liberar geral | **Tracks** | Testa **no mesmo app que vai para o cliente**, roteando o patch para canais lógicos (`beta` → `stable`) |

Os dois se combinam: dá para ter um patch no track `beta` **do flavor production**.

---

### 4. A situação atual do Amulets-mobile

O projeto **não utiliza Tracks** hoje:

- O pipeline de CI e os scripts de deploy interagem exclusivamente com o canal padrão `stable`.
- O `auto_update` **não está declarado** no `shorebird.yaml` — só existe comentado —, então vale o padrão (ligado): o app baixa patches do `stable` sozinho ao abrir.
- Os `app_id` de `development` e `staging` existem no `shorebird.yaml`, mas nenhum comando os usa: todo release e patch fixa `--flavor production`.

A **Recomendação #7** da auditoria sugere adotar tracks (`staging` / `beta`) para validar patches antes de mandá-los para produção. Isso evita que um patch defeituoso seja distribuído silenciosamente para toda a base sem nenhuma validação em ambiente real.

> ⚠️ Pré-requisito no Android: os três flavors do Amulets declaram
> `applicationIdSuffix ""`, ou seja, têm o **mesmo** `applicationId`
> (`io.amulets.wallet`). Enquanto isso não mudar, não dá para ter o app de
> desenvolvimento e o de produção instalados no mesmo aparelho.

---

## Correções aplicadas ao texto original

Três trechos do rascunho tinham API que não existe. Registrado aqui para não voltarem por cópia:

| Estava | Correto | Por quê |
| --- | --- | --- |
| `ShorebirdCodePush()` | `ShorebirdUpdater()` | A classe `ShorebirdCodePush` **não existe** na 2.x — era a API da 1.x |
| `shorebird.setTrack('beta')` | `updater.update(track: UpdateTrack.beta)` | `setTrack` não existe; o track é parâmetro de cada chamada, não estado do aparelho |
| `promote --from-track=beta --to-track=stable` | `promote --release-version <v> --patch-number <n>` | Essas flags não existem; `promote` sempre leva para `stable` |
| `UpdateTrack.custom('nome')` | `UpdateTrack('nome')` | Não há construtor `.custom` — `UpdateTrack` é um extension type sobre `String` |

Exports reais do pacote `shorebird_code_push 2.0.7`:

```dart
Patch, ReadPatchException, ShorebirdUpdater,
UpdateException, UpdateFailureReason, UpdateStatus, UpdateTrack
```
