# [003] How To Build Feature Flags Like A Senior Dev In 20 Minutes

| Campo | Valor |
|-------|-------|
| **Fonte** | https://youtu.be/VBCYqp8l3Lc |
| **Autor/Canal** | Web Dev Simplified (Kyle) |
| **Publicado em** | 2024-10-29 |
| **Duração** | 20min32s |
| **Adicionado em** | 2026-08-18 |
| **Tema** | Feature flags — teoria, trade-offs e algoritmo de rollout |
| **Idade** | 🟢 atual — conceitual e independente de linguagem |
| **Código** | https://github.com/WebDevSimplified/feature-flags-sample-code |
| **Transcrição** | [003-transcricao-bruta.md](003-transcricao-bruta.md) (ASR `en-orig`) |

## Por que está aqui

**Não é Flutter** — os exemplos são TypeScript/Next.js. Está aqui de propósito: é a
única das três referências que trata feature flag como **problema de arquitetura**, e
não como uso de um produto. O autor deixa isso explícito em [06:12]: *"o código que
estou mostrando funciona em qualquer linguagem que você quiser"*.

Cobre três coisas que nem a [001] nem a [002] tocam: **quando NÃO usar** flags, **onde
armazená-las** (com trade-offs medidos), e **como o rollout por porcentagem funciona por
dentro** — que na [001] e [002] é caixa-preta do console do Firebase.

