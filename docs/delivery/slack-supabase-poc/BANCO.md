# Catálogo das tabelas da POC

Todas têm RLS e acesso somente de servidor. Nenhuma tabela `lab_*` é alterada.


## poc_user_directory

| Coluna | Significado |
|---|---|
| `github_login` | Conta GitHub verificada; operador/criador não é inferido do Slack. |
| `github_id` | ID numérico GitHub usado para validar iniciador e reexecutor. |
| `slack_user_id` | Conta Slack que realizou ou realizará a decisão. |
| `display_name` | Nome legível da identidade verificada. |
| `verified_at` | Data da verificação da identidade. |

## poc_config

| Coluna | Significado |
|---|---|
| `flow` | Entrega isolada flutter-code-push. |
| `repository` | Repositório autorizado exato. |
| `team_id` | Workspace Slack autorizado. |
| `channel_id` | Canal privado de teste autorizado. |
| `enabled` | Flag geral; começa false. |
| `publication_enabled` | Permissão de publicar TESTE; começa false. |
| `mode` | solo_test ou two_reviewers; solo não prova duas pessoas. |
| `operator_github` | Conta autorizada a iniciar/reexecutar workflows. |
| `technical_reviewer` | ID Slack congelado para aceite técnico. |
| `business_reviewer` | ID Slack congelado para aceite de negócio. |

## poc_candidates

| Coluna | Significado |
|---|---|
| `id` | Identidade imutável da candidata ou sequência de evento. |
| `flow` | Entrega isolada flutter-code-push. |
| `version` | Versão semver legível. |
| `rc_number` | Número sequencial da candidata dentro da versão. |
| `rc_tag` | Tag imutável poc-vVERSÃO-rc.N. |
| `source_sha` | Commit exato avaliado; imutável. |
| `report_text` | Relatório original congelado, incluindo preview/changelog/base por plataforma. |
| `report_digest` | SHA-256 dos bytes do relatório. |
| `creator_github` | Quem iniciou a candidata no GitHub. |
| `creator_slack` | Destinatário da DM após 2/2; separado dos revisores. |
| `technical_reviewer` | ID Slack congelado para aceite técnico. |
| `business_reviewer` | ID Slack congelado para aceite de negócio. |
| `mode` | solo_test ou two_reviewers; solo não prova duas pessoas. |
| `team_id` | Workspace Slack autorizado. |
| `channel_id` | Canal privado de teste autorizado. |
| `is_lab` | Identificação do ensaio; nunca concede autorização. |
| `publication_scope` | none ou github_test, congelado na criação. |
| `previous_candidate` | RC substituída por ajuste, preservada para auditoria. |
| `created_at` | Instante de criação/reserva no servidor. |
| `expires_at` | Prazo de 36h da RC ou 5min do token modal. |
| `status` | Estado da candidata; uma ativa por fluxo. |
| `message_ts` | Identidade do cartão Slack associado, não de uma conversa livre. |
| `revision` | Revisão usada para convergir atualização do cartão. |
| `adjustment_reason` | Motivo de ajuste obrigatório. |
| `adjustment_author` | ID de quem solicitou ajuste. |
| `adjustment_at` | Instante do ajuste. |

## poc_approvals

| Coluna | Significado |
|---|---|
| `candidate_id` | Candidata à qual pertence a evidência. |
| `role` | Papel técnico ou negócio; chave única por candidata. |
| `slack_user_id` | Conta Slack que realizou ou realizará a decisão. |
| `approved_at` | Instante do voto salvo no banco. |
| `mode` | solo_test ou two_reviewers; solo não prova duas pessoas. |

## poc_private_notices

| Coluna | Significado |
|---|---|
| `candidate_id` | Candidata à qual pertence a evidência. |
| `event` | Tipo de evento/aviso. |
| `recipient` | Destinatário congelado da reserva. |
| `state` | Estado da reserva/envio/publicação. |
| `slack_channel` | Destino confirmado na resposta Slack. |
| `slack_ts` | Timestamp confirmado do envio Slack. |
| `delivery_receipt` | Recibo real Slack ou ACK de dispatch; não uma prova inventada. |
| `created_at` | Instante de criação/reserva no servidor. |
| `finished_at` | Instante de conclusão ou incerteza. |

## poc_adjustment_tokens

| Coluna | Significado |
|---|---|
| `token` | Nonce exclusivo do modal de ajuste. |
| `candidate_id` | Candidata à qual pertence a evidência. |
| `slack_user_id` | Conta Slack que realizou ou realizará a decisão. |
| `message_ts` | Identidade do cartão Slack associado, não de uma conversa livre. |
| `created_at` | Instante de criação/reserva no servidor. |
| `expires_at` | Prazo de 36h da RC ou 5min do token modal. |
| `consumed` | Nonce usado/cancelado; impede replay. |

## poc_publications

| Coluna | Significado |
|---|---|
| `candidate_id` | Candidata à qual pertence a evidência. |
| `intent_id` | Intenção reservada antes de alterar tags/Release. |
| `run_id` | Run GitHub original autorizado à recuperação. |
| `state` | Estado da reserva/envio/publicação. |
| `created_at` | Instante de criação/reserva no servidor. |
| `receipt` | Tag, SHA e Release retornados pelo GitHub. |
| `finished_at` | Instante de conclusão ou incerteza. |

## poc_events

| Coluna | Significado |
|---|---|
| `id` | Identidade imutável da candidata ou sequência de evento. |
| `candidate_id` | Candidata à qual pertence a evidência. |
| `event` | Tipo de evento/aviso. |
| `actor` | Autor do evento auditável. |
| `at` | Data do evento no servidor. |
| `detail` | Contexto de auditoria sem secrets. |
