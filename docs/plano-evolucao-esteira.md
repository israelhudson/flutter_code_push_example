# Plano de evolução da esteira no laboratório Flutter

**Próximo passo:** seguir o [quadro de ajustes e prioridades](delivery/AJUSTES-E-PRIORIDADES.md) e configurar o Slack pelo [manual](delivery/CONFIGURAR-SLACK-LAB.md). A etapa ilustrativa gera o aviso sem enviar.

Data original: 07/10/2026; atualização: 08/10/2026, Fortaleza. Responsável pelo laboratório: Israel. **Estado atual: promoção da 1.6.0 no GitHub validada; refinamentos, IA/envio Slack, aceites mobile e adaptação à Amulets continuam pendentes.**

O objetivo é experimentar a esteira neste projeto pessoal antes de adaptar qualquer parte ao Amulets. O simulador local usa SQLite e provedor falso; comandos, snapshots e recuperação foram exercitados. O LAB GitHub já validou preparação, duas contas aprovadoras e comando final separado, criando tags/Release reais. Distribuição mobile, revisão independente pelo time e adaptação à Amulets continuam aceites próprios. As seções marcadas como inventário de 07/10 preservam a fotografia original.

```bash
python3 tools/delivery/lab.py demo --folder build/delivery-lab/meu-primeiro-ensaio
```

O demo cria repositório e previews **sintéticos** em uma sessão descartável; o build real de Flutter web é o artefato do workflow de preview. SQLite e recibos locais não fornecem reviews ou status de sucesso no gate GitHub real.

Leitura rápida: seções “Fluxo escolhido” e “Backlog por etapas”, cerca de 5 minutos. Os contratos e cenários servem de consulta durante a implementação.

**Adendo de 08/10/2026:** [changelog semitécnico, IA independente e avisos no Slack](delivery/CHANGELOG-E-AVISOS-SLACK.md). A proposta preserva as tags RC após a promoção, usa descrições de PR/task para explicar o impacto e mantém o histórico de commits como fallback, sem atrasar os gates ou o comando final. A `v1.6.0` desta rodada foi publicada no GitHub; resumo por IA e novos avisos continuam planejados. O inventário de 07/10 abaixo permanece uma fotografia histórica.

**Próxima rodada:** consultar [ajustes e prioridades](delivery/AJUSTES-E-PRIORIDADES.md) e o [manual Slack](delivery/CONFIGURAR-SLACK-LAB.md). A etapa ilustrativa de Slack foi preparada na branch de trabalho; gera payload e resumo, sem envio. Integração na main e remetente real continuam etapas próprias.

## Fluxo escolhido

1. Israel desenvolve; o papel Ian/Yan faz a revisão técnica. PRs revisados integram a `main`, sem criar uma candidata por PR.
2. Israel agrupa mudanças e aciona **Preparar candidata** no Actions. A automação fixa código, preview, changelog e destinos.
3. A pré-análise classifica cada plataforma. Samuel e Vinícius avaliam a mesma candidata e registram duas aprovações de versão.
4. **2/2 libera o comando Publicar agora.** A segunda aprovação e o merge de um registro não publicam automaticamente.
5. Na proposta Amulets, **Samuel OU Vinícius** executa o comando final. No LAB, **Israel OU Fabrícia**. A automação revalida tudo, processa os destinos autorizados e registra o resultado real de cada um.

“RC” significa candidata à publicação. Durante o ensaio, a tela precisa dizer **LABORATÓRIO — papéis simulados por Israel**. “2/2 simulado” nunca significa duas pessoas diferentes.

## Inventário e evidências existentes

Fotografia histórica conferida em 07/10/2026: a POC inicial está na branch `codex/github-release-approval-poc`, commit `14a0d02d41f266f43fe4d868307c34d213cbf051`, e no PR #2. A evolução foi implementada no mesmo worktree da POC; este plano e as referências de estudo foram copiados para acompanhar o código.

| Parte | Implementado | Testado sinteticamente | Validado real e limite |
|---|---|---|---|
| Preview web e comparação de conteúdo | Sim, no PR #2 | Fingerprint, inputs e expiração | Build real no Actions e reuso entre SHAs diferentes registrados em 06/10. ZIP para execução local; não é site hospedado nem teste mobile. |
| Política Samuel mais Vinícius | Sim, nomes fixos e revisão no HEAD do registro | 0/2, 1/2, 2/2, repetição, autor, revogação e HEAD diferente | PR #3 continua sem reviews, bloqueado e com review requerida. 2/2 real ainda não validado. |
| RC e manifesto | Sim, tag anotada, SHA e hashes | Integridade do registro e preview | Candidata antecipada `lab/delivery/2026-10-06-rc.1`; não prova ciclo após merge na main. |
| Publicador GitHub de laboratório | Sim, exige registro integrado e revalida | APIs substituídas por fixtures; bloqueio e revogação durante upload | Há pre-release `0.0.1+1` na tag da RC, sem assets ou recibo anexados. Isso não comprova passagem pelo publicador nem aprovação 2/2. |
| Papéis, RC, comando final, fila e retomada locais | Sim, CLI e SQLite | 0/2, 1/2, 2/2, repetição, substituição, urgência, snapshot e falha parcial | Demo e CLI em processos separados exercitados. Identidade real `local:israel`; nenhum efeito remoto. |
| Pré-análise por plataforma | Sim, offline conservadora | Dart, asset empacotado, nativo/engine, base desconhecida e comparação acumulada | Previsão por arquivos e inputs. Não comparou binários do Shorebird nem validou dispositivo. |
| GitHub manual revisado | Sim, nos arquivos de workflow e criador | Tags neutras, baseline explícito e gate preservado | Depende de integração/ativação e proteção do namespace neutro. Fila/seed local não persistem entre runs GitHub. |
| Avisos Slack com links | Adaptador opcional, sem callbacks de aprovação | Renderização e provedor substituído em testes | Canal privado `app-deploy-test-isr` escolhido; envio depende de credencial configurada. Não comprova envio real. |

