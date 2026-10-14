# Publicação automática 1.14.1 — evidências e lições para Amulets

**Resultado: validado no laboratório pessoal em 13/10/2026.** Dois aceites no
Slack iniciaram a publicação automaticamente, sem Run manual do agente.
A entrega resultou em uma **prerelease GitHub TESTE**, não distribuição mobile.
Israel exerceu os dois papéis: este ensaio não comprova dois revisores independentes.

## Percurso para demonstrar

1. Integrar alteração por PR em `slack-main` e aguardar seu check de integração.
2. Executar **Slack - Preparar candidata**, em `slack-main`, versão sem prefixo/RC,
   título legível e escopo `github_test` (com os três controles de publicação ativos).
3. A preparação congela a fonte, cria a tag RC, testa, compila, publica e verifica
   o preview e registra o cartão pelo bot exclusivo da POC.
4. Revisar preview e changelog; registrar Aceite técnico e Aceite de negócio.
5. Com 2/2 válidos, o backend reserva o dispatch, reconfere a candidata e chama
   **Slack - Publicar teste aprovado**, passando seu ID congelado.
6. O workflow reconfere estado, permissões e SHA. Cria a tag final e a prerelease,
   registra o recibo e atualiza o Slack para published.

Não existe um terceiro botão PUBLICAR nessa alternativa Slack. LAB e Issue
coexistem com seus comandos finais separados. `none` não autoriza publicação;
instalar uma credencial não muda o escopo de uma candidata já congelada.

## Linha do tempo comprovada

Horários de Fortaleza (UTC−03), **13/10/2026**. Os JSONs mantêm os timestamps UTC,
por isso mostram 14/10/2026.

| Hora | Evidência |
|---|---|
| 22:43:18 | Cartão da RC1 enviado pelo bot POC |
| 22:44:26 | Aceite técnico registrado |
| 22:44:27 | Aceite de negócio registrado |
| 22:44:29 | Backend reservou o dispatch |
| 22:44:30 | GitHub confirmou a chamada; Run criado |
| 22:44:51 | Release publicada |
| 22:44:57 | Aviso final confirmado como enviado |

O evento do GitHub é `workflow_dispatch` mesmo quando a chamada vem do backend.
Esse nome isolado não distingue clique manual de automação. A correlação dos
aceites com o journal `dispatch=sent`, `acknowledged=true`, Run e recibo final
comprova o automatismo nesta rodada. HTTP 204 sozinho não comprova publicação.

## Identidade e links da entrega

| Item | Valor |
|---|---|
| Candidata | `poc-d90c43ec138544479b44d6c8fda1a1c0` |
| RC | `poc-v1.14.1-rc.1` |
| Tag final | `poc-v1.14.1` |
| SHA da RC e da tag final | `17c8fcb181e2069320217df73f83746c1975eaba` |
| Escopo / modo | `github_test` / `solo_test` |
| Resultado | `published`; Release não draft, `isPrerelease=true` |
| Bot POC | `U0C8XJ5S0Q6`, app `A0C8J5ZC9JT` |
| Canal POC | `C0C8DUJB52L` — app-deploy-test-isr |

