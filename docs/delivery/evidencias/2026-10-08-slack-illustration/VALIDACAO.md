# Etapa ilustrativa de Slack — validação local

Preparada em 08/10/2026, Fortaleza, na branch `codex/rc-operator-planning`. Sem envio Slack, configuração de app/secret, consumo de Copilot ou disparo manual de Actions.

## Alteração

O job opcional `slack_preview` recebe o relatório congelado da avaliação e cria um exemplo de aviso com commits e links para preview/changelog/gates. O conteúdo declara simulação; não consulta o estado ao vivo. O script não possui operação de envio e não lê as credenciais Slack.

O job depende somente de preflight e relatório/preview. Aprovação, autorização e promoção não dependem dele. Não tem Environment de revisão nem permissões de escrita, Pages ou OIDC. A integração à main é necessária para aparecer em uma nova rodada; o workflow já executado da 1.6.0 permanece preservado.

## Conferências executadas

| Conferência | Resultado | Registro |
| --- | --- | --- |
| Relatório real da RC 1.6.0, mesmo com credenciais fictícias no ambiente | Gera JSON/Markdown, `message_sent=false`; não incorpora os valores do ambiente | `validation.json`, `preview/` |
| Identidade, host ou sucesso do preview incorretos | Três entradas recusadas, sem criar saída | Logs por caso e exit code esperado 1 |
| Tentativa de habilitar `--send` | Flag inexistente recusada, exit code esperado 2 | `unsupported-send-stderr.log` |
| YAML e grafo de dependências | Sintaxe aceita, grafo sem ciclos e nenhum job dependente de `slack_preview` | `workflow-graph-validation.json` |
| Actionlint 1.7.12 | PASS; sintaxe, expressões e dependências do workflow alterado | `actionlint-validation.json`, stdout/stderr |
| Suíte offline existente da esteira | 273 testes passaram em 190,003 segundos | `delivery-suite-summary.json` |

O Actionlint foi baixado do release oficial `rhysd/actionlint`, com SHA-256 conferido contra os checksums oficiais. Shellcheck e pyflakes não foram utilizados. Nenhum binário de ferramenta entra no commit.

A saída integral da suíte desta execução ficou no histórico das ferramentas; não foi exportada integralmente para um arquivo. O JSON registra esse limite, o comando, duração, contagem e resultado terminal. As recusas dos smoke cases são resultados esperados; os logs originais foram mantidos.

## Pendências após esta entrega

Configurar o Incoming Webhook e `SLACK_WEBHOOK_URL` pelo [manual](../../CONFIGURAR-SLACK-LAB.md). Depois, integrar o remetente real e confirmar recebimento no canal privado. A simulação não se transforma em envio ao encontrar o secret.

O resumo semitécnico por IA, fallback assíncrono, estados consolidados e outros refinamentos estão no [quadro de prioridades](../../AJUSTES-E-PRIORIDADES.md) e no [contrato de comunicação](../../CHANGELOG-E-AVISOS-SLACK.md).
