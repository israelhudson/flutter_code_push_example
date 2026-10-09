# Alternativa de aprovação por Issue

Esta POC convive com a esteira atual. O prefixo dos novos workflows é **Issue ·**:

| Workflow | Entrada | Resultado |
|---|---|---|
| Issue · Preparar candidata | Run workflow na main | Congela a RC de teste, testa o app, publica/verifica preview e abre a ficha |
| Issue · Conferir decisões | Comentário novo, editado/excluído ou alteração na ficha | Reconfere comentários e atualiza a ficha. Termina sem esperar pessoas |
| Issue · Publicar candidata | /publicar válido ou recuperação do mesmo comando | Reconfere autorização e arquivos. Cria tag e prerelease de teste no GitHub |
| Issue · Verificar PR | PR para main ou test-issue-release/** | Verifica contratos. Em correções da candidata, também roda análise/testes Flutter |

O primeiro ensaio exige **Israel 1/1**. Uma aprovação apenas habilita o comando
final. Este fluxo não implementa 2/2 da Amulets, não usa os ambientes de revisão
do LAB e não distribui aplicativo ou patch Shorebird.

## Instalação após o merge deste PR

1. Integre o PR à `main` da POC usando a revisão e os checks existentes.
   `issue_comment` só dispara quando o workflow existe na branch padrão.
2. No checkout atualizado deste PR, confira e aplique somente as novas proteções:

   ```bash
   python3 tools/delivery/configure_issue_release.py --output build/issue-rulesets-plan
   python3 tools/delivery/configure_issue_release.py --apply --output build/issue-rulesets-applied
   ```

   O segundo comando requer administração do repositório via autenticação do `gh`.
   Cria as três regras Issue, sem bypass: tags `test-issue-*` sem update/deletion,
   branches de correção por PR com check obrigatório, journal sem force/deletion.
   Não substitui regras existentes de nome diferente. Se uma regra Issue já
   existir com configuração divergente, interrompe para inspeção.
3. Em Settings > Secrets and variables > Actions > Variables, crie a variável de
   repositório **`ISSUE_RELEASE_ENABLED`** com o valor literal **`true`**.
   A ausência ou `false` desativa apenas esta alternativa. Não é um secret.
4. O secret de Slack já existente, **`SLACK_BOT_TOKEN`**, atende também a este
   ensaio no canal privado `app-deploy-test-isr`. Sua ausência não bloqueia a entrega.
   O código não precisa de PAT adicional nem instala a Action manual-approval.

Não aplique estas instruções na Amulets. Sua política e seus destinos precisam
ser acordados antes. Este PR não altera a visibilidade da POC.

## Roteiro de uma candidata

1. Faça a alteração por PR para `main` e aguarde os checks/revisão.
2. Abra **Actions > Issue · Preparar candidata > Run workflow**, na `main`, com
   a conta Israel. Informe uma versão, por exemplo `1.13.0`, e um título claro.
3. A automação cria `test-issue-release/1.13.0` e `test-issue-1.13.0-rc.1`. Depois
   de testar, compilar e confirmar o link por HTTP, abre uma Issue com changelog,
   preview, SHA e instruções. A preparação termina e não espera sua aprovação.
4. Experimente o preview e comente, em uma linha nova:

   ```text
   /aprovar test-issue-1.13.0-rc.1
   ```

   Aguarde a ficha indicar **Aprovada (1/1). Falta /publicar**. A verificação precisa
   registrar o evento de criação desse aval; comentário não processado não autoriza.
5. Quando quiser publicar, escreva **outro comentário**, posterior ao aval:

   ```text
   /publicar test-issue-1.13.0-rc.1
   ```

   A automação reconfere tudo, cria `test-issue-1.13.0` no mesmo commit da RC e uma
   **prerelease de TESTE**, com `make_latest=false`. A Release estável `v1.12.0`,
   os gates e o catálogo da esteira atual permanecem preservados.

Cada conta conta uma vez. Comandos de outro usuário, de bot, de PR, de uma Issue
não registrada, de outra tag ou em texto citado não dão autorização. Permissão
atual de escrita/administração também é obrigatória. Checkbox manual não é aval.
Uma edição/exclusão invalida o comentário por ID. Escreva um novo aval para retomar
uma RC ainda não rejeitada. Alterar ou fechar a ficha bloqueia publicação e invalida
os avais existentes. A automação restaura o corpo conhecido, mas não recria decisões.

## Rejeição, correção e RC2

1. Na ficha da RC1, comente `/reprovar test-issue-1.13.0-rc.1`.
   Rejeição encerra essa RC. Um novo `/aprovar` nela não a reabre.
2. Crie uma branch de correção a partir de **`test-issue-release/1.13.0`**.
3. Faça o PR dessa branch para **`test-issue-release/1.13.0`**, aguarde os checks e
   faça o merge. A branch da entrega não contém o número RC.
4. Execute novamente **Issue · Preparar candidata** com `1.13.0` e o título da
   correção. A tag será **`test-issue-1.13.0-rc.2`**, após o merge do PR.
5. A RC2 recebe outra ficha, seu código e hashes. Começa com **0/1**, exige novo
   `/aprovar` e novo `/publicar`. RC1/tag/ficha ficam no histórico. Um comando na
   ficha antiga não pode publicar a RC2.

Uma RC por vez vale **dentro da alternativa Issue**. O caminho LAB possui seu
próprio diário e pode continuar funcionando. As duas esteiras compartilham apenas
o site e seu lock de publicação `pages-preview`, sem compartilhar avais ou versões.
Integrar tarefas novas à main durante a revisão não altera o código congelado.
Correção na branch da candidata bloqueia a publicação antiga até preparar nova RC.

## Preview e changelog

O PR executa checks. A preparação da RC compila o snapshot exato e só abre a ficha
depois de confirmar arquivos, hashes e link. O build roda em runner sem credencial
de escrita. Outro runner publica somente os arquivos estáticos validados.

O histórico Pages usa `snapshots/SHA/`. Se já existir esse SHA, o importador exige
o mesmo fingerprint de fontes/toolchain e o mesmo hash dos bytes do app. Reutiliza
esses bytes e preserva o wrapper original, que pode mostrar o nome de uma entrega
anterior. **A Issue identifica a RC de teste e seu relatório**. Inputs/bytes diferentes
para o mesmo SHA bloqueiam a importação, nunca sobrescrevem o snapshot.

O changelog inicial usa o histórico completo de commits desde a última publicação
Issue, ou desde a última tag estável convencional no primeiro ensaio. Lista truncada
ou base não ancestral bloqueia o corte. Nenhum resumo por IA é necessário.

## Recuperação e limites

- Falha antes de abrir a ficha: repita a preparação com mesma versão e título.
  A reserva/corte parcial é reconciliado. Um build incompleto reutiliza a RC sem avais.
- Intenção de publicação parcial: use **Issue · Publicar candidata**, na main,
  informando o número da Issue e o ID do `/publicar` **original**. Essa entrada não
  concede aprovação: o código busca os comentários reais e valida seu conteúdo,
  autoria, integridade e anterioridade dos avais.
- Repetição de `/publicar` após conclusão apenas observa o recibo existente.
  Tag ou Release divergente interrompe o processo, sem apagar/mover/sobrescrever.
- Edição/exclusão do aval ou do comando original durante publicação parcial bloqueia
  a continuação. Outra RC também fica bloqueada enquanto houver efeito incompleto.
  Inspecione o journal/efeito antes de decidir a recuperação. Não troque o ID da intenção.
- A concorrência do Actions não garante entrega de todos os eventos: execuções
  pendentes podem ser substituídas. O código consulta todas as páginas, mas exige um
  evento de criação registrado para autorizar um aval. Se um comando não avançar,
  confira o resultado do run e poste um comentário novo. Não há publicação por edição.
- GitHub não oferece transação atômica entre comentários, tags e Releases. O código
  reconfere a aprovação antes da tag e antes da Release. Uma revogação depois de um
  efeito já confirmado não desfaz esse efeito. Falha entre ambos fica como parcial.
- A alternativa não protege contra um administrador que deliberadamente altera
  políticas/proteções/código confiável. Esse administrador controla o repositório.
- Slack é opcional. Um checkpoint remoto `unknown` precede o POST. Uma resposta
  incerta não é reenviada automaticamente. Confira o canal e o journal antes de
  qualquer reconciliação manual. O primeiro PR não adiciona reconciliação automática
  de avisos Slack incertos. Avisos de aval obsoleto não são enviados.

## Logs e evidências

Cada workflow preserva por 90 dias seus artefatos: corte, metadata/HTTP, relatório,
decisão, recibo e avisos. O journal independente registra transições e intenções em
`issue-release/state.json`, na branch `codex/issue-release-state`. IDs/autores/hashes
dos comentários ficam ligados à autorização. Credenciais nunca entram nos registros.

O relatório em `evidencias/2026-10-09-issue-approval/` separa testes com API falsa,
checks reais do PR e o ensaio por comentários que só pode ocorrer após o merge.
1/1 comprova o mecanismo da POC; não prova dois revisores independentes da Amulets.

## Relação com as referências fornecidas

- [Revisar deployments](https://docs.github.com/pt/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments)
  descreve os gates nativos. Os required reviewers privados têm restrição de plano.
- [Manual Workflow Approval](https://github.com/marketplace/actions/manual-workflow-approval)
  usa Issues e permite repositórios privados sem Enterprise, mas mantém o runner
  consultando a Issue. Este PR implementa o padrão por eventos e não instala essa Action.
- [issue_comment](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#issue_comment)
  fornece criação/edição/exclusão na branch padrão, incluindo comentários de PRs.
- [Comentários](https://docs.github.com/en/rest/issues/comments),
  [Releases](https://docs.github.com/en/rest/releases/releases) e
  [rulesets](https://docs.github.com/en/rest/repos/rules) fundamentam as chamadas.
- [Concorrência](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
  e [uso seguro de Actions](https://docs.github.com/en/actions/reference/security/secure-use)
  fundamentam o lock, texto como dados, tokens por job e Actions fixadas por SHA.

Consulta em 09/10/2026. A aprovação por Issue pode funcionar em repositório privado.
Para manter as proteções e o Pages desta POC pessoal privada, GitHub Pro atende.
O site Pages pode ser público mesmo quando o repositório é privado.
[Planos e rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets),
[visibilidade do Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site).
