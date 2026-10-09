# QA dos Sites V5 e V5-2 — rodadas com Slack

Registro em 2026-10-09 02:32 UTC. Revisão local concluída antes do empacotamento;
publicação e privacidade informadas pelo agente principal. Este arquivo fica
fora das duas fontes dos Sites.

## Resultado local

- Ambos os Sites: 13 seções, âncoras internas válidas, IDs sem duplicação e
  arquivos locais de CSS/JS presentes. Verificação de sintaxe dos scripts passou.
- Duas jornadas renderizadas, com 11 marcos concluídos. Hero, tabela Amulets e
  seção 13 apresentam 1.7.0/1.8.0, três RCs, duas Releases GitHub e 13 avisos
  reais, sem tratar pendências adversariais ou mobile como concluídas.
- Hero aponta para o preview corrigido da RC2 de 1.8.0, fonte
  `c8d8f337ee390755bcff795d558f8c6f6f19c35b`. Links de 1.5.0 permanecem no
  apêndice histórico. Contagens 9/9, 15/20 e 13 prints são rotuladas históricas;
  não foram convertidas na suíte posterior de 404 testes.
- Fonte normal 18 px, A+ 21 px, com controle e preferência persistente
  preservados. Console local sem mensagens de erro ou aviso nas capturas finais.
- V5-2 em viewport 420 × 900: largura do corpo/documento de 405 px, sem
  overflow horizontal; título, CTA, preview atual e card 1.7.0 + 1.8.0 legíveis.
  Viewport temporário foi restaurado depois do QA.
- Modelo V5-2: Samuel e Vinícius são os únicos aprovadores e opções de comando
  final; Israel aparece como desenvolvedor. 0/2 e 1/2 bloqueiam PUBLICAR; 2/2
  libera apenas o comando separado. Rejeição bloqueia; nova RC recomeça sem
  herdar avais. São interações didáticas locais, sem conexão ao GitHub.
- Proposta Amulets separada das provas LAB: Israel/Fabrícia permanecem como
  atores históricos. Contas reais não foram apresentadas como dois revisores
  humanos independentes. B foi operada manualmente pelo usuário; A e seus
  PRs/avais/comando foram operados por Codex autorizado.
- HTML base também apresenta o resultado final, mesmo sem execução do JS;
  o render de dados acrescenta os marcos e links detalhados.

## Provas e limites mantidos

As duas jornadas completas e os 13/13 avisos foram comprovados pelos coletores
GitHub/Slack da equipe, não pelos controles didáticos do Site. Na rejeição da
RC1 de 1.8.0 houve cancelamento operacional para encerrar o outro gate. A
correção posterior recebeu CI com 404 testes, mas não teve novo ensaio negativo
remoto. O relatório congelado da RC2 usou commits_fallback porque 1486 caracteres
excederam o limite agregado de 1400; não houve IA nem reescrita após os avais.
Slack opcional não bloqueia a entrega; unknown exige prova positiva e não
promete envio exatamente uma vez. Distribuição mobile e os cinco subcasos
adversariais remotos continuam com aceites próprios.

[Pacote congelado d162f208](https://github.com/israelhudson/flutter_code_push_example/blob/d162f208535d9b75d8172fe0c8dbc8ce5ac6273d/release-lab/evidencias/2026-10-09-slack-rondas/README.md):
968 arquivos, 49 logs reais/19.725 linhas, 17 prints e 348 blobs distintos
conferidos byte a byte pelo coletor. Quatro logs ausentes da RC1 cancelada ficam
explícitos. Ambos os Sites apontam para esse commit preservado.
[Manual integrado](https://github.com/israelhudson/flutter_code_push_example/blob/be2bff221bc498b4be66602d912fb2cae1f9ce2a/docs/delivery/SLACK-AUTOMATICO.md).

Captura final local feita pelo agente principal:
`build/slack-integration/live-screenshots/19-v5-2-proposal-final-local.jpg`.
Capturas desktop/móvel adicionais foram emitidas no CUA durante o QA.

## Publicação informada pelo agente principal

- V5: source `cedeb0bf586d8e225970f6b261aeb8da74e174f7`, versão 3,
  deploy `appgdep_6ac851c91b048191beb339dbc1603ed9`.
- V5-2: source `622332030f7a20c6ae2d58b0bfa2b07bccad17dc`, versão 1,
  deploy `appgdep_6ac851fc21688191925bc0c7d6ecc74c`.
- Ambos com publicação success e acesso owner-private preservado, conforme
  validação do agente principal. No IAB foi necessário login; este QA local
  não acrescenta uma inspeção autenticada independente da versão hospedada.
- V4 pública preservada. Fontes dos Sites não foram editadas após o pacote.

## Encerramento

Servidores próprios 127.0.0.1:8346 e :8347 encerrados após autorização do agente
principal. As duas abas temporárias do IAB já não estavam disponíveis no
encerramento: o inventário retornou somente o Chrome pessoal, que não foi
alterado. Não foi possível emitir um comando adicional de fechamento para
aquelas abas. Arquivos locais preservados.
