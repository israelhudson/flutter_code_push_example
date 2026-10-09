# Aprovar uma versão no GitHub

**Para testar sozinho agora, abra o [laboratório local](LABORATORIO.md).**
Ele já permite operar papéis simulados e estados persistentes. Este guia explica
o caminho GitHub com reviews reais; a contagem local não autoriza esse caminho.

As seções de PR de versão e bootstrap abaixo preservam o ensaio de 06/10.
Para o fluxo atual com dois gates e comando final separado, seguir
[FLUXO-DOIS-APROVADORES.md](FLUXO-DOIS-APROVADORES.md); para a comunicação,
seguir [SLACK-AUTOMATICO.md](SLACK-AUTOMATICO.md).

## Laboratório: nenhuma distribuição real

Esta POC adiciona um fluxo de aprovação ao projeto pessoal. Não contém comandos
Shorebird, credenciais de lojas, TestFlight, Play, tracks ou deploy do aplicativo.
O resultado final permitido é uma **GitHub pre-release de laboratório**, identificada
como dry-run, com um recibo que diz `distribution_performed: false`.

## O caminho GitHub nativo

1. **PR de código:** revisão técnica (Ian no plano do Amulets). Actions gera o
   preview Flutter web, que pode ser baixado e executado localmente.
2. **Actions → Preparar candidata:** Israel escolhe o lote integrado e informa
   SHA completo, artifact ID do preview, entrega e SHA-base da última publicação.
   Nenhum merge ou preview cria RC automaticamente.
3. **PR de versão:** changelog, link fixo do preview, tag RC, SHA, base mobile e
   tabela dos responsáveis. Samuel e Vinicius aprovam esse PR, depois do merge do
   código. Ele adiciona somente um JSON à branch `codex/lab-versions`.
4. **Actions → Publicar agora:** depois de 2/2 reviews válidos e do merge do PR
   de versão, Israel seleciona `action=publish`. A automação revalida tudo e cria
   somente a pre-release LAB. Aprovação e merge não executam esse comando.

**A tela e os botões de review/merge são nativos. A política dos dois nomes,
criação da candidata, reuso do preview e publicação são automações deste projeto.**
O botão de integração chama-se **Merge pull request**. O comando final usa
**Run workflow** no Actions. Esse botão pode estar visível enquanto a regra
interna mantém a operação bloqueada. Não há botão customizado em release notes.

Use zoom de 125% ou 150% no navegador. Os registros usam títulos grandes, tabela
curta e textos de estado por extenso, sem depender só de cor. A POC não altera o
tema ou a preferência global do seu navegador.

## O que foi verificado no GitHub em 6 de outubro de 2026

- Repositório privado; usuário proprietário com permissão admin.
- Conta **GitHub Pro**, verificada na tela de Billing. Não inferida do token.
- Actions habilitado; antes da POC não havia workflows, tags, releases,
  Environments ou rulesets. `main` não tinha branch protection.
- Somente `israelhudson` aparecia como colaborador. Não foram convidados outros.
- A opção de Actions criar/aprovar PRs estava desabilitada.
- Pro oferece proteção de branches/rulesets privados. Required reviewers de
  Environment em repositório privado não está disponível neste plano.
- Mesmo onde está disponível, um Environment com vários revisores libera com
  **um** deles, não exige todos.

