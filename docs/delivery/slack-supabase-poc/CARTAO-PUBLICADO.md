# Cartão após a publicação

> Regra atual: a versão promovida é uma Release final no GitHub, mantendo o escopo de teste e sem promoção mobile. Consulte [Release final e correção do histórico](RELEASE-FINAL.md). As menções a pré-release abaixo descrevem a configuração inicial.

A POC atualiza a mesma mensagem: título “Versão X publicada · GitHub TESTE”,
tag final, “Promovida de: <tag RC>”, os dois aceites e links Abrir Release,
Preview aprovado e Changelog e execução. A conversa e a tag RC são preservadas.

O estado privado `published` é a condição para essa apresentação. Ele só é
gravado pelo protocolo de publicação após validar o recibo e conferir a Release
no GitHub. A tag final segue a convenção validada no banco `poc-v<version>`.
Aceites completos sem publicação não exibem uma Release final.

Depois de publicada, a candidata não volta a aparecer bloqueada quando vencem
as 36 horas. Isso muda somente a apresentação: permissões, votos e dispatch
permanecem iguais. O botão da Release recebe ACK de navegação sem registrar voto.

## Validação em 13/10/2026 (Fortaleza)

- 35 testes Deno passaram, incluindo estados anteriores, publicação após
  expiração e navegação sem efeitos sobre aprovações.
- Funções poc-control e poc-slack-approvals implantadas somente no projeto
  xtvueqciogzkyjkkqxcx; fonte implantada conferida contra a fonte local.
- Recibo da 1.14.1 conferido contra versão, SHA e digest antes de atualizar.
- Mesmo cartão, canal C0C8DUJB52L, timestamp 1791942198.118459,
  autor U0C8XJ5S0Q6. Atualização confirmada pela API e leitura independente.
- [Cartão atualizado](https://amuletsworkspace.slack.com/archives/C0C8DUJB52L/p1791942198118459)
- [Release de teste](https://github.com/israelhudson/flutter_code_push_example/releases/tag/poc-v1.14.1)

Logs locais: Documents/Codex/2026-10-13/slack-supabase-poc/published-card/
(tests.log, deploy.log e update.json). Nenhuma credencial nesses registros.
Não houve nova publicação nem mudança de tags. Amulets não foi alterada.

A implantação da POC antecede a integração do PR; integrar a correção antes
de futuras implantações para evitar restaurar a apresentação antiga.
