# Disparo automático da POC após dois aceites

> Regra atual: a versão promovida é uma Release final no GitHub, mantendo o escopo de teste e sem promoção mobile. Consulte [Release final e correção do histórico](RELEASE-FINAL.md). As menções a pré-release abaixo descrevem a configuração inicial.

## Configuração em 13/10/2026

O backend exclusivo `xtvueqciogzkyjkkqxcx` recebeu o secret
`POC_GITHUB_DISPATCH_TOKEN`. A credencial fine-grained `flutter-poc-slack-dispatch`
pertence a Israel e tem acesso somente a `israelhudson/flutter_code_push_example`:
Actions leitura/escrita, Contents/Metadata leitura, sem permissões de usuário.
Israel optou explicitamente por **sem expiração** nesta POC; definir rotação antes
de transportar a proposta para outro projeto. Não usar o token amplo do CLI.

O token GitHub dispara o workflow; o bot Slack continua sendo Flutter POC Deploy
(`A0C8J5ZC9JT`, usuário `U0C8XJ5S0Q6`) no canal `C0C8DUJB52L`.
Não foi alterado receptor, token, canal ou backend da Amulets. O token temporário
usado para instalação foi removido; o valor não fica em repositório ou logs.

## Sequência e bloqueios

1. Primeiro aceite: candidata pendente; não há dispatch.
2. Segundo papel aceito: candidata approved. Com escopo `github_test`, configuração
   habilitada e nenhuma pendência de ajuste, a RPC permite reservar o dispatch.
3. Backend reconfere o estado e faz POST somente em `poc-slack-publish.yml`,
   branch `slack-main`, passando o ID congelado da candidata.
4. HTTP 204 registra recebimento do disparo. Isso ainda não significa Release criada.
5. O workflow reconfere os aceites, os controles de publicação e o SHA antes de
   criar a prerelease TESTE. Recibo final e mensagem published confirmam o resultado.

Um dispatch já reservado/enviado/incerto não é repetido automaticamente. Falhas
403, timeout ou resposta diferente de 204 ficam uncertain; conferir Runs e
recibos antes de qualquer repetição. Não apagar o registro para forçar nova chamada.
Sem token, o caminho manual continua disponível e não se registra reserva falsa.
Uma candidata `none` não ganha publicação ao instalar o token.

A configuração não dispara retroativamente entregas já publicadas, nem substitui
os aceites. A versão 1.14.0 foi publicada por dispatch manual e deve continuar
identificada assim nos registros. A **1.14.1 comprovou o disparo automático**:
o segundo aceite foi seguido por reserva/recibo de dispatch, Run bem-sucedido,
Release criada e aviso final. Nenhum Run manual foi iniciado nessa rodada.

[Relatório, evidências e lições para Amulets](VALIDACAO-1.14.1-E-LICOES.md).

## Testes e operação

`deno task check:poc`: 33 testes passaram após incluir seis testes de transporte
(ausência de token, reserva negada, mudança de estado, destino/ID, erro HTTP e
falha de rede), além do bloqueio explícito de dispatch com 1/2 no Postgres local.
São testes locais, não prova de duas pessoas independentes ou entrega mobile.
O modo solo continua usando Israel para os dois papéis.

Logs privados: `/Users/israelhudson/Documents/Codex/2026-10-13/slack-supabase-poc/auto-dispatch/`.
`configuration.json` contém somente identidade/permissões e confirmação de instalação;
`local-tests.log` contém a suíte; prints das permissões não exibem o token.

Para interromper publicação, desligar os controles de publicação da POC. Para
rotacionar, criar credencial restrita equivalente, atualizar apenas esse secret,
validar leitura e dispatch e então revogar a credencial substituída. Não usar
credencial Amulets como fallback. Responsável pelo token da POC: Israel.
