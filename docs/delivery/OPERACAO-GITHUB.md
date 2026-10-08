# Operar no GitHub

Esta versão é um laboratório de um operador. O GitHub autentica Israel; Ian,
Samuel e Vinícius são papéis **simulados por Israel**. Dois papéis aprovados não
representam duas pessoas reais. O fluxo nativo de reviews reais continua separado.
As execuções manuais são reservadas a Israel; o agente prepara mudanças,
revisões e evidências, sem disparar esses controles em seu lugar.
A promoção de uma pre-release tem uma decisão real separada: Israel revisa a
candidata e registra seu próprio aceite no GitHub, sem representar outros papéis.

## Preview que abre no navegador

Abra **Actions → Web - Preview Pages por snapshot → Run workflow**, escolha
`main` e informe o SHA completo do commit. Push em `main` também publica o preview.

- [Último preview](https://israelhudson.github.io/flutter_code_push_example/)
- Cada commit tem seu próprio endereço: `/snapshots/<SHA40>/`.
- A página mostra versão, SHA e identidade do build. Os snapshots anteriores
  permanecem na branch `codex/pages-previews`.
- O build tem a base URL do Pages, por isso seus bytes/hash diferem do ZIP do CI.
  A fonte e o SDK ficam fixados; não se afirma equivalência de bytes com o ZIP.
- O site é público. Somente o build web e sua identidade vão para o Pages.
  Aprovações, bancos, recibos e credenciais ficam fora do site.
- O preview web não valida atualização Shorebird, Android ou iOS.

## Controles de entrega

Abra **Actions → Delivery - controle persistente do laboratorio → Run workflow**.
Use `main`. O resumo de cada execução mostra o estado, a candidata e o hash que
precisa ser copiado para a próxima ação.

| Ordem | operation | Preencher | Resultado |
|---|---|---|---|
| 1, apenas uma vez | `initialize` | `source_sha` da base escolhida | Produção e release-bases simuladas |
| 2 | `technical-review` | `source_sha`, role `ian` | Revisão técnica simulada; 0 aprovações |
| 3 | `prepare` | mesmo SHA, `delivery_id` ex. `entrega-0042`, `rc=1` | Builds web/Android/iOS; RC imutável em 0/2 |
| 4 | `approve` | candidata, hash, role `samuel` | 1/2, sem publicação |
| 5 | `approve` | candidata, mesmo hash, role `vinicius` | 2/2 autorizada, sem publicação |
| 6 | `publish` | candidata e mesmo hash | Recibos **fictícios**; produção simulada só avança se todos concluírem |
| Consulta | `status` | candidata opcional | Estado recuperado em outro runner |

`prepare` compila Android AAB de laboratório e iOS XCArchive sem assinatura.
Os artifacts têm SHA e hashes próprios; iOS não gera IPA instalável. Nenhum build
é enviado ao Shorebird, Play Console, App Store Connect ou TestFlight.

Para corrigir, revise o SHA novo e prepare a próxima `rc` da mesma entrega.
As aprovações da RC anterior não aprovam a nova. Outra entrega entra na fila.
`next` ativa a próxima quando não houver candidata ativa; se a base mudou,
ela fica bloqueada e exige nova preparação.

## Registrar a release LAB no GitHub

O `publish` da tabela acima grava recibos fictícios no estado persistido. Para
registrar essa candidata como uma **GitHub pre-release real de laboratório**, o
proprietário usa outro comando manual. A decisão final de publicar é de Israel;
Samuel e Vinícius continuam sendo papéis simulados, identificados dessa forma
no plano, no recibo e nas notas da release.

1. Abra **Actions → Delivery - Registrar release LAB no GitHub → Run workflow**.
2. Escolha `main`, `action=plan` e copie a candidata e o hash completo do resumo
   do controle persistente. O comando carrega os registros e os bytes congelados;
   não compila outra versão nem escolhe a ponta atual da main.
3. Confira no plano a versão, tag, SHA da fonte, hash do manifesto e preview.
   O artifact da execução preserva o plano, os eventos e os checkpoints.
4. Confira também `tag-spec.json`. Se a tag ainda não existir, o proprietário
   executa, no checkout revisado do projeto e com o `gh` já autenticado:

   ```bash
   python3 tools/delivery/create_lab_tag.py --spec CAMINHO/tag-spec.json --output build/github-lab-tag
   ```

   O comando relê o estado remoto e cria **somente a tag anotada descrita nesse
   arquivo**, no SHA congelado e com a mensagem exata. Uma tag já existente e
   idêntica é apenas conferida. Para outra candidata, use outra pasta `--output`,
   preservando os logs anteriores. O
   `GITHUB_TOKEN` da Action não cria a tag: o snapshot pode ter workflows
   diferentes dos da main, e essa criação pode exigir permissão `Workflows: write`.
   A [documentação da API de releases](https://docs.github.com/en/rest/releases/releases#create-a-release)
   explica essa permissão adicional para commits que alteram workflows.
   Não troque o SHA aprovado por `main`/`latest` nem crie um PAT para esse ensaio.
5. Para executar a decisão final, abra **Run workflow** novamente com
   `action=publish`, a mesma candidata e o mesmo hash. O helper revalida a
   identidade do proprietário, a tag preexistente e os registros antes de publicar.
6. Abra o link confirmado mostrado no resumo. A pre-release reúne a candidata,
   o preview fixo, os hashes e o recibo que declara o caráter de laboratório.

Esse fluxo registra evidência no GitHub. Não cria patch Shorebird, upload em loja,
IPA para TestFlight ou distribuição do app. O preview continua sendo web.
Nenhum banco SQLite ou secret entra nos assets ou no artifact de evidência.

O caminho **Delivery - Publicar agora (GitHub LAB)** permanece separado: ele
exige reviews GitHub reais de `samuelcamilo` e `friasvinicius` no PR de versão
integrado em `codex/lab-versions`. Os papéis simulados deste novo comando não
autorizam aquele caminho.

Se houver interrupção após iniciar uma publicação, confira os eventos,
checkpoints e a release/draft existente antes de tentar novamente. Não apague,
sobrescreva ou refaça os assets congelados para esconder uma tentativa incerta.

### Entrega-0100: registro concluído pelo proprietário

Em 07/10/2026, o [plano 37702713050](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37702713050)
foi conferido e a tag `entrega-0100-rc.1` foi criada no SHA aprovado. A primeira
[tentativa de publicação 37702829375](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37702829375)
criou o draft `406248758`, mas falhou no primeiro upload; a consulta daquele
momento confirmou draft com zero assets. Esse resultado permanece no histórico.

Após a correção integrada no [PR8](https://github.com/israelhudson/flutter_code_push_example/pull/8)
e o [CI 37703315084](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37703315084)
com sucesso, Israel executou manualmente o [publish 37704202085](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37704202085).
A mesma Release `406248758` está publicada como pre-release desde
`2026-10-07T23:47:41Z`, com `draft=false` e quatro assets confirmados.

| Campo | Valor |
|---|---|
| Versão | `1.1.0+2` |
| Candidata/tag | `entrega-0100-rc.1` |
| Fonte congelada | `08ce07d615905e33f0572f9264808683cab53349` |
| Ferramentas da retomada | `0817b4fbf84204b24a20858925fa414a1dcac54a` |
| manifest_hash | `28a15ae28f273bd13742dfbec2191d907769db53de6d5b3550a35070823acaeb` |

Abra a [GitHub pre-release confirmada](https://github.com/israelhudson/flutter_code_push_example/releases/tag/entrega-0100-rc.1)
para consultar `candidate.json`, `receipt.json`, `preview.zip` e `checksums.sha256`.
Os arquivos foram baixados e seus tamanhos, hashes e conteúdo conferidos contra
o plano e os artifacts congelados. O recibo declara **2 papéis simulados,
0 reviews reais e `distribution_performed=false`**. Não representa Shorebird,
loja, TestFlight ou uma nova validação mobile.

Não há novo publish pendente para esta RC. Os [logs e lições](LICOES-APRENDIDAS.md)
preservam falha, correção e retomada manual com sucesso. As execuções manuais
seguintes continuam sendo de Israel.

Para uma futura RC, quando houver outra mudança, siga os controles gerais acima:
revise a fonte nova, prepare uma nova candidata e obtenha novos avais. Não
reinicialize a produção, reaproveite aprovações antigas ou mova a tag publicada.
Esta é a referência do processo futuro, não uma instrução para publicar novamente
a entrega já concluída.

## Promover a candidata após revisão de Israel

O fluxo **Delivery - Promover candidata LAB após revisão** promove a pre-release
existente para uma **release estável no GitHub**. Neste laboratório, “produção”
significa esse registro estável; a aplicação não é enviada ao Shorebird ou às
lojas. Israel é o revisor real e o operador final. Os dois papéis simulados da
preparação continuam no histórico e não contam como reviews reais de PR.

O GitHub [não permite que o autor aprove seu próprio PR](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews).
Além disso, os [required reviewers de environments nos planos Free, Pro e Team
ficam disponíveis somente para repositórios públicos](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).
Por isso, este laboratório privado usa uma issue de revisão atribuída a Israel,
com decisão autenticada por comentário. É uma aprovação do proprietário para
promover uma versão; não é uma aprovação de PR nem uma revisão independente.

1. Abra a [issue #10 — Revisar promoção de entrega-0100-rc.1](https://github.com/israelhudson/flutter_code_push_example/issues/10),
   atribuída a Israel, e confira o preview, a versão, a fonte, os hashes e os
   assets da pre-release. Para esta candidata, informe `review_issue=10`.
2. Abra **Actions → Delivery - Promover candidata LAB após revisão → Run workflow**.
   Escolha `main` e `action=plan`. Informe a candidata, o hash completo e o número
   da issue. O plano somente consulta a identidade e os bytes congelados; ele
   não promove a release.
3. Quando concluir sua revisão, publique você mesmo na issue um novo comentário,
   contendo somente esta linha:

   ```text
   APROVAR PRODUCAO entrega-0100-rc.1 28a15ae28f273bd13742dfbec2191d907769db53de6d5b3550a35070823acaeb
   ```

   A aprovação precisa ser da conta real `israelhudson`, para a candidata e o
   hash exatos. O agente não escreve esse aceite por você. Para retirar uma
   aprovação antes da promoção, publique um novo comentário:

   ```text
   REVOGAR PRODUCAO entrega-0100-rc.1 28a15ae28f273bd13742dfbec2191d907769db53de6d5b3550a35070823acaeb
   ```

   O controle consulta comentários atualmente visíveis; não recupera decisões
   apagadas. Conserve o histórico e revogue por um comentário novo. Um comentário
   editado de Israel após a decisão bloqueia o aceite antigo até uma nova decisão.

4. Execute **Run workflow** novamente na `main`, agora com `action=promote` e os
   mesmos três campos. O helper revalida a decisão atual do revisor, a tag, a
   fonte e os quatro assets antes de atualizar a release existente.
5. Confira `result.json`, os eventos e o link do resumo. Só a consulta final com
   `draft=false` e `prerelease=false`, mantendo a identidade congelada, confirma
   a promoção. Uma falha ou timeout exige conferir o checkpoint e a release
   antes de tentar novamente.

| Campo desta candidata | Valor preservado na promoção |
|---|---|
| Versão | `1.1.0+2` |
| Candidata/tag | `entrega-0100-rc.1` |
| Fonte | `08ce07d615905e33f0572f9264808683cab53349` |
| Hash do manifesto | `28a15ae28f273bd13742dfbec2191d907769db53de6d5b3550a35070823acaeb` |
| Release ID | `406248758` |
| Assets | `candidate.json`, `receipt.json`, `preview.zip`, `checksums.sha256` |

O nome passa a ser **[LAB · ESTÁVEL] 1.1.0+2 · entrega-0100-rc.1**. A tag conserva o sufixo
`rc.1` porque já identifica os bytes revisados: promover não cria uma tag nova,
não move a tag existente, não recompila nem substitui assets. O recibo original
continua registrando a preparação com dois papéis simulados e zero reviews
reais de PR; a decisão real de Israel fica nos eventos próprios da promoção.
O estado persistente do publicador fictício também não muda.

**Preparação registrada em 07/10/2026:** a pre-release estava publicada e a
issue #10 foi atribuída a Israel, sem comentário de aprovação ou execução de
promoção naquele momento. A aprovação atual deve ser conferida na issue, e a
promoção precisa de um resultado remoto confirmado. As execuções manuais e o
comentário de aprovação continuam sendo do usuário.

## Falha e recuperação no publicador fictício

No `publish`, `fail_destination=ios-after` grava um recibo fictício e simula
timeout. Depois execute `reconcile`: ele consulta o journal preservado, confirma
o iOS já processado e mantém os demais destinos pendentes. Um novo `publish`
retoma somente os destinos restantes. Não usar outro banco/provedor para fingir
que os efeitos anteriores desapareceram.

`abandon` encerra apenas uma tentativa comprovadamente sem efeitos no provedor
falso síncrono. Qualquer recibo impede esse encerramento. A próxima tentativa
precisa de outra RC e novas aprovações.

## Persistência e avisos

`codex/delivery-state` guarda snapshots atômicos de estado, journal do provedor,
outbox do Slack e ZIPs congelados. Um commit preserva todos juntos; conflitos
não são resolvidos reaplicando o comando silenciosamente. O workflow inteiro
usa uma única fila de concorrência. Os commits avançam sem force push.

Os runners Linux usam `/tmp/flutter-code-push-lab/repository` e
`/tmp/flutter-code-push-lab/state`. Os caminhos fazem parte da identidade imutável;
a importação não reescreve manifests ou hashes de aprovação.

O bot `Flutter Deploy LAB` usa `chat:write` e `groups:read`. Sua credencial fica
no secret `SLACK_BOT_TOKEN` deste repositório, nunca em código ou artifact. Antes
do envio, o bot verifica que `app-deploy-test-isr` é privado e contém somente
Israel e ele próprio. Os avisos trazem um link para o run; aprovações continuam
nos controles GitHub.

A outbox `unknown` é preservada remotamente **antes** de enviar ao Slack. Se a
resposta se perder, não há reenvio automático: é necessário conferir a mensagem
e reconciliar a incerteza. Aviso Slack não altera o estado de aprovação.

Se a confirmação do commit de estado se perder, o artifact do run conserva
`remote-commit-checkpoint.json`. Conferir o mesmo `proposed_head` com
`remote_state.py confirm --checkpoint <arquivo>` antes de qualquer novo efeito.
Não reinicializar uma branch/banco ausente como recuperação de falha.
