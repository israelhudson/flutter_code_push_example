# Planejamento: cadastro de aprovadores e substitutos

Solicitação registrada em 15/10/2026. **Registro original de planejamento,
preservado para acompanhar a decisão.** A proposta 1 foi autorizada e implementada
em código e migração no mesmo dia; aplicação no projeto exclusivo e rodada remota
ainda precisam de evidência própria. Não é uma autorização para alterar a Amulets.

## Evolução: proposta 1 implementada em código

- Uma nova tabela, `delivery_reviewers`, define elegíveis e titulares automáticos.
  O modelo passa de duas para três tabelas de aplicação, sem nova tabela de histórico.
- A nova política usa `reviewer_source: database-v1` e remove as pessoas do JSON.
  O RPC `delivery_resolve_reviewers` lê o titular técnico e o de negócio.
- A migração inclui Israel nos dois papéis para o ensaio `solo: true`. Fora desse
  modo, o preparo exige pessoas distintas. Isso não representa o cadastro da Amulets.
- `delivery_control` recebe chaves estrangeiras e snapshot congelado, também
  incluído no manifesto e nos novos eventos do GitHub. O histórico anterior não é
  reescrito nem preenchido com responsáveis escolhidos retroativamente.
- Administração restrita por SQL/migração auditada em PR, sem painel ou endpoint
  de CRUD. O runtime só lê o cadastro. Ausência de titular bloqueia, sem fallback.
- Troca de padrão não altera uma avaliação aberta. Inativação ou retirada do papel
  impede novas decisões dos designados, sem apagar decisões já confirmadas.
- Publicação permanece bloqueada. A validação operacional deve usar
  `controls_only` e escopo `none`, sem Release, tag, preview ou patch novos.

O [guia de operação e implantação](APROVADORES.md) descreve o código implementado,
a substituição atômica e o que falta validar. As seções abaixo registram o cenário
e as perguntas que motivaram a proposta; menções a “hoje” ou “planejado” descrevem
o momento em que o plano foi escrito, antes dessa implementação.

## Necessidade

Cadastrar pessoas que podem dar aceite técnico ou de negócio, permitindo escolher
um substituto autorizado quando o titular estiver ausente. Ter várias pessoas
cadastradas não significa exigir o aceite de todas.

Exemplo ilustrativo: Samuel é titular técnico, Vinícius é titular de negócio e
outra pessoa está habilitada como substituta de negócio. Se Vinícius estiver
ausente, um administrador marca essa pessoa como titular padrão de negócio antes
do próximo preparo. Não será necessário escolher pessoas em cada Run workflow.

## Como funciona hoje

- `delivery/delivery-policy.json` define um responsável técnico e um de negócio,
  com ID do Slack e login do GitHub. Atualmente Israel ocupa os dois papéis no
  ensaio solo; isso não comprova aprovação por duas pessoas.
- O preparo registra a política usada no manifesto do GitHub e congela os
  destinatários em `delivery_control`, nos campos `technical_user` e
  `business_user`. O receptor compara o autor e a DM com esses responsáveis.
- Não existe tabela de cadastro de usuários/aprovadores. O banco tem somente
  `delivery_control` e `delivery_outbox`.

## Proposta a detalhar antes de implementar

Acrescentar um cadastro mínimo, provisoriamente `delivery_reviewers`, com uma
entrada por pessoa e projeto. O desenho físico e a migração ainda serão revisados.
Isso passa de **duas para três tabelas de aplicação**; é uma alteração explícita
do limite anterior, e não deve ser aplicada como parte deste registro de plano.

| Informação | Finalidade |
|---|---|
| Identificador interno e nome de exibição | Reconhecer a pessoa sem depender do apelido |
| Projeto/repositório | Restringir em qual entrega ela pode atuar |
| ID do workspace e ID do usuário Slack | Identificar quem pode clicar e receber a DM |
| Papéis autorizados | Técnico, negócio ou ambos; titularidade e substituição precisam de regra explícita |
| Ativo/inativo | Suspender novas designações sem apagar histórico |
| ID e login do GitHub, opcionais conforme o papel | Relacionar autoria/revisão no GitHub quando necessário |

