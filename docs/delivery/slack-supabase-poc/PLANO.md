# POC: aceites no Slack e estado no Supabase

Plano registrado em 13/10/2026, antes da implementação. Esta alternativa convive
com LAB e Issue; começa desativada. Não exige GitHub Enterprise.

## Primeiro: o que estamos reproduzindo

1. Feature por PR, com preview identificado pelo SHA do PR.
2. Após o merge, cortar uma RC imutável, com preview e changelog daquele SHA.
3. Publicar um cartão no `app-deploy-test-isr` (`C0C8DUJB52L`). Os botões são
   **Aceite técnico**, **Aceite de negócio** e **Solicitar ajuste**.
4. Registrar cada papel uma vez no banco. Em 1/2, atualizar o cartão e mandar DM
   ao papel pendente, tanto técnico→negócio quanto negócio→técnico.
5. Em 2/2, atualizar o cartão e mandar DM ao criador. A publicação é uma
   capacidade separada, inicialmente desligada; `is_lab` não concede permissão.
6. Um ajuste registra motivo, autor e hora e bloqueia a candidata. A correção
   entra por PR na branch da entrega. RC2 ganha tag, cartão e zero aceites novos.
7. Quando habilitado e validado, publicar uma prerelease de TESTE no GitHub,
   sempre a partir do SHA congelado. Patches Shorebird ficam em uma etapa própria.

## Etapas e critério de saída

| Etapa | Trabalho | Prova para avançar |
|---|---|---|
| 1. Auditar | Main, workflows, permissões, bot e referências | Inventário sem expor credenciais |
| 2. Isolar | Projeto Supabase exclusivo, tabelas `poc_*`, funções `poc-*`, bot existente com encaminhamento | Destino confirmado; nenhum consumidor Mobile alterado |
| 3. Implementar | Transações, assinatura Slack, cartão, DMs, prazo de 36h e ajustes | Testes locais de banco e HTTP, separados dos cliques reais |
| 4. Integrar | Preview de PR; corte, preview e changelog da RC; workflows `Slack -` | SHA/tag/artefato/HTTP verificados; runners de build sem escrita |
| 5. Ensaiar | Solo Israel; duas pessoas somente com identidades Slack verificadas | 0/2→1/2→2/2, ordem inversa, repetição, ajuste/RC2 e falhas |
| 6. Publicar no GitHub | Habilitação própria, intenção antes dos efeitos e recibo | Uma tag final/prerelease de teste; repetição sem duplicar |
| 7. Preparar Shorebird | Base exata por plataforma, canal e instalação de teste | Compatibilidade e critérios de aceite confirmados antes de qualquer patch |

## Isolamento e rollback

- Referência de leitura: `amuletslabs/amulets-release-lab`, commit `68941a3`;
  Mobile `main-test`, commit informado `9803f3b`. Datas dos documentos da referência
  não tornam seus enunciados equivalentes ao estado atual: conferir migrations e código.
- O projeto Supabase `uvfwvplcziehxrkidrxh` é compartilhado com o teste Mobile e
  não recebe deploy, migrations, novos registros ou mudança de secrets nesta tarefa.
- Israel escolheu reutilizar o app Slack existente. O receptor `poc-slack-router`
  encaminha payloads antigos intactos ao receptor atual e separa namespaces POC.
  Trocar a Request URL somente depois de testar e registrar o rollback.
- Nunca usar `#app-deploy` nesta POC. Canal fixo de teste em código, banco e configuração.
- Flags GitHub e backend independentes. Desligá-las impede novas operações;
  preservar cartões, tags, tabelas, eventos e recibos para auditoria.
- Não apagar nem mover tags. Não reutilizar aceites, nem mudar o SHA de uma RC.
- Reserva de envio vem antes do POST. Resposta incerta requer reconciliação;
  não reenviar cegamente em runner novo. A thread fica para conversa.

## Identidades e pendências explícitas

- Israel foi consultado no Slack: `U0BMFQKC001`; GitHub `israelhudson`.
- Israel confirmou que Fabrícia não tem Slack. A alternativa Slack será solo: Israel dá os aceites técnico e de negócio. Fabrícia não será solicitada como revisora nos novos workflows.
- Solo permite Israel nos dois papéis e fica identificado como simulação de papéis,
  sem atribuir decisão à Fabrícia, Samuel ou Vinícius.
- `creator`, `technical_reviewer` e `business_reviewer` são campos independentes.
  Em 2/2 real, os revisores precisam ser pessoas distintas e verificadas.
- Israel escolheu projeto exclusivo na organização **iHud Tecnologia**.
  A organização está no plano Free. Israel confirmou a criação pelo CLI a US$ 0/mês,
  sem upgrade. Projeto criado: `xtvueqciogzkyjkkqxcx`, região São Paulo.
- A réplica inicial da publicação é GitHub TESTE. Android/iOS, versões-base e
  patches efetivos têm campos separados; nenhum número de patch será presumido.

## Evidências

Salvar inventário, testes e recibos em `evidencias/`. Distinguir teste local,
chamadas a serviços reais, cliques reais e publicação. Um check verde de fixtures
não comprova uma aprovação humana, envio Slack ou distribuição mobile.

## Ajuste solicitado por Israel durante a implementação

O prefixo dos workflows é `Slack -`. O modo real desta POC será solo Israel.
A main do laboratório antigo exige uma revisão de outra conta; essa regra é global.
A alternativa escolhida por Israel é `slack-main`, com PR e check obrigatório, zero reviews
humanos obrigatórios, e `poc-release/VERSÃO` para correções. A instalação inicial dos arquivos na main passa pela proteção
existente; não remover essa regra em silêncio, pois o LAB depende dela.

## Decisão posterior sobre o Slack

Israel confirmou reutilização de Flutter Deploy LAB no mesmo canal, com
encaminhamento. As credenciais foram verificadas e copiadas somente para o
projeto exclusivo. Scopes chat:write/groups:read existentes são suficientes;
nenhuma permissão nova foi solicitada. A URL atual foi observada no navegador
e segue apontando ao receptor antigo enquanto se conclui o ensaio do router.
