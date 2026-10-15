# Base validada antes da simplificação do formulário

Registrada antes de alterar os inputs do workflow. A base é a `main` no commit
`7ef832024cafc54f1f1f5eb81c602bdcd6594107`, merge do
[PR #65](https://github.com/israelhudson/flutter_code_push_example/pull/65).
Este registro não dispara uma nova rodada.

## O que já funciona e deve continuar funcionando

| Rodada | Evidência | Resultado e limite |
|---|---|---|
| 1.15.6: nomes oficiais, sem preview/patch | [Preparo 38788973624](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38788973624), [publicação 38789277335](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38789277335) e [Release v1.15.6](https://github.com/israelhudson/flutter_code_push_example/releases/tag/v1.15.6) | Dois aceites reais nas DMs de Israel; um aceite sozinho não publicou. O segundo disparou uma única publicação automática. `build` e `web` pulados; nenhuma execução Shorebird. |
| 1.15.5: preview e Android staging | [Preparo 38784099405](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38784099405), [publicação 38785467883](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38785467883) e [recibo Android](https://github.com/israelhudson/flutter_code_push_example/releases/download/poc-v1.15.5/platform-receipt-android.json) | Preview conferido; patch Android 5, base `1.1.0+2`, enviado pela CLI para staging. Stable preservado. Não comprova execução em dispositivo, iOS ou produção Web. |

Na 1.15.6, `release/1.15.6`, `v1.15.6-rc.1` e `v1.15.6` apontam para
o mesmo commit da base acima. A Release final não é draft nem prerelease.
O cartão do canal e as duas DMs foram atualizados no lugar, com avisos por marco.
As 44 tags e 21 Releases anteriores permaneceram preservadas.

As duas rodadas usam uma pessoa em dois papéis; não comprovam revisão por duas
pessoas independentes. O histórico da 1.15.5 conserva seus nomes `poc-*`.
O [relato da rodada Android](RODADA-PREVIEW-STAGING.md#resultado-real-da-1155)
detalha a prova, sem reescrever os identificadores históricos.

## Contratos a preservar

- Mesmos scripts de preparo, registro, publicação, worker e ponte Android.
- Mesmos contratos internos: `none`/`github_test`, `controls_only`/`full` e
  `none`/`android_staging`; resolver apenas a nova escolha do formulário.
- Mesmas três tabelas: `delivery_control`, `delivery_outbox`, `delivery_reviewers`.
  Nenhuma migração, troca de credencial, alteração de titulares ou de decisões.
- Novas versões usam nomes oficiais; RC2 conserva a branch da versão, mantém a
  tag RC1 e exige novos aceites. Famílias históricas permanecem históricas.
- Preview/retenção e patch staging continuam com seus bloqueios existentes.
  Plano Android é congelado antes dos aceites e executado localmente após a Release.
- Sem ativar publicação, criar tags de teste ou alterar Amulets nesta refatoração.

## Evidências privadas preservadas

Os logs, snapshots e prints originais permanecem nas pastas locais
`2026-10-15/rodada-1.15.6-nomes-oficiais/` e
`2026-10-15/rodada-preview-android-staging/`, sob `Documents/Codex` do operador.
O primeiro conjunto contém `RESULTADO.md`, `verification.json`,
`preservation.json`, logs, artefatos, journal e oito prints; o segundo contém
`RELATORIO-RODADA.md`, recibos Android, logs e prints por marco.
Não copiar snapshots privados, credenciais ou payloads completos para o PR.

## Critério de regressão e retorno

A nova entrada deve produzir as mesmas combinações internas e os mesmos efeitos
dos caminhos validados. Simulação da CLI não acessa serviços nem dispara ações.
Testes locais de rejeição, RC2, repetição e autorização Android continuam sendo
testes locais, não novas provas de execução remota.

Em caso de regressão, reverter por PR apenas a mudança de formulário/CLI.
Não mover tags, apagar Releases, restaurar banco por cima do histórico ou
reescrever aceites. A publicação permanece dependente dos controles existentes.
