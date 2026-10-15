# Entrega: controle em duas tabelas

Implementação opt-in da proposta B. **Fluxo não ativado remotamente.**

Em 14/10/2026, as migrações aditiva e de aposentadoria foram aplicadas no projeto
exclusivo após backup e restauração verificados. Há somente `delivery_control` e
`delivery_outbox` no schema público. O receptor de DMs está implantado para testes;
publicação e preparos permanecem bloqueados. O worker da main ainda aguarda integração.
Veja o [estado atual e a prova dos cliques](evidence/main-migration/README.md).
Veja [resultados da validação do banco](evidence/database-validation/README.md).
Nenhuma candidata foi preparada, nenhum aceite enviado e nenhuma tag/Release
alterada nesta implementação. A rodada 1.15.2 permanece cancelada; sua RC não deve
ser reutilizada silenciosamente.

## O que muda

| Responsabilidade | Destino |
|---|---|
| SHA, tag, responsáveis congelados, dois aceites, rejeição, revisão, mensagens e run | `delivery_control` |
| Registro no GitHub, envio/edição de mensagens e disparo, com tentativas/recibos | `delivery_outbox` |
| Manifesto completo, changelog e eventos permanentes | branch `codex/delivery-history`, diretório por candidata |
| Configuração e identificação dos responsáveis | `delivery/delivery-policy.json`, no commit confiável do workflow |
| Builds, preview, Release Candidate e Release final | GitHub/Pages existentes |
| Credenciais | secrets existentes; nada em JSON de configuração ou eventos |

A configuração atual é **solo**: Israel representa técnico e negócio. São dois
papéis e duas DMs distintas, não duas pessoas. O manifesto guarda `tooling_sha`,
que identifica a versão da política usada. O controle congela os destinatários;
uma alteração posterior de política não troca quem pode aprovar essa candidata.

Não há prazo de 36 horas na avaliação nova. A assinatura Slack continua vencendo
em cinco minutos para proteção contra replay. Encerramento ocorre por rejeição,
cancelamento explícito ou publicação. `none` nunca dispara publicação; uma
avaliação encerrada com dois aceites nesse escopo pode ser cancelada pelo operador.

## Caminho normal

1. `Entrega v2 - Preparar candidata` usa a integração configurada e as mesmas
   verificações de código, proteção de tags e build/preview do fluxo atual.
2. `controls_only` dispensa build/preview/patch. `full` valida preview, **sem patch**.
   O escopo `github` é convertido para `github_test` e permite só GitHub Release.
3. O script grava um manifesto imutável no GitHub e cria a Release Candidate com
   o preview, quando houver. O banco recebe apenas referência, digest e controle.
4. A fila publica um cartão de acompanhamento no canal e uma DM por papel.
   Cada DM tem seu aceite e **Negar versão**. O canal não tem botões de decisão.
5. O receptor valida assinatura, app, workspace, destinatário, papel e ID da DM.
   Grava decisão **e tarefa de histórico na mesma transação**, antes do ACK.
6. Um aviso de despertar acelera o worker; a fila persistida e a varredura
   periódica recuperam um despertar perdido. Não usamos `waitUntil` como fila.
7. O worker grava cada evento no GitHub e confirma os bytes pelo commit imutável.
   O receptor verifica novamente o conteúdo antes de dar baixa na tarefa.
8. Dois aceites fecham a avaliação. Depois da persistência dos eventos, é feito
   um único dispatch; a publicação possui um único `run_id` proprietário.
9. A publicação conserva tags RC e cria a tag final no SHA aprovado. O cartão é
   editado, mostra o link da execução e depois os resultados de versões comprovados.
10. Operações concluídas de candidatas terminais saem da fila após sete dias,
    somente se todas estiverem confirmadas e o evento final tiver recibo GitHub.
    O controle mínimo permanece para rejeitar interações antigas.

A Release final reaproveita a validação existente da tabela de versões e usa
`Mudanças` com links de PRs/commits e evidências ao final. O preview fica somente
na Release Candidate; o título final inclui versão e título informado no preparo.
Não existe distribuição Android/iOS nesta etapa. Não foi criado um fluxo de lojas.

## Rejeição e RC2

Rejeição e segundo aceite disputam o mesmo bloqueio de linha. Se a rejeição
confirmar primeiro, nenhum aceite posterior reabre a candidata. Se o segundo
aceite confirmar primeiro, a avaliação fecha e o botão de negar perde efeito.

Após correção por PR na branch da release, novo preparo cria outra identidade e
outra tag RC. O banco exige antecessora rejeitada/cancelada e sequência crescente.
Nenhum aceite ou mensagem é transferido. Tags de outro fluxo, versão já promovida
e tag órfã são recusadas antes de serem sobrescritas.

