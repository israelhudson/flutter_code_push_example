# Ensaio pelo bot exclusivo, sem preview

Rodada solicitada por Israel em 14/10/2026. Objetivo: demonstrar candidata,
rejeição, RC2, dois aceites e Release de teste no GitHub com prints e logs.
O ensaio não comprova build web, preview, patches Shorebird ou distribuição.

## Bot e permissões

- Bot **Flutter Deploy POC Slack**, app `A0C8J5ZC9JT`, usuário `U0C8XJ5S0Q6`.
- Canal privado **app-deploy-test-isr**, `C0C8DUJB52L`.
- Receptor e banco exclusivos: projeto `xtvueqciogzkyjkkqxcx`.
- Não mudar o bot, canal ou projeto Supabase da Amulets.
- `slack-main` e `poc-release/**` exigem PR e check **Slack / Verificar contratos**,
  com zero reviews humanos obrigatórios. Isso já era assim; `main` não muda.
- Israel exerce os papéis técnico e de negócio. Dois aceites do mesmo usuário
  são um ensaio solo, não aprovação por duas pessoas independentes.

## Dois campos diferentes

| Campo | Valor | Efeito |
|---|---|---|
| `scope` | `none` | Não autoriza a publicação |
| `scope` | `github_test` | Autoriza somente uma pré-release no GitHub após 2/2 |
| `validation_mode` | `full` (padrão) | Exige build, preview publicado e verificação dos bytes |
| `validation_mode` | `controls_only` | Pula build/preview; testa apenas os controles |

`github_test` sozinho não desliga o preview. O modo fica congelado junto da
candidata; não é possível mudar uma candidata existente para omitir sua prova.
No modo `controls_only`, os links/hashes de preview são nulos, o cartão não
oferece um preview fictício e a Release informa a limitação. Relatórios antigos
sem esse campo continuam exigindo preview. Nenhum desses modos distribui patches.

## Passo a passo da rodada

1. Enviar uma mensagem de conexão com o bot exclusivo; verificar a identidade
   com `auth.test` antes do envio. Guardar recibo e print.
2. Integrar a implementação por PR para `slack-main`. Esperar o check do commit
   integrado; o check do PR não substitui essa verificação.
3. Preparar uma versão ainda não publicada com `scope=github_test` e
   `validation_mode=controls_only`:

   ```sh
   gh workflow run poc-slack-prepare.yml \
     --repo israelhudson/flutter_code_push_example --ref slack-main \
     -f version=1.15.0 -f title='Ensaio de rejeição e RC2 sem preview' \
     -f scope=github_test -f validation_mode=controls_only
   ```

4. Conferir o cartão 0/2. Clicar em **Negar versão**; não há campo de motivo.
   O backend registra quem negou e quando, bloqueia a candidata e mantém a tag
   original. Os aceites antigos, se existirem, permanecem apenas como evidência.
5. Criar uma branch de correção a partir de `poc-release/1.15.0`. Abrir PR de
   volta para essa branch, aguardar os checks, fazer merge e esperar o check
   do commit integrado. Para esta rodada, a correção pode ser documental.
6. Executar novamente o mesmo workflow pela `slack-main`, com a mesma versão.
   A automação vem da integração; o código da RC2 vem de `poc-release/1.15.0`.
   A tag será `poc-v1.15.0-rc.2`, com outro cartão e zero aceites herdados.
7. Aceitar o papel técnico. O cartão deve mostrar 1/2; não deve haver publicação.
8. Aceitar o papel de negócio. O backend deve disparar automaticamente
   **Slack - Publicar teste aprovado** uma única vez.
9. Confirmar `poc-v1.15.0` no mesmo commit da RC2, com GitHub Release marcada
   como pré-release de teste. O cartão passa a destacar a versão publicada.
10. Repetir o workflow de publicação com o mesmo ID: deve devolver o recibo já
    existente, sem outra tag, Release ou decisão de aprovação.

Se a versão do exemplo já estiver publicada, escolher uma nova versão; nunca
mover nem apagar tags para repetir um ensaio. O namespace `poc-*` protege os
fluxos LAB e Issue que coexistem neste repositório.

## Cenários e provas

| Cenário | Resultado esperado |
|---|---|
| Mensagem de conexão | Identidade exclusiva e mensagem visível no canal |
| Preparo sem preview | Jobs build/web pulados; relatório explicita ausência |
| Negação sem motivo | Estado bloqueado, autor/data registrados, tag preservada |
| Aceitar/publicar RC negada | Operação recusada |
| Correção e RC2 | Commit corrigido, RC1 intacta e RC2 sem votos antigos |
| Um aceite | 1/2 e nenhuma publicação |
| Dois aceites | Disparo automático, uma Release de teste |
| Publicação repetida | Mesmo recibo e mesmo ID de Release |
| Relatório sem modo explícito e sem preview | Recusado; o padrão continua completo |
| Usuário/canal incorreto | Operação recusada |

Guardar separadamente evidências locais e reais. Logs de CI, IDs, tags, SHAs e
recibos podem ir ao repositório após revisão de segredos. Os prints completos do
Slack ficam privados, pois a barra lateral pode expor outros canais/pessoas.

## Cuidados operacionais

- Durante esta rodada sem preview, guardar o valor atual de
  `POC_PR_PREVIEW_ENABLED`, suspender o preview de PR e restaurar o valor ao final.
- Usar CLI/API para PR, merge e dispatch. Usar a interface do Slack para os
  cliques reais e as capturas, sem fabricar callbacks de aprovação.
- Aplicar a migração e atualizar somente `poc-control` e `poc-slack-approvals`
  no projeto exclusivo. Preservar o handler de ajuste antigo para cartões antigos.
- O botão **Negar versão** só funciona antes de a publicação começar. Se a
  publicação já foi reclamada, a rejeição é recusada; não promete rollback.
- Gatilho por tag e skill operacional ficam para uma etapa posterior.

## Validação

Resultados reais e links serão anexados após a execução. A implementação e os
testes locais, isoladamente, não comprovam que o cartão chegou nem que publicou.
