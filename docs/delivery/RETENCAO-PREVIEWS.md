# Retenção automática dos previews

Antes de importar um build, os publicadores Slack (PR e candidata), Issue e LAB
calculam a retenção sob o mesmo lock `pages-preview`. O relatório
`preview-retention.json` acompanha o artefato de evidências, inclusive quando
uma etapa posterior falha.

A política mantém:
- Todos os snapshots cujo commit tem qualquer tag (incluindo tags anotadas).
- Todos os snapshots com metadado de candidata.
- O destino da página inicial e o snapshot que está sendo importado.
- Os dois commits mais recentes entre os demais previews de PR.

Os outros previews saem do site online, mas seus bytes continuam recuperáveis
no commit Git `history_commit` registrado no relatório. O push é normal, sem
reescrever o histórico. Tags, aprovações, candidatas e releases não são alteradas.
Falha ao consultar tags, checkout sujo ou nova tag protegendo um item planejado
bloqueiam a operação antes de remover arquivos.

O cálculo considera o tamanho do novo artefato antes de importá-lo.
Se os itens preservados excederem 800 MiB, a publicação bloqueia: não apaga
entregas para ganhar espaço. Nesse caso é necessário planejar outro armazenamento.
A validação de integridade e o limite do Pages continuam ativos.

## Por que faltava na execução

A retenção existia apenas na slack-main. A definição efetiva executada pelo
GitHub ainda era a da main, sem essa etapa. Por isso a correção também precisa
ser integrada à main; um PR aberto ou uma implantação no Supabase não a ativa.

## Validação

Testes cobrem preservação por tags/metadados/página inicial, dois PRs recentes,
imutabilidade dos bytes preservados, recuperação pelo Git, nova tag durante a
operação, checkout sujo, falha da API, tags anotadas/paginação e snapshot de entrada.
Um contrato de workflow verifica retenção antes da importação/persistência e
a presença do relatório nos quatro publicadores.
