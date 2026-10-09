# Comunicação vinculada à mesma candidata

Implementação integrada pela [PR #18](https://github.com/israelhudson/flutter_code_push_example/pull/18), em 09/10/2026 UTC (08/10 em Fortaleza). Provedor de IA e Plane permanecem inativos. A [conexão Slack real](CONFIGURAR-SLACK-LAB.md) tem prova isolada; os [avisos automáticos da candidata](SLACK-AUTOMATICO.md) foram integrados pela PR #19 e comprovados na 1.7.0, com cinco mensagens reais. A 1.8.0 concluiu rejeição/cancelamento operacional, correção, RC2 com dois novos avais, promoção e retorno à main. Ao todo, 13 avisos reais nas duas jornadas. Nenhuma dessas provas comprova distribuição do aplicativo.

A descrição histórica de um PR não confirma o estado atual. A 1.8.0 RC1
confirmou o fallback sem commits adicionais quando base e fonte eram iguais;
não reutilizou contexto de PR antigo. Preservar o relatório aprovado e seus
recibos, e mostrar a observação atual com fonte própria. O novo encerramento
automático após rejeição e a leitura curta de `sent` concorrente foram
integrados no PR #21, com CI aprovado em 404 testes; sem novo negativo remoto.

## O que o código faz

`tools/delivery/changelog_summary.py` separa três operações:

1. **Coletar:** copiar o histórico do intervalo `base..source_sha` e descrições das PRs mescladas desse intervalo. A consulta só lê dados; não executa o código da candidata. Coleta até 12 commits com orçamento total de 20 segundos e até 3 segundos por consulta de PR. Erro/timeout preserva os commits e registra o motivo. O Plane não está conectado a esse coletor.
2. **Selecionar sem espera:** o caminho da entrega consulta uma única vez um artefato opcional já disponível na mesma execução, com orçamento compartilhado de até 3 segundos e sem polling. Artefato ausente, lento, inválido ou de outra candidata leva ao histórico de commits. Os gates não dependem do job coletor.
3. **Congelar:** guardar o texto selecionado, o texto das fontes, a base, a RC, o SHA, os instantes e os hashes no relatório antes dos avais. Alterar uma PR depois não altera esse material. A ilustração e o remetente Slack leem a seleção congelada; não recompõem o conteúdo com fontes mais recentes.

Quando existe contexto válido de PR com as seções **O que muda para o usuário**, **Como validar** e **Limitações** e o total cabe no limite agregado de 1400 caracteres, o texto é copiado para a comunicação e identificado como **descrição das PRs — sem IA**. Não há tradução automática dos títulos técnicos em funcionalidades. Uma descrição vazia, apenas técnica ou sem essas seções usa commits. O [template de PR](../../.github/pull_request_template.md) facilita a escrita desse conteúdo antes do merge.

O histórico técnico completo permanece em `report.changes`. A cópia destinada ao aviso é limitada e remove caracteres de controle; inclui `source_history_sha256`, quantidade original e indicação de truncamento. Isso evita que um subject longo ou mais de mil commits faça uma comunicação opcional bloquear a preparação. O aviso aponta para o registro completo.

## Limite agregado comprovado na RC2

Na 1.8.0 RC2, os contextos dos PRs #20/#21 estavam disponíveis. As seções
literais tinham 744 e 741 caracteres; com a quebra de linha, somaram 1486 e
excederam `SUMMARY_LIMIT=1400`. A seleção usou `commits_fallback`, sem IA.
O digest congelado foi preservado até a publicação. Usar descrições menores
ou mudar o limite antes de uma nova candidata; não reescrever texto aprovado.

## IA: contrato preparado, provedor inativo

A documentação oficial atual permite Copilot CLI em Actions com `GITHUB_TOKEN` e `copilot-requests: write`; em repositório pessoal o consumo é debitado do proprietário. O GitHub recomenda avaliar Agentic Workflows, pois o CLI direto pode acessar amplamente o runner. Fontes: [configuração](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli-in-actions) e [autenticação/cobrança/segurança](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/copilot-cli-in-github-actions).

**Este ajuste não concede `copilot-requests: write`, não instala/executa Copilot, não consulta saldo e não consome créditos.** O módulo apenas valida um possível resultado futuro: RC, SHA, hash do contexto, IDs das fontes, provedor, modelo, versão do prompt e instante de conclusão. Esses controles demonstram vinculação à entrada, não garantem que uma IA escreveu um resumo correto; a revisão humana continua necessária.

Resultado com erro, timeout, sem crédito/acesso, estrutura inválida ou outra RC usa **histórico de commits**, inclusive se houver descrições de PR disponíveis. Resultado que terminou após a seleção fica marcado `late_result`, com hash para investigação, e não substitui o texto. O adaptador de IA, o disparo independente e sua leitura oportunista ainda precisam ser implementados e autorizados após definir orçamento/políticas. Não anunciar isso como uma IA ativa.

O job opcional de contexto PR em paralelo ao build implementa a coleta determinística. Não usar `workflow_run: completed` de “LAB - Preparar candidata” para tentar antecipar a comunicação: esse workflow também aguarda as revisões e a promoção por meio do avaliador reutilizável, portanto seu término chegaria tarde.

## Arquivos e API de integração

O coletor gera `context.json`, `communication.json`, `communication.md` e `collection.json`. O artefato tem nome fixo `release-lab-context`. O leitor rejeita artefato expirado, ambíguo, de outra execução, ZIP/carga maiores que 512 KiB, caminhos que saem do pacote, symlinks e contextos duplicados. Não extrai arquivos do ZIP.

```python
context, observation = read_available_context(run_id)
# O chamador registra observation e valida o contexto contra seu relatório.
communication = frozen_communication(report, context=context)
report['communication'] = communication
# Só depois calcular o digest do relatório que será revisado.
```

`context=None` usa imediatamente os commits; não faz consultas externas. O chamador deve recusar o contexto divergente e continuar com esse fallback. O recibo de publicação inclui o digest do material escolhido. O texto não pode alterar versões, destinos, contas, aprovações, classificação mobile ou permissões.

Para reproduzir a coleta em uma cópia confiável com os commits já presentes:

```bash
python3 tools/delivery/changelog_summary.py \
  --collect-candidate CAMINHO/candidate.json \
  --repo CAMINHO_DO_CHECKOUT_CONFIAVEL \
  --output build/changelog-context
```

Essa operação consulta PRs no GitHub pela identidade do commit. A [API oficial](https://docs.github.com/en/rest/commits/commits#list-pull-requests-associated-with-a-commit) exige leitura de pull requests; PR aberta ou com merge fora do intervalo não fornece uma seção do resumo. O coletor não resolve sozinho backports equivalentes: antes de anunciar uma mudança como novidade, o responsável deve conferir o diff em relação à última versão publicada.

## Próxima validação

Os testes locais cobrem PR editada depois da coleta, seções ausentes, outra RC/SHA/base, hash alterado, IA tardia/sem crédito/falha, orçamento da coleta, artefato ausente/timeout/expirado, ZIP inválido e histórico longo. Resultados de IA nos testes são fixtures, não respostas de um provedor. A integração passou pelo CI da PR #18; o próximo ensaio de candidata ainda deve confirmar coleta paralela, ausência de espera por ela, fallback e preservação do material após os dois avais. O bot e secret existentes já enviaram no [teste isolado](CONFIGURAR-SLACK-LAB.md); seguir o [aceite do fluxo automático](SLACK-AUTOMATICO.md) para comprovar os avisos da candidata.
