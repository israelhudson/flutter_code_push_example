# Promoção para Release final no GitHub

Após os dois aceites, o fluxo Slack cria `poc-vX.Y.Z` como **Release final no GitHub**, com `draft=false` e `prerelease=false`. O escopo continua `github_test`: isso não promove patches Shorebird nem publica em lojas.

| Momento | Identificação |
|---|---|
| Em revisão | Tag `poc-vX.Y.Z-rc.N` e cartão da candidata |
| Aprovada e publicada | Tag `poc-vX.Y.Z` e Release final, sem o selo “Pré-lançamento” |
| Histórico | A tag da RC continua apontando ao código original |

Esta correção não cria uma segunda GitHub Release para a RC: no fluxo atual, a candidata é representada pela tag, pelo preview e pelo cartão. O nome da tag e a marcação `prerelease` são propriedades independentes.

## O que foi corrigido

- O publicador deixa de marcar a versão promovida como pré-lançamento.
- O receptor exclusivo da POC confirma na API GitHub que a Release é final e aponta para a tag correta antes de aceitar o recibo. Um pré-lançamento, draft, SHA divergente ou recibo que ainda diga `prerelease=true` é recusado.
- A descrição da Release apresenta o título, as mudanças e o link do preview. O relatório técnico congelado fica recolhido em um bloco JSON, sem modificar seu texto nem digest.
- O cartão Slack já destaca a tag promovida e preserva a RC de origem; não ganha nova autorização mobile com essa mudança.
- `make_latest=false` mantém a Release de teste fora da seleção `Latest` usada pela linha principal. Nenhuma regra do LAB, Issue ou Amulets é alterada.

## Corrigir uma Release antiga

No workflow **Slack - Publicar versão aprovada**, use o ID da candidata já publicada e marque `finalize_existing=true`. O padrão continua `false`.

```bash
gh workflow run poc-slack-publish.yml \
  --repo israelhudson/flutter_code_push_example --ref slack-main \
  -f candidate=poc-e79dbcf4fc4b42f2ace8e30f4ebe7049 \
  -f finalize_existing=true
```

A operação exige estado `published`, recibo original e tags RC/final no SHA aprovado. Só aceita a descrição original conhecida ou a nova descrição esperada. Se houver edição divergente, bloqueia para não sobrescrever trabalho manual.

Ela atualiza o título para `Versão X.Y.Z`, a descrição e `prerelease`, com `make_latest=false`; mantém ID, tags e anexos. A tabela usa metadados e recibos verificados conforme [Versões e publicação](VERSOES-E-PUBLICACAO.md). Salva intenção, antes/depois e recibo de correção. Não altera o recibo original no banco nem os aceites. Atualiza a mesma mensagem do Slack, sem novo aviso, tag, preview ou patch.

Repetir a correção de uma Release já corrigida apenas confere e retorna `changed=false`. Se a resposta do PATCH se perder, a próxima execução consulta o efeito e não envia outro PATCH quando a correção já estiver aplicada. O botão normal de publicação mantém seu comportamento idempotente e não corrige Releases antigas silenciosamente.

## Validação

- Testes Python: criação final, repetição sem efeitos, correção preservando anexos/recibo, bloqueio antes de publicar, divergência de tag/recibo/descrição e perda de resposta após PATCH.
- Testes HTTP: receptor só conclui com Release final real; recusa pré-lançamento, flag ausente, draft, tag/SHA divergente e recibo falso.
- Os cenários existentes de rejeição, RC2 sem avais antigos e publicação única continuam na suíte Postgres.
- Ensaio remoto de correção: registrar execução, antes/depois, anexos, tags e print da 1.15.1. Não reclassificar evidências históricas de versões anteriores como se já usassem essa regra.

Fonte: [API oficial de Releases](https://docs.github.com/en/rest/releases/releases#update-a-release). `prerelease=false` classifica uma Release completa; `make_latest` é uma decisão separada.
