# Referências de Estudo

Base de conhecimento do projeto. Toda decisão técnica deve ser checada contra
o que está aqui **antes** de recorrer a conhecimento genérico.

## Como está organizado

```text
referencias/
├── README.md          # este índice
├── _TEMPLATE.md       # modelo para novas referências
├── videos/            # aulas, talks, cursos (+ transcrições brutas)
└── docs/              # documentação oficial, artigos, specs
```

## Índice

### Vídeos

| # | Título | Tema | Idade | Status |
|---|--------|------|-------|--------|
| [001](videos/001-firebase-remote-config-flutter.md) | Curso Flutter NV2 — [03] Firebase Remote Config | Implementação em Flutter: wrapper, singleton, widget de toggle | 🟡 2022 — arquitetura vale, API não | ✅ transcrito ([bruto](videos/001-transcricao-bruta.md)) |
| [002](videos/002-remote-config-package-of-the-week.md) | Firebase Remote Config (Package of the Week) — canal oficial Flutter | Visão canônica do produto: segmentação, condições, tipos | 🟢 conceitual | ✅ transcrito ([bruto](videos/002-transcricao-bruta.md)) |
| [003](videos/003-feature-flags-arquitetura.md) | How To Build Feature Flags Like A Senior Dev (Web Dev Simplified) | Teoria de feature flags: trade-offs, onde armazenar, algoritmo de rollout | 🟢 2024, independente de linguagem | ✅ transcrito ([bruto](videos/003-transcricao-bruta.md)) |

**Idade:** 🟢 atual · 🟡 conceito válido, API defasada · 🔴 substituída

#### Como as três se encaixam

[001], [002] e [003] cobrem o mesmo assunto em camadas diferentes. Ao atacar um
problema de feature flag, entrar pela camada certa:

| Pergunta | Referência |
|---|---|
| *Devo usar flag aqui? Vale a complexidade?* | [003](videos/003-feature-flags-arquitetura.md) — prós, contras, manutenção |
| *Onde guardar a flag? Quão rápido preciso mudá-la?* | [003](videos/003-feature-flags-arquitetura.md) — tabela de armazenamento |
| *O que o Remote Config sabe fazer?* | [002](videos/002-remote-config-package-of-the-week.md) — condições, tipos, segmentação |
| *Como escrever isso em Dart?* | [001](videos/001-firebase-remote-config-flutter.md) — wrapper, singleton, widget |
| *Como o percentil funciona por dentro?* | [003](videos/003-feature-flags-arquitetura.md) — hash determinístico |

[001]: videos/001-firebase-remote-config-flutter.md
[002]: videos/002-remote-config-package-of-the-week.md
[003]: videos/003-feature-flags-arquitetura.md

### Docs

| # | Título | Tema | Idade | Status |
|---|--------|------|-------|--------|
| [004](docs/004-shorebird-patch-e-elegibilidade.md) | Shorebird e elegibilidade de patches | Release-base exata, compatibilidade, autorização e limites do ensaio | 🟢 consultada em 07/10/2026 | ✅ fonte oficial lida; execução pendente |

## Regras de uso

1. **Antes de implementar** qualquer coisa que toque um tema listado no índice,
   ler a referência correspondente.
2. **Conflito entre referência e conhecimento geral** → a referência vence.
   Se a referência estiver desatualizada, sinalizar em vez de ignorar.
3. **Idade não desqualifica referência.** Separar o que envelhece do que não:

   | Envelhece 🔴 | Não envelhece 🟢 |
   |---|---|
   | assinatura de método, nome de classe | por que a decisão existe |
   | número de versão, dependências | armadilha do runtime e sua causa |
   | passos de UI de console | trade-off entre abordagens |

   Uma fonte antiga com boa explicação **do porquê** vale mais que doc oficial atual
   que só mostra a chamada. O caminho é usar o raciocínio da referência e trocar a
   API pela atual — não descartar a referência inteira. Marcar 🟡 no índice e
   registrar as divergências na seção `Complemento` do arquivo.
4. **Nova referência** → copiar `_TEMPLATE.md`, numerar em sequência, e
   adicionar a linha no índice acima. O índice é a fonte de verdade do que existe.
5. **Transcrever vídeos** com `yt-dlp` (instalado). O arquivo `NNN-transcricao-bruta.md`
   fica ao lado da referência como fonte primária conferível:
   ```bash
   yt-dlp --skip-download --write-auto-sub --sub-lang "pt.*,pt" --sub-format vtt -o "aula.%(ext)s" URL
   ```
   O ASR erra muito com termos técnicos — cada transcrição bruta traz sua tabela de
   decodificação no topo. Nunca citar o ASR literalmente.
6. **Marcar o que não foi verificado.** Todo arquivo separa `Fonte verificada`
   de `Complemento`. Nunca misturar o que a fonte disse com o que foi inferido.