## Recuperação de falhas

| Caso | Comportamento |
|---|---|
| GitHub indisponível ao registrar evento | Evento continua pendente; publicação bloqueada |
| Worker interrompido durante escrita de histórico | Lease expira; escrita é repetida no mesmo caminho e compara bytes |
| Slack/dispatch com resposta perdida | Estado `uncertain`; não há reenvio cego |
| Outra execução tenta publicar | Rejeitada pelo proprietário `publication_run` |
| Mesma execução repete publicação | Reconfere tags e Release existentes; não sobrescreve diferenças |
| Callback Slack repetido | Aceite já gravado não incrementa revisão nem cria evento |
| Bot/app incorreto | Envio/ação bloqueados; bot da Amulets é explicitamente recusado |

**Limite deliberado:** resultado incerto de Slack/dispatch exige reconciliação pelo
operador com a mensagem/run real. Não há botão de “tentar de novo” que possa
publicar duas vezes. Não marcar uma tarefa como concluída apenas para liberar a
fila. A reconciliação assistida e o ensaio remoto precisam de uma rodada própria.

Cancelamento manual: workflow `Entrega v2 - Recuperar operações`, campo opcional
`cancel_candidate`. Só funciona antes de começar o dispatch. Não equivale a rollback
de uma publicação iniciada.

## Implantação sem apagar legado

1. Revisar/mergear este PR. Manter `DELIVERY_V2_ENABLED` ausente/false no GitHub e
   nas Edge Functions. LAB, Issue e os workflows atuais continuam existindo.
2. Fazer backup privado das oito tabelas, funções, grants e configuração atuais.
   Conferir contagens e digests do backup, registrar onde restaurar. Não publicar
   payloads Slack, IDs privados desnecessários ou secrets no repositório público.
3. Aplicar a migração aditiva no projeto **xtvueqciogzkyjkkqxcx** e publicar
   `delivery-control`, `poc-slack-approvals` (e router se usado) com a flag desligada.
4. Criar ruleset **Entrega - historico preservado**, ativo, tipo branch, somente
   `refs/heads/codex/delivery-history`, sem exclusões/bypass, com `non_fast_forward`
   e `deletion`. O CLI recusa operar sem essa proteção. Restringir os
   escritores. A Release aponta para esse histórico; editar seu texto não aprova.
   O escritor usa o token efêmero do job com `contents:write`; o PAT do receptor
   continua com Actions write e Contents read. Não ampliar permissões da Amulets.
5. Instalar também o worker na branch padrão `main`: GitHub só executa cron da
   branch padrão. A execução manual de recuperação funciona na `slack-main`.
   Agendamento não promete pontualidade; os cliques também solicitam despertar.
6. Em rodada autorizada, habilitar ambas as flags e executar uma candidata nova.
   Confirmar DMs, identidade, histórico, duas ordens de aceite, negação/RC2, queda de
   worker e publicação repetida. Usar `controls_only`/`github_test` primeiro.
7. Desativar novos preparos no modelo antigo somente após comparar as evidências.
   Manter receptor legado para seus IDs. Não converter aceites antigos para v2.
8. Só remover as oito tabelas antigas em outra migração, depois de backup validado,
   encerramento das pendências e período de observação combinado.

A transição com dez tabelas foi concluída no projeto exclusivo. O banco remoto
da aplicação agora possui duas tabelas; o legado foi arquivado e removido pela
migration `20261015012542_retire_legacy_delivery_tables.sql`. O roteiro acima
permanece como referência para uma migração futura, não como estado pendente da POC.

Rollback: desligar entrada v2 para novos preparos e preservar controles/fila.
Não apagar a fila nem reabrir decisões antigas. Se houver publicação em andamento,
reconciliar o `run_id` antes de desligar o receptor. O rollback não apaga tags ou
Releases que já foram confirmadas.

## Código e limites da evidência

- SQL: transações, papel/DM, dois aceites, RC2, fila, leases e compactação.
- Edge: assinatura, API server-only, procedência do run, confirmação GitHub/Slack.
- Python: reaproveita preparo/publicação existentes e escreve histórico imutável.
- YAML: coordena jobs; build não recebe permissões de publicação do aplicativo.
- Testes PGlite executam SQL real local; HTTP/GitHub/Slack usam fixtures.

Os testes locais não comprovam entrega de DMs reais, cron, proteções da branch
remota nem distribuição mobile. A rodada foi cancelada pelo usuário; não executada.
