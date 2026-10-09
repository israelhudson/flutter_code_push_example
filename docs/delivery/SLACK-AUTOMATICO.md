# Avisos automáticos da candidata no Slack

**Estado: implementação preparada na branch `codex/slack-candidate-notices`,
aguardando integração e ensaio do fluxo da candidata.** A
[conexão real já foi validada](CONFIGURAR-SLACK-LAB.md); essa prova isolada
não confirma os avisos automáticos descritos aqui. Copilot e Plane continuam
inativos. O material usado vem da comunicação congelada, com contexto explícito
de PR quando disponível e histórico de commits como fallback.

## Como funciona

1. A avaliação valida o preview e congela o relatório com candidata, SHA, base,
   versões, texto e links. Sem relatório congelado e preview válido, o worker
   ignora o aviso; não recompõe um changelog para uma avaliação que falhou antes
   desse ponto.
2. Novas candidatas recebem `notification_schema=1`. As transições registram
   eventos em `slack_events` na mesma escrita do estado correspondente. O
   fluxo não acrescenta avisos retrospectivos à entrega 1.6.0 nem a registros
   anteriores sem esse esquema.
3. Jobs opcionais chamam `release-lab-slack.yml`. O worker lê a fila da mesma RC,
   gera os avisos a partir do relatório congelado e drena os eventos pendentes.
   Cada evento preserva sua identidade e conteúdo.
4. Antes do POST, ele confirma bot e destino e persiste a tentativa como
   `unknown`. Só registra `sent` após resposta válida com canal/`ts` ou prova
   positiva encontrada por leitura do histórico.
5. O recibo sanitizado fica disponível para conferir o resultado. Slack com
   falha, indisponível ou lento gera aviso opcional; os gates e a publicação
   continuam pelo caminho obrigatório.

| Job opcional | Evento observado |
| --- | --- |
| `slack_candidate` | Candidata com relatório/preview válidos, aguardando revisores |
| `slack_first` | Aval de Israel registrado |
| `slack_second` | Aval de Fabrícia registrado |
| `slack_ready` | Dois avais; aguardando comando final separado |
| `slack_publication` | Resultado de promoção confirmado ou publicação parcial para recuperar |
| `slack_final_status` | Estado final reconciliado com a execução e as decisões |

A reconciliação do estado pode chamar o mesmo worker depois da observação.
Os jobs de aprovação e publicação não dependem dos jobs Slack. Um aviso atrasado
pode mostrar uma transição anterior; a execução e o diário no GitHub são a fonte
atual para decidir. A mensagem traz o estado do evento, a RC e seus links.
Os nomes `first`/`second` identificam os papéis Israel/Fabrícia, e não obrigam
que as decisões humanas ocorram nessa ordem. Há eventos de rejeição,
cancelamento, falha e substituição quando houver relatório congelado elegível.

**1/2 continua bloqueado. 2/2 habilita somente PUBLICAR.** As contas Israel e
Fabrícia registram os dois avais no LAB; qualquer um dos publicadores autorizados
dá o comando final separado no GitHub. A evidência registra as contas usadas;
o aceite de revisão independente na Amulets continua pendente. Slack apenas
comunica esses fatos.

## Persistência e recibo

A fila pertence ao registro da candidata. A outbox de comunicação é outro
arquivo: `release-lab/slack-outbox.json`, na branch `codex/release-lab-state`.
O adaptador `slack_outbox.py` não edita `release-lab/state.json`. Acrescenta
checkpoints `unknown`/`sent` usando o SHA do arquivo na API Contents como
comparação antes da escrita; um conflito exige reler e preservar o que já
existe. SQLite local é restaurado a partir desse registro durável.

| Estado/resultado | Significado | Conduta |
| --- | --- | --- |
| `sent` | Canal e `ts` confirmados | Reaproveitar o recibo para o mesmo evento/conteúdo |
| `unknown` na outbox | Tentativa persistida; resultado do POST não confirmado | Ler histórico; não repetir o POST |
| `skipped` no recibo | Envio omitido, por exemplo token ausente/inválido | Registrar motivo e seguir a entrega |
| `blocked` no recibo | Destino, identidade, persistência ou reconciliação não confirmados | Preservar o estado; investigar sem reenviar automaticamente |

O recibo `slack-receipt.json` inclui o resultado, indicação de duplicata,
hash do payload, `client_msg_id`, canal e a identidade congelada de
candidata/run/snapshot; quando confirmado, inclui o `ts` exato. O worker
termina sem falhar a entrega mesmo quando a comunicação foi omitida ou
bloqueada. **Job verde sozinho não prova mensagem enviada: conferir `sent`,
recibo e a mensagem visível.**

