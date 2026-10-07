# Ensaiar a esteira com Israel

**Próximo passo: execute o cenário local abaixo.** Ele percorre a aprovação e a
publicação fictícia sem depender de credenciais remotas. Leitura inicial: 5 minutos.

```bash
python3 tools/delivery/lab.py demo --folder build/delivery-lab/meu-primeiro-ensaio
```

O comando mostra **LABORATÓRIO — papéis simulados por Israel** e devolve JSON com
o resultado e os caminhos das evidências. Cada execução cria uma sessão própria
em `session-UUID/`: `repo/`, `state.sqlite`, `provider/`, `targets.json`,
`inputs.json`, `preview-rc1.zip`, `preview-rc2.zip`, `preview.json`, `manifest.json`,
`events.json`, `state.json` e `report.json`.
Os arquivos ficam em `build/`, fora do código versionado.

Os previews desse cenário são HTML **sintético** identificado como laboratório.
Eles testam identidade, expiração e troca de snapshot; o build real de Flutter web
continua sendo o artefato do workflow “preview web”.

## As duas experiências

| Experiência | O que você exercita | Identidade e persistência |
|---|---|---|
| CLI local `lab.py` | Preparar, revisar tecnicamente, aprovar, revogar, enfileirar, autorizar, publicar no provedor falso e reconciliar | Operador `local:israel`; papéis simulados. SQLite e recibos continuam disponíveis entre comandos. |
| Actions “Ensaio local de papéis” | Rodar testes e um cenário sintético isolado, baixar as evidências | Banco novo por execução. Não mantém uma sessão de aprovação entre runs e não atualiza o status protegido do GitHub. |
| Actions “Preparar candidata” e “Publicar agora” | Registro GitHub, preview real e reviews nativas | Exigem políticas, proteções e duas identidades reais. A única distribuição possível pelo publicador é uma GitHub pre-release LAB. |

Uma conta representando Samuel e Vinícius permite testar a regra dos dois papéis;
não comprova duas pessoas diferentes. Israel não aprova seu próprio PR nativamente.
O simulador não envia reviews e não cria status de sucesso no gate real.

## Percorrer uma sessão local

O cenário `demo` é a primeira referência executável. Para operar outra sessão,
use um manifesto e alvos JSON compatíveis com o contrato do motor. Os comandos
globais `--db` e `--provider-dir` aparecem **antes** da ação e permitem separar ensaios.

1. **Registrar a base fictícia.** `targets.json` contém um objeto por destino
   `android`, `ios` e `web`, incluindo a release-base exata e a evidência local.

   ```bash
   python3 tools/delivery/lab.py init --production-sha SHA_COMPLETO_DA_BASE --targets targets.json
   python3 tools/delivery/lab.py technical-review --sha SHA_COMPLETO_CANDIDATO --role ian
   ```

2. **Preparar a foto da entrega.** O comando `manifest` resolve a referência
   uma vez, fixa SHA, árvore, produção esperada, inputs, preview, changelog,
   destinos e pré-análise. Ele grava um arquivo novo, sem sobrescrever outro.
   O JSON de preview deve identificar os bytes e inputs do build; copiar o
   preview de outra foto sem comprovar equivalência será rejeitado.

   ```bash
   python3 tools/delivery/lab.py manifest --repo CAMINHO_DO_REPOSITORIO_LOCAL --ref SHA_COMPLETO_CANDIDATO --targets targets.json --preview preview.json --inputs inputs.json --delivery-id entrega-0042 --rc 1 --output candidate.json
   ```

   `request-id` é a identidade da solicitação: repetir a mesma operação não
   cria outra candidata.

   ```bash
   python3 tools/delivery/lab.py prepare --manifest candidate.json --request-id preparar-0042-rc1
   python3 tools/delivery/lab.py status --candidate entrega-0042-rc.1
   ```

