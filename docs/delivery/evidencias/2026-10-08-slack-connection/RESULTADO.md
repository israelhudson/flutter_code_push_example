# Conexão Slack validada

Execução: https://github.com/israelhudson/flutter_code_push_example/actions/runs/37869235129

Em 08/10/2026 às 22:19:46 (Fortaleza), uma mensagem de teste foi enviada pelo bot Flutter Deploy LAB ao canal privado app-deploy-test-isr. O secret SLACK_BOT_TOKEN foi consumido somente pelo runner, sem leitura de seu valor pelo agente. O adaptador verificou a identidade de bot, o canal privado fixo e os membros Israel + bot antes do envio. A API confirmou channel/ts; uma leitura independente pelo conector confirmou a mensagem visível e o autor do bot.

Resultado: job concluído com sucesso em 7 segundos; recibo state=sent e duplicate=false. Actionlint passou. Nenhuma candidata, tag, aprovação ou Release foi alterada. O texto simulation=true/dry_run=true se refere ao ensaio e à ausência de distribuição do aplicativo; o envio Slack foi real.

Esta execução valida credencial, permissões, destino e envio pelo GitHub Actions. Os avisos automáticos das candidatas ainda não estão integrados. O workflow existe apenas na branch codex/slack-connection-test e não deve ser integrado à main como remetente de produção. Reexecuções são bloqueadas pelo run_attempt para evitar repetir o teste; não se deve reenviar automaticamente quando o resultado de uma chamada for incerto.

Aviso observado: checkout/upload-artifact utilizam versões com runtime Node 20; o GitHub as executou em Node 24. O teste passou, mas atualizar essas actions deve entrar na manutenção da esteira.

Evidências: receipt.json, actions.log e artefato slack-connection-proof (inclui outbox, retenção de 30 dias). Nenhuma credencial foi adicionada aos arquivos.
