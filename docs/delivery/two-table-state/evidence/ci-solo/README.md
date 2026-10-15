# PRs solo e validação compartilhada

A pedido de Israel, a regra da main e release/** exige PR e o check `Flutter analyze e test`, mas zero aprovações humanas. Auto-merge foi habilitado no repositório; precisa ser solicitado em cada PR. Não há autoaprovação fictícia.

O workflow `release-lab-pr.yml` agora aparece como **CI · Verificar PR**. O arquivo e o nome do check são preservados para manter compatibilidade. Ele executa análise e testes, incluindo regressões dos fluxos antigos; não prepara nem publica uma candidata LAB. Os workflows de entrega LAB continuam separados.

Os checks de Issue e Entrega também podem aparecer em PRs para main porque validam contratos que coexistem no repositório. Executar testes não equivale a executar uma entrega.

A alteração não modifica os aceites de release, os controles de publicação, as tags ou a Amulets. Regras de bloqueio de exclusão, force-push e resolução de conversas continuam preservadas. Os JSONs adjacentes registram a regra antes e depois.
