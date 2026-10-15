# Entrega: controle, fila e cadastro de aprovadores

**Preparar uma nova rodada:** usar [o formulário por cenário e a CLI com simulação](FORMULARIO-E-CLI.md).
O fluxo oficial é **Entrega · Preparar candidata**, pela `main`.
A [base anterior preservada](BASE-VALIDADA-FORMULARIO.md) registra as provas das
rodadas 1.15.5 e 1.15.6 antes da simplificação da interface.

Fluxo oficial opt-in, validado na **`main`**. A rodada **1.15.5** concluiu
preview Web, dois aceites manuais nas DMs, publicação GitHub automática e
**Android `1.1.0+2`, patch `5` em staging**, com atualização da tabela e do cartão
Slack. Não houve validação em dispositivo nem promoção stable. Os controles
foram pausados no encerramento; publicação não está liberada permanentemente.

Novas versões usam **`release/X.Y.Z`**, **`vX.Y.Z-rc.N`** e **`vX.Y.Z`**.
O histórico `poc-release/...` e `poc-v...` permanece intacto, sem misturar os
formatos na mesma versão. A mudança de nomes não dispara releases nem altera
aceites. Veja [a convenção completa e o exemplo de RC2](NOMES-OFICIAIS.md).

Evolução em 15/10: o preparo pode congelar `patch_mode=android_staging`, com
preview completo e escopo GitHub. A geração Android é uma etapa local explícita,
somente após os dois aceites e a Release GitHub, sem promoção para stable.
O cartão continua sendo editado e avisos por marco aparecem também no canal.
Veja o [roteiro da rodada](RODADA-PREVIEW-STAGING.md) e a
[ponte Android com autorização e recibos](ANDROID-STAGING.md).
O [resultado real da 1.15.5](RODADA-PREVIEW-STAGING.md#resultado-real-da-1155)
comprova esses caminhos até o upload em staging e a apresentação final.
Testes locais, upload e preview continuam sem comprovar execução no aparelho.

Extensão de 15/10/2026: a proposta 1 de **titulares automáticos no banco** está
integrada na `main`, com migração aplicada e ensaio solo por DMs reais concluído.
Acrescentou somente `delivery_reviewers`: **três tabelas de aplicação** no total.
Israel ocupou os dois papéis automaticamente, sem pessoas no JSON. A candidata
`1.15.3 RC1` foi cancelada depois dos dois aceites; não houve promoção final,
preview ou patch. A tag RC e sua prerelease foram criadas e preservadas.
Veja os [resultados e logs sanitizados](evidence/reviewer-defaults/README.md), o
[guia dos aprovadores](APROVADORES.md) e o
[planejamento original e sua evolução](PLANO-APROVADORES.md).

Em 14/10/2026, as migrações aditiva e de aposentadoria foram aplicadas no projeto
exclusivo após backup e restauração verificados. Naquele momento, restaram somente
`delivery_control` e `delivery_outbox` no schema público. O receptor de DMs está implantado para testes;
publicação e preparos permanecem bloqueados. O worker da main foi integrado e validado com DMs reais; veja [evidências](evidence/main-worker/README.md).
Veja o [estado atual e a prova dos cliques](evidence/main-migration/README.md).
Veja [resultados da validação do banco](evidence/database-validation/README.md).
Ensaios operacionais com controles fictícios validaram aceites reais nas DMs, rejeição e RC2. Nenhuma tag/Release foi criada nessas rodadas. A rodada 1.15.2 permanece cancelada; sua RC não deve ser reutilizada silenciosamente.
Veja [recuperação, correções e limites do cron](evidence/worker-recovery/README.md).
Em 15/10, uma execução `schedule` na `main` recuperou as oito tarefas do ensaio
prolongado. Ocorreu depois da janela combinada; a pausa também foi tardia.
Worker e receptor estão desligados, com fila sem pendências e publicação bloqueada.
Veja a [prova do cron, os horários e a lacuna de encerramento](evidence/cron-extended/README.md).


## Pendência: restaurar validações humanas antes da adoção na Amulets

A dispensa de revisão humana em PRs para `main` e `release/**` é temporária, exclusiva deste projeto durante o amadurecimento da esteira. Não representa a política final da Amulets.

Antes da adoção, alinhar com Samuel quem pode preparar candidatas, revisar código, dar aceite técnico e de negócio e autorizar publicação. Restaurar as regras de revisão humana acordadas, definir quantidade de revisores e validar os bloqueios com contas distintas. Essa pendência deve aparecer nos próximos balanços do que falta concluir.

Durante esta fase, priorizar CLI e APIs para preparar PRs, acompanhar checks e integrar alterações autorizadas. Usar Computer Use quando necessário para validar a experiência visual e as interações reais. A dispensa de review de PR não remove os aceites de release nem autoriza publicação por si só.

Para a Amulets, ainda alinhar administração, substituição e identidade dos
aprovadores com Samuel. O [cadastro implementado](APROVADORES.md) escolhe titulares
automaticamente e não transfere aceites de candidatas abertas. O ensaio deste
projeto usa Israel nos dois papéis, com `solo: true`; não comprova revisão por duas pessoas.


## O que muda

| Responsabilidade | Destino |
|---|---|
| Pessoas elegíveis, identidades e titulares automáticos | `delivery_reviewers`, nova migração |
| SHA, tag, responsáveis congelados, dois aceites, rejeição, revisão, mensagens e run | `delivery_control` |
| Registro no GitHub, envio/edição de mensagens e disparo, com tentativas/recibos | `delivery_outbox` |
| Manifesto completo, changelog e eventos permanentes | branch `codex/delivery-history`, diretório por candidata |
| Regras da entrega, modo solo e fonte `database-v1`, sem pessoas no JSON | `delivery/delivery-policy.json`, no commit confiável do workflow |
| Builds, preview, Release Candidate e Release final | GitHub/Pages existentes |
| Credenciais | secrets existentes; nada em JSON de configuração ou eventos |

A configuração de teste é **solo**: o seed da nova migração cadastra Israel como
titular técnico e de negócio. São dois papéis e duas DMs distintas, não duas
pessoas. O preparo lê os padrões pelo RPC `delivery_resolve_reviewers`, guarda o
snapshot em `manifest.reviewers` e o banco compara novamente os padrões ao
registrar a candidata. `delivery_control` mantém duas chaves estrangeiras e uma
cópia dos responsáveis daquela avaliação. Sem titular ativo, o preparo bloqueia;
não escolhe outro elegível por conta própria.

O manifesto guarda `tooling_sha`, que identifica a versão da política usada.
Trocar o titular não muda as candidatas já abertas. Revogar o papel ou inativar
um designado bloqueia novas decisões dessa avaliação, preservando os aceites já
registrados. Candidatas antigas permanecem com seus IDs congelados e sem cadastro
retroativo. Retentativa do mesmo manifesto não elege os titulares de novo.

Não há prazo de 36 horas na avaliação nova. A assinatura Slack continua vencendo
em cinco minutos para proteção contra replay. Encerramento ocorre por rejeição,
cancelamento explícito ou publicação. `none` nunca dispara publicação; uma
avaliação encerrada com dois aceites nesse escopo pode ser cancelada pelo operador.

## Caminho normal

1. `delivery-prepare.yml` usa a integração configurada (`main`) e as mesmas
   verificações de código, proteção de tags e build/preview do fluxo atual.
2. O cenário selecionado resolve os parâmetros internos uma única vez.
   `controls_only` dispensa build/preview/patch. `full` valida preview, **sem patch**.
   Cenários com Release final usam `github_test` e permitem só GitHub Release.
   O preparo normal cria tag RC e prerelease mesmo em `controls_only`/`none`;
   `none` bloqueia a promoção final, não esses registros de candidata.
   Para uma versão nova, cria `release/X.Y.Z` e `vX.Y.Z-rc.1`; a numeração RC
   pertence à tag, não ao nome da branch. O cenário `android_staging` resolve
   `patch_mode=android_staging`, `full` e escopo interno `github_test`:
   congela um plano para execução local após a publicação GitHub. O job de
   preparo continua sem executar `shorebird patch`.
3. O script grava um manifesto imutável no GitHub e cria a Release Candidate com
   o preview, quando houver. Novas candidatas incluem os titulares resolvidos no
   banco; o registro confere o snapshot em transação antes de congelá-lo. O banco
   mantém referência, digest, controle e a pequena cópia de identidades.
4. A fila publica um cartão de acompanhamento no canal e uma DM por papel.
   Cada DM tem seu aceite e **Negar versão**. O canal não tem botões de decisão.
5. O receptor valida assinatura, app, workspace, destinatário, papel e ID da DM.
   Grava decisão **e tarefa de histórico na mesma transação**, antes do ACK.
6. Um aviso de despertar acelera o worker; a fila persistida e a varredura
   periódica recuperam um despertar perdido. Não usamos `waitUntil` como fila.
7. O worker grava cada evento no GitHub e confirma os bytes pelo commit imutável.
   O receptor verifica novamente o conteúdo antes de dar baixa na tarefa.
8. Dois aceites fecham a avaliação. Com escopo de publicação e controles
   habilitados, depois da persistência dos eventos é feito um único dispatch;
   a publicação possui um único `run_id` proprietário. Em `none`, não há dispatch.
9. A publicação conserva tags RC e cria a tag final no SHA aprovado. O cartão é
   editado, mostra o link da execução e depois os resultados de versões comprovados.
10. Operações concluídas de candidatas terminais saem da fila após sete dias,
    somente se todas estiverem confirmadas e o evento final tiver recibo GitHub.
    O controle mínimo permanece para rejeitar interações antigas.

A Release final reaproveita a validação existente da tabela de versões e usa
`Mudanças` com links de PRs/commits e evidências ao final. O preview fica somente
na Release Candidate; o título final inclui versão e título informado no preparo.
Sem plano Android e recibo separado, não existe distribuição mobile comprovada.
A ponte opcional nova executa somente Android staging; não foi criado um fluxo de lojas.

## Rejeição e RC2

Rejeição e segundo aceite disputam o mesmo bloqueio de linha. Se a rejeição
confirmar primeiro, nenhum aceite posterior reabre a candidata. Se o segundo
aceite confirmar primeiro, a avaliação fecha e o botão de negar perde efeito.

Após correção por PR na branch da release, novo preparo cria outra identidade e
outra tag RC. O banco exige antecessora rejeitada/cancelada e sequência crescente.
Nenhum aceite ou mensagem é transferido. Tags de outro fluxo, versão já promovida
e tag órfã são recusadas antes de serem sobrescritas.

Para novas versões, a branch continua `release/X.Y.Z` e a nova tag é
`vX.Y.Z-rc.2`. Reexecuta-se o mesmo workflow na `main`, informando a mesma
versão; o script encontra o código corrigido da release. RC2 de uma versão
histórica mantém a branch `poc-release/X.Y.Z` e a sequência `poc-vX.Y.Z-rc.N`
da candidata anterior, sem conversão nem transferência de aceites. Versão já
publicada, referência órfã e referência de outro fluxo bloqueiam ambos os
formatos. Ver [nomes oficiais](NOMES-OFICIAIS.md).

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
da aplicação possuía duas tabelas no encerramento do ensaio do cron; o legado foi arquivado e removido pela
migration `20261015012542_retire_legacy_delivery_tables.sql`. O roteiro acima
permanece como referência para uma migração futura, não como estado pendente da POC.
A nova migração `20261015132214_delivery_reviewer_defaults.sql` acrescenta o
cadastro de aprovadores e foi aplicada em 15/10; o banco tem agora três tabelas.
Seu roteiro está em [APROVADORES.md](APROVADORES.md), e a distinção entre versão
local e registro remoto da migração está na [prova da aplicação](evidence/reviewer-defaults/README.md).

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
remota nem distribuição mobile. A rodada de release 1.15.2 foi cancelada pelo
usuário. Os ensaios remotos do worker e das DMs documentados acima não equivalem
à publicação de uma release. A posterior rodada **1.15.5** possui provas próprias
de preview, aceites, Release e patch Android em staging, reunidas no
[resultado da rodada](RODADA-PREVIEW-STAGING.md#resultado-real-da-1155).