O cadastro guarda quem é elegível; cada candidata guarda quem foi efetivamente
designado. Proposta inicial: manter **um aceite técnico e um aceite de negócio**,
por pessoas distintas na Amulets. Vários elegíveis por papel não aumentam essa
quantidade automaticamente. Solo continua sendo exceção identificada de teste.

O diretório no banco seria a fonte dos elegíveis; a configuração versionada no
GitHub continuaria definindo as regras da entrega. A migração deve eliminar a
ambiguidade entre o cadastro e os atuais campos de pessoas do JSON. O manifesto
registra os responsáveis selecionados e a regra usada, preservando a auditoria.

## Detalhamento da proposta 1: titulares automáticos

Refino solicitado em 15/10: o cadastro deve definir os titulares uma vez. Cada
preparo usa automaticamente o titular técnico e o titular de negócio do projeto.
Hoje isso ocorre pelo arquivo JSON; ler esses padrões do banco ainda é proposta,
não comportamento implementado.

| Tabela | Campos novos ou relevantes | Responsabilidade |
|---|---|---|
| `delivery_reviewers` (nova) | `id`, `repository`, `name`, `slack_team_id`, `slack_user_id`, `github_user_id`/`github_login` opcionais, `can_technical`, `can_business`, `default_technical`, `default_business`, `active` | Uma pessoa por projeto, suas identidades, papéis e indicação de titular padrão |
| `delivery_control` (existente) | Adicionar `technical_reviewer_id` e `business_reviewer_id`, referências ao cadastro; preservar `technical_user`, `business_user`, `team_id` e os registros atuais | Guardar quem foi selecionado para aquela candidata e a cópia dos IDs usados nos aceites |
| `delivery_outbox` (existente) | Preservar `candidate_id` e a relação atual com `delivery_control`; nenhum vínculo novo necessário | Histórico, mensagens e disparo pendentes, com recibos |

Exemplo ilustrativo para a Amulets, não cadastro real:

| Pessoa | Pode avaliar técnico? | Pode avaliar negócio? | Titular técnico? | Titular negócio? | Ativo? |
|---|---|---|---|---|---|
| Samuel | Sim | Não | Sim | Não | Sim |
| Vinícius | Não | Sim | Não | Sim | Sim |
| Pessoa substituta | Não | Sim | Não | Não | Sim |

Regras planejadas:

- Exigir identidade Slack única por projeto/workspace, nomes só para exibição;
  referência a pessoa existente não basta: conferir também projeto, workspace,
  papel e situação ativa.
- `default_technical` exige `active` e `can_technical`; `default_business` exige
  `active` e `can_business`.
- Índices únicos parciais por projeto impedem dois titulares do mesmo papel.
  Isso garante **no máximo um**; no preparo, exigir **exatamente um ativo por
  papel**. Se faltar titular, bloquear e informar a configuração ausente.
- Leitura dos titulares e congelamento na candidata devem ocorrer na mesma
  transação, com proteção contra troca concorrente. Na Amulets, exigir pessoas
  distintas; repetir uma pessoa só na exceção explícita de modo solo.
- Substitutos permanecem elegíveis, mas não são escolhidos por acaso, por presença
  no Slack ou pelo primeiro registro retornado. Um administrador muda o titular
  padrão em uma operação atômica e auditada. Os próximos preparos usam a mudança.
- Preservar as referências das candidatas antigas; inativar cadastro em vez de
  apagar/cascatear registros referenciados. Não fazer joins dinâmicos para trocar
  a identidade de decisões históricas.
- A alteração do cadastro não concede permissões no GitHub nem herda aceites.
  Troca em candidata aberta e revogação de acesso seguem os procedimentos
  explícitos descritos abaixo.