| O que | Validade | Onde conferir |
|---|---|---|
| Trade-offs, casos de uso, algoritmo | 🟢 vale hoje, em qualquer linguagem | [Fonte verificada](#fonte-verificada) |
| Sintaxe TS/Next.js dos exemplos | ⚪ irrelevante aqui — traduzir para Dart | [GitHub do autor](https://github.com/WebDevSimplified/feature-flags-sample-code) |

## Fonte verificada

### A tese

> "À primeira vista, feature flags parecem um conceito simples de ligar e desligar
> features, mas são muito mais do que isso — e eu acho que todo projeto deveria ter
> pelo menos algumas flags." [00:00]

### Os 5 prós — em ordem de importância declarada pelo autor

**1. Kill switch** [01:35–02:04] — o que ele considera *a* razão principal, e a que
"a maioria das pessoas não comenta".

Exemplo dado: e-commerce em que um bug de deploy faz os produtos saírem de graça. Sem
flag: mexer no código, dar push, esperar o redeploy — tudo isso custando dinheiro por
minuto. Com flag: virar um switch.

> "Ter kill switches onde roda código realmente crítico, onde se algo der errado você
> quer parar a execução imediatamente — esse é o exemplo perfeito de uma flag de vida longa."

É a única categoria de flag que ele considera **permanente**. Todas as outras são temporárias.

**2. Beta testing** [02:04–03:06] — usuário opta por entrar nas features beta pelas
próprias configurações. Pode ser combinado (10% dos que optaram, só admins, etc).

**3. Teste A/B** [03:06] — 30% veem, 70% não; mede-se conversão.

**4. Refactor seguro** [03:06–04:08] — o caso de uso mais original do vídeo.

Você tem uma query SQL lenta e escreve uma versão otimizada, mas não tem certeza de
que ela retorna o mesmo em todo edge case. A flag permite **rodar as duas lado a lado,
comparar os resultados, e continuar devolvendo a original**. Quando a confiança
acumula, troca-se a flag. Ele volta ao padrão em código no fim do vídeo [18:39]:

```
produtosAntigos = queryOriginal()
se flag('testar_query_nova'):
    produtosNovos = queryNova()
    se produtosNovos != produtosAntigos:
        log_erro(...)      # manda pro serviço de logging que você usa
retorna produtosAntigos    # sempre a original
```

> "Depois de semanas ou meses com as duas queries rodando lado a lado, eu sei que
> retornam o mesmo dado." [19:41]

Só então se apaga a query antiga e a flag. Isso transforma um refactor arriscado em
observação empírica em produção — sem risco para o usuário.

**5. Deploy mais fácil** [04:08–05:10] — a feature incompleta já está na `main`, mas
escondida atrás da flag. Quando surge um fix de segurança urgente, você faz deploy
direto da `main` em vez de voltar à versão em produção, corrigir lá, e depois
reconciliar tudo.

### Os 4 contras — e eles são levados a sério

**1. Complexidade** [05:10] — branching extra em todo lugar (`if flag ... else ...`).

**2. Mais código** — múltiplos cenários a cobrir.

**3. Manutenção** [05:10–06:12] — o ponto mais importante da seção:

> "Salvo um kill switch, na maioria das vezes elas são **temporárias**. Você mantém a
> flag por talvez um mês, alguns meses, no máximo um ano — mas idealmente um ou dois
> meses, e então você remove a flag."

E a consequência de não remover:

> "Se você não remove as flags quando não são mais necessárias, isso aumenta
> drasticamente a quantidade de código e a complexidade que você tem."

**Flag sem data de remoção é dívida técnica, não feature.**

**4. Novos pontos de falha** — o próprio sistema de flags pode ter bugs. Ele classifica
como ponto menor, mas cita.

### Onde armazenar as flags — a tabela de trade-offs

[08:20–12:18] Quatro opções comparadas em cinco eixos:

| | No código | Env var | Banco de dados | SaaS |
|---|---|---|---|---|
| **Implementar** | fácil | fácil | "difícil" ¹ | fácil |
| **Velocidade de leitura** | instantânea | instantânea | rede ² | rede ² |
| **Velocidade para mudar** | deploy | redeploy (10–30 min) | segundos (UI) | segundos (UI) |
| **Custo** | grátis | grátis | grátis ³ | pago |
| **Flexibilidade** | infinita | **só boolean** | alta | alta |

¹ Ele mesmo relativiza: *"marquei como difícil só porque é mais difícil que código ou env var — mas realmente não é tão difícil"* [09:18].
² **Resolvido com cache.** Ver abaixo.
³ Se você já tem banco no projeto.

**O argumento do cache** [09:18] é o que dissolve a desvantagem de banco/SaaS:

> "Flags realmente não mudam com frequência. Você provavelmente muda uma a cada duas
> semanas, no máximo a cada poucos dias — então dá para cachear por um tempo
> incrivelmente longo. Com um cache na frente do banco, você tem exatamente a mesma
> velocidade que teria no código."

**Por que "velocidade para mudar" é o eixo decisivo** [10:20]:

> "Se você precisa de um kill switch, quer que seja o mais rápido possível. Você não
> quer esperar uma hora pelo kill switch iniciar."

Isso elimina código e env var como opção para kill switch — o caso de uso nº 1.

**A recomendação dele** [11:24]: começar em **env var** enquanto o app é pequeno →
migrar para **banco** conforme cresce e as flags se acumulam → **SaaS** só em
enterprise com necessidade muito nichada. *"Em 99,9% dos casos"*, banco + a
implementação dele resolve.

### O algoritmo de rollout por porcentagem

[15:32–16:35] A parte tecnicamente mais valiosa do vídeo, e o que está escondido dentro
do "percentil" do console do Firebase nas referências [001] e [002].

O modelo de dados: uma flag é **ou** um boolean **ou** um array de regras, onde cada
regra tem `userRoles` e/ou `percentageOfUsers`. `canViewFeature(flag, user)` retorna o
boolean direto se for boolean; se for array, avalia as regras. Regra sem roles definidos
sempre passa no teste de role.

O cálculo da porcentagem:

```
valor = MurmurHash(nomeDaFeature + idDoUsuario)   // inteiro de 32 bits
n     = valor / MAX_INT32                          // normaliza para [0, 1]
libera = n < porcentagemPermitida
```

Três decisões de projeto, todas justificadas no vídeo:

**Por que hash e não `random()`** [14:30] — é o ponto central:

> "Não importa de qual computador eu acesse nem de onde eu venha, eu sempre vejo
> exatamente as mesmas features, porque está atrelado ao ID do meu usuário. Não está
> atrelado ao meu browser, nem ao local storage, nem a cookies."

Determinismo por usuário. `random()` faria a feature piscar a cada render; cookie ou
local storage quebraria ao trocar de dispositivo.

**Por que concatenar `nomeDaFeature + idDoUsuario`** — e não só o ID. Se fosse só o ID,
o mesmo usuário cairia sempre na mesma faixa do intervalo e estaria dentro (ou fora) de
*todos* os rollouts simultaneamente. Concatenar o nome redistribui o usuário a cada feature.

**Por que MurmurHash** [15:32] — requisito é distribuição uniforme e velocidade, **não
segurança**:

> "Isso não vai ser seguro para propósitos criptográficos. Você nunca usaria isso para
> senhas. Mas não precisa ser seguro."

Ele conta que primeiro tentou os hashes nativos do JavaScript e eles eram muito mais
lentos, por serem voltados a criptografia — e ainda forçavam `async/await`.

## Complemento

Nada acrescentado de fora. O vídeo é autocontido e recente, e o código está publicado
no [repositório do autor](https://github.com/WebDevSimplified/feature-flags-sample-code)
para conferência linha a linha.

## Aplicação neste projeto

Esta referência é a **camada de teoria** por baixo das outras duas. Três aplicações
diretas:

**1. Onde armazenar, no contexto deste projeto.** A tabela dele mapeia assim:

| Opção dele | Equivalente aqui |
|---|---|
| No código | valor hardcoded em Dart — muda só com patch Shorebird |
| Env var | `--dart-define` — muda só com build novo, nem patch resolve |
| Banco + UI | **Firebase Remote Config** — é exatamente isso, com a UI já pronta |
| SaaS | LaunchDarkly e afins |

Remote Config é o "banco com UI" da tabela: segundos para mudar, flexível, e — pelo
critério dele — o único aceitável para kill switch. O `minimumFetchInterval` da [001] é
literalmente o "cache na frente do banco" que ele recomenda em [09:18], o que explica
por que 1 hora é um default razoável e não uma limitação.

**2. O algoritmo justifica confiar no percentil do Firebase.** Saber que o rollout
gradual é hash determinístico por usuário — e não sorteio por sessão — é o que garante
que um usuário em 10% não perca a feature ao reabrir o app. Sem isso, o percentil da
[001] e [002] é fé.

**3. Kill switch é o argumento que fecha Shorebird + Remote Config.** O caso do
e-commerce em [01:35] é exatamente o cenário deste projeto: Shorebird corrige o bug,
mas leva o tempo de gerar patch + propagar. Remote Config desliga na hora. **São
respostas a tempos de reação diferentes** — e o que Kyle argumenta é que para código
crítico o tempo de reação é o que importa mais.

Nenhuma flag foi implementada aqui ainda.

## Pendências

- [ ] Traduzir `canViewFeature` + regras para Dart, decidindo se compensa ter camada
      própria de porcentagem ou se o percentil do Firebase basta
- [ ] Definir política de expiração de flag no projeto — o contra nº 3 é o que mais
      cobra a longo prazo. Sem data de remoção, não cria a flag
- [ ] Avaliar o padrão de refactor seguro [03:06] para a própria lógica de update do
      Shorebird — rodar o caminho novo em paralelo e comparar antes de trocar
