# Evidências de entrega — POC pessoal

Estes arquivos documentam o laboratório em `israelhudson/flutter_code_push_example`. Ações GitHub, builds e Pages podem ser reais; os papéis de aprovação e os recibos FakePublisher são simulados. Nenhuma evidência aqui aplica mudanças na Amulets ou comprova distribuição mobile de produção.

| Arquivo | Origem e leitura |
|---|---|
| [2026-10-07.jsonl](2026-10-07.jsonl) | Baseline reconstruída: runs, incidentes, builds, Pages e persistência. Usa `historical_backfill` e declara quando a hora original não está disponível. |
| [2026-10-07-release.jsonl](2026-10-07-release.jsonl) | Registro curado pelo coordenador sobre a fase de registro GitHub; preservado separadamente das cópias do emissor abaixo. |
| [Plano 37702713050](2026-10-07-release-plan-37702713050.jsonl) | Cinco eventos originais de `build/operational-evidence/github-release/plan-37702713050/release-events.jsonl`. Plano confirmado; não houve publicação. |
| [Tag entrega-0100-rc.1](2026-10-07-tag-entrega-0100-rc.1.jsonl) | Seis eventos originais de `build/operational-evidence/github-release/tag-entrega-0100-rc.1/release-events.jsonl`. Bootstrap real autenticado pelo owner; objeto e ref exatos confirmados. |
| [Publish falho 37702829375](2026-10-07-release-publish-failed-37702829375.jsonl) | Onze eventos originais de `build/operational-evidence/github-release/publish-failed-37702829375/release-events.jsonl`, incluindo intenção, resposta, upload incerto e falha. Não omite a interrupção. |

As três cópias do emissor foram produzidas posteriormente em `2026-10-07T23:34:46Z`. Preservam os horários UTC originais em `at` e a ordem dos eventos; não fingem observação em tempo real pelo agente que fez a cópia. São logs instrumentados com `event` e somente campos permitidos de identidade, hash, estado e operação. A reconstrução de baseline tem outro schema, descrito em [Lições aprendidas](../LICOES-APRENDIDAS.md#continuidade-do-log).

Os campos permitidos nas cópias são `at`, `event`, `candidate_id`, `source_sha`, `manifest_hash`, `release_identity`, `state_head`, `run_id`, `actor_id`, `login`, `operation`, `release_id`, `asset`, `sha256`, `size`, `status`, `http_status`, `published`, `tag_sha`, `simulated_count`, `reason`, `error_type`, `version` e `fingerprint`. Eventos fora da lista usada pelo emissor e campos adicionais são recusados antes da cópia. Valores foram conferidos sem copiar tokens, bancos, respostas brutas ou participantes/canais privados.

## Estado após a tentativa falha

- Fonte: `08ce07d615905e33f0572f9264808683cab53349`.
- Candidata/tag: `entrega-0100-rc.1`; versão `1.1.0+2`.
- Manifesto: `28a15ae28f273bd13742dfbec2191d907769db53de6d5b3550a35070823acaeb`.
- Identidade Release: `765134435bdb2ecc8eedd008f62c0907f21e4ecc945a24bb03b59e9189403a40`.
- Objeto da tag: `4650c3c985d1e47f6211bdd1cc47a193ed0c31a2` — diferente do SHA do commit, por ser tag anotada.
- Draft remoto: `406248758`; uma leitura posterior confirmou `draft=true`, `assets=[]`, `published_at=null`.
- Checkpoint: upload de `candidate.json`, `status=uncertain`; resultado do run `failed`, `published=false`.

O usuário reservou as próximas execuções manuais para ele. Depois da correção e integração, deverá reexecutar explicitamente o publish da mesma identidade. Até confirmação nova, não registrar sucesso nem recriar/apagar o draft ou mover a tag. Preservar falhas e acrescentar a futura confirmação como novo evento; um draft criado não é uma Release publicada.

## Correção validada localmente, ainda sem retomada remota

O coordenador relatou 14 testes do publicador passando, incluindo [regressão com gh real](../../../tests/delivery/test_github_lab_release.py), versão 2.101.0, contra localhost com autenticação sintética. Sem `Content-Length`, o servidor de teste respondeu 411; com o tamanho dos bytes UTF-8, recebeu o conteúdo exato, sem chunked, e respondeu 201. Metadata, tamanho e digest foram conferidos. Não atribuir esse 411 ao GitHub: o log remoto preservado tem `http_status=null`.

Fontes consultadas: [contrato de upload de assets](https://docs.github.com/en/rest/releases/assets?apiVersion=2026-03-10#upload-a-release-asset) e [implementação HTTP do gh 2.101.0](https://github.com/cli/cli/blob/v2.101.0/pkg/cmd/api/http.go). Esses resultados locais não alteram os logs originais nem o estado do draft. A publicação remota segue aguardando integração e execução manual pelo usuário.
