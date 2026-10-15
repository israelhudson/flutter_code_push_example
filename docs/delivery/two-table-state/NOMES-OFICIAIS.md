# Branches e tags do fluxo oficial

Novas versões deixam de usar `poc-` nos nomes de branch e tag. A regra muda os
identificadores das próximas entregas; não muda os responsáveis, os aceites,
os controles ou os gatilhos da esteira.

## Uma versão, uma família de nomes

| Elemento | Novas versões | Histórico preservado |
|---|---|---|
| Automação e integração principal | `main` | Sem renomear a `main` |
| Branch da versão | `release/1.16.0` | `poc-release/1.15.5`, por exemplo |
| Primeira Release Candidate | `v1.16.0-rc.1` | `poc-v1.15.5-rc.1` |
| Segunda Release Candidate | `v1.16.0-rc.2` | Tags antigas continuam no código original |
| Versão final | `v1.16.0` | `poc-v1.15.5` |

`1.16.0` é um exemplo didático; não afirma que a versão foi preparada nem que
está disponível. Conferir versões existentes antes de escolher a próxima.
O identificador da candidata continua sendo `delivery-...`; ele não é uma tag.

Não criar `v1.15.5` para substituir `poc-v1.15.5`. A 1.15.5 já foi entregue
com a família histórica. Não duplicar nem misturar candidatas `poc-vX.Y.Z-rc.N`
com `vX.Y.Z-rc.N` para a mesma versão.

**RC2 de uma versão histórica continua na família histórica.** Se uma candidata
`poc-vX.Y.Z-rc.1` foi recusada, a correção entra por PR na sua
`poc-release/X.Y.Z`. O novo preparo da mesma versão encontra a candidata
anterior congelada e cria `poc-vX.Y.Z-rc.2`, mantendo `poc-release/X.Y.Z`.
A futura tag final dessa sequência também permanece `poc-vX.Y.Z`.
Os aceites da candidata recusada não são reaproveitados.

Versão já publicada, referência órfã e referência de outro fluxo bloqueiam
o preparo nos dois formatos. Não escolher outro prefixo para contornar o bloqueio.
O formato oficial fica para **uma versão nova**, sem registros conflitantes.

## RC1 recusada: a branch não muda de nome

Exemplo de uma **nova** versão:

```text
main
  |
  +--> release/1.16.0 -----+--------------------+-------------->
                          |                    |
                    [v1.16.0-rc.1]       [v1.16.0-rc.2]
                    recusada; mantida     novo codigo aprovado
                          |                    ^
                          +--> fix/login -------+
                               PR de volta para release/1.16.0
```

1. O primeiro preparo corta `release/1.16.0` e cria `v1.16.0-rc.1`.
2. Se ela for recusada, a tag RC1 continua no seu código original.
3. A correção nasce da `release/1.16.0`, por exemplo em `fix/login`.
4. O PR da correção tem **base `release/1.16.0`**. Depois do merge, a mesma
   branch contém o código corrigido; ela não vira `release/1.16.0-rc.2`.
5. O mesmo workflow de preparo é executado novamente pela `main`, com a mesma
   versão `1.16.0`. O script consulta o estado da entrega, encontra a sequência
   anterior e usa o código da `release/1.16.0` para criar `v1.16.0-rc.2`.
6. A RC2 começa com novos aceites. Aprovação da RC1 não é transferida.
7. Depois dos dois aceites e da confirmação da publicação, `v1.16.0` aponta
   para o mesmo commit da RC aprovada. Nenhuma tag candidata é movida.

“Use workflow from main” escolhe a origem das instruções da automação. O código
do aplicativo pode estar na `release/1.16.0`; o script faz essa escolha de forma
explícita. Isso não é um comportamento automático do GitHub por causa da tag.

## O que esta mudança não executa

- Não dispara preparação, Release, preview ou patch.
- Não muda o gatilho para push de tag; o início continua `workflow_dispatch`
  via Run workflow ou `gh workflow run` autorizado.
- Não renomeia nem apaga tags ou branches antigas.
- Não move tags para outro commit, não altera manifestos e não migra aceites.
- Não remove nomes internos antigos de variáveis, secrets, schemas ou arquivos
  necessários à compatibilidade; isso exige migração própria quando pertinente.
- Não altera o bot ou a implantação da Amulets.

O [resultado da 1.15.5](RODADA-PREVIEW-STAGING.md) registra uma rodada real no
formato histórico. Ele continua usando os nomes que existiam no momento dos
aceites, da publicação e do patch, sem reescrever a prova para o formato novo.

## Proteções e compatibilidade operacional

O configurador `tools/delivery/configure_delivery_names.py` gera um plano por
padrão. Com `--apply --output PASTA_PRIVADA`, ele adiciona as regras
`Entrega - tags imutaveis` e `Entrega - correcoes por PR`, sem substituir regras
existentes. As novas tags não podem ser movidas nem apagadas. Correções em
`release/**` exigem PR, Flutter e contratos de Entrega; a revisão humana segue
temporariamente dispensada neste projeto, conforme o ensaio solo autorizado.

A migração `20261015183439_official_delivery_tag_names.sql` aceita os dois
formatos no controle existente e impede misturar famílias na mesma versão.
Ela não cria tabela, não altera linhas nem reescreve eventos. O receptor deve
ser atualizado junto do código da automação, mantendo os controles desligados
durante a atualização. Habilitar a próxima rodada é uma ação separada.

O LAB conserva seu fluxo próprio. Um push de tag no formato compartilhado
`v*-rc.*` só entra nos jobs do LAB quando existe uma candidata LAB registrada,
ativa e preparada para o mesmo código. Uma tag de Entrega ou sem registro não
ganha autorização por ter o mesmo formato.