- [Preparação 38496901759](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38496901759)
- [Publicação automática 38497337584](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38497337584)
- [Release poc-v1.14.1](https://github.com/israelhudson/flutter_code_push_example/releases/tag/poc-v1.14.1)
- [Cartão no canal privado](https://amuletsworkspace.slack.com/archives/C0C8DUJB52L/p1791942198118459)
- [PR 41: testes do dispatch e configuração](https://github.com/israelhudson/flutter_code_push_example/pull/41)

## Logs preservados no repositório

O [pacote de evidências](evidencias/1.14.1/README.md) inclui recibo final,
extração dos estados/aceites/dispatch, identidade do Run, Release e tags, trecho
do log de publicação e SHA-256 dos arquivos originais. São extrações documentadas,
não logs integrais nem uma assinatura externa de autenticidade.
Os originais privados ficam em
`/Users/israelhudson/Documents/Codex/2026-10-13/slack-supabase-poc/publication-1.14.1/`.
Esse caminho não existe automaticamente para quem clonar o repositório.

O link Slack exige acesso ao canal. Os logs completos do GitHub e seus artefatos
estão sujeitos à retenção do serviço. A extração versionada preserva a conclusão
sem publicar o histórico inteiro do canal, headers ou credenciais.

## O que foi testado e o que ainda falta

| Cenário | Evidência | Limite |
|---|---|---|
| Dois aceites → dispatch → Release → aviso | Rodada real 1.14.1, links e recibos acima | Israel nos dois papéis; GitHub TESTE |
| Publicação sem token de dispatch | 1.14.0: ficou approved; conclusão por Run manual | Não atribuir automatismo à 1.14.0 |
| Bloqueio com 1/2; segunda ordem de aceites; repetição | Postgres local, suíte `deno task check:poc` | Não declarar repetição real de publicação testada nesta rodada |
| Token ausente, reserva negada e ajuste antes do envio | Testes locais de transporte/estado | Sem injeção de falhas na conta real |
| HTTP não 204 e falha de rede | Testes locais: uncertain, sem retry cego | Falha parcial real ainda requer ensaio dedicado |
| Isolamento do destino | Token restrito à POC; testes verificam URL, branch e ID | Não valida automaticamente uma implantação Amulets |

Suíte local: **33 testes aprovados**, além de formatação, lint e type check.
O PR 41 passou no check obrigatório, build Flutter e preview no GitHub.
As provas de transporte local não equivalem a cliques humanos ou entrega de app.

## Lições e decisões para aplicar na Amulets

| Prioridade | Lição do laboratório | Ação / alinhamento com Samuel |
|---|---|---|
| P0 | Aprovação e disparo são estados distintos; faltava token na 1.14.0 | Verificar credencial, escopo, flags e destino antes de abrir uma rodada; definir alerta quando approved não gerar Run |
| P0 | Bot compartilhado acopla os projetos pela Request URL e pelos tokens | Manter apps, receptores e credenciais separados; não usar token da POC no backend Amulets |
| P0 | Modo solo não garante segregação de pessoas | Definir quem inicia RC, quem dá aceite técnico/negócio e como tratar ausência/substituição; validar Samuel e Vinícius com identidades próprias |
| P0 | Retorno 204 é somente aceitação da chamada | Correlacionar candidata, dispatch, Run, commit, recibo e destino; published só após confirmação real |
| P0 | Um envio incerto pode já ter produzido efeito | Reservar antes de enviar; reconciliar sem apagar journal; testar interrupção, retomada e duplicidade reais |
| P1 | Mesmo SHA não garante build byte a byte reproduzível | Priorizar reutilização de artefato verificado; investigar divergência antes de substituir preview |
| P1 | Corrigir ferramentas depois do corte conflita com a política da RC | Definir recuperação revisada e restrita a hashes exatos; não mover tag nem aplicar exceção genérica |
| P1 | Logs e mensagens técnicas dificultam a revisão de negócio | Separar resumo legível do relatório técnico; alinhar resumo por PR/Plane, IA assíncrona e fallback de commits — ainda proposta |
| P1 | Links Pages e logs têm custo/retenção | Retenção explícita, preservar previews de candidatas/releases e arquivar PRs antigos com inventário |
| P1 | Token sem expiração foi uma escolha do laboratório | Definir dono, validade, rotação e alerta na Amulets; avaliar credencial de serviço apropriada antes da adoção |
| P1 | Backend Free pode afetar disponibilidade | Decidir hospedagem, observabilidade e resposta a indisponibilidade antes de uso operacional |
| P2 | Histórico das RCs explica rejeições e correções | Preservar RC1/RC2 e registrar substituição, motivo e novos avais; não apagar tags após promover |

Na recuperação 1.14.0, a única diferença do app foi o valor numérico gerado
`serviceWorkerVersion` em `flutter_bootstrap.js`. O [PR 39](https://github.com/israelhudson/flutter_code_push_example/pull/39)
permitiu comparar esse campo sem reescrever arquivos, exigindo igualdade de todo
o restante e dos inputs. O [PR 40](https://github.com/israelhudson/flutter_code_push_example/pull/40)
vinculou a recuperação de ferramentas à RC2 e objetos Git exatos. Essa exceção
específica não deve virar uma regra ampla de aceitar builds diferentes.

Antes de adaptar para distribuição mobile, validar separadamente plataforma,
release-base, track, elegibilidade de patch, instalação e disponibilidade para
testadores. Uma Release no GitHub não prova upload, instalação ou produção.
Esta documentação propõe próximos passos; não altera a esteira Amulets.