Fontes verificadas: [Environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
[branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches),
[rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets),
[eventos e GITHUB_TOKEN](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow).

## Identidade que os responsáveis aprovam

- Nova tag neutra: `entrega-0042-rc.N`; a entrega é informada no gatilho manual.
- Primeira RC parte de SHA integrado na main; correções posteriores podem
  descender de `release/entrega-0042`, preservando features posteriores da main fora.
- Tag anotada aponta ao SHA exato e guarda SHA-256 do manifesto completo.
- O criador exige ruleset ativo que impeça alterar/excluir as novas RCs, sem bypass.
  O existente cobre `lab/delivery/**`; não cobre os novos nomes automaticamente.
  O bootstrap revisável prepara a configuração, sem executá-la neste ensaio.
- O manifesto fixa changelog, versão base, preview, expiração e seus hashes.
- Reviews precisam ser dos dois nomes fixos, no **HEAD exato do PR de versão**.
  Uma review antiga, revogada, duplicada, de terceiro ou do próprio autor não vale.
- Base mobile vem do `pubspec.yaml`; não prova que essa base existe no Shorebird.
- Patch iOS e Android ficam `null` / **a gerar**. Nenhum número é reservado.

O changelog usa `previous_sha` explícito da última entrega efetivamente publicada
ou da base inicial escolhida. A última RC não é baseline de compatibilidade.
O criador exige base ancestral do snapshot candidato. O mantenedor precisa
confirmar a evidência real dessa base: informar um SHA não comprova publicação.
Não tenta inventar uma descrição de produto a partir do diff.

O estado da tabela no corpo do PR começa em 0/2; o **status obrigatório e o summary
da execução mais recente** são a fonte atualizada das aprovações. O GitHub também
mostra as reviews nativas. Não se publica nem se autoriza a partir de uma checkbox
editável no corpo do PR.

## Preview privado e expiração

O preview é um **artefato real**, não uma página hospedada. GitHub Actions não
serve HTML de um ZIP como site. Isso preserva o repositório privado e evita fazer
um deploy. O link fixo usa o ID imutável do artefato; não usa “latest”.

1. Baixe o ZIP pelo link do registro (exige acesso ao repositório).
2. Extraia-o e depois extraia `preview.zip`.
3. Dentro da pasta, execute `python3 -m http.server 8080`.
4. Abra http://localhost:8080.

Valida somente web. Não prova funcionamento do engine Shorebird no mobile.
Flutter web pode buscar recursos do engine na rede.

O fingerprint inclui blobs/modos/caminhos dos arquivos rastreados e as entradas
fixadas do build. Exclui somente documentação conhecida e registros de versões.
Inclui lockfile, scripts, CI e `delivery/build-inputs.json`. SHA de commit não entra
nesse hash: squash/merge com mesmo conteúdo e mesmas entradas reutiliza o preview.
A busca fica restrita a execuções bem-sucedidas do workflow esperado, deste repo,
e ao head do PR realmente integrado. O hash do ZIP é conferido novamente.

Retenção: 30 dias. Expirado, removido ou divergente: não reutilizar e não publicar.
Antes de aprovar, a automação pode reconstruir; depois de fixar uma candidata,
**crie outra candidata e obtenha novas aprovações**, sem trocar o ZIP aprovado.
Para isso execute novamente o workflow de preview na referência escolhida e o gatilho manual Preparar candidata;
um novo artifact ID gera nova RC, mesmo se o SHA de código for igual.

## Evidência histórica e experiência atual

O PR #2 executou testes e produziu um build web em 06/10/2026. O PR #3 registrou
uma candidata **demo-before-main-merge**, demonstração antecipada em
`lab/delivery/2026-10-06-rc.1`. Esses registros antigos permanecem como evidência.
Na consulta de 07/10, ambos estavam abertos e a versão continuava em 0/2 real.
Há uma pre-release `0.0.1+1` naquela tag, sem assets/recibo da automação; sua
existência não comprova autorização 2/2 nem execução deste publicador.

A proteção de 2 reviews e o status 0/2 são reais. Os cenários 1/2 e 2/2 no summary
são **fixtures de testes**; não aparecem como reviews reais e não publicam nada.
Sem acesso dos dois responsáveis, não é possível exercitar duas identidades reais.

```bash
python3 -m unittest discover -s tests/delivery -v
python3 tools/delivery/lab.py demo --folder build/delivery-lab/meu-ensaio
python3 tools/delivery/github_delivery.py gate --pr NUMERO_DO_PR_DE_VERSAO
# O gate retorna exit 1 em 0/2: bloqueio esperado.
```

## Ativar o registro GitHub posteriormente

A implementação está em PR; o agente **não faz merge na main**.

1. Revisar e integrar o PR de implementação na `main` por decisão do proprietário.
2. A branch `codex/lab-versions` e os rulesets RC precisam existir/protegidos.
   Revisar também o namespace neutro e a branch release. O bootstrap revisável
   está em `tools/delivery/configure_lab.py --seed SHA`;
   sem proteção neutra a criação bloqueia antes de escrever uma nova candidata.
3. Em Settings → Actions → General, a criação automática de PRs com `GITHUB_TOKEN`
   depende de **Allow GitHub Actions to create and approve pull requests**.
   Essa opção não foi habilitada pela POC. Alternativa: o mantenedor executar o
   criador pela CLI com sua autenticação existente. Não é preciso criar um PAT.
4. Samuel e Vinicius precisariam ter acesso adequado e aprovar de verdade.
   Convites, menções e review requests exigem instrução adicional; não são enviados.
5. Depois dessas condições: PRs revisados integram main → preview/reuso →
   **Preparar candidata manual** → tag + PR de versão → 2/2 reviews reais →
   merge do registro → **Publicar agora manual** → GitHub pre-release LAB.

`pull_request_target` e o botão Run workflow dependem dos workflows
na branch padrão. Antes do merge da implementação, o gate pode ser executado pela
CLI. Não há loop de polling nesse gate. Os avisos Slack opcionais do fluxo
atual são descritos separadamente em [SLACK-AUTOMATICO.md](SLACK-AUTOMATICO.md).

O workflow de candidata roda o gate inicial explicitamente: eventos de `pull_request_target` causados pelo `GITHUB_TOKEN` não iniciam outros
workflows automaticamente. Pela documentação atual, eventos `pull_request` de
abertura/atualização podem criar runs que exigem **Approve workflows to run**. Reviews humanas
subsequentes disparam somente o gate. O dispatch com `action=evaluate` reavalia;
`action=publish` solicita o comando final. A publicação falha sem 2/2 real e PR
integrado. O evento `closed` deixou de executar publicação.

## Persistência e avisos Slack

A escolha é GitHub nativo para aprovar e publicar; Slack recebe apenas avisos e
links no canal privado `app-deploy-test-isr` (`C0C8DUJB52L`). O bot
`Flutter Deploy LAB` e o secret `SLACK_BOT_TOKEN` já têm
[prova de conexão real](CONFIGURAR-SLACK-LAB.md). Os avisos automáticos da
candidata estão preparados na branch, aguardando integração e ensaio próprio;
seu [manual de operação](SLACK-AUTOMATICO.md) explica eventos e recuperação.
Secret ausente ou falha Slack produz aviso opcional e não bloqueia os gates
nem a publicação. O publicador mobile não existe nesta POC.

Os parágrafos de bootstrap acima descrevem a etapa anterior da POC. O fluxo
atual mantém estado/diário em `release-lab/state.json`, na branch
`codex/release-lab-state`. Manifestos e decisões reais pertencem à mesma RC;
`concurrency` ajuda a serializar jobs e não substitui a comparação do estado
antes de cada escrita nem a recuperação de efeitos parciais.

A outbox preparada para avisos é separada: `release-lab/slack-outbox.json`,
na mesma branch de estado. Persiste `unknown` antes do POST e `sent` somente
após confirmação ou prova positiva no histórico; um runner novo recupera
esses checkpoints. Resultado incerto não causa reenvio automático. Isso não
é uma promessa de entrega exatamente uma vez. Uma falha de comunicação não
deve fazer repetir o publicador; 2/2 habilita somente o comando final separado.

## Limites de confiança e recuperação

Esta é uma POC sob controle de administradores do repositório. Um administrador
pode editar regras, scripts ou criar uma Release manualmente; ela não impede isso.
Nenhum segredo de publicação mobile está disponível. Para produção seriam
necessários os controles e a decisão de acesso próprios do projeto de destino.

O publicador revalida reviews, HEAD, tag, manifesto, hash e expiração antes de
criar a release, e revalida de novo antes de torná-la visível. A API do GitHub não
oferece transação atômica entre reviews e criação de release; existe uma janela
residual de concorrência. Erros falham fechados. Uma falha após criar o draft pode
exigir recuperação manual, e o script recusa sobrescrever releases existentes.
Tags nunca são movidas. Uma falha parcial ao criar a candidata pode deixar uma
RC reservada sem PR; a próxima tentativa usa outro número, sem reutilizar a tag.

O branch de estudos e seus documentos anteriores foram consultados e preservados.
As recomendações históricas de publicar primeiro em uma track Shorebird não são
usadas aqui: a decisão atual é **aprovar antes de gerar qualquer patch**.
