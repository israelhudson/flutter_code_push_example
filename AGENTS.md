# flutter_code_push_example

Projeto de estudo de code push em Flutter com Shorebird.

## Referências de estudo — leia antes de implementar

A pasta [`referencias/`](referencias/README.md) é a base de conhecimento deste
projeto. **No início de cada sessão, ler `referencias/README.md`** — o índice
diz o que existe e sobre qual tema.

Antes de implementar, decidir arquitetura ou responder qualquer coisa sobre um
tema que aparece no índice, abrir a referência correspondente e usá-la como base.
Conhecimento genérico é fallback, não ponto de partida.

Regras:

- **A referência vence** o conhecimento geral em caso de conflito.
- **Idade não desqualifica referência.** Várias são de anos anteriores e estão
  marcadas 🟡 no índice. Nelas, o *raciocínio* (por que a decisão existe, qual
  armadilha ela evita) continua válido — só a *API* envelheceu. Usar o raciocínio
  da referência e trocar a API pela atual, sinalizando a divergência. Nunca
  descartar a referência inteira por causa da versão, nem seguir a API antiga.
- Cada arquivo separa **`Fonte verificada`** (o que a fonte realmente diz) de
  **`Complemento`** (doc oficial e outras fontes). Não tratar as duas como equivalentes.
- Ao adicionar uma referência nova: copiar `referencias/_TEMPLATE.md`, numerar em
  sequência, e **atualizar o índice** em `referencias/README.md`.

## Comandos

```bash
flutter pub get
flutter analyze
flutter test
flutter run
```
