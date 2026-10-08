# Após o primeiro aval registrado: conta de Fabrícia

Observação de 8 de outubro de 2026. O job de `aprovacao-fahnassau30` concluiu com sucesso. O de `aprovacao-israel` permanece aguardando; PUBLICAR não iniciou.

O job liberado fez somente checkout das ferramentas congeladas, conferência da conta autenticada, da RC ativa e do relatório, registro do aval no journal e preservação do artefato. Não houve build novo, republicação do preview ou distribuição móvel depois desse clique.

O journal ainda registra `awaiting_approvals` e contém apenas o recibo `second`. O histórico do GitHub registra a conta `fahnassau30` no único Environment correspondente. Não há recibo final.

Limite da evidência: o GitHub verifica a conta autenticada que decidiu. Isso não comprova, por si só, revisão humana independente por duas pessoas. O laboratório deve separar teste técnico entre contas de revisão efetivamente realizada pelos dois revisores.

Lição para Amulets: registrar uma aprovação também executa um job curto de validação e auditoria. Explicar isso no nome e no guia da etapa evita interpretar qualquer execução como publicação. A API de logs retornou escapes de terminal; a consulta foi repetida permitindo a leitura e os códigos ANSI foram removidos antes de salvar. Nenhuma mudança na candidata ou aprovação foi realizada pelo agente.

Evidências: `approval-second.log`, `audit-after-second-approval.json` e `state-after-second-approval.json`.
