# Ajuste demonstrativo da 1.15.0

A RC1 foi negada pelo botão do Slack durante um ensaio autorizado. Este PR
documental representa a correção antes de gerar a RC2; não altera o aplicativo
e não afirma que houve um defeito de login ou um patch mobile.

## O que os dois aceites autorizam nesta rodada

- Aceite técnico: confirmar a identidade da candidata e os checks do commit.
- Aceite de negócio: confirmar que a entrega é somente um ensaio dos controles.
- Depois de 2/2, criar automaticamente uma **pré-release de teste no GitHub**.
- Nenhum preview, build web, patch Android/iOS ou distribuição do app.

## Caminho da correção

`poc-release/1.15.0` → `codex/rc2-1.15.0-adjustment` → PR para
`poc-release/1.15.0` → merge e check integrado → novo preparo pela `slack-main`.

A RC1 permanece em seu commit original. A RC2 aponta para o commit deste ajuste,
ganha um novo cartão e começa em 0/2. O texto e o escopo congelados no cartão
devem ser lidos antes de clicar nos dois aceites.