3. **Representar os aprovadores.** Copie o `manifest_hash` mostrado pelo estado.
   Cada aprovação se refere à mesma RC e ao mesmo hash. O papel técnico não conta.

   ```bash
   python3 tools/delivery/lab.py approve --candidate entrega-0042-rc.1 --role samuel --hash HASH_DO_MANIFESTO --request-id samuel-0042-rc1
   python3 tools/delivery/lab.py approve --candidate entrega-0042-rc.1 --role vinicius --hash HASH_DO_MANIFESTO --request-id vinicius-0042-rc1
   ```

   Para voltar a 1/2, use `revoke` com os mesmos campos e um novo `request-id`.
   Repetir Samuel não aumenta a contagem. Os eventos mantêm Israel como operador.

4. **Dar o comando final separado.** 2/2 libera a autorização; não executa
   publicação. O único adaptador desta CLI é o provedor falso em uma pasta local.

   ```bash
   python3 tools/delivery/lab.py publish --candidate entrega-0042-rc.1 --hash HASH_DO_MANIFESTO --command-id publicar-0042-rc1 --repo CAMINHO_DO_REPOSITORIO_LOCAL
   ```

   A publicação verifica novamente o estado e inspeciona o snapshot em
   checkout isolado. O ensaio escreve recibos locais; os números fictícios de patch
   não são números do Shorebird. Preview web não comprova binário mobile.

5. **Conferir estado e auditoria.** Uma falha parcial continua parcial. A retomada
   consulta o provedor falso e preserva os destinos já confirmados. Para injetar
   falha no comando `publish`, use `--fail-destination ios --failure-mode after`:
   simula um timeout depois de gravar o recibo. `before` falha antes do efeito;
   `warning` bloqueia por incompatibilidade simulada. Esses controles operam
   apenas no provedor falso.

   ```bash
   python3 tools/delivery/lab.py reconcile --candidate entrega-0042-rc.1 --repo CAMINHO_DO_REPOSITORIO_LOCAL
   python3 tools/delivery/lab.py events --candidate entrega-0042-rc.1
   python3 tools/delivery/lab.py status
   ```

   Depois de reconciliar, se ainda houver destinos pendentes, execute `publish`
   novamente **sem a injeção de falha**, usando outro `command-id` para a retomada.
   Repetir o ID anterior devolve o resultado daquela tentativa e não repete efeitos.

6. **Continuar a fila.** Use `next` depois de resolver a publicação anterior.
   Uma candidata que ficou obsoleta precisa de preparação e aprovações novas.

   ```bash
   python3 tools/delivery/lab.py next
   ```

O banco local é evidência do ensaio, não um registro inviolável contra seu
administrador. Não copiar suas aprovações para o contexto GitHub real.

## A foto que será publicada

```text
main:     B ─── C ─── D       (features continuam avançando)
          │
release:  B ── conserto ── F′
          ↑                ↑
         RC1              RC2 aprovada → comando final → recibos no SHA de F′
```

Cada commit registra todos os arquivos versionados. Cherry-pick aplica uma
alteração sobre B; não copia automaticamente C e D. Avaliar suas dependências
e testar o conserto na release. Branches podem avançar; tags RC permanecem fixas.

Nova foto ou novos inputs exigem RC, preview, changelog e avais novos. Publicar
usa o SHA completo aprovado em detached HEAD; não usa a ponta atual da `main`.
Receipts e tags de resultados apontam para esse mesmo commit após confirmação.
O ensaio local não altera tags nem branches do projeto real.

## Preparar e publicar usando GitHub nativo

Workflows revisados nesta implementação:

1. **Delivery - preview web:** PRs e integrações podem gerar/reutilizar preview.
   Isso não cria uma candidata automaticamente.
2. **Delivery - Preparar candidata:** somente `workflow_dispatch`; informar
   `source_sha` completo, `preview_artifact` fixo, `delivery_id` e `previous_sha`.
   Na primeira RC, o código precisa estar integrado à main; uma RC de correção
   pode ser descendente da branch release da entrega, sem incorporar C/D da main.
   O preview precisa comprovar equivalência de conteúdo e inputs. Sem preview
   equivalente válido, produzir outro primeiro.
