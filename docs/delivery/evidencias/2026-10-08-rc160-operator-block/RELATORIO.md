# Preparação de 1.6.0 recusada por operador não autorizado

Execução: [37863070381](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37863070381).
Iniciada em **08/10/2026 às 21:06:47, Fortaleza**, com versão `1.6.0`, título
`Tema escuro manual`, branch `main` e tentativa 1. O commit da main é
`1cb8f3ef72a0d21c11cfa3b2c0d51f7c8c769935`, já contendo o PR #17.

## Causa e resultado observado

- Iniciador e triggering actor: `fahnassau30`.
- A política `delivery/release-lab-policy.json` possui somente `israelhudson`
  em `operators`; Fabrícia está em `approvers` e `publishers`.
- O helper bloqueou: **Iniciador/reexecutor não é operador autorizado; aprovação é outro papel.**
- `validate_context` é executado antes de `prepare`, portanto o bloqueio ocorre
  antes da reserva no diário e da criação das refs.
- Na conferência após o bloqueio: nenhum registro de candidata `1.6.0`, nenhuma
  branch `release/1.6.0`, nenhuma tag `v1.6.0*`, nenhuma Release dessa versão,
  `preparation=null` e nenhuma publicação parcial. A última estável continua `v1.5.0`.

As respostas e logs preservados comprovam o iniciador, a falha e as refs ausentes.
O horário de coleta está em [collection.json](collection.json). O estado do
repositório pode avançar em outra execução depois dessa fotografia.

## Como continuar a mesma entrega

1. Preservar esta execução recusada; não apagar tags, branches ou a versão anterior.
2. Abrir **LAB - Preparar candidata** autenticado como `israelhudson`.
3. Iniciar uma **nova execução** com `main`, versão `1.6.0` e título `Tema escuro manual`.
4. A primeira candidata criada será `v1.6.0-rc.1`; a tentativa recusada não consumiu uma RC.

Não usar **Re-run jobs** desta execução: a política recusa `run_attempt != 1`,
e o reexecutor não substitui o iniciador original para esse controle. Não é
necessário recriar a alteração, o PR #17 ou escolher outra versão por este bloqueio.

## Lição e decisão para Amulets

O controle funcionou como configurado. A orientação anterior deixou de informar
a conta exigida, levando a uma tentativa normal numa conta sem o papel de
preparador. Separar falha operacional de bloqueio esperado e explicitar os
papéis antes do primeiro clique.

**Perguntar ao Samuel:** quem será autorizado a gerar RCs, quem será seu
substituto e quem poderá iniciar recuperação? Aprovar uma candidata e dar o
comando final são permissões distintas de prepará-la. A decisão segue pendente;
nenhuma permissão foi ampliada nesta investigação.

## Evidências

- [Execução original](run.json), [jobs](jobs.json) e [log do job recusado](failed-log.log).
- [Resumo do diário após o bloqueio](state-summary.json) e [resposta original](state-response.json).
- [Consulta das tags 1.6.0](candidate-tags.json) e [da branch de release](release-branch.json).
- [Consulta das Releases 1.6.0](releases-160.json).
- [Print original informado pelo usuário](erro-operador.png).

Esta é uma verificação remota do bloqueio de iniciador antes de criar a candidata.
Não testa os avais de RC2, recuperação parcial ou distribuição mobile. O agente
não disparou outro workflow, não criou candidata e não mudou a política de acesso.