O checkpoint durável `unknown` precisa existir antes do POST. Se essa escrita
falhar, nenhum POST é autorizado. Se o runner cair depois do POST e antes do
checkpoint `sent`, a próxima tentativa encontra `unknown` e procura prova no
histórico. Mudar o conteúdo com a mesma chave é bloqueado.

Isso reduz repetições dentro do contrato do LAB; **não há promessa de entrega
exatamente uma vez**. `client_msg_id` é correlação adicional. Perder a outbox,
alterar manualmente as chaves ou apagar checkpoints compromete a recuperação.

## Conferir e retomar

Para inspecionar os avisos de uma candidata sem enviar:

```bash
GITHUB_REPOSITORY=israelhudson/flutter_code_push_example \
python3 tools/delivery/slack_events.py \
  --candidate-tag TAG-DA-CANDIDATA \
  --output build/slack-inspecao \
  --render-only
```

Também é possível localizar a candidata com `--evaluation-run-id RUN`.
A inspeção pode consultar dados do GitHub; `--render-only` não envia ao Slack.
O gerador ilustrativo `slack_preview.py` continua separado e sem credenciais.

Para recuperação operacional, usar o mesmo worker e a mesma RC para drenar a
fila; ele recupera os recibos confirmados e reconcilia `unknown`. Após integrar,
abrir **Actions → LAB - Avisos automáticos no Slack → Run workflow**, selecionar
`main` e informar a tag da candidata. A opção `render_only` permite inspecionar
antes do envio. O workflow bloqueia dispatch manual fora da `main`.

O artefato se chama `release-lab-slack-<notification_label>` e preserva os
resultados e subdiretórios por evento, com `notice.json` e `slack-receipt.json`.
O adaptador também aceita um aviso já congelado:

```bash
python3 tools/delivery/slack_outbox.py \
  --notice CAMINHO/notice.json \
  --output-dir build/slack-integracao
```

Esse segundo comando pode enviar um evento ainda não tentado quando executado
com as credenciais do fluxo. Para `unknown`, ele somente consulta o histórico
e exige correspondência positiva de `client_msg_id`, conteúdo visível, usuário
do bot, app esperado, canal e `ts`. A busca é limitada a três páginas, até
100 mensagens por página, com timeout de 10 segundos por chamada Slack.
Permissão ausente, timeout, falta de correspondência, identidade/conteúdo
divergente ou mais de uma mensagem correspondente na busca mantém o bloqueio.
Uma correspondência positiva prova existência; não prova unicidade nas páginas
não consultadas nem além da retenção do histórico. Ausência na busca não prova
que o envio nunca ocorreu.

Não existe opção de forçar reenvio ou aceitar uma prova arbitrária na CLI.
Preservar a outbox e o aviso congelado; obter acesso de leitura/evidência
e repetir a reconciliação pelo worker. Não trocar chave, apagar `unknown`
ou executar `chat.postMessage` como contorno.

## Próximo ensaio e aceite

As duas próximas jornadas completas autorizadas serão realizadas no GitHub,
com decisões pelas contas do LAB e avisos reais no Slack:

| Jornada | Percurso a comprovar |
| --- | --- |
| A — rejeição e correção | Preparar RC1 → rejeitar → corrigir por PR para a release → preparar RC2 com novos avais → dar comando final → promover estável → retornar a correção à main por PR |
| B — aprovação direta | Preparar uma nova RC1 → registrar dois avais → dar comando final → promover estável |

São **três novas tags RC e duas novas versões estáveis**. As etapas ficam
pendentes neste manual até a coleta dos runs, decisões, mensagens e recibos;
o plano não comprova sua execução.

1. Após integrar, preparar uma nova RC e guardar run, relatório congelado,
   eventos, outbox, recibos e a mensagem visível no canal privado correto.
2. Conferir 0/2, 1/2, 2/2 e comando final separado; confirmar que Slack lê
   as transições reais e não muda autorização nem publicação.
3. Reexecutar a mesma RC/evento em outro runner: recibo `sent` deve ser
   reaproveitado, com `duplicate=true`, sem mensagem adicional.
4. Ensaiar checkpoint falho antes do POST e queda/resposta perdida após o POST.
   Provar ausência de POST no primeiro caso e reconciliação positiva no segundo.
