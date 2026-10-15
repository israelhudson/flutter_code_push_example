# Conferir a retenção automática no preview

A definição da main foi corrigida pelo PR #44. Para comprovar a ativação,
use uma nova execução de Slack - Preview do PR para a slack-main.
Reexecutar um run antigo não comprova que o workflow novo foi carregado.

1. Confirme no log a chamada de preview_retention.py antes de issue_preview.py.
2. Baixe o artefato poc-web-proof e confira preview-retention.json.
3. Confira preserved, pinned, archived, projected_bytes e history_commit.
4. Verifique que os snapshots protegidos conservaram seus arquivos e hashes.
5. Confirme que web terminou com sucesso e que o link do novo preview abriu.

Previews arquivados continuam recuperáveis pelo history_commit. Se não houver
previews elegíveis, archived pode estar vazio: isso não é falha. Se as entregas
protegidas excederem a capacidade, deve bloquear sem removê-las.

Este procedimento publica apenas um preview web. Não cria candidata, aprovação,
tag, release ou distribuição do aplicativo.
