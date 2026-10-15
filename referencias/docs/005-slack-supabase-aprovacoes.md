# [005] Interações Slack e estado privado no Supabase

| Campo | Valor |
|---|---|
| **Fonte** | https://docs.slack.dev/authentication/verifying-requests-from-slack/ |
| **Autor/Canal** | Slack e Supabase, documentação oficial |
| **Publicado em** | Documentação contínua; consulta em 13/10/2026 |
| **Duração/Extensão** | Assinatura de requisições, interações, Edge Functions e RLS |
| **Adicionado em** | 2026-10-13 |
| **Tema** | Aceites por papel, autenticação e acesso privado ao estado |
| **Idade** | 🟢 atual na consulta |

## Por que está aqui

Evitar tratar um botão Slack como autorização irrestrita ou expor estado de
publicação por API pública. A assinatura autentica a origem; as regras da candidata
continuam sendo verificadas no banco.

| O que | Validade | Onde conferir |
|---|---|---|
| HMAC sobre corpo bruto e proteção temporal | 🟢 vale hoje | Fonte verificada |
| Scopes e configuração de app/functions | Conferir antes de ativar | Complemento |

## Fonte verificada

A [documentação Slack de assinatura](https://docs.slack.dev/authentication/verifying-requests-from-slack/)
orienta usar Signing Secret, corpo bruto, timestamp e assinatura da requisição;
o exemplo recusa diferença de relógio superior a cinco minutos.
A [documentação de interações](https://docs.slack.dev/interactivity/handling-user-interaction/)
exige confirmação HTTP rápida, em até três segundos. O processamento posterior
não deve bloquear essa confirmação.

## Complemento

[Supabase Edge Functions — autenticação](https://supabase.com/docs/guides/functions/auth)
permite autenticação própria para webhooks externos; desligar verify_jwt no gateway
não dispensa verificar a assinatura no código.
[Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
descreve RLS e os cuidados com credenciais que contornam políticas. Nesta POC, as
tabelas negam acesso anônimo/autenticado e somente o backend usa credencial de servidor.

A [documentação de botões](https://docs.slack.dev/reference/block-kit/block-elements/button-element/)
esclarece que botões com URL também enviam payload e exigem ACK. Esses callbacks
de navegação não registram votos na POC.

## Aplicação neste projeto

Projeto Supabase e app Slack exclusivos da POC; tabelas poc_* e funções poc-*.
O encaminhamento pelo app compartilhado foi estudado, mas a decisão final foi
isolar os apps por projeto. A Request URL da Amulets permanece no seu receptor.
O [mapa de bots](../../docs/delivery/BOTS-POR-PROJETO.md) descreve a migração
dos avisos LAB/Issue e o tratamento dos registros antigos.
HMAC antes de parsing; workspace/canal/app/candidata/papel/prazo conferidos;
transação e chave única para voto; reserva antes de enviar avisos. Essas últimas
escolhas são regras locais, não exigências declaradas pelas fontes oficiais.
O [conversations.members](https://docs.slack.dev/reference/methods/conversations.members/)
usa GET com parâmetros na query; POST JSON de fixture não é evidência de transporte real.
Flags e escopo separados; is_lab não concede publicação. Revisão por papel em modo
solo não comprova duas pessoas independentes.

## Pendências

- [x] Clique real em diagnóstico negativo do app exclusivo; nenhum aceite criado.
- [x] Aceites reais e recibos de avisos da RC 1.14.1; dispatch e publicação GitHub TESTE confirmados.
  [Evidência local do projeto](../../docs/delivery/slack-supabase-poc/VALIDACAO-1.14.1-E-LICOES.md);
  não é afirmação da fonte oficial nem comprovação de leitura das DMs.
- [ ] Recuperação de publicação parcial em um Run GitHub real.
- [ ] Base, plataforma, track e instalação antes de qualquer patch Shorebird.