5. Ensaiar secret ausente, destino/membros alterados, histórico sem permissão
   e Slack indisponível: aviso opcional, sem impedir os gates/publicação.
6. Criar RC2 e conferir que suas fontes, links, chaves e decisões não reutilizam
   os da RC1; registros antigos permanecem sem backfill.

Guardar a primeira prova desse fluxo antes de declarar os avisos automáticos
ativos. Os cinco subcasos remotos adversariais da entrega e a validação mobile
continuam pendentes; o ensaio Slack não os substitui.

## O que este LAB ensina para a Amulets

A política atual fixa `app-deploy-test-isr` (`C0C8DUJB52L`), bot
`U0C750FTCS3`, app `A0C750DS05D` e somente Israel + bot. A identidade e os
membros são conferidos antes do envio; a recuperação também confere o autor
e o app da mensagem. Adicionar pessoas ou usar outro canal exige uma política
da Amulets acordada com o time, e uma prova própria.

Definir com Samuel quem prepara a RC, quem substitui/recupera uma tentativa,
canal/app, fontes permitidas e os aceites por destino mobile. A proposta usa
Samuel **E** Vinícius para os avais e Samuel **OU** Vinícius para PUBLICAR;
as contas e permissões ainda precisam ser configuradas na adaptação. Falha
de comunicação é aviso opcional; falha de publicação é resultado da entrega.
GitHub Release, mensagem Slack e preview web não comprovam app distribuído,
disponibilidade em TestFlight/Google Play ou Production.

## Fonte verificada e decisões do laboratório

Fontes oficiais consultadas em **08/10/2026 (Fortaleza)**:

- [auth.test](https://docs.slack.dev/reference/methods/auth.test/): permite conferir `user_id`/`bot_id` da credencial. O app esperado da mensagem é conferido na reconciliação; não é inferido somente dessa chamada.
- [chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/): requer `chat:write`, admite canal privado com participação e retorna canal/`ts`. Erros internos/fatais podem ocorrer após algum efeito; as referências a `client_msg_id` não definem garantia de entrega exatamente uma vez.
- [conversations.history](https://docs.slack.dev/reference/methods/conversations.history/): bot precisa do escopo de histórico pertinente e participação; resultados podem exigir paginação. Para este canal privado, o escopo é `groups:history`.
- [Rate limits](https://docs.slack.dev/apis/web-api/rate-limits/): HTTP 429 informa `Retry-After`; respeitar esse prazo. O LAB preserva resultado incerto e não faz retry automático de POST.
- [API Contents do GitHub](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents): atualização de arquivo existente exige seu SHA. A outbox separada e os checkpoints são decisões deste LAB.

Os limites de busca, timeout, estados, fila e política de membros são decisões
da implementação do laboratório, não garantias atribuídas ao Slack.

## Manutenção das Actions

A prova isolada de conexão registrou o aviso de Actions antigas em Node 20.
O GitHub encerrou esse runtime em 23/09/2026 e passou a usar Node 24;
[anúncio oficial](https://github.blog/changelog/2026-09-23-node-20-is-no-longer-available-in-github-actions/).
As versões estáveis abaixo foram conferidas pela API oficial, incluindo
`runs.using=node24` no `action.yml` do SHA indicado:

| Action | Release consultada | SHA para pin |
| --- | --- | --- |
| checkout | [v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) | [`3d3c42e5aac5ba805825da76410c181273ba90b1`](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/action.yml) |
| upload-artifact | [v7.0.2](https://github.com/actions/upload-artifact/releases/tag/v7.0.2) | [`cf430e030ddbb5b0abf93d22962f4752f3646cd9`](https://github.com/actions/upload-artifact/blob/cf430e030ddbb5b0abf93d22962f4752f3646cd9/action.yml) |
| download-artifact | [v8.0.2](https://github.com/actions/download-artifact/releases/tag/v8.0.2) | [`9000827ccba6bdab643e8b6fd33ac0654aef8333`](https://github.com/actions/download-artifact/blob/9000827ccba6bdab643e8b6fd33ac0654aef8333/action.yml) |

Manter os pins completos e validar os inputs utilizados na migração. Checkout
v7 restringe código de forks em `pull_request_target`/`workflow_run`; não usar
`allow-unsafe-pr-checkout` como contorno. Artifacts mantêm o contrato de arquivos
arquivados por padrão; `archive:false` é uma escolha explícita que não é
necessária para este fluxo. Essas mudanças não alteram retroativamente o teste
de conexão registrado na branch isolada.