**Evidências para abrir:**

- [PR #2 da implementação](https://github.com/israelhudson/flutter_code_push_example/pull/2) e [PR #3 do registro](https://github.com/israelhudson/flutter_code_push_example/pull/3): ambos abertos, sem merge na consulta de 07/10.
- [Execução do preview e testes em 06/10](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37537872345) e [artefato do preview](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37537872345/artifacts/11447291249).
- [Documentação da POC no commit inspecionado](https://github.com/israelhudson/flutter_code_push_example/blob/14a0d02d41f266f43fe4d868307c34d213cbf051/docs/delivery/README.md) e [16 testes existentes](https://github.com/israelhudson/flutter_code_push_example/blob/14a0d02d41f266f43fe4d868307c34d213cbf051/tests/delivery/test_policy.py). São evidências da implementação anterior, não testes novos deste plano.
- [Release atualmente existente](https://github.com/israelhudson/flutter_code_push_example/releases/tag/lab/delivery/2026-10-06-rc.1). O registro local `build/delivery-evidence/verification.json`, datado de 06/10, dizia zero releases; esse campo já está desatualizado.

Na consulta de 07/10, a proteção de `codex/lab-versions` exigia duas reviews, descartava reviews antigas, aplicava-se a administradores e exigia o status `delivery / Samuel + Vinicius`. O ruleset `24612293` bloqueava atualização e exclusão de `lab/delivery/**`, sem bypass; a opção de Actions criar/aprovar PRs estava desabilitada. A implementação local não alterou essas configurações.

## Diferenças resolvidas no código e limites de ativação

| POC anterior | Comportamento desejado |
|---|---|
| Preview após merge pode disparar criação de candidata | Somente o gatilho manual Preparar candidata inicia um lote. |
| Merge do registro aprovado pode publicar | Aprovação libera; Publicar agora autoriza a execução separadamente. |
| Duas identidades GitHub reais são necessárias para passar pelo gate | Simulador local separado permite ensaiar papéis, mantendo o gate real intacto. |
| Changelog começa na candidata ancestral anterior | Changelog principal parte da última entrega efetivamente publicada; comparação com a RC anterior é complementar. |
| Uma base declarada no pubspec e patches nulos | Alvos exatos por plataforma, pré-análise e resultado independente por destino. |

Os arquivos revisados removem a candidata automática por merge/preview e a publicação pelo evento de merge. Antes de integrar/ativar, revisar a configuração remota correspondente. A existência de uma Release manual não representa autorização da esteira. Para uso real, revisar quem pode criar releases e usar credenciais de distribuição.

## Papéis e limite de uma única conta

| Papel no processo | Quem opera no laboratório | O que pode registrar |
|---|---|---|
| Desenvolvedor Israel | Israel | Mudanças, preparação e comando final de publicação do ensaio. |
| Revisor técnico Ian/Yan | Israel representando Ian/Yan | Revisão técnica simulada, separada da aprovação da versão. |
| Aprovador Samuel | Israel representando Samuel | Uma aprovação simulada da RC. |
| Aprovador Vinícius | Israel representando Vinícius | Uma aprovação simulada da mesma RC. |

O GitHub não permite que o autor aprove o próprio PR. Uma conta representando Samuel e Vinícius **não comprova segregação entre duas identidades**. No laboratório, a revisão técnica também será uma simulação explicitamente registrada; não será enviada como review nativa em nome de Ian/Yan. [Regra oficial do GitHub](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews).

O primeiro incremento está implementado: `tools/delivery/lab.py` opera SQLite, eventos acrescentados sem reescrever o histórico e um publicador falso. Não precisa de credencial remota. A base local comprova o comportamento do ensaio, não é um registro inviolável contra seu administrador.

Cada evento registra identidade real, papel representado, ambiente, RC, SHA, hash do manifesto, ação, instante e resultado. Exemplo abreviado do retorno de `events`:

```json
{
  "mode": "laboratory",
  "simulation": true,
  "actor": "local:israel",
  "identity_source": "local_session",
  "simulated_role": "samuel",
  "candidate": "entrega-0042-rc.1",
  "sha": "SHA_FIXADO_DA_CANDIDATA",
  "hash": "HASH_DO_MANIFESTO",
  "action": "approve",
  "id": "IDENTIFICADOR_UNICO",
  "at": "INSTANTE_UTC",
  "result": {"count": 1, "simulation": true}
}
```

O caminho GitHub consulta IDs das reviews reais. Slack recebe somente avisos e links, sem aprovar ou publicar. Nunca aceitar nome digitado como autenticação. O papel simulado é um campo separado, não uma identidade forjada.

O modo real deverá recusar eventos com `simulation: true`, autor como aprovador, identidade repetida e pessoas fora da política autorizada. Dois cliques de Samuel valem uma aprovação. Os papéis de revisão técnica e aprovação de versão têm registros e contadores separados.

O simulador não publica status de sucesso no contexto protegido, não altera a lista real de aprovadores e não usa credenciais de produção. O caminho de produção não pode aceitar `laboratory=true` de um manifesto ou botão como forma de dispensar sua política. Validar identidades distintas será uma etapa posterior, com acesso autorizado.

## Contrato da candidata

**Exemplo de nome:** `entrega-0042-rc.1`. O número 0042 é ilustrativo, não foi reservado. A tag é neutra: não presume plataforma, número de patch nem versão de loja.

1. Resolver o SHA integrado escolhido e criar a branch de release proposta `release/entrega-0042` a partir dele. Resolver conflitos antes de disponibilizar a RC para avaliação.
2. Fixar preview e changelog. Na primeira entrega do laboratório, registrar explicitamente a base inicial escolhida; depois usar a última entrega publicada. A última RC não é a base de compatibilidade do patch.
3. Registrar manifesto imutável e tag anotada no SHA fixado da candidata. Alterações na branch após o corte exigem uma nova RC, novo manifesto e aprovações zeradas. A aprovação desse snapshot vem depois da preparação.
4. Fixar por destino: app/ambiente, plataforma, flavor, entrypoint, versão e build da release-base, evidência dessa base, inputs e condição prevista de publicação. Não usar `latest`.
5. Guardar os resultados posteriores em recibos separados. Números de patch começam `null`/“a gerar”; preencher apenas a partir da resposta confirmada do provedor.

O manifesto também vincula autor, papéis necessários, versão da política, SHA-base de produção, hashes do preview e changelog, validade e destinos requeridos. O conjunto de destinos não pode ser reduzido silenciosamente depois da aprovação.

**Proteção a planejar:** o ruleset existente cobre somente `lab/delivery/**`. Ele não protege automaticamente `entrega-*`. Antes de criar tags neutras remotas, será necessário revisar e autorizar regras para os novos nomes e para os registros. Nesta etapa não criar tags nem alterar rulesets. Preservar a RC e a Release existentes como evidência histórica.

### Snapshot é a foto completa do código

**Snapshot é o estado completo dos arquivos versionados em um commit.** É a foto do código da entrega: inclui também os arquivos que permaneceram iguais. O diff mostra a alteração entre duas fotos; não representa sozinho o conteúdo que será compilado. O SHA identifica o commit que registra essa foto. [Fundamento no livro oficial do Git](https://git-scm.com/book/en/v2/Getting-Started-What-is-Git%3F).

Exemplo ilustrativo, sem operações reais no repositório:

```text
main:     B ──────> C ──────> D
          │         features novas continuam na main
          │
release:  B ── aplicar conserto ──> F′
          ↑                        ↑
         RC1                      RC2
```

1. **B é a foto original.** A branch de release nasce em B, e `entrega-0042-rc.1` aponta para B.
2. **A main avança para C e D.** Essas features não entram automaticamente na branch de release.
3. **O conserto na release cria F′.** Sua foto é B com o conserto aplicado, preservando o restante de B. A branch avança para F′; RC1 continua em B e uma nova tag RC2 fixa F′.
4. **F′ passa por uma nova avaliação.** Preparar o preview correspondente e atualizar o changelog para essa foto; começar em 0/2 e obter novos avais. Não reutilizar automaticamente o preview ou as aprovações de B.
5. **Publicar usa F′ aprovado.** A tag final de entrega proposta `entrega-0042` e as tags de resultado, criadas após confirmação do sucesso correspondente, apontam para o SHA de F′. B ficou como RC1 histórica; a ponta atual da main não determina a entrega.

Os nomes B, C, D e F′ representam commits e seus snapshots; F′ não é um nome real de SHA. A branch pode continuar avançando para preparar outra candidata. As tags de RC permanecem fixas por política e proteção: não mover RC1 para F′ nem mover RC2 para uma correção posterior.

Se o conserto existir num commit F da main, um **cherry-pick aplica a alteração introduzida por F sobre B**, criando um novo commit F′ na release. Ele não copia automaticamente o snapshot completo da main. Avaliar se a alteração depende de C/D, resolver conflitos e testar na release. Se depender dessas features, adaptar o conserto ou incluir dependências deliberadamente numa nova candidata, com escopo, preview e aprovações próprios. [Comportamento documentado do cherry-pick](https://git-scm.com/docs/git-cherry-pick).

### Foto do código e artefato compilado

| Item | O que fica fixado ou demonstrado |
|---|---|
| Snapshot B ou F′ | Arquivos versionados do commit. Dependências externas, credenciais e inputs de build precisam de seus próprios registros. |
| Preview web | Artefato compilado para web a partir do código e inputs identificados. Não comprova um binário nativo ou patch mobile já testado. |
| Patch Android ou iOS | Gerado somente depois dos avais e do comando final, usando o snapshot aprovado e a release-base exata. Sua compatibilidade e seu resultado ainda precisam ser confirmados. |

Portanto, o MVP aprova **código, preview web e plano de destinos**. Os artefatos mobile serão gerados posteriormente. Aprovação do snapshot não permite afirmar que os patches nativos já existiam ou já tinham sido testados antes do comando final. A pré-análise e a barreira final do Shorebird continuam obrigatórias.

### Publicação pelo SHA fixado

Contrato implementado no ensaio: vincular a RC ao `source_sha` e à árvore do manifesto, mantendo esse commit durante a operação. Registros de tags do simulador ficam no SQLite. O caminho GitHub confere a tag anotada e o commit apontado, não confunde o SHA do objeto da tag com o SHA do código.

O ensaio inspeciona checkout isolado, em **detached HEAD**, usando o SHA completo conferido; o futuro adaptador mobile também deve compilar nele. Conferir HEAD, árvore versionada, inputs fixados e ausência de alterações locais ou arquivos inesperados capazes de afetar o build. Detached HEAD significa que o checkout está diretamente num commit, sem acompanhar a ponta de uma branch. [Documentação do Git](https://git-scm.com/docs/git-checkout#_detached_head).

Não resolver novamente `main`, `release/entrega-0042` ou “latest” para escolher o código entre aprovação e publicação. O avanço dessas branches não autoriza trocar F′. Se a produção mudou nesse intervalo, aplicar a regra de candidata obsoleta; se o conteúdo/inputs precisar mudar, preparar nova RC. Registrar SHA, inputs e hashes dos artefatos nos recibos por destino.

### Preview reutilizável

Reutilizar o preview de PR somente com equivalência verificada entre o código resultante integrado e o código compilado, mais as mesmas entradas de build. Incluir lockfiles, toolchain, renderer, comandos, defines, flavor/entrypoint, scripts e configuração relevante. Se algo puder influenciar o build, deve participar da identidade.

Confirmar origem confiável da execução, ID fixo, hash dos bytes, disponibilidade e validade do artefato. SHA de commit diferente não impede reuso quando a equivalência é provada. Igualdade apenas do diff visível ou do nome do ZIP é insuficiente.

Sem prova completa, reconstruir antes de congelar a RC. Trocar/reconstruir um preview já aprovado cria outra RC e exige novas aprovações. Preview web continua sendo validação web; não prova comportamento de Android, iOS ou Shorebird.

### Pré-análise por plataforma

| Resultado | Significado no plano | Próxima ação permitida |
|---|---|---|
| Patch previsto | Não foi encontrada incompatibilidade conhecida contra a release-base exata | Apresentar a previsão aos aprovadores; aguardar Publicar agora para geração. |
| Loja necessária | Mudanças empacotadas, nativas ou de engine incompatíveis com aquela base | Preparar outro plano de entrega para loja; não gerar patch para esse destino. |
| Pendente | Base ausente, versão não confirmada ou evidência insuficiente | Completar a evidência; manter publicação bloqueada. |

A comparação inclui o conteúdo acumulado desde a **release-base de cada plataforma**, não apenas a última RC ou o último patch. Uma RC só com Dart ainda pode conter mudança nativa acumulada desde essa base. Mudança em recurso remoto não equivale automaticamente a asset empacotado; classificar pelo artefato afetado. Ver [referência 004](../referencias/docs/004-shorebird-patch-e-elegibilidade.md).

“Patch previsto” não é garantia. Depois do comando final autorizado, a comparação do Shorebird com seus artefatos armazenados é uma barreira obrigatória. Incompatibilidade ou warning não resolvido bloqueia. A política deste laboratório proíbe ignorar warnings e usar `--allow-native-diffs`/`--allow-asset-diffs`; também proíbe fallback automático para loja. Mudança de rota ou de base exige nova RC e novas aprovações.

No MVP, destinos obrigatórios em “pendente” ou “loja necessária” impedem iniciar publicação mobile. Ensaiar esses estados com adaptadores falsos. Não haverá TestFlight nem track beta como requisito do MVP. A validação real futura terá escopo isolado e autorização própria.

## Aprovar e publicar são duas ações

Estado previsto: `preparando → em_aprovacao → autorizada → publicando → concluida`.

Estados de exceção: `bloqueada`, `substituida`, `expirada` e `parcial`. O encerramento local comprovadamente sem efeitos usa `encerrada_sem_efeito`. A palavra “autorizada” significa apenas que o comando final pode ser solicitado.

| Situação | Resultado |
|---|---|
| 0/2 ou 1/2 | Publicar agora bloqueado. |
| 2/2 na mesma RC válida | Comando final liberado; nenhum efeito de publicação. |
| Publicar agora por operador autorizado | Revalidar estado, política, RC, hashes, aprovações, destinos e base de produção; só então executar. |
| Nova RC ou mudança de SHA, inputs, base, preview, changelog ou destinos | Preservar histórico, invalidar autorização anterior e começar em 0/2. |
| Revogação ou RC obsoleta | Bloquear novos efeitos; se já houver efeito externo, registrar o que ocorreu e entrar em recuperação. |

A revalidação e a aquisição do direito de publicar ocorrem na transação do estado local. Usar versão do estado e chave de idempotência por candidata, destino e operação. Comando repetido retorna a tentativa existente; a retomada explícita usa um novo ID e preserva os destinos confirmados.

Uma falha de rede não significa que o provedor falhou. Antes de repetir, consultar o resultado pelo identificador registrado. O processo não pode prometer atomicidade entre GitHub, Slack e Shorebird: registrar o início e reconciliar os efeitos confirmados. Não executar código vindo do registro de versão com credenciais privilegiadas.

### Interface escolhida

| Parte | Experiência escolhida | Limite e trabalho necessário |
|---|---|---|
| GitHub nativo | PR/registro para leitura e reviews reais; workflows separados Preparar candidata e Publicar agora | O botão nativo é Run workflow. Ele pode estar visível mesmo quando a regra interna bloqueia. Não presumir botão customizado que se habilita em release notes. |
| Slack somente avisos | Mensagem com estado e links do GitHub em `app-deploy-test-isr` | Adaptador opcional requer token da automação; nenhum botão/callback de aprovação ou publicação. |

O gatilho de preparação foi alterado para manual no arquivo do Actions. Um `workflow_dispatch` precisa existir na branch padrão para ser disparado dessa forma; integrar o workflow revisado é uma etapa de ativação. [Documentação do GitHub](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

Israel criou e escolheu **`app-deploy-test-isr`**, canal privado `C0C8DUJB52L`; o único membro humano confirmado é Israel (`U0BMFQKC001`). O adaptador verifica canal e membros antes de enviar. As mensagens não chegam ao canal oficial. Token/configuração e envio real ainda precisam de validação própria.

O adaptador de avisos mantém outbox local com ID e estado para não reenviar uma tentativa desconhecida. Runner efêmero não fornece deduplicação entre runs: persistência remota confiável do outbox fica pendente. Essa limitação não afeta a autorização, porque Slack não contém ações de aprovação/publicação.

**Limite do GitHub nesta evolução:** registro e reviews são nativos; fila, seed de produção, reconciliação por destino e estado SQLite funcionam na CLI local. O workflow de ensaio cria um banco novo por run. `concurrency` não reproduz a fila de negócio e não autoriza copiar contagens simuladas para o gate real.

## Fila e urgência

1. Manter **uma RC ativa em aprovação** e uma publicação por vez. Novas solicitações ficam em uma fila persistente; um grupo de concorrência do Actions não substitui essa fila de negócio.
2. Ao priorizar urgência, bloquear/substituir a RC anterior e invalidar seus botões e aprovações. Se uma publicação já começou, reconciliar seus efeitos antes de trocar a candidata ativa.
3. Criar a correção a partir do SHA da última produção confirmada, sem levar mudanças pendentes da main. Preparar conflitos, preview e uma nova RC; exigir revisão e aprovações próprias.
4. Depois da urgência, incorporar a correção na linha de desenvolvimento e resolver conflitos antes de avaliar o próximo lote. Criar outra RC, com 0/2, a partir desse conteúdo atualizado.
5. Publicar o SHA exato aprovado. Não fazer merge/rebase tardio para “atualizar” o código depois da aprovação. Se o resultado mudar, voltar à preparação.

Antes de publicar, comparar a base de produção esperada com o registro atual. Uma entrega concorrente torna a RC obsoleta até reconciliação. Se Android, iOS e web estiverem em versões diferentes por falha parcial, registrar essa diferença: não inventar uma única “última produção”. Uma urgência nesse estado exige plano explícito por destino e nova aprovação antes de seguir.

### Procedimento de urgência documentado e ensaiado localmente

- [x] [Procedimento operacional](delivery/procedimento-urgencia.md): consultar/reconciliar, bloquear a candidata antiga, preparar da produção confirmada, validar/aprovar/publicar no provedor falso, incorporar conserto e retomar com nova RC/avais.
- [x] Testes locais de urgência e falha parcial impedem trocar candidata enquanto a publicação não está reconciliada. Os recibos separam efeitos confirmados, pendentes e desconhecidos.
- [ ] Ensaiar com provedores e identidades reais na Etapa 7; recuperação local não comprova o comportamento desses serviços externos.

A identidade real de Israel e os papéis simulados continuam explícitos durante todo o exercício.

## Publicação parcial e identificação dos resultados

Cada destino guarda tentativa, estado, chave de idempotência, base alvo, SHA, identificador remoto, artefato/hash e instante confirmado. Estados mínimos: `pendente`, `executando`, `sucesso`, `falha`, `resultado_desconhecido`.

**Exemplo hipotético:** Android confirmou patch 7; iOS falhou; web confirmou publicação. A entrega fica **parcial**. A retomada consulta o que já ocorreu e tenta apenas o iOS pendente, sem recriar patch Android nem reenviar web. Se mudar o conteúdo ou a base para corrigir a falha, é outra RC.

Se a tentativa falhou antes de qualquer efeito, `lab.py abandon --candidate RC --repo REPOSITORIO` permite encerrá-la após consultar todos os destinos no mesmo journal do FakePublisher. Registra `abandon_no_effect`, muda para `encerrada_sem_efeito` e desativa os avais; a correção segue numa nova RC com preview/manifesto e aprovações novos. Qualquer recibo, mesmo após timeout ainda desconhecido para a esteira, recusa esse encerramento e exige preservar/reconciliar/retomar a publicação parcial. O caminho de `provider.sqlite` fica vinculado à tentativa: manter o mesmo `--provider-dir` na recuperação. Essa prova de zero efeitos vale para o journal local síncrono; não presumir que um lookup vazio de serviço externo ofereça a mesma garantia.

Depois de sucesso confirmado em cada destino, criar a respectiva tag no **mesmo SHA aprovado**. Nomes propostos, ainda sujeitos à revisão das proteções:

| Destino | Exemplo ilustrativo de tag | Evidência necessária |
|---|---|---|
| Android | `android/1.1.0+2/patch-7` | Confirmação do patch 7 na release-base Android exata. |
| iOS | `ios/1.1.0+2/patch-3` | Confirmação do patch 3 na release-base iOS exata. |
| Web | `web/1.1.0/entrega-0042` | Confirmação do deployment e hash do artefato aprovado. |

Os números Android e iOS podem divergir; não reservar nem sincronizar números artificialmente. Tags são registros, não gatilhos automáticos de nova distribuição. Falha ao gravar uma tag após publicar exige recuperar o registro, não publicar de novo. Não mover tags já existentes.

Só marcar **concluída** após sucesso de todos os destinos requeridos e registro das evidências. Sucesso na API de publicação não comprova que todos os dispositivos instalaram o patch; validar adoção é outro critério. Publicação de loja e disponibilidade a testadores também são resultados separados.

## Backlog por etapas

Cada etapa entrega algo demonstrável antes de começar a próxima. **Etapas 1 a 6 têm implementação e testes locais; Etapas 7 e 8 permanecem pendentes.** Os critérios abaixo continuam necessários para avaliação humana. Israel opera o laboratório; uso real com outras pessoas depende da autorização e disponibilidade delas.

### Etapa 0 Inventário

**Estado:** concluído para este planejamento, sem ativar a esteira. Evidências e diferenças estão nas seções acima.

**Aceite:** localizar PRs, commit, preview, testes, proteções e Release existente; separar fatos atuais de ensaios sintéticos. Antes de ativar o caminho remoto, renovar a fotografia se o GitHub tiver mudado. Não reutilizar a Release existente como saída de um novo teste nem sobrescrevê-la.

### Etapa 1 Simulação local de papéis

**Estado:** implementada na CLI/SQLite e exercitada em processos separados; testes sintéticos preservam o gate real.

**Entrega:** estado persistido localmente, fixture de RC e ações representar papel, revisar tecnicamente, aprovar, revogar e consultar histórico. Adaptadores externos permanecem falsos.

**Aceite:** Israel percorre 0/2 → 1/2 → 2/2 simulado; reiniciar o processo preserva o estado; papel repetido não aumenta a contagem; toda ação preserva a identidade real. Um evento simulado é rejeitado pela política real. Nenhuma review ou status remoto é criado.

### Etapa 2 Preparação manual da candidata

**Estado:** preparação local implementada; workflow manual e criador GitHub revisados. Ativação remota e proteção neutra ainda pendentes.

**Depende:** Etapa 1 e revisão autorizada dos workflows antes de integração.

**Entrega:** operação Preparar candidata; primeiro em modo local, depois exposta por Actions quando autorizado. Congelar SHA, branch de release, tag neutra, manifesto, preview e changelog do lote.

**Aceite:** dois PRs integrados não criam RCs automaticamente; um acionamento prepara um lote. Reuso exige prova de código e inputs equivalentes; divergência reconstrói. Repetir a mesma solicitação não cria candidata duplicada. No ensaio B → F′, comparar a árvore completa com B mais o conserto e confirmar que os marcadores das features C/D da main estão ausentes. RC1 permanece em B e RC2 fixa F′, com novo registro de preview/changelog e 0/2. Nova tag remota só após autorização das proteções correspondentes.

### Etapa 3 Pré-análise de elegibilidade

**Estado:** implementada offline e coberta por fixtures; comparação final Shorebird e bases reais pendentes.

**Depende:** Etapa 2.

**Entrega:** relatório separado para Android e iOS, com base exata e resultado patch previsto, loja necessária ou pendente; evidências e motivo legíveis.

**Aceite:** Dart compatível, asset empacotado, mudança nativa/engine e base desconhecida produzem os resultados previstos. Caso acumulado desde a release-base é detectado mesmo se o diff da última RC for só Dart. Nenhum patch é gerado durante a preparação.

### Etapa 4 Aprovação e comando final

**Estado:** implementada no laboratório; GitHub nativo escolhido, Slack somente avisos. Gate real continua exigindo duas identidades e ainda não foi validado em 2/2.

**Depende:** Etapas 1 a 3; ativação da interface GitHub é posterior aos critérios locais.

**Entrega:** contagem por RC, estado autorizada e comando Publicar agora separado, com autenticação e permissão apropriadas ao modo.

**Aceite:** 2/2 não publica; somente comando final autorizado pode chamar o adaptador. Autor/identidade repetida não passam na política real. Repetição, operador não autorizado, RC antiga, aprovação revogada e mudança de manifesto bloqueiam sem efeito externo.

### Etapa 5 Fila serial e urgência

**Estado:** fila, substituição, obsolescência e urgência implementadas no SQLite; procedimento e testes locais disponíveis. Persistência de negócio entre runs GitHub pendente.

**Depende:** Etapa 4.

**Entrega:** fila persistente, substituição auditada, base de produção registrada e caminho de hotfix. Procedimento operacional disponível em `delivery/procedimento-urgencia.md`.

**Aceite:** duas solicitações simultâneas deixam só uma RC em aprovação. Urgência parte da produção confirmada e inutiliza a aprovação anterior. Reincorporação do hotfix gera nova RC em 0/2. Publicador rejeita base obsoleta; conflito é resolvido antes de aprovar. Após uma publicação parcial, o procedimento reconcilia os resultados por destino antes de liberar outra entrega.

### Etapa 6 Publicação dry-run e retomada

**Estado:** provedor falso, timeout, recibos, retomada sem duplicação e snapshot exato exercitados pelo demo e CLI. Nenhuma distribuição real foi validada.

**Depende:** Etapas 4 e 5.

**Entrega:** adaptadores falsos por destino, recibos, falhas injetáveis, timeout e recuperação após reinício. Marcar `dry_run: true` e `distribution_performed: false`.

**Aceite:** exercício completo chega a conclusão simulada. Falha parcial retoma só pendências; timeout consulta resultado antes de repetir; falha de registro após sucesso não republica. Avançar main e release depois de aprovar F′ não muda o checkout usado pelo publicador: ele continua no SHA aprovado, com inputs conferidos; checkout mutável ou divergente bloqueia. Uma execução parcial nunca aparece como sucesso total. Dry-run desta etapa não chama Shorebird, loja, hospedagem ou criação de GitHub Release.

### Etapa 7 Ensaios reais isolados

**Estado:** pendente, incluindo credenciais/destinos e duas identidades reais distintas.

**Depende:** Etapas anteriores aceitas e autorização explícita para destinos, credenciais e efeitos de cada ensaio.

**Entrega:** duas validações independentes: mecânica de distribuição num app/base exclusivos da POC; e segregação de aprovação com identidades reais distintas. A segunda não pode ser concluída só por Israel.

**Aceite:** confirmar app/base e dispositivos autorizados; executar comparação final sem ignorar incompatibilidades; registrar resultado por destino e observar o app. Não usar TestFlight nem track beta para o MVP. A rota de instalação iOS local precisa ser validada antes de declarar cobertura iOS; falta de acesso mantém esse item pendente. Ensaio mobile por Israel não comprova o gate de duas pessoas.

### Etapa 8 Critérios antes de adaptar ao Amulets

**Estado:** pendente; este laboratório não autoriza mudanças no Amulets.

**Depende:** evidências das etapas anteriores e aprovação de um plano específico para o Amulets.

**Entrega:** pacote de transferência com contratos, testes, exemplos de recibos, matriz de acessos, recuperação e diferenças do projeto de destino.

**Aceite:**

1. Demonstrar simulação completa e ensaio real com identidades distintas, sem misturar os resultados.
2. Validar bases por plataforma, SHA aprovado, patch incompatível bloqueado e retomada sem duplicação.
3. Definir responsáveis por preparar, aprovar, publicar, verificar dispositivos e tratar incidentes; incluir procedimento de rollback ensaiado quando autorizado.
4. Auditar CI, flavors, app IDs, segredos, permissões e proteções atuais do Amulets somente em leitura; aprovar as diferenças antes de implementar.
5. Registrar validação humana do fluxo e autorização para a adaptação. Nenhum comando Shorebird será executado no Amulets como parte deste laboratório.

### Decisão com Samuel: quem poderá gerar uma RC na Amulets?

**Pendente de definição pelo time.** Perguntar ao Samuel: **quem será autorizado
a preparar/gerar as RCs, quem poderá substituir essa pessoa e quem poderá
iniciar uma recuperação de publicação parcial?** Definir pessoas ou grupo,
contas autenticadas e regras para entregas normais e urgentes antes de adaptar
a esteira. Ser aprovador ou poder iniciar um Action não concede automaticamente
o papel de preparador.

No LAB atual, `operators` permite somente `israelhudson` preparar a candidata.
Israel e Fabrícia aprovam, e qualquer um dos dois pode dar o comando final
depois dos dois avais. Essa matriz do laboratório não define a política da Amulets.

Na rodada manual de 08/10/2026, a conta `fahnassau30` tentou preparar `1.6.0` e
foi recusada antes de criar a candidata, branch ou tag. É um bloqueio esperado
da política; a orientação anterior não tinha explicitado a conta necessária.
As [evidências e o procedimento para continuar](delivery/evidencias/2026-10-08-rc160-operator-block/RELATORIO.md)
preservam a execução e o motivo. Melhoria de experiência pendente: apresentar
os preparadores autorizados antes da execução e explicar a ausência de efeitos
na mensagem de bloqueio. Não ampliar permissões como contorno.

## Cenários de aceite

Os resultados são critérios de aceite. As suítes `test_lab_engine.py`, `test_snapshots.py`, `test_github_candidate.py` e `test_policy.py` cobrem cenários sintéticos; `lab.py demo` fornece evidência executável de snapshots e falha parcial. APIs substituídas e papéis simulados não são validação real. Consultar a saída da suíte executada e os recibos da sessão, preservando os testes anteriores.

### Aprovação e identidade

| Cenário | Resultado esperado |
|---|---|
| 0/2 e 1/2 | Publicação bloqueada. |
| 2/2 na RC atual | Apenas libera o comando final. |
| Autor tenta aprovar na política real | Rejeitado; a simulação local continua claramente separada. |
| Mesmo papel ou mesma identidade real repetidos | Papel repetido não soma; identidade única não satisfaz 2/2 real. |
| Ian/Yan aprova tecnicamente | Não soma às aprovações Samuel/Vinícius. |

### Integridade da candidata

| Cenário | Resultado esperado |
|---|---|
| Nova RC, SHA ou manifesto alterado | Aprovações efetivas zeradas; histórico preservado. |
| Candidata substituída, expirada ou baseada em produção antiga | Comando antigo rejeitado. |
| Preview equivalente por conteúdo e inputs | Reuso permitido, com hash e origem registrados. |
| Preview divergente, indisponível ou inputs desconhecidos | Reconstruir antes da RC; após aprovação, exigir nova RC. |
| Patch inelegível ou base ausente | Bloquear; não ignorar warnings nem migrar para loja automaticamente. |

### Snapshots e publicação

| Cenário | Resultado esperado |
|---|---|
| Main recebe C/D após cortar a release em B | Snapshot da release conserva B; as features novas ficam ausentes. |
| Conserto gera F′ na release | Árvore completa corresponde a B mais conserto; RC1 fica em B, RC2 fixa F′ e exige nova avaliação e 0/2. |
| Cherry-pick de F depende de C/D | Bloquear a candidata até adaptar o conserto ou declarar/testar as dependências numa nova RC. Ausência de conflito não prova compatibilidade. |
| Main ou branch release avança após aprovação | Publicador usa checkout isolado do SHA aprovado F′. Alterações locais, inputs divergentes ou resolução para uma ponta mutável bloqueiam. |
| Publicação de F′ confirma sucesso | Tag final e tags de destinos confirmados apontam para F′; não apontam para B original nem para o HEAD atual da main. |

### Concorrência e recuperação

| Cenário | Resultado esperado |
|---|---|
| Dois comandos finais ou solicitações repetidas | Uma operação efetiva; demais consultam a mesma tentativa. |
| Revogação durante execução | Impedir próximos efeitos; registrar e reconciliar os efeitos já confirmados. |
| Android publicado e iOS falha | Entrega parcial; retomada do iOS sem duplicar Android. |
| Timeout ou processo cai após sucesso remoto | Consultar provedor e reconciliar antes de repetir; recuperar tags/recibos faltantes. |
| Warning/falha antes de qualquer efeito no provedor falso | Encerramento auditado `abandon` consulta o journal, desativa avais e permite nova RC; produção permanece na base anterior. |
| Pedido de encerramento com recibo ou outro provider-dir | Recusar; preservar o journal e reconciliar/retomar os efeitos existentes. |
| Urgência durante aprovação ou publicação | Invalidar RC anterior; se houver efeito em andamento, reconciliar primeiro. |

## Decisões pendentes no momento certo

| Quando | Decisão necessária |
|---|---|
| Antes da ativação remota | GitHub nativo escolhido; definir persistência confiável da fila/seed/reconciliação e outbox de avisos. |
| Antes de criar novas refs remotas | Proteções para tags neutras, branches de release e registros; estratégia para conservar a POC histórica. |
| Antes de ensaio real | Apps e release-bases isoladas, dispositivos, rota iOS, destinos web e autorização para efeitos externos. |
| Antes de comprovar segregação | Identidades reais, permissões e responsáveis por publicação e incidentes. |
| Antes de adaptar à Amulets | Confirmar com Samuel quem pode gerar RCs, substituir o preparador e iniciar recuperação; separar esses acessos dos avais e do comando final. |
| Antes de ativar resumo/avisos | Definir acesso e orçamento Copilot, contexto de PR/Plane, timeout, canal/app Slack e congelamento do texto apresentado; IA/Slack não bloqueiam a esteira. Ver o adendo de changelog semitécnico. |
| Na Etapa 7 | Validar procedimento de urgência e reconciliação com provedores reais e identidades distintas. |

**Próxima ação:** executar o demo do [laboratório](delivery/LABORATORIO.md), abrir `report.json` e observar 0/2 → 1/2 → 2/2, RC2 no SHA de F′ e retomada parcial. Depois avaliar os critérios locais antes de ativar qualquer caminho remoto.
