# 004 Shorebird e elegibilidade de patches

| Campo | Valor |
|-------|-------|
| **Fonte** | https://docs.shorebird.dev/code-push/patch/ |
| **Autor/Canal** | Shorebird, documentação oficial |
| **Publicado em** | Data de publicação não informada na página |
| **Duração/Extensão** | Guia Create a Patch |
| **Adicionado em** | 2026-10-07 |
| **Tema** | Release-base, compatibilidade e publicação de patch |
| **Idade** | 🟢 consultada em 07/10/2026; verificar CLI instalada antes de implementar |

## Por que está aqui

Fundamenta a pré-análise da candidata e a conferência final contra a release-base exata de cada plataforma.

| O que | Validade | Onde conferir |
|---|---|---|
| Comparar o build com a release-base armazenada | 🟢 fundamento verificado | Fonte verificada |
| Opções e comportamento da CLI | 🟡 reconferir na implementação | Guia oficial e ajuda da versão instalada |

## Fonte verificada

O [guia oficial](https://docs.shorebird.dev/code-push/patch/) afirma que patches dependem de uma release existente. O Shorebird compara o build local com os artefatos armazenados e detecta diferenças nativas e de assets. O checklist também exige compatibilidade da versão Flutter.

A opção `--release-version` seleciona uma base específica. A operação de patch pode compilar, enviar e promover para `stable`; não é apenas análise. O guia documenta `--dry-run` para compilar e validar sem upload. As opções `--allow-native-diffs` e `--allow-asset-diffs` contornam verificações e não são recomendadas pela fonte.

Esta leitura confirma documentação, não execução da CLI instalada nem compatibilidade de uma candidata concreta.

## Complemento

A [FAQ oficial](https://docs.shorebird.dev/code-push/faq/) distingue versão da release e número do patch. Mudanças nativas exigem uma nova release; atualizar o Flutter também exige nova release. Um preview web não substitui validação mobile.

A [documentação GitHub de reviews](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews) informa que o autor não pode aprovar o próprio PR. Isso fundamenta o limite da simulação com uma única conta, não é uma regra do Shorebird.

## Aplicação neste projeto

Decisões do laboratório, e não comandos impostos pelas fontes:

1. Pré-analisar por plataforma e base exata; manter número do patch “a gerar” na RC.
2. Gerar patches apenas após autorização final; bloquear incompatibilidade sem ignorar warnings ou mudar automaticamente para loja.
3. Separar simulação de papéis, teste sintético e validação real.

Ver o [plano de evolução da esteira](../../docs/plano-evolucao-esteira.md).

## Pendências

- [ ] Conferir ajuda e versão da CLI no projeto isolado antes de implementar o adaptador.
- [ ] Confirmar releases-base, toolchain e permissões por plataforma antes de um ensaio autorizado.
- [ ] Validar o resultado nos dispositivos autorizados; leitura de documentação não conclui essa validação.
