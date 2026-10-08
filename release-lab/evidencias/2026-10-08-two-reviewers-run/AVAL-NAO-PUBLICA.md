# Esclarecimento: Approve and deploy no gate de revisão

Verificação em 8 de outubro de 2026, após a dúvida sobre os prints fornecidos pelo usuário. Histórico de reviews ainda vazio; execução aguardando os dois revisores.

O botão **Approve and deploy** é a interface nativa do GitHub para autorizar o job vinculado ao Environment selecionado. Nesta janela está selecionado apenas `aprovacao-fahnassau30`; o `1` do botão representa esse único Environment selecionado. A própria janela mostra `aprovacao-israel` aguardando outro reviewer.

Neste workflow, aprovar esse gate libera apenas o registro do aval de Fabrícia. Israel ainda precisa aprovar o próprio gate. O job PUBLICAR depende do sucesso dos dois jobs (`approve_first` e `approve_second`); depois exige uma terceira decisão em `autorizar-publicacao`, que pode ser dada por Israel ou Fabrícia.

O helper final confere as identidades reais, os dois recibos, o sucesso dos jobs e o mesmo relatório congelado. Não houve envio de aprovação pelo agente. Nenhuma falha de bloqueio foi encontrada nesta inspeção. A distribuição móvel continua ausente: somente o resultado final do LAB é simulado. O preview web já estava publicado antes da revisão, como material de validação.

Fontes conferidas:
- [GitHub: Reviewing deployments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments)
- [Workflow congelado, gates e dependências](https://github.com/israelhudson/flutter_code_push_example/blob/9e0320fca6fdfba5931d6c80d9181c362ac33c17/.github/workflows/release-lab-evaluate.yml#L200)
- [Helper congelado, conferência final](https://github.com/israelhudson/flutter_code_push_example/blob/9e0320fca6fdfba5931d6c80d9181c362ac33c17/tools/delivery/release_lab.py#L448)

Lição para Amulets: explicar no guia de revisão que o rótulo nativo libera uma etapa. A publicação exige a cadeia completa de decisões; o nome de um botão isolado não representa essa política.
