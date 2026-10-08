# Auditoria independente do ensaio real no GitHub

Auditor: agente de revisão de segurança, com leituras independentes da API REST
do GitHub e dos snapshots coletados pelo executor. O auditor não aprovou
Environments, não publicou, não alterou código nem fez mutações remotas.
Este documento é seu único arquivo de saída.

## Alcance e limite das evidências

- Reviews confirmam **contas GitHub**, seus IDs, Environment e decisão no run.
- As contas foram operadas em ensaio automatizado autorizado por Israel. Os
  comentários oficiais registram essa condição. **Não demonstram revisão humana
  independente de Israel e Fabrícia**, nem aceite de negócio.
- A promoção deste ensaio cria somente tag estável e Release no GitHub.
  Não equivale a distribuição Android/iOS, loja, Shorebird ou TestFlight.
- O journal pressupõe armazenamento confiável. Sua proteção contra exclusão e
  force push não impede novos commits de um writer/admin malicioso. Os hashes
  detectam divergências no caminho normal; não autenticam um journal forjado por
  quem já possui permissão de escrita.
- A concurrency dos jobs não trava mutações externas por administradores.

## Identidade da candidata inicial

| Campo | Valor verificado |
|---|---|
| RC | `v1.5.0-rc.1` |
| Fonte e ferramentas | `9c4ad37fc415a98ef2a8cfdc5be8d5cf97fe35b0` |
| Run original | [Preparar candidata inicial](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37850467026) |
| Tentativa | `1` |
| Relatório congelado | `8a074cf72f9d5a4a3966112d1e6843a3a9a3235653e71963800f11224f37d2d9` |
| Modo | `github_release_only`; sem distribuição mobile |

## Resultados acumulados

| Caso | Esperado | Observado | Resultado |
|---|---|---|---|
| 0/2 | Dois gates aguardam; sem promoção | Snapshots `rc1-zero-approvals-*`: duas pendências, reviews vazias, sem receipt final/publication; stable e Release ausentes (404) | PASS |
| 1/2 | Israel sozinho não libera autorização/publicação | Consulta REST independente: review `israelhudson`, ID `18661493`; Gate first success; Gate second waiting; somente receipt first; sem job de autorização/promoção iniciado; stable e Release ausentes (404) | PASS |
| Rejeição da RC1 | Segundo gate recusado impede promoção | REST independente: segundo gate failure; autorização e promoção skipped; sem intenção/receipt final; stable e Release ausentes (404) | PASS |
| Correção → RC2 | Fonte nova, RC1 preservada, novos avais 0/2 | Ainda não observado pelo auditor | PENDENTE |
| 2/2 sem comando final | Dois avais liberam apenas terceiro gate | Ainda não observado pelo auditor | PENDENTE |
| Promoção real da RC2 | Comando final cria stable e Release no mesmo SHA aprovado | Ainda não observado pelo auditor | PENDENTE |

## Conferência independente de 1/2

Leituras REST em 08/10/2026, após o término do Gate first:

- Run original com `status=waiting`, tentativa `1`, ator `israelhudson`.
- Review aprovada exclusiva do Environment `aprovacao-israel`, ID `23819079490`.
- O comentário declara ensaio automatizado por Codex autorizado por Israel e
  ausência de revisão humana independente.
- Job `113563115783`: Gate first, `completed/success`.
- Job `113563115800`: Gate second, `waiting`, sem conclusão.
- O journal mantém RC1 ativa e `status=awaiting_approvals`. `approval_receipts`
  contém somente `first`; não contém `publication` nem `receipt` final.
- SHA de origem e digest de relatório correspondem ao corte. O SHA-256 recalculado
  do relatório em JSON canônico corresponde ao digest congelado.
- GET da referência `tags/v1.5.0` e GET da Release `v1.5.0` retornaram 404.

Nenhuma divergência identificada nesta etapa. Resultados pendentes não devem ser
tratados como PASS antes das respectivas leituras e evidências.

## Conferência independente da rejeição da RC1

O run original terminou `completed/failure`. A API oficial de approvals retornou
review `rejected` da conta `fahnassau30`, ID `339824994`, exclusiva do Environment
`aprovacao-fahnassau30`. O comentário identifica teste automatizado autorizado,
motiva a correção da mensagem inicial e exige RC2 com novos avais.

- Gate first manteve `success` e seu recibo histórico.
- Gate second `113563115800` terminou `failure`.
- AUTORIZAR PUBLICAR `113564492241`: `skipped`.
- PROMOVER `113564492381`: `skipped`.
- Snapshots `rc1-rejected-*` não contêm intenção de publicação nem receipt final.
- O auditor repetiu GETs de stable e Release: ambos 404, sem publicação.

**Semântica do estado:** a rejeição é registrada no histórico oficial de reviews
e na conclusão dos jobs; o journal mantém `awaiting_approvals` e somente o receipt
`first`. Portanto esse status isolado não descreve a rejeição. Na criação da RC2,
o journal deverá marcar RC1 `superseded`, mantendo o registro histórico. Não houve
tentativa de reaproveitar o receipt para publicar a RC1 rejeitada.
