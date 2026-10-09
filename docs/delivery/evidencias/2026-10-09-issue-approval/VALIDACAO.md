# Validação da alternativa Issue

Data: 09/10/2026, Fortaleza. Branch: codex/issue-approval-poc.

## Evidência obtida antes do PR

| Verificação | Resultado | Prova |
|---|---|---|
| Suíte da esteira incluindo os primeiros 40 testes Issue | 502 testes, OK, 209,894 s | regression-tests.log |
| Suíte final da alternativa, após adicionar quatro cenários de recuperação/integridade | 44 testes, OK | unit-tests.log |
| Sintaxe dos quatro workflows | Actionlint 1.7.12, exit 0 | Comando abaixo |
| Imports/sintaxe Python e whitespace | py_compile e git diff --check, exit 0 | Execução local |
| Plano de proteções separado | Somente três regras Issue; applied=false | issue-rulesets-plan.json |
| Jornada rejeição/RC2/repetição | Resultado esperado em API GitHub falsa com estado/CAS | scenarios.json |

Os números 502 e 44 se sobrepõem. Não somar como 546 testes distintos. A suíte
completa no CI final deve incluir os quatro casos adicionados depois da primeira
regressão. Resultados reais do CI serão registrados após criar o PR.

```bash
python3 -m unittest discover -s tests/delivery -v
python3 -m unittest discover -s tests/delivery -p 'test_issue*.py' -v
actionlint -shellcheck= -pyflakes= .github/workflows/issue-release-*.yml
```

## Cenários e limites

| Cenário | Resultado esperado e obtido no ensaio local |
|---|---|
| Aprovação 1/1 sem comando final | Estado approved, sem tag final/Release |
| /publicar antes do aval | Bloqueado, mesmo quando o aval chega depois |
| Reprovação da RC1 | Estado rejected, sem publicação |
| Correção e preparação RC2 | Tag RC1 preservada, SHA corrigido, nova ficha em 0/1 |
| /publicar da RC2 sem novo aval | Bloqueado |
| Novo aval e novo /publicar da RC2 | Um efeito de tag e um de Release, mesmo SHA aprovado |
| Publicação repetida | Mesmo recibo, sem segundo efeito |
| Resposta perdida depois da Release | Consulta a Release existente, valida intenção e confirma recibo |
| Falha antes da tag final | Recupera o comando original com os mesmos avais íntegros |
| Aval retirado entre tag e Release | Preserva tag parcial, bloqueia Release e outro corte |
| Comando editado/excluído após intenção | Bloqueia continuação |
| Aval editado/excluído, inclusive edição no mesmo segundo | ID revogado ou conteúdo divergente, 0/1 |
| Aval sem evento de criação registrado | Não autoriza publicação |
| Conta não autorizada/bot/permissão removida | Não conta aval |
| Comentário de PR/Issue desconhecida/tag diferente | Ignorado |
| Ficha alterada/relatório modificado/branch ou tag avançada | Bloqueio |
| Comentários em mais de uma página | Todas as páginas consultadas |
| Changelog truncado/URL de preview de outro host | Não abre a ficha |
| HTTP indisponível na publicação | Nenhuma intenção/efeito de publicação |
| Tag ou Release final divergente | Preservada sem sobrescrita |
| CAS recusado antes dos efeitos | Não cria tags |
| Criação da ficha com resposta perdida | Recupera a mesma Issue sem duplicar |
| PATCH da ficha não confirmado | Repara somente o corpo anterior conhecido e reconfere |
| Slack com resposta incerta | Checkpoint remoto unknown, sem reenvio cego |
| Preview com mesmo SHA e bytes iguais | Preserva wrapper e root do fluxo atual |
| Preview com mesmo SHA e bytes diferentes | Bloqueia sem sobrescrever |

Cada caso é um teste local com provedor falso. Os IDs, SHAs, Issues e Releases em
scenarios.json são fixtures. Não são decisões humanas nem publicações reais.
O plano de rulesets não foi aplicado. Nenhuma variável de ativação foi criada.
Os workflows antigos e o diário codex/release-lab-state não receberam mudanças.

## Lições registradas durante a implementação

1. O primeiro teste de falha parcial encontrou a mensagem genérica de RC ativa
   antes da mensagem de recuperação. A proteção já bloqueava o corte. Reordenei
   os checks para explicar primeiro a intenção parcial. A suíte passou depois.
2. O formato real do smoke existente usa success/snapshot_url. A alternativa
   reutiliza esse contrato, sem inventar outro formato de confirmação HTTP.
3. Uma criação/edição da ficha pode concluir com resposta perdida. Intenções e
   corpo anterior conhecido permitem recuperação sem criar outra Issue ou aval.
4. O Pages já existente usa SHA como identidade. Um fluxo paralelo não pode
   sobrescrever o snapshot nem trocar o root da esteira atual só para exibir outra tag.
5. Action manual-approval no Marketplace usa polling e ocupa runner na espera.
   Esta alternativa aproveita a Issue com eventos curtos e comando final separado.

## O que falta comprovar no GitHub

Após o merge do PR na main e a ativação/proteções, executar uma rodada humana:
preparar RC1, rejeitar, corrigir por PR para test-issue-release/VERSÃO, preparar
RC2, aprovar, publicar e repetir o comando. Conferir Issues, preview, recibos,
tag/Release de TESTE e mensagens reais no Slack. Essa rodada não foi declarada
concluída no ensaio local. issue_comment exige o workflow na branch padrão.

Antes da Amulets, validar 2/2 com duas contas distintas e alinhar quem prepara,
quem publica, destinos móveis e política de recuperação. Repositório privado
não exige Enterprise para este padrão. Rulesets e Pages pessoais privados
dependem do plano compatível, como GitHub Pro. A visibilidade do Pages é separada.
