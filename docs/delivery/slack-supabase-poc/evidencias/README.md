# Evidências em 13/10/2026

- `contracts.txt`: 25 testes Deno locais, PostgreSQL PGlite/HTTP fixtures.
- `python-tests.txt`: 6 testes da ponte GitHub POC.
- `python-regression.txt`: 512 testes, incluindo os fluxos anteriores.
- `actionlint.txt`: validação dos quatro workflows novos.
- `deploy.txt`: deploy real das três funções no projeto exclusivo, flags false.
- `cloud-and-rulesets.json`: projeto/health e regras consultadas no GitHub.

O banco remoto contém zero candidatas; RLS em oito tabelas, anon/auth sem SELECT.
Não houve clique humano, envio Slack da nova POC, RC ou Release nesta execução.
O projeto compartilhado Mobile recebeu leitura de metadados e, depois da decisão
de reutilizar o bot, um probe HTTP de tipo inválido: recusa antes de RPC/voto/envio.
Não recebeu deploy, migration ou alteração de secrets. A Request URL ainda não mudou.

Falhas de desenvolvimento corrigidas antes do deploy: lint de mocks assíncronos,
uso incorreto do retorno da fixture Request, transporte POST JSON incorreto
para leitura de membros Slack (corrigido para GET com query) e alias SQL incorreto na seleção de
funções. Não são falhas de publicação real. Os logs finais comprovam a correção.

Supabase advisors: oito INFO de RLS sem policy são intencionais: acesso exclusivo
backend. Dez INFO de FKs sem índices foram corrigidos por migration. Os índices
novos aparecem como não usados enquanto o projeto não recebe candidatas.
[Explicação RLS](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)
e [índices não usados](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index).

As ferramentas get_cost/confirm_cost estavam indisponíveis. Israel confirmou
explicitamente US$0/mês sem upgrade; CLI criou projeto Free e a organização foi
reconsultada no plano Free. Credenciais e resposta privada da criação estão fora
do checkout, com acesso restrito; nenhum secret está nestes registros.

Reutilização: auth.test e membros do canal confirmados com token existente; scopes
chat:write/groups:read suficientes, sem ampliar permissões. Router testado localmente
e com probes HTTP inválidos reais. Isso não comprova cliques humanos de cartão antigo.

Decisão final desta rodada: Israel escolheu manter a Request URL antiga.
O novo receptor foi preparado e publicado, mas a integração interativa continua
com o laboratório/Mobile. As flags da POC permanecem false.

CI inicial: Slack e Issue passaram; o check Flutter parou em um teste legado
de HTTP/CLI (antes de analyze/test Flutter). O runner usa gh 2.102.0, local gh
2.101.0. A fixture não herdava HOME: preserve-se a referência de home do sistema,
sem substituir seu valor. GH_CONFIG_DIR/XDG continuam vazios/isolados e o token
continua sintético. Contrato 411, Content-Length e bytes permanece obrigatório.
O teste específico local passou depois do ajuste; validar novamente no GitHub.
Nenhum workflow antigo ou função de publicação foi alterado por esta correção.
