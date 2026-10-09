# Refinamentos de estados, comunicação e versões por plataforma

Registro de 08/10/2026 em Fortaleza; arquivos usam a data UTC 09/10. Implementação preparada na branch `codex/rc-operator-planning`. Este relatório separa código/testes de ensaio remoto e da distribuição do app.

## O que mudou

- O journal distingue 0/2 e 1/2 aguardando revisores de 2/2 aguardando autorização final. O finalizador e o observador `workflow_run` registram rejeição, cancelamento e falha usando o run original e reviews oficiais. Não geram avais nem efeitos de publicação.
- Relatórios e recibos aprovados permanecem congelados. Observação atrasada não reabre uma candidata encerrada, desfaz uma Release concluída ou impede recuperação de intenção parcial autorizada. Writers concorrentes são tratados por CAS e rechecagem dos recibos atuais.
- Preview novo identifica a entrega de origem separada do metadado web. Mesmo SHA pode reutilizar o snapshot anterior, sem alterar seus bytes; o relatório informa a candidata atual e a origem do preview.
- Um manifesto validado identifica a entrega e as informações por Android/iOS/web, com digest próprio dentro do relatório aprovado. A Release e o recibo copiam esse material. Android/iOS permanecem sem versão observada, patch ou distribuição no adaptador GitHub-only.
- Coleta de contexto PR roda em paralelo ao build, com leitura e prazo limitado. A revisão não depende desse job. O relatório faz uma consulta oportunista de até três segundos, sem polling; descrição semitécnica literal de seções explícitas ou histórico de commits é escolhido e congelado antes dos avais.
- Slack segue ilustrativo: lê o material congelado e gera mensagem/links e artefato. Nenhum envio. O contrato de resultado IA está preparado, mas Copilot não foi executado; Plane não foi consultado.
- O coletor de evidências usa GET, guarda run/reviews/jobs/logs/hash/stdout/stderr e recusa uma pasta já existente. Coleta completa não transforma automaticamente um teste negativo em PASS.

## Validação e seu alcance

| Verificação | Resultado | Evidência e limite |
|---|---|---|
| Suíte local completa | **351 testes PASS**, 184,469 s | `delivery-suite-final.log`; fixtures e repositórios Git descartáveis, não distribuição real |
| Precisão final do changelog | **28 testes PASS** | `changelog-final-precision-tests.log`; inclui resultado tardio em fração de segundo |
| Estados após último ajuste | **22 testes PASS** | `state-final-tests.log`; inclui concorrência com segundo aval e contexto opcional futuro/inválido |
| YAML dos três workflows alterados/novos | **actionlint 1.7.12 PASS** | `actionlint-final.log`, vazio em sucesso; shellcheck/pyflakes desativados |
| Revisão independente de código | **Sem finding restante** | `security-review-final.json`, hashes do conteúdo revisado e limites explícitos |
| Coleta real da entrega 1.6 | **8/8 logs coletados** | `coleta-v160/collection-summary.json`, run 37863610149; somente leitura |
| Contexto real da RC 1.6 | **5 commits, PRs 17/16, fallback commits** | `context-readonly-real160/`; descrições antigas sem seções semitécnicas, zero consultas IA |
| Manifesto demonstrativo histórico | **Geração offline** | `historical-v1.6-example/`; não modifica o relatório aprovado original |

A suíte completa foi seguida dos checks focados dos últimos ajustes. A prova de CI/integração do PR e qualquer nova avaliação remota devem ser consultadas separadamente: este pacote não afirma que os novos workflows já percorreram rejeição/cancelamento/publicação no GitHub. QA e fonte do Site V5 permanecem nos artefatos privados, fora do repositório público.

## Falhas encontradas e prevenção

| Achado na revisão | Correção | Prevenção |
|---|---|---|
| Resumo opcional recusava commit com mais de 500 caracteres ou histórico acima de 1.000 commits e derrubava report | Limitar a cópia, normalizar controles e guardar quantidade/hash do histórico original; histórico técnico integral mantido | Testes de integração para entrada longa, controles e 1.001 commits; comunicação não derruba os gates |
| Artefato novo podia trazer etiqueta de outra RC | Conferir `delivery_tag` antes da importação com permissões; manter histórico imutável | Negativo para outra etiqueta; separar identidade atual do relatório da origem de snapshot reutilizado |
| Observação concorrente podia mostrar 1/2 após segundo aval | Recalcular recibos oficiais atuais na mutação CAS e usar a contagem final no Markdown | Fixture intercalando observador e segundo writer; não usar snapshot antigo como autorização |
| Precisão de segundos escondia fração de segundo no resultado tardio | Canonicalizar instantes UTC com microssegundos | Resultado posterior à seleção continua tardio, inclusive dentro do mesmo segundo |
| Coletor de PR exigia permissão REST ausente no job/caller | `pull-requests: read` apenas no contexto opcional e capacidade do caller reutilizável | Validar a herança de permissões; build do app permanece somente leitura de contents |

Nenhuma tag ou Release existente foi movida/apagada. Os achados acima foram correções de revisão local; não são cinco falhas remotas de publicação observadas nesta rodada.

## Estratégia de versionamento solicitada

A tag representa a **entrega**, não força Android/iOS/web a terem a mesma versão instalada. O [contrato por plataforma](../../VERSIONAMENTO-ENTREGA-E-PLATAFORMAS.md) registra versão/build, base Shorebird exata, identificação do app/flavor e patch confirmado pelo provedor; web usa build/hash/URL, sem patch Shorebird.

O plano aprovado é imutável; o resultado futuro de cada destino será um recibo separado vinculado ao plano. Número de patch desconhecido permanece desconhecido. Se somente uma plataforma concluir, o changelog precisa indicar resultado parcial. O adaptador mobile e sua recuperação ainda não estão implementados.

## Pendências preservadas antes do Amulets

Conflito real de tag, falha parcial/recovery, concorrência real, preview falho e deriva real de proteções continuam sem comprovação remota. Também falta a variante de main/workflows avançando. Não retirar proteções do projeto de trabalho para simular esses casos.

Samuel deve definir operador do corte, substituto, recuperador e identidades reais de revisores/publicadores. Falta integrar e comprovar Copilot/Plane/Slack conforme orçamento e acesso; configurar secret não ativa o remetente. Lojas, Shorebird e disponibilidade/instalação para testers continuam aceites próprios. Dois accounts de ensaio não comprovam dois aceites humanos independentes.
