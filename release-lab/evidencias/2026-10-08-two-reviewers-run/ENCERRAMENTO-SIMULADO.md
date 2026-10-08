# Encerramento do primeiro ensaio, resultado simulado

Execução concluída com sucesso em 8 de outubro de 2026. Os dois jobs de aprovação passaram e o terceiro gate registrou o comando final pela conta `fahnassau30`.

O recibo e os dois avais apontam à mesma candidata `v1.4.0-rc.1`, ao mesmo código `9e0320fca6fdfba5931d6c80d9181c362ac33c17`, ao mesmo relatório congelado e à mesma execução. O journal encerrou a candidata com `completed`.

Resultado explícito do recibo: `result_simulated=true`, `distribution_performed=false`, `patch_generated=false`. Não foi criada uma tag estável `v1.4.0` nem uma Release GitHub para esta candidata. As Releases antigas do laboratório continuam preservadas; uma delas tem nome estável e tag histórica terminando em RC. O novo ciclo de promoção deve criar uma tag final própria, mantendo a RC original.

Os dados do GitHub comprovam decisões das contas autenticadas. O usuário relatou que operou a conta da Fabrícia durante o teste; este ensaio técnico não comprova revisão humana independente por duas pessoas. O campo legado `human_decision_real` é mantido no recibo histórico, com esse limite documentado. Os registros novos devem distinguir evidência de conta e revisão independente.

## Evidências

- `04-ensaio-concluido.jpg`: execução Success e todos os jobs concluídos.
- `05-recibo-e-tres-decisoes.jpg`: recibo simulado e as três decisões dos Environments.
- `final-receipt/receipt.json` e `final-receipt/events.jsonl`: artefato original baixado do GitHub.
- `final-command.log`: log do terceiro comando, sem códigos ANSI.
- `state-final.json`: snapshot final observado no journal.

A consulta inicial `gh release list --json ...url` foi recusada porque a CLI instalada não oferece esse campo; a consulta REST `GET /releases` confirmou as Releases existentes. Nenhuma alteração de tag ou Release ocorreu nessa consulta.

## Lições

1. Success do workflow demonstra somente o resultado programado. O ensaio anterior só programava um recibo simulado; não chamar esse estado de Release GitHub criada nem produção móvel.
2. Aprovações de revisão e comando final precisam ficar separados na interface e nos registros.
3. Promoção preserva a tag RC e cria a tag estável no mesmo commit avaliado. Não remover o sufixo reescrevendo/deletando a RC.
4. Uma alteração no modo de publicação exige outra candidata e novos avais; não converter a autorização simulada anterior silenciosamente.
5. Captura de tela do ambiente de teste deve focar o GitHub. Conteúdo incidental de outros aplicativos não foi incluído nos arquivos de evidência.
