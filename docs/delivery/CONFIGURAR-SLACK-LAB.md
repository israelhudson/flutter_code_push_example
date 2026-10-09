# Configurar os avisos do laboratório no Slack

**Comece criando um Incoming Webhook para `app-deploy-test-isr`.** É a opção
mais simples para o primeiro aviso. As aprovações e o comando final continuam
no GitHub; o Slack apresenta as mudanças e aponta para a execução correta.

Neste estágio, a etapa ilustrativa **só gera uma prévia**. Não lê credenciais,
não envia mensagens e não altera as decisões da candidata. Configurar o secret
agora prepara a integração; não ativa o envio automaticamente.

## 1. Criar o app e selecionar o canal

1. Abra [Seus apps no Slack](https://api.slack.com/apps), crie um app com o nome
   `LAB — Avisos de entrega` e escolha o workspace que contém o canal.
2. Nas configurações do app, abra **Incoming Webhooks** e ative
   **Activate Incoming Webhooks**.
3. Clique em **Add New Webhook to Workspace**. Selecione o canal privado
   `app-deploy-test-isr` e autorize. Sua conta precisa participar desse canal.
4. Confira o destino em **Webhook URLs for Your Workspace**. A URL gerada fica
   vinculada ao canal escolhido; não se troca o canal no payload.
5. Copie a URL diretamente para o secret do GitHub descrito abaixo. Não cole
   a credencial no chat, código, arquivo, print ou log.

Procedimento e restrição de canal privado conferidos na
[documentação oficial de Incoming Webhooks](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/).

## 2. Guardar a credencial no GitHub

Abra [Actions secrets do laboratório](https://github.com/israelhudson/flutter_code_push_example/settings/secrets/actions):

1. **Settings → Secrets and variables → Actions**.
2. Clique em **New repository secret**.
3. No nome, informe **`SLACK_WEBHOOK_URL`**; no valor, cole a URL privada.
4. Clique em **Add secret**.
5. Informe apenas que o secret está configurado. Nunca envie seu valor.

O workflow futuro precisa receber explicitamente esse secret no job de envio.
Criar o secret sozinho não o disponibiliza a todos os passos.
[Guia oficial de secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets?tool=webui).

## 3. Conferir a etapa simulada

Com um `report.json` da candidata já avaliada, execute na raiz do projeto:

```bash
python3 tools/delivery/slack_preview.py \
  --report CAMINHO/report.json \
  --policy delivery/release-lab-policy.json \
  --output build/slack-preview
```

Troque `CAMINHO/report.json` pelo arquivo real. Os resultados são
`slack-message.json`, `slack-preview.md` e `slack-preview-metadata.json`: conteúdo ilustrativo para inspecionar
localmente ou nos artefatos do Actions. **Nenhuma mensagem é enviada.**

O gerador usa a candidata e os links do relatório. Nesta primeira simulação,
o histórico de commits é o fallback; o resumo por IA ainda é uma melhoria
planejada. Falha ou demora de IA/Slack não deve segurar os gates da entrega.

Depois de integrar a alteração à main, uma nova execução da avaliação mostrará
o job **ILUSTRAR AVISO SLACK — simulação, sem envio** e o artefato
`release-lab-slack-preview`. Nenhum job de aprovação/publicação depende dele.
A execução 1.6.0 já concluída não recebe novos steps retroativamente.

## 4. Modelo do aviso que queremos enviar

Exemplo editorial da mudança de tema; não é resultado de IA nem prova do estado
atual de uma execução. Substitua a identidade e os links pela candidata da vez:

> **Candidata [VERSÃO-RC] — Tema claro e escuro**
>
> Agora você pode alternar o tema pelo botão no topo do aplicativo.
> Ao reiniciar, ele volta ao tema claro; a escolha não é salva e não acompanha
> o tema do sistema.
>
> **Como conferir:** alterne os temas e reinicie o aplicativo.
>
> **Estado:** aguardando Israel e Fabrícia (0/2).
> Depois dos dois avais, qualquer um dos dois poderá autorizar a publicação.
>
> **Experimentar:** [LINK DO PREVIEW]
> **Ver mudanças completas:** [LINK DO CHANGELOG]
> **Revisar/aprovar/publicar:** [LINK DA EXECUÇÃO NO GITHUB]

Se o resumo não estiver pronto, substituir seu texto por
**“Resumo indisponível; histórico de commits desta candidata:”** e listar os
commits. O estado real vem do diário da esteira, nunca da IA. Na Amulets, o
modelo proposto usa Samuel **E** Vinícius para os avais, depois Samuel **OU**
Vinícius para o comando final; as contas precisam ser configuradas.

## 5. O que falta para o envio real

Depois de configurar o app e o secret, integrar um remetente ao aviso preparado,
executado fora do caminho que bloqueia aprovações/publicação. A etapa simulada
nunca deve passar a enviar apenas porque encontrou uma credencial.

Validar na próxima rodada:

- [ ] Recebimento no canal privado correto, com candidata, conteúdo e links.
- [ ] Resposta HTTP `200`/`ok` registrada sem URL secreta; confirmar também
      a mensagem visível no canal. [Resposta do webhook](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/).
- [ ] Ausência de secret, timeout ou erro registra aviso pendente sem bloquear
      a entrega; resposta incerta exige conferir o canal antes de reenviar.
- [ ] 1/2 continua bloqueado; 2/2 informa que falta o comando final separado.
- [ ] RC2 recebe aviso próprio e não reutiliza texto, links ou avais da RC1.

Para um único aviso inicial, webhook basta. **Ele não oferece atualização da
mensagem pelo próprio webhook**, e não retorna o `ts` da mensagem no envio.
Para manter um aviso atualizado, a próxima opção é um bot com **`chat:write`**,
participante do canal privado, usando `chat.postMessage` e `chat.update` para
mensagens do próprio bot. Guardar `channel`/`ts` e evidências do envio.
[Envio com bot](https://docs.slack.dev/reference/methods/chat.postMessage/),
[atualização com bot](https://docs.slack.dev/reference/methods/chat.update/).

O adaptador antigo `tools/delivery/slack_notify.py` utiliza `SLACK_BOT_TOKEN`
e valida um canal restrito a Israel e ao bot. Ele não utiliza
`SLACK_WEBHOOK_URL` e não é ativado por este manual. Sua evolução para um canal
da Amulets com outros participantes requer política própria.

Fontes oficiais consultadas em **08/10/2026 (Fortaleza)**. Nenhum app, secret,
permissão ou envio real foi configurado por meio deste documento.