3. **Delivery - Publicar agora (GitHub LAB):** reviews reavaliam o gate;
   selecionar `action=evaluate` apenas consulta/reavalia. `action=publish` é o
   comando final explícito. Exige as duas reviews reais e o PR de registro integrado.

O botão nativo é **Run workflow**. Ele pode estar visível e a operação ser
bloqueada internamente. Aprovação, segundo aval e merge não disparam publicação.
0/2 ou 1/2 fazem o gate retornar erro: bloqueio esperado, não falha que deva ser
contornada. O preparador registra o estado inicial bloqueado sem exigir 2/2.

Antes de ativar: integrar os workflows por revisão, verificar permissões de
Actions e autorizar proteções para `entrega-*`/`release/*`. As proteções existentes
de `lab/delivery/**` não se estendem automaticamente ao namespace neutro.
Nenhuma alteração de configuração remota é executada pelos ensaios locais.
O workflow manual depende da presença na branch padrão do repositório.

O canal privado **`app-deploy-test-isr`** (`C0C8DUJB52L`) é o destino escolhido
para avisos com links do GitHub. O único membro humano confirmado é Israel.
Os avisos não aprovam a RC e não substituem o comando final. A integração de avisos
depende de credencial de automação e permissões configuradas; nenhum segredo é
gravado no código. Usar somente esse canal de ensaio, preservando o canal oficial.

Os workflows incluem avisos opcionais com o segredo `SLACK_BOT_TOKEN`. Sem ele,
registram que o aviso foi pulado. Com ele, o adaptador verifica o canal privado
e seus membros antes de enviar. Falha de aviso gera uma advertência da etapa e
não repete nem autoriza publicação. O outbox no runner dura só aquela execução;
deduplicação confiável entre runs exige persistência própria antes do uso real.
É possível inspecionar um aviso sem enviar, omitindo `--send`:

```bash
python3 tools/delivery/slack_notify.py --event lab --status "Ensaio sintético concluído" --candidate entrega-0042-rc.2 --source-sha SHA_COMPLETO_APROVADO --url https://github.com/israelhudson/flutter_code_push_example/actions --simulation --dry-run
```

## Critérios de aceite e limites

Execute os testes com:

```bash
python3 -m unittest discover -s tests/delivery -v
```

| Cenário | Resultado exigido |
|---|---|
| 0/2 e 1/2 | Bloqueiam publicar. |
| 2/2 simulado | Habilita comando final local; não fornece gate real. |
| Papel repetido ou papel de desenvolvedor/técnico como aprovador | Não aumenta a contagem ou é rejeitado. |
| RC nova, hash divergente ou candidata substituída | Aprovações anteriores não autorizam a nova entrega. |
| Main avançou para C/D enquanto release recebeu apenas o conserto | O checkout publicado não contém C/D. |
| Asset/nativo/engine incompatível ou base desconhecida | Loja necessária ou pendente; patch bloqueado. |
| Falha ou resultado desconhecido em um destino | Entrega parcial; reconciliar sem repetir destinos confirmados. |
| Chamada final repetida | Sem duplicar efeitos do provedor falso. |
| Urgência | Bloqueia a anterior; parte da produção confirmada e exige novos avais. |

As etapas 1 a 6 do [plano](../plano-evolucao-esteira.md) têm um caminho local
para ensaio. A pré-análise local é uma previsão conservadora: não executa Shorebird
e não confirma compatibilidade de um build mobile concreto. Publicação GitHub real,
segregação com identidades distintas e confirmação em dispositivos ainda exigem
validação real autorizada. Não há adaptador de distribuição mobile, loja,
TestFlight ou track beta nesta CLI.

Antes de adaptar ao Amulets, concluir os critérios com identidades reais,
definir credenciais/autorizações por destino e ensaiar a comparação final do
Shorebird. Warnings ou incompatibilidade bloqueiam; não ignorar diffs nem mudar
automaticamente para loja. Ver [referência Shorebird](../../referencias/docs/004-shorebird-patch-e-elegibilidade.md)
e [procedimento de urgência](procedimento-urgencia.md).
