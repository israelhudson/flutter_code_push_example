# Cenários e limites da evidência

Os ensaios SQL usam PostgreSQL local PGlite e fixtures; HTTP usa transportes falsos.
Não representam cliques humanos, DMs entregues ou publicação real no GitHub.

| Cenário | Resultado esperado | Prova local | Próxima prova real |
|---|---|---|---|
| Técnico primeiro | 1/2, DM ao negócio, sem publicar | SQL/HTTP | Cartão e recibo Slack |
| Negócio primeiro | 1/2, DM ao técnico | SQL | Mesmo teste na conta Israel |
| Dois papéis solo | 2/2, DM criador, identificado solo | SQL/HTTP | Cliques Israel e DM |
| Operador/branch indevidos | Bloquear antes de gerar RC | Python/HTTP | Run controlado sem efeitos |
| Ajuste com motivo | Autor/hora/motivo; bloqueia RC1 | SQL | Modal Slack real |
| Correção/RC2 | Novo ID, SHA/tag/cartão e zero votos | SQL | PR para poc-release, nova preparação |
| Repetir aceite | Um registro por papel | SQL | Clique repetido |
| Voto de outra pessoa/canal/app | Bloquear sem gravar | SQL/HTTP | Outro usuário autorizado apenas para ensaio futuro |
| Prazo 36h | Recusar voto/publicação após expirar | SQL | Inspeção de expiração real sem alterar relógio |
| Preview alterado | Recusar bytes/SHA/hash divergentes | HTTP/Python | Snapshot real e prova íntegra |
| Envio incerto | Reservar antes de POST, sem duplicar | SQL/HTTP | Reconciliação de recibo real |
| Falha de aviso após voto | Voto permanece salvo | HTTP | Falha controlada sem falsificar usuário |
| Publicação desabilitada | is_lab não concede permissão | SQL/Python | Run bloqueado |
| Publicação parcial | Recuperar mesma intenção/mesmo Run | SQL | Rerun da execução original |
| Publicação repetida | Retornar recibo sem Git writes | SQL/Python | Segunda consulta da mesma candidata |
| Encaminhamento antigo | Bytes/headers intactos; POC nunca cai no receptor antigo | HTTP router | Clique antigo com responsável Mobile |
| Tabelas privadas | RLS, anon/auth denied, servidor restrito | SQL | Advisors e catálogo do projeto exclusivo |

Registrar resultado, SHA, Run URL, candidata, recibo Slack e classificação em
`evidencias/`. Erro de fixture/lint corrigido não é falha de entrega real.
Teste negativo verde significa que o bloqueio esperado ocorreu.

## Lições e pontos para Amulets

- Quem pode iniciar RC é uma decisão distinta de quem aprova e publica.
  Confirmar com Samuel operadores, substitutos e permissões de PR.
- Solo valida o mecanismo de papéis, não independência de duas pessoas.
- Um app Slack tem uma URL de interação. Reutilizá-lo requer encaminhamento por
  namespace, preservar corpo/HMAC e ensaiar os cartões antigos antes da troca.
- Branch própria exige validar a branch tanto no workflow quanto no backend.
- ACK em até três segundos; DB/avisos rodam depois e têm evidência separada.
- Um voto confirmado não pode ser anunciado como falho por um erro posterior de DM.
- Tag RC é evidência preservada. Correção entra por PR; RC2 não herda votos.
- Changelog imutável tem fallback de commits. Resumo IA pode ser um job próprio,
  mas não reescrever a candidata aprovada. Integração Plane/Copilot fica fora deste PR.
- Antes de Shorebird, confirmar APP ID da POC
  `bc6a30bd-0768-4326-8885-8be69c59aed2`, release-base por Android/iOS,
  track e dispositivo instalado. Patch efetivo começa nulo até recibo real.
- Não há publicação em stores nem patch mobile neste PR.
