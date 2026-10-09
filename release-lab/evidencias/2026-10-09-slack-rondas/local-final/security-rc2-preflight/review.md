# Revisão final antes da RC2 — somente leitura

Nenhum bloqueio encontrado na combinação aprovada do PR20.

- Main confiável: `fbcf01271e9a03834f7f54bfd92b0ae21745cf0f`.
- Head revisado no PR20: `532ae653afe32f3eb515ab5881e34bdfc22385ac`.
- Release após merge: `c8d8f337ee390755bcff795d558f8c6f6f19c35b`.
- Árvores `.github`, `deploy`, `tools/delivery` e política, além de build-inputs, pubspec.lock e shorebird.yaml: idênticas à main.
- CI `37872899430`: sucesso no head revisado; PR20 aprovado e integrado.
- Proteções efetivas dos três ambientes e dos rulesets passaram pela leitura dos helpers de produção, com todas as chamadas limitadas a GET.
- Operador de corte: Israel. Revisores obrigatórios: Israel e Fabrícia em ambientes exclusivos. Publicadores finais: Israel ou Fabrícia no terceiro ambiente, somente após 2/2.
- RC1 permanece na tag/código original, journal rejeitado e run encerrado/cancelado. Não havia preparação nem publicação parcial; versão 1.8.0 disponível e RC2 ausente antes do corte.
- Manifesto legado/congelado validado; Android/iOS continuam sem distribuição, patch ou base configurada. GitHub Release não comprova distribuição mobile.

## Roteiro de preflight e validação da RC2

1. Conferir novamente a release remota e sua igualdade com os quatro caminhos críticos da main imediatamente antes do corte; qualquer avanço exige nova comparação.
2. Executar Preparar candidata na main pela conta de Israel, versão 1.8.0. Não criar/mover/apagar tag manualmente e não reexecutar o run da RC1.
3. Confirmar nova tag v1.8.0-rc.2 no SHA da release corrigida, novo run original e nenhum recibo antigo. RC1 deve passar a substituída mantendo tag, source SHA, report digest e histórico.
4. Conferir analyze/test/build, smoke do link, hashes dos bytes e relatório da mesma RC/SHA. Manifesto e changelog devem ser congelados antes dos gates, com resumo reconhecido do PR20 ou fallback de commits explícito.
5. Confirmar aviso Slack da RC2 e, depois de cada aval, recibos da mesma candidata. Slack opcional nunca participa dos needs de aprovação/publicação; unknown não autoriza reenvio cego.
6. Com um único aval, manter o comando final bloqueado. Com 2/2, confirmar que somente o comando separado foi habilitado e nenhuma tag estável ou Release foi criada automaticamente.
7. Registrar comando final por Israel ou Fabrícia; confirmar v1.8.0 e Release no exato SHA da RC2, recibo congelado e ausência de distribuição mobile. Preservar ambas as tags RC.
8. Após promoção, levar a correção para main por PR/revisão/check obrigatório; comparar os digests históricos para documentar ausência de reescrita.

## Limite das evidências

O novo encerramento automático após uma única rejeição passou em 13 testes locais. A RC1 nasceu antes desse listener e foi encerrada manualmente; o fechamento automático ainda precisa de uma candidata futura rejeitada no GitHub para ser marcado como comprovado ao vivo. Não é bloqueio da preparação/promoção da RC2.

Nenhuma aprovação, merge, dispatch, cancelamento, publicação, edição tracked ou alteração de refs Git foi feita por esta revisão. Somente os arquivos privados deste diretório registram a evidência.
