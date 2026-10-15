# Preparar uma entrega por cenário

No GitHub Actions, abrir **Entrega · Preparar candidata** (`delivery-prepare.yml`)
e usar **Run workflow**, com **Use workflow from: main**.
O fluxo anterior aparece como **Legado · Preparar candidata** e continua bloqueado.
LAB e Issue mantêm seus próprios fluxos.

## Escolher o resultado desejado

| Cenário do formulário | Identificador da CLI | Preview Web | Release final após aceites | Patch |
|---|---|---|---|---|
| Só avaliar a candidata (padrão) | `candidate_only` | Não | Não | Não |
| Avaliar a candidata com preview | `candidate_preview` | Sim | Não | Não |
| Teste rápido com Release no GitHub | `release_only` | Não | Sim | Não |
| Teste com preview e Release no GitHub | `release_preview` | Sim | Sim | Não |
| Android staging — preview, Release e patch via CLI | `android_staging` | Sim | Sim | CLI posterior, somente staging |

**Todos criam uma candidata real**, com branch, tag e pré-lançamento no GitHub,
cartão no canal e DMs para avaliação. “Só avaliar” impede a promoção final;
não significa simulação. Nenhuma opção distribui automaticamente Android/iOS.

O exemplo **1.15.7** no campo de versão é uma orientação, sem valor preenchido
automaticamente. Escolher uma versão disponível, sem `v` nem `RC`.
O título pode ser **Corrigir renovação do token no login** (até 120 caracteres).

Nos cenários com Release final, a publicação exige os dois aceites, o histórico
confirmado e os controles existentes habilitados. Nos cenários somente de
avaliação, dois aceites não publicam nem encerram automaticamente a candidata:
o operador deve cancelá-la pelo procedimento existente para liberar outra rodada.

O cenário Android congela o plano antes dos aceites, mas não executa Shorebird
no workflow. Após a publicação GitHub, seguir a [ponte CLI Android](ANDROID-STAGING.md).
O cartão distingue Release publicada, patch pendente e patch confirmado.
Upload em staging não comprova execução no dispositivo nem promoção para stable.

## Terminal e IA: primeiro simular

Executar a partir de um checkout com esta interface integrada:

```bash
python3 tools/delivery/run_delivery.py prepare \
  --scenario release_only \
  --version 1.15.7 \
  --title 'Corrigir renovação do token no login' \
  --dry-run
```

`--dry-run` é totalmente local: mostra JSON com repositório, workflow, referência,
inputs e efeitos previstos. Não acessa GitHub/Supabase, não confere disponibilidade
da versão ou permissões remotas, não compila e não cria candidata, preview ou patch.
Não é o dry-run do Shorebird, que pode compilar artefatos.

Quando houver intenção de iniciar a rodada real, usar o mesmo comando trocando
`--dry-run` por **`--execute`**. As opções são mutuamente exclusivas e uma é
obrigatória. A execução usa a GitHub CLI autenticada e solicita o preparo na
`main` de `israelhudson/flutter_code_push_example`. O comando não habilita flags,
não concede aceites e não executa o patch.

Saída `dispatch_submitted: true` confirma somente o envio da solicitação;
conferir a execução no GitHub Actions. Falha ou timeout não gera retentativa
automática: verificar o histórico antes de repetir um disparo sem confirmação.
Títulos são enviados por JSON na entrada padrão do processo, sem shell.

Para chamada direta pela GitHub CLI, o formulário recebe o **rótulo completo**:

```bash
gh workflow run delivery-prepare.yml \
  --repo israelhudson/flutter_code_push_example --ref main --json <<'JSON'
{"scenario":"Teste rápido com Release no GitHub","version":"1.15.7","title":"Corrigir renovação do token no login"}
JSON
```

Esse comando direto **executa**; não é uma simulação. Preferir `run_delivery.py`
para IDs estáveis e simulação explícita. Os exemplos não afirmam que 1.15.7 existe
ou está disponível.

## Mesmo workflow para RC2

Se a RC1 for negada, corrigir por PR na `release/X.Y.Z` e executar novamente
o mesmo workflow, pela `main`, com a **mesma versão**. A esteira consulta o estado,
confere o código da branch da entrega e cria a próxima candidata com novos aceites.
A branch não é renomeada para RC2 e a tag RC1 permanece no commit anterior.
O dry-run local não consulta esse estado nem prevê qual será o número da RC.
Ver [nomes oficiais e histórico compatível](NOMES-OFICIAIS.md).

## Contrato preservado e atualização das chamadas

O catálogo `tools/delivery/delivery_scenarios.py` é compartilhado pelo workflow
e pela CLI. GitHub `choice` usa o próprio rótulo como valor; o catálogo oferece
IDs estáveis para a CLI e testes garantem correspondência com as opções do YAML.

| ID | Escopo interno | Validação | Plano de patch |
|---|---|---|---|
| `candidate_only` | `none` | `controls_only` | `none` |
| `candidate_preview` | `none` | `full` | `none` |
| `release_only` | `github_test` | `controls_only` | `none` |
| `release_preview` | `github_test` | `full` | `none` |
| `android_staging` | `github_test` | `full` | `android_staging` |

O workflow passa a aceitar somente **`scenario`, `version`, `title`**.
Atualizar automações que enviavam `scope`, `validation_mode` e `patch_mode`;
esses inputs foram substituídos, sem aliases ocultos. Rótulos desconhecidos
são recusados antes da criação de referências, sem fallback.
Relatórios congelados e contratos internos mantêm os valores anteriores.
O legado conserva seu arquivo/inputs e seu bloqueio, sem redirecionar chamadas.

Publicação em produção, gatilho por tag, skill para IA e patch automático em CI
ficam fora desta mudança. Não houve migração de banco.
Ver a [base preservada e orientação de retorno](BASE-VALIDADA-FORMULARIO.md).
Os [prints reais e resultados da validação](evidence/scenario-form/README.md)
mostram o formulário na branch do PR, sem disparar uma execução.

Fontes: [inputs de workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs),
[GitHub CLI workflow run](https://cli.github.com/manual/gh_workflow_run).
