# Avisos automáticos da candidata no Slack

**Estado: fluxo real comprovado na jornada B, entrega 1.7.0.
A jornada A, entrega 1.8.0, teve RC1 rejeitada e está em correção; RC2 pendente.**
A implementação foi integrada pela [PR #19](https://github.com/israelhudson/flutter_code_push_example/pull/19). A
[conexão real já foi validada](CONFIGURAR-SLACK-LAB.md); essa prova isolada
não confirma os avisos automáticos descritos aqui. Copilot e Plane continuam
inativos. O material usado vem da comunicação congelada, com contexto explícito
de PR quando disponível e histórico de commits como fallback.

A integração entrou na main no commit `22b29663d85724ba619600766c78ff38cd3456ec`,
desde 09/10/2026 01:39:53 UTC (08/10, 22:39:53 em Fortaleza). O
[CI 37870620819](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37870620819)
aprovou analyze, testes Flutter e 384 testes da esteira. Isso prova a validação
do código. A jornada 1.7.0 tem os recibos próprios e as mensagens reais abaixo.

## Provas reais e estado atual

A ordem mudou durante o ensaio: o usuário acionou manualmente os dois gates e
PUBLICAR na 1.7.0. Essa entrega passou a ser a jornada B, de aprovação direta;
a jornada A, com rejeição e correção, passou para 1.8.0. As contas do LAB são
Israel e Fabrícia; as operações nesta sessão não comprovam dois aceites humanos
independentes da equipe Amulets.

**B — 1.7.0 concluída.** A
[execução 37870868223](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37870868223)
terminou `completed/success`. Dois recibos e a autorização final de Israel foram
conferidos nas fontes oficiais. A [Release v1.7.0](https://github.com/israelhudson/flutter_code_push_example/releases/tag/v1.7.0)
foi confirmada por GET com `draft=false` e `prerelease=false`, publicada em
08/10/2026 às 22:46:39 de Fortaleza. Tag estável e RC1 apontam ao mesmo código
`22b29663d85724ba619600766c78ff38cd3456ec`.

Cinco mensagens reais foram observadas no canal `C0C8DUJB52L`, com o bot
esperado; os links permitem conferir conteúdo, autor e timestamp:

| Aviso | `ts` confirmado | Prova no Slack |
| --- | --- | --- |
| RC1 pronta, 0/2 | `1791510213.021329` | [Candidata](https://app.slack.com/archives/C0C8DUJB52L/p1791510213021329) |
| Aval Israel | `1791510292.512419` | [Primeiro aval](https://app.slack.com/archives/C0C8DUJB52L/p1791510292512419) |
| Aval Fabrícia | `1791510318.577539` | [Segundo aval](https://app.slack.com/archives/C0C8DUJB52L/p1791510318577539) |
| 2/2, aguardando PUBLICAR | `1791510321.511589` | [Comando final separado](https://app.slack.com/archives/C0C8DUJB52L/p1791510321511589) |
| Publicação concluída | `1791510418.960699` | [Publicação](https://app.slack.com/archives/C0C8DUJB52L/p1791510418960699) |

**A — 1.8.0 RC1 rejeitada, RC2 pendente.** A
[execução 37871436136](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37871436136)
preparou RC1 em 0/2, reutilizando o snapshot do mesmo código, com novo relatório
da candidata. Base e fonte eram iguais; o fallback informou “Sem commits
adicionais desde a base registrada”, sem reaproveitar uma descrição de PR antiga.
O [aviso de candidata](https://app.slack.com/archives/C0C8DUJB52L/p1791510649910329)
foi confirmado em `1791510649.910329`.

A review oficial `fahnassau30` rejeitou o gate Fabrícia. O outro gate continuou
`waiting`, exigindo **cancelamento operacional** do run; nenhum aval Israel
foi gravado. O [observer 37871944797](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37871944797)
terminou com sucesso e consolidou `rejected`, preservando sua prioridade sobre
`cancelled` e mantendo 0/2. Autorização e promoção foram canceladas; não havia
estável 1.8.0 na captura. O
[aviso de rejeição](https://app.slack.com/archives/C0C8DUJB52L/p1791510851085829)
foi confirmado em `1791510851.085829`. O clique da Fabrícia sozinho **não**
encerrou as esperas nesse run.

Correção por PR, RC2 com novos avais, promoção 1.8.0 e retorno da correção à main
continuam pendentes. São três RCs e duas estáveis no plano total; este registro
não acrescenta uma RC negativa extra.

## Correções em preparação após a rejeição

O encerramento automático das esperas está em preparação: reconhecer somente
rejeição nas reviews oficiais, cancelar as esperas sem registrar avais e
conciliar o resultado. Treze testes locais do encerramento, 70 testes Slack e actionlint passaram.
O CI da correção ainda está pendente; o novo encerramento **ainda não tem prova
negativa real**. A recuperação operacional
observada acima permanece registrada.

Há também refinamento da disputa entre workers na outbox: até três leituras,
dentro de três segundos, para reaproveitar um checkpoint `sent` que outro writer
acabou de confirmar. Essa espera consulta somente a outbox do GitHub, sem novo
POST Slack. Se continuar `unknown`, a reconciliação ainda exige prova positiva
no histórico; ausência/timeout não autoriza reenviar. Esse refinamento está em
preparação e não muda os gates, relatórios ou autorização da entrega.

Uma descrição histórica de PR pode falar de uma limitação já corrigida. Não
editar a comunicação congelada para escondê-la: separar o texto histórico do
estado atual observado, com run, review e recibo próprios.

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
fila; ele recupera os recibos confirmados e reconcilia `unknown`. Na main integrada,
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

## Aceite registrado e verificações restantes

As jornadas autorizadas usam decisões nas contas do LAB e avisos reais no Slack:

| Jornada | Percurso a comprovar |
| --- | --- |
| A — 1.8.0, rejeição e correção | RC1 rejeitada e conciliada após cancelamento operacional → correção por PR para release, RC2 com novos avais, comando final, estável e retorno à main ainda pendentes |
| B — 1.7.0, aprovação direta | Concluída: RC1 → dois avais → comando final separado → estável; cinco mensagens reais confirmadas |

O plano total preserva **três novas tags RC e duas novas versões estáveis**.
Duas RC1 e a estável 1.7.0 já têm prova. RC2/estável 1.8.0 e backmerge ficam
pendentes até a coleta de seus próprios runs, decisões, mensagens e recibos.

1. Preparar uma nova RC e guardar run, relatório congelado,
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

A prova do caminho feliz 1.7.0 confirma o fluxo Slack nesse escopo.
Os cinco subcasos remotos adversariais da entrega e a validação mobile
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
As versões abaixo foram conferidas pela API oficial. As Actions JavaScript usam
`runs.using=node24`; `upload-pages-artifact` é composite e usa
`upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f` (v7.0.0), cujo
`action.yml` usa Node 24:

| Action | Release consultada | SHA para pin |
| --- | --- | --- |
| checkout | [v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) | [`3d3c42e5aac5ba805825da76410c181273ba90b1`](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/action.yml) |
| upload-artifact | [v7.0.2](https://github.com/actions/upload-artifact/releases/tag/v7.0.2) | [`cf430e030ddbb5b0abf93d22962f4752f3646cd9`](https://github.com/actions/upload-artifact/blob/cf430e030ddbb5b0abf93d22962f4752f3646cd9/action.yml) |
| download-artifact | [v8.0.2](https://github.com/actions/download-artifact/releases/tag/v8.0.2) | [`9000827ccba6bdab643e8b6fd33ac0654aef8333`](https://github.com/actions/download-artifact/blob/9000827ccba6bdab643e8b6fd33ac0654aef8333/action.yml) |
| upload-pages-artifact | [v5.0.0](https://github.com/actions/upload-pages-artifact/releases/tag/v5.0.0) | [`fc324d3547104276b827a68afc52ff2a11cc49c9`](https://github.com/actions/upload-pages-artifact/blob/fc324d3547104276b827a68afc52ff2a11cc49c9/action.yml) |
| deploy-pages | [v5.0.1](https://github.com/actions/deploy-pages/releases/tag/v5.0.1) | [`368f82528645a54fb793d4d04e342629a3f51346`](https://github.com/actions/deploy-pages/blob/368f82528645a54fb793d4d04e342629a3f51346/action.yml) |

Checkout/upload/download foram integrados no PR #19. Os pins Pages estão no
refinamento em preparação; seu novo preview precisa de validação no fluxo real
da RC2. Não declarar o aviso Node 20 resolvido antes dessa prova.

Manter os pins completos e validar os inputs utilizados na migração. Checkout
v7 restringe código de forks em `pull_request_target`/`workflow_run`; não usar
`allow-unsafe-pr-checkout` como contorno. Artifacts mantêm o contrato de arquivos
arquivados por padrão; `archive:false` é uma escolha explícita que não é
necessária para este fluxo. Essas mudanças não alteram retroativamente o teste
de conexão registrado na branch isolada.
