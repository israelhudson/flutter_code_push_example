# Titulares automáticos: implantação e teste real

Em 15/10/2026, o [PR #62](https://github.com/israelhudson/flutter_code_push_example/pull/62)
foi integrado na `main`, no commit `8913fd51cacd0e620b589ab3fdb06164e215f62d`.
O cadastro foi aplicado somente ao Supabase exclusivo `xtvueqciogzkyjkkqxcx`.
A Amulets não foi alterada.

## Resultado

O preparo escolheu Israel automaticamente no cadastro para os dois papéis,
sem informar pessoas no formulário. O manifesto, o controle e os eventos
congelaram a mesma seleção. São **dois papéis exercidos por uma pessoa em modo
solo**, não duas aprovações independentes.

| Etapa real | Resultado observado |
|---|---|
| Preparar `1.15.3 RC1` na main | Sucesso; `controls_only`, escopo `none`; build e web pulados |
| Envio pelo bot exclusivo | Cartão no canal e duas DMs, uma por papel |
| Clique no aceite técnico | `pending`, revisão 1; só o aceite técnico gravado |
| Clique no aceite de negócio | `approved`, revisão 2; ambos gravados; zero dispatch |
| Cancelamento operacional do ensaio | `cancelled`, revisão 3; aceites e tag RC preservados |
| Drenagem e pausa | 16 operações concluídas; zero pendências e avaliações ativas |

Os cliques foram feitos pelo agente, usando a sessão autorizada de Israel no
Slack. O [preparo](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38744723709)
criou a [tag RC e sua prerelease](https://github.com/israelhudson/flutter_code_push_example/releases/tag/poc-v1.15.3-rc.1).
**Não houve tag estável, Release final, preview ou patch.** `publication_run`
permaneceu nulo. `none` impede a promoção final; não suprime a Release Candidate.

Workers reais na main:
[aceite técnico](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38744926071),
[aceite de negócio](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38745051119)
e [encerramento](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38745241492).
Esses runs são `workflow_dispatch`; esta rodada não é nova comprovação do cron.

## Banco, preservação e controles

- Três tabelas: `delivery_control`, `delivery_outbox` e `delivery_reviewers`.
- Um cadastro, com Israel titular técnico e de negócio no ensaio solo.
- RLS habilitado; sem leitura para `anon`/`authenticated`. O runtime lê o
  catálogo, mas não tem INSERT, UPDATE ou DELETE nele.
- Sete controles e 88 tarefas anteriores comparados e preservados; as 39 tags
  anteriores também. A única tag acrescentada foi `poc-v1.15.3-rc.1`.
- Manifesto e quatro eventos relidos por commit imutável. Bytes/digests e
  conteúdo conferidos; o histórico anterior continua ancestral do atual.
- Ao encerrar: `DELIVERY_V2_ENABLED=false` no GitHub e Supabase;
  `POC_SLACK_ENABLED=false`, `POC_SLACK_PUBLISH_ENABLED=false`,
  `POC_LEGACY_ENABLED=false` no GitHub; `POC_PUBLICATION_ENABLED=false`
  no backend. Os controles de publicação ficaram desligados durante o ensaio.

## Logs, prints e lições

[Resultado sanitizado](result.json), [recibos e digests dos logs](evidence-digests.json),
[índice dos oito prints](screenshots.json) e [trecho da suíte Python](ci-excerpt.txt).
Logs completos, snapshots e prints ficam no diretório privado local
`/Users/israelhudson/Documents/Codex/2026-10-15/reviewer-defaults/`.
Não foram enviados payloads privados ou screenshots ao repositório público.

A CI posterior aprovou **580 testes Python**, **76 Deno**, análise e testes
Flutter. O primeiro teste local teve três erros com a política antiga em disco;
o arquivo foi corrigido e a CI final confirmou a seleção automática. A causa da
regravação local não foi determinada. Uma falha de lint `no-control-regex` também
foi corrigida antes do merge. Conferir o conteúdo da política e executar o lint
antes do push evita repetir essas falhas de desenvolvimento.

O `db push --dry-run` recusou versões remotas antigas que divergem dos nomes
locais. Nenhuma migração histórica foi reparada ou reaplicada. A aplicação usou
somente a nova migração pelo MCP: arquivo local `20261015132214`, registro remoto
`20261015133825`, nome `delivery_reviewer_defaults`, SHA-256 do SQL
`588ea01475591d866fa3084a74e08807fa314f2c5028ec21d1e3e8c1ae2045ef`.
Conferir o inventário remoto antes de usar um push global em futuras implantações.

## O que esta rodada não prova

Troca de titular, revogação, rejeição/RC2 e disputa de decisões do novo catálogo
têm cobertura local, mas não foram executadas remotamente nesta rodada. Os testes
SQL locais também não comprovam concorrência entre conexões PostgreSQL reais.
Preview, patch e promoção final ficaram fora do ensaio. O corpo da prerelease
mantém o texto inicial; a conferência do estado terminal usou controle, eventos e Slack.

Antes da Amulets: testar duas contas distintas, troca/revogação e concorrência
remotas, definir administradores e substitutos com Samuel e restaurar as regras
de revisão humana dos PRs. O cadastro não concede acesso ao GitHub nem substitui
os controles de publicação.
