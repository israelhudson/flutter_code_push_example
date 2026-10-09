# Ajustes e prioridades após a entrega 1.6.0

Registro de 08/10/2026, Fortaleza. A `v1.6.0` foi publicada no GitHub com os oito jobs da rodada concluídos, dois avais e comando final separado. A RC1 foi preservada no mesmo commit. Manter as tags RC é uma decisão de rastreabilidade; não é um defeito a corrigir.

## Ajustes integrados e prova do Slack

A implementação separa 0/2 e 1/2 de 2/2 aguardando PUBLICAR; concilia rejeição/cancelamento/falha com run/reviews oficiais; preserva histórico e intenções parciais. O manifesto de versões e o material de comunicação entram no relatório congelado, na Release e no recibo. Campos novos não são acrescentados retrospectivamente aos relatórios aprovados.

O contexto de PRs é coletado em job paralelo ao build. Sem resultado válido disponível, o relatório usa commits e preserva o motivo. Seções explícitas do novo template produzem texto semitécnico sem IA. Esses ajustes foram integrados pela [PR #18](https://github.com/israelhudson/flutter_code_push_example/pull/18). **Copilot e Plane permanecem inativos.** A ilustração Slack lê o material escolhido, sem alterá-lo nem enviar mensagem.

O bot `Flutter Deploy LAB` e o secret `SLACK_BOT_TOKEN` já foram configurados.
A [execução isolada 37869235129](https://github.com/israelhudson/flutter_code_push_example/actions/runs/37869235129)
confirmou envio real ao canal privado `app-deploy-test-isr`, com verificação de
identidade/membros e recibo `sent`. Os avisos automáticos da candidata estão
integrados pela [PR #19](https://github.com/israelhudson/flutter_code_push_example/pull/19), aguardando prova própria do fluxo. O
workflow de teste de conexão permanece separado desse fluxo.

O [coletor de evidências](COLETAR-EVIDENCIAS.md) está implementado e coletou os oito logs reais da entrega 1.6.0. O orquestrador que julga os cenários negativos ainda é pendente. [Comunicação congelada](COMUNICACAO-CONGELADA.md) e [versionamento por plataforma](VERSIONAMENTO-ENTREGA-E-PLATAFORMAS.md) explicam os contratos e limites.

Integração e ensaios remotos desses ajustes têm prova própria no relatório desta rodada. Testes locais de estados/contexto/versões não comprovam cancelamento real no GitHub ou distribuição mobile. A ordem abaixo permanece como roteiro antes do Amulets, com essas partes de código já preparadas.

## Ordem de trabalho proposta

| Ordem | Prioridade e momento | Ajuste | Como comprovar |
| --- | --- | --- | --- |
| 1 | **P1 — próxima rodada do LAB** | Consolidar estados e identidade visível: distinguir aguardando revisores, aguardando comando final, rejeitada, cancelada e publicada; mostrar versão da candidata e versão interna do app com rótulos claros | Conferir journal, reviews e run em 0/2, 1/2, 2/2, rejeição e cancelamento. Preview identifica RC/SHA e explica `pubspec_version`; hoje mostra `1.1.0+2` para RC `1.6.0-rc.1` |
| 2 | **P1 — antes de adaptar à Amulets** | Completar os cinco subcasos remotos e o caso de fonte congelada com avanço da main/workflows | Ensaiar conflito de tag, recuperação parcial, deriva de proteções, writers concorrentes e preview falho. Validar permissões da promoção sem mover a tag nem ampliar acesso como contorno |
| 3 | **P1 — decisão com o time antes da Amulets** | Definir quem gera RC, substituto, recuperador e contas Samuel/Vinícius; validar revisão independente e destinos mobile | Matriz acordada com Samuel; duas decisões próprias na mesma RC, comando final separado e aceites específicos por destino/dispositivo. Release GitHub não comprova distribuição mobile |
| 4 | **P2 — comunicação da entrega** | Validar os avisos automáticos integrados, com comunicação congelada, fallback e outbox persistente; avaliar IA/Plane separadamente | Confirmar mensagem da candidata, recibo e reexecução segura. Slack indisponível produz aviso opcional e não segura gates/promoção; `unknown` exige reconciliação positiva e não reenvio automático |
| 5 | **P3 — manutenção e apresentação** | Automatizar o coletor de evidências e o relatório de testes negativos; atualizar os materiais após as correções | Coletar por tentativa/job, indicar logs ausentes e guardar coleta parcial. Teste negativo recebe PASS só após provar bloqueio esperado e ausência de efeitos; preservar o job original e erros reais |

P1 não significa que a entrega GitHub 1.6.0 falhou. Indica a ordem de refinamento do LAB e as condições antes de ampliar o processo ao projeto de trabalho. Não há um bypass crítico comprovado nos relatórios consultados; a rechecagem das proteções já foi corrigida antes da promoção anterior.

## Próximos passos do Slack

- [Configuração atual](CONFIGURAR-SLACK-LAB.md): bot `Flutter Deploy LAB` no canal privado `app-deploy-test-isr` e secret existente `SLACK_BOT_TOKEN`, com envio real comprovado.
- Gerador `tools/delivery/slack_preview.py`: cria `slack-message.json`, `slack-preview.md` e `slack-preview-metadata.json`, sem operação de envio nem leitura de credenciais.
- Job opcional **ILUSTRAR AVISO SLACK — simulação, sem envio** no workflow de avaliação. Usa o relatório congelado, mostra o texto no resumo e preserva o artefato `release-lab-slack-preview`.
- Os jobs de aprovação, autorização e promoção não dependem desse job. Ele tem apenas leitura, timeout curto e falha opcional; não tem Environment de aprovação.
- O [manual de operação](SLACK-AUTOMATICO.md) descreve os avisos integrados, os estados da outbox e a retomada de resultado incerto. Ensaiar esse fluxo antes de declarar os avisos automáticos comprovados.
- O provedor de IA, a consulta ao Plane e a atualização da mesma mensagem continuam pendentes. A captura paralela e o resumo literal das seções de PR já foram integrados. Configurar o secret não transforma o gerador ilustrativo em remetente; a rodada 1.6.0 não recebe novos passos retroativamente.

## Contrato de comunicação registrado

[Changelog e avisos](CHANGELOG-E-AVISOS-SLACK.md) detalha as fontes, o exemplo semitécnico e os cenários. Na Amulets, Samuel **E** Vinícius aprovam, depois Samuel **OU** Vinícius dá PUBLICAR. No laboratório, Israel e Fabrícia ocupam esses papéis. Os avisos apontam aos gates no GitHub; Slack não toma decisões.

O conteúdo selecionado para os revisores fica congelado. IA atrasada ou indisponível usa commits; saída tardia não troca texto já apresentado/aprovado. Não adquirir créditos automaticamente nem fazer a entrega esperar pelo resumidor.

## Itens já corrigidos: não tratar como pendências novas

Defaults seguros da API, rechecagem de proteções, fixture do namespace, parser HTTP 422, interpretação dos snapshots intermediários e caminho do journal já foram corrigidos/tratados. O download de logs por job funcionou na rodada 1.6.0; resta transformar a coleta e seu resumo em rotina automática.

Base das prioridades: [auditoria da 1.6.0](evidencias/2026-10-08-theme-rc160-live/RELATORIO.md) e [falhas/prevenção da rodada anterior](https://github.com/israelhudson/flutter_code_push_example/blob/codex/release-lab-state/release-lab/evidencias/2026-10-08-real-promotion-live/FALHAS-E-PREVENCAO.md). Os cinco subcasos remotos são pendências de prova, não cinco falhas observadas na publicação 1.6.0.