Base técnica para a implementação futura: [índices únicos parciais](https://www.postgresql.org/docs/current/indexes-partial.html)
e [chaves estrangeiras](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-FK).

## Slack e GitHub: quais dados precisamos?

Para um aceite recebido no Slack, a identidade mínima é **workspace + ID do
usuário Slack**. Apelido, nome de exibição e e-mail não serão usados como chave
de autorização. O nome serve apenas para facilitar a leitura.
A [documentação Slack](https://docs.slack.dev/reference/objects/user-object/)
orienta combinar `id` e `team_id` e não usar `display_name` como identificador.

Uma pessoa que só avalia a versão pelo Slack não precisa, por esse motivo, de
uma conta GitHub. Para operações no GitHub, cadastrar/verificar a identidade e
as permissões correspondentes. A [API de usuários GitHub](https://docs.github.com/en/rest/users/users#get-a-user)
expõe `id` e `login`; os dois provedores não devem ser associados por semelhança
de apelido. Estar na organização ou ter um login cadastrado não concede, por si
só, acesso de merge ou o papel de aprovador da versão.

O cadastro não guarda tokens, senhas ou dados de perfil desnecessários. Não
precisa criar contas no Supabase Auth para representar pessoas que clicam no
Slack. A administração será restrita; um avaliador não poderá conceder papéis a
si mesmo. A forma de administração ainda precisa ser escolhida.

## Troca de titular e preservação dos aceites

1. Um administrador autorizado cadastra/ativa o substituto e seus papéis.
2. No próximo preparo, a esteira usa automaticamente os titulares padrão ativos
   e registra a escolha no manifesto. Somente eles recebem DMs de decisão da
   candidata; não há seleção manual obrigatória em cada execução.
3. Alterar o cadastro não troca silenciosamente o responsável de uma candidata
   aberta e não transfere aceites anteriores.
4. Proposta inicial para troca durante avaliação: cancelar a candidata anterior
   e preparar uma nova RC com os novos responsáveis, novos avisos e zero aceites.
   Essa operação precisa preservar tags e registrar a substituição no GitHub.
5. Suspensão/revogação de acesso exige regra própria para candidatas já abertas:
   bloquear novas decisões da pessoa desabilitada e exigir reconciliação da
   candidata, sem apagar decisões históricas nem liberar publicação sozinha.

O histórico das alterações de cadastro/designação deve registrar autor e momento
no GitHub, sem adicionar tabela de histórico. Definir a confirmação desse registro
e o comportamento em falha antes de permitir administração operacional.

## Perguntas para alinhar com Samuel

- [ ] Quem administra os aprovadores e autoriza substituições?
- [ ] Basta um aceite de qualquer elegível de cada papel, ou designamos um titular por candidata? A proposta inicial é designar um por papel.
- [ ] Manter um técnico e um de negócio, por pessoas distintas, atende à Amulets?
- [ ] Quem pode alterar o titular padrão para ativar um substituto? A proposta usa titulares automáticos, com troca explícita e sem fallback por presença no Slack.
- [ ] Para substituir alguém numa candidata aberta, concordamos em cancelar e gerar nova RC, sem herdar aceites?
- [ ] Como suspender imediatamente decisões de uma conta revogada e tratar uma publicação já iniciada?
- [ ] Em quais papéis a conta GitHub é obrigatória? Distinguir aceite da versão de revisão/merge do PR.
- [ ] A terceira tabela compensa a flexibilidade administrativa, mantendo o histórico no GitHub?

## Cenários de validação quando esta proposta for implementada

- Titulares recebem as DMs corretas e completam os dois papéis.
- Novo preparo escolhe os titulares padrão sem preenchimento manual dos aprovadores.
- Segundo titular do mesmo papel é recusado; ausência de titular bloqueia o preparo.
- Troca concorrente de titular não mistura responsáveis nem altera uma candidata já criada.
- Substituto selecionado aprova; pessoa cadastrada mas não designada é recusada.
- Mudança de apelido no Slack não troca a identidade; mesmo apelido com outro ID não autoriza.
- Conta apenas de negócio sem GitHub consegue avaliar no Slack.
- Inativação impede novas designações e segue a regra acordada para candidatas abertas.
- Troca de responsável exige nova avaliação; cliques antigos não reabrem a candidata.
- Várias pessoas elegíveis continuam exigindo a quantidade acordada de aceites.
- Alteração de cadastro concorrente com preparo/aceite não muda responsáveis sem registro.
- Usuário comum não consegue cadastrar a si mesmo como aprovador ou ampliar papéis.

Esses cenários foram definidos no planejamento original. A cobertura local da
implementação e os ensaios remotos devem ter registros separados; esta lista não
atesta execução real. Até ativação controlada, worker/receptor e publicação
permanecem desligados conforme o encerramento do ensaio do cron.
