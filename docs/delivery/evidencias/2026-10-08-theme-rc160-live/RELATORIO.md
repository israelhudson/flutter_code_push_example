# Observação da RC 1.6.0 — tema escuro manual

Execução iniciada pelo usuário em 08/10/2026 às 21:12:50 (Fortaleza):
[37863610149](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37863610149).
Este relatório registra o ponto de espera pelas duas aprovações; não é um recibo de promoção.

## Resultado observado

- Iniciador e reexecutor: `israelhudson`, tentativa 1, `workflow_dispatch` em `main`.
- RC: `v1.6.0-rc.1`; branch: `release/1.6.0`.
- RC e branch apontam para `1cb8f3ef72a0d21c11cfa3b2c0d51f7c8c769935`, merge do PR #17.
- Congelamento, preflight, analyze/test/build web e publicação/verificação do preview: quatro jobs concluídos com sucesso.
- Gates `aprovacao-israel` e `aprovacao-fahnassau30`: aguardando seus respectivos revisores. Histórico de decisões vazio neste registro.
- Journal: candidata ativa, estado `awaiting_approvals`, sem recibos de aprovação ou publicação.
- Consulta de refs por prefixo `v1.6.0`: somente a RC existe; nenhuma tag estável `v1.6.0` neste ponto.

O comando final depende das duas aprovações. Depois, Israel ou Fabrícia autoriza a promoção em `autorizar-publicacao`. Nesta rodada a promoção cria tag estável e Release no GitHub; não distribui aplicativo Android/iOS nem patch Shorebird.

## Atualização após o registro inicial

O snapshot `03-*` confirmou que Fabrícia (`fahnassau30`) aprovou e seu job de registro terminou com sucesso. Israel continuava aguardando: uma das duas aprovações, com publicação ainda bloqueada. O histórico inicial vazio foi preservado em `02-reviews.json`; o registro posterior está em `03-reviews.json`.

## Último ponto observado: dois avais, comando final pendente

O snapshot `04-*` confirmou os dois jobs de aprovação concluídos com sucesso. Os recibos de Israel e Fabrícia têm a mesma RC, SHA e digest de relatório. O job **AUTORIZAR PUBLICAR — Israel OU Fabrícia, após os dois avais** está aguardando. Nenhum recibo de publicação foi criado; a consulta da Release `v1.6.0` retornou 404 e somente a tag RC está presente. O journal ainda informa `awaiting_approvals`, apesar dos dois recibos, enquanto o comando final não é dado.

Também vale refinar esse nome de estado para distinguir “aguardando revisores” de “aguardando comando final” na interface e nos relatórios. Nenhuma mudança de estado ou permissão foi aplicada pelo agente.

## Preview conferido no navegador

[Preview da candidata](https://israelhudson.github.io/flutter_code_push_example/snapshots/1cb8f3ef72a0d21c11cfa3b2c0d51f7c8c769935/).

O smoke HTTP do workflow passou na primeira tentativa e verificou manifest, identidade, wrapper HTML e arquivos principais do app. O artefato `release-lab-evaluation` foi baixado com sucesso e preservado em `evaluation-artifact/`.

| Verificação manual no preview publicado | Resultado | Evidência |
| --- | --- | --- |
| Abrir aplicação | Tema claro e botão “Ativar tema escuro” | `preview-claro.jpg` |
| Clicar no botão do topo | Tema escuro em azul petróleo e botão “Ativar tema claro” | `preview-escuro.jpg` |
| Recarregar a página | Retorna ao tema claro, sem preferência persistida | `preview-reinicio-claro.jpg` |

As árvores de acessibilidade foram salvas junto dos prints. Essas ações não enviaram nenhuma decisão de aprovação. A conferência web não comprova funcionamento mobile.

## Refinamentos encontrados para o próximo ciclo

1. **Identidade visível da versão:** o wrapper mostra `1.1.0+2`, vindo do `pubspec.yaml`, enquanto a candidata é `1.6.0-rc.1`. Ambas as identidades estão registradas no relatório técnico, mas a tela pode confundir o revisor. Definir a regra de versionamento do app para a Amulets e exibir candidata e versão interna com rótulos explícitos. Se o versionamento interno precisar mudar nesta entrega, corrigir por PR para a branch release e preparar RC2, com novos avais.
2. **Changelog legível:** os cinco títulos vêm de `git log` desde o commit da `v1.5.0`. Incluem dois merges, documentação e “identificar laboratório”, reaplicada na main pelo backport. O diff entre a base publicada e a candidata confirma que a alteração de produto é o tema manual; o texto “Laboratório de atualizações” já estava na base. Melhorar a geração das notas para separar mudança de produto do histórico técnico e evitar anunciar novamente um backport equivalente. Preservar o histórico bruto como evidência.

Nenhum destes refinamentos foi aplicado à RC congelada durante a observação. Os achados são de clareza/versionamento; nenhum dos quatro jobs de preparação falhou.

## Coleta e prevenção de erros

As primeiras consultas `gh run view --job … --log` recusaram a coleta porque a execução completa ainda aguardava revisores, embora os jobs consultados já estivessem concluídos. A alternativa oficial de download de logs por job funcionou para os quatro jobs: `GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs`. O CLI exigiu `--allow-escape-sequences` para salvar os logs com códigos ANSI. As cópias `*-plain.log` removem esses códigos sem executar seu conteúdo. [Documentação oficial](https://docs.github.com/en/rest/actions/workflow-jobs#download-job-logs-for-a-workflow-run).

Uma consulta do coletor usou o caminho de journal incorreto e recebeu 404; foi corrigida para `release-lab/state.json` na branch `codex/release-lab-state`. Os resultados originais e os comandos corrigidos foram preservados. Esses erros pertencem à coleta local, não ao pipeline.

Os JSON `01-*` e `02-*` registram snapshots em momentos diferentes. `02-state-response-corrected.json` e `02-state.json` contêm a consulta correta. `corrected-collection.json` registra os quatro downloads completos. Os logs brutos mantêm o mascaramento do GitHub; a busca por formatos comuns de tokens não encontrou tokens aparentes sem máscara.

## Próxima ação do usuário

Abrir o preview, conferir claro/escuro e recarregar. Ler `evaluation-artifact/release-lab/report.md` antes de aprovar. Cada revisor decide no próprio gate da execução; somente depois das duas decisões aprovadas fica disponível o comando final separado. Não excluir nem mover a tag RC1 para corrigir código.

O verificador de whitespace do Git sinalizou espaços finais presentes nos logs, no diff capturado e nas árvores de acessibilidade. São dados brutos preservados, sem correção de conteúdo; o documento autoral foi verificado separadamente.
