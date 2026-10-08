# Limitação de texto do botão nativo

Consulta em 8 de outubro de 2026, após pedido para substituir `Approve and deploy` por `Approve`.

A documentação oficial da interface de revisão usa o botão `Approve and deploy`. As configurações oficiais de Environments, tanto na interface quanto na API de criação/atualização, não oferecem parâmetro para personalizar o texto desse botão. Conclusão baseada na configuração documentada: o workflow não pode renomear esse controle nativo.

É possível ajustar nomes de jobs e Environments para esclarecer que a etapa registra apenas uma aprovação. Um botão com texto livre exigiria outra interface de aprovação e validação equivalente das identidades e da candidata. Esta consulta não altera o workflow, os Environments ou a candidata em andamento, e não envia nenhum aval.

Lição para Amulets: validar a linguagem da interface com os revisores antes de escolher o mecanismo de aprovação. O rótulo nativo pode sugerir publicação imediata mesmo quando o job apenas registra um aval.

Fontes oficiais:
- https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments
- https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- https://docs.github.com/en/rest/deployments/environments#create-or-update-an-environment
