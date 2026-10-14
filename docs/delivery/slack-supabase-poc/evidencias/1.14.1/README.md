# Evidências da publicação automática 1.14.1

- `evidence.json`: campos selecionados do banco POC, API de Runs, Release e tags.
- `receipt.json`: recibo final do artefato `poc-publication-receipts`.
- `publication-excerpt.log`: linha de resultado do step de publicação; headers,
  ambiente, setup e dados sem relação com a conclusão foram omitidos.
- `source-files-sha256.json`: hashes dos originais locais antes da extração.
  Os hashes identificam os arquivos coletados, não são prova externa de autenticidade.

Fonte: Run 38497337584, candidata poc-d90c43ec138544479b44d6c8fda1a1c0,
consulta ao banco e cartão Slack confirmados em 13/10/2026, Fortaleza.
JSONs mantêm UTC. O evento GitHub `workflow_dispatch` foi chamado pelo backend;
o journal confirma a reserva e o recibo após os dois aceites. Não houve Run manual
nesta publicação. Não confundir com a rodada 1.14.0, que usou execução manual.

Os originais completos foram mantidos no diretório privado
`/Users/israelhudson/Documents/Codex/2026-10-13/slack-supabase-poc/publication-1.14.1/`.
Os recibos aqui não incluem tokens, Signing Secret, headers de autenticação,
valores de secrets ou histórico integral de canal privado.

[Relatório e limites](../../VALIDACAO-1.14.1-E-LICOES.md).
