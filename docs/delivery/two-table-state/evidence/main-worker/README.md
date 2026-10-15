# Worker da main e DMs reais — 14/10/2026

Código executado: `4a88d4fa377f924519db49a70705a119cbe5bb5a` na main. Projeto exclusivo `xtvueqciogzkyjkkqxcx`. Publicação desabilitada no GitHub e no Supabase; controle com escopo `none`.

## Comprovado

- Worker vazio: [38666885089](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38666885089).
- Histórico e envio real das duas DMs: [38666927632](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38666927632).
- Despertar automático após aceite técnico: [38666962499](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38666962499).
- Aceite de negócio clicado pelo agente via Computer Use e despertar automático: [38667006022](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38667006022).
- Estado após os aceites: `approved`, revisão 2, `publication_run=null`; nenhuma execução de `delivery-publish.yml`.
- DMs atualizadas com dois checks e sem botões. Primeiro aceite entrou antes do clique do agente; não atribuir os dois cliques ao agente.
- Cancelamento de encerramento solicitado pelo worker: [38667079319](https://github.com/israelhudson/flutter_code_push_example/actions/runs/38667079319).

## Limites do ensaio

O controle `delivery-10f6554131c34ed5b17b81f1b6673182`, versão fictícia 99.0.2, foi inserido pela RPC para testar worker/receptor. Não houve preparo completo, tag, Release, build, preview ou patch. Manifesto explicitamente marcado `validation_only` e eventos reais ficaram na branch `codex/delivery-history`. O link de Release exibido pelo template não existe neste ensaio; não usá-lo como evidência de publicação. A interface de ensaios precisa identificar esse caso e apontar para o histórico.

## Falha e aprendizado

A execução 38666841838 foi recusada antes de efeitos porque faltava o ruleset do histórico. Criado `Entrega - historico preservado`, sem bypass, bloqueando exclusão/force-push. A repetição passou. Instalar e conferir a proteção ANTES de habilitar o worker no próximo ambiente.

## Ainda falta

- Comprovar cron recuperando evento sem despertar; lease interrompido e resultado incerto com serviços reais.
- Rejeição/RC2 e publicação idempotente no novo caminho remoto (há testes locais, não substituir essa evidência).
- Rodada completa de preparo/preview e publicação apenas quando autorizada.
- Duas pessoas distintas, configuração de responsáveis e restauração das revisões humanas antes da adoção na Amulets.
- Refinar identificação visual de testes sem Release e documentação operacional.

Logs e prints privados: `/Users/israelhudson/Documents/Codex/2026-10-14/main-worker-validation/`. Screenshots preservam a interface e podem conter nomes da barra lateral; não publicar imagens brutas no repositório público.

## Encerramento confirmado

Worker de cancelamento concluído com sucesso. Controle cancelado na revisão 3; 16 operações concluídas, zero pendentes e nenhuma operação de dispatch. Somente duas tabelas públicas. O controle terminal foi preservado para recusar cliques antigos. `DELIVERY_V2_ENABLED=false` no GitHub ao final: preparos e cron pausados até a próxima rodada autorizada. Publicação permanece false nos dois lados.
