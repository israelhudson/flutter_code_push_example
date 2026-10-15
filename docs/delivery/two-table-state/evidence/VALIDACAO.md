# Validação desta alteração

Somente execução local e inventário remoto de leitura. Nenhum clique Slack real,
workflow de release, deploy Edge ou migração remota foi executado.

| Verificação | Resultado | Evidência |
|---|---|---|
| Formatação, lint, tipos e testes Deno/Postgres | 52 testes passaram | `deno-local.log` |
| Contratos Python de preparação/publicação, incluindo journal v2 | 31 passaram | `python-local.log` |
| Preservação dos previews | 6 passaram | `preview-local.log` |
| YAML dos três workflows novos | Parse Ruby/Psych passou | comando abaixo |
| Whitespace do diff | passou | `git diff --check` |
| Inventário Supabase | 8 tabelas antigas, 6 candidatas encerradas, 22 avisos enviados | `inventory.json` |

Comandos:

```sh
deno task check:poc
python3 -m unittest discover -s tests/delivery -p 'test_poc*.py' -v
python3 -m unittest discover -s tests/delivery -p 'test_issue_preview.py' -v
ruby -ryaml -e 'ARGV.each { |p| YAML.load_file(p) }' .github/workflows/delivery-*.yml
git diff --check
```

Cenários específicos executados:

- Papel/DM trocados recusados; assinatura falsa/antiga e outro app recusados.
- Persistência antecede ACK; falha do banco não retorna confirmação falsa.
- Um aceite mantém pendência; repetição não cria revisão/evento novo.
- Rejeição bloqueia publicação; RC2 começa sem votos; RC1 não altera RC2.
- Dois aceites fecham rejeição; GitHub sem recibo mantém publicação bloqueada.
- Uma execução reivindica publicação; outra é recusada; repetir a mesma é idempotente.
- Conteúdo GitHub divergente não é sobrescrito nem marcado como persistido.
- Efeito externo começa uma única vez; lease vencida fica incerta, sem reenvio cego.
- Cancelamento e compactação não apagam trabalho pendente; controle terminal permanece.
- RLS/grants impedem acesso anônimo; SHA congelado não pode ser alterado.
- Cartão público sem ações; DM com apenas seu papel; estados finais sem botões.
- Workflows/ator/flag incorretos recusados antes do banco.

Não comprovado nesta rodada: concorrência em duas conexões Postgres remotas,
entrega de DMs reais, recuperação de falha parcial real, cron, ruleset remoto,
backup/restauração dos dados antigos e redução efetiva do banco. A migração só
pode ser ativada após essas etapas do guia; os testes usam fixtures externas e
Postgres local PGlite. Nenhum resultado local é evidência de publicação mobile.

O Security Advisor remoto foi consultado antes do commit. Retornou apenas oito
avisos informativos `rls_enabled_no_policy` nas tabelas legadas: é o bloqueio
intencional de acesso público, com operações de servidor. Não foram criadas
políticas públicas para silenciar esse aviso. [Descrição do aviso no Supabase](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy).
Esse resultado se refere ao schema remoto antigo, não certifica a migração nova.
