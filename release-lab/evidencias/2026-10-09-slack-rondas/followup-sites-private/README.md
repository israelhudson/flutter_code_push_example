# Publicação privada dos Sites V5 e V5-2

Este complemento preserva os registros finais de publicação dos dois Sites após os ensaios GitHub/Slack. O serviço confirmou `succeeded`, source, versão, arquivo e acesso privado do proprietário. O conteúdo foi validado localmente. No browser, ambos os endereços mostraram a tela de login do ChatGPT; **não foi realizada leitura autenticada do conteúdo hospedado**.

| Site | Source | Deployment | Versão | Serviço |
| --- | --- | --- | ---: | --- |
| [V5](https://amulets-esteira-distribuicao-v5.israeldev.chatgpt.site) | cedeb0bf586d8e225970f6b261aeb8da74e174f7 | appgdep_6ac851c91b048191beb339dbc1603ed9 | 3 | succeeded, atualizado 02:30:49.116769 UTC |
| [V5-2](https://amulets-esteira-distribuicao-v5-2.israeldev.chatgpt.site) | 622332030f7a20c6ae2d58b0bfa2b07bccad17dc | appgdep_6ac851fc21688191925bc0c7d6ecc74c | 1 | succeeded, atualizado 02:31:47.041621 UTC |

[publication-final.json](publication-final.json) conserva os resultados obtidos pelo agente principal: owner-only verificado, role=owner e zero grupos. Este coletor conferiu a consistência dos IDs, sources, versões, estado e contagens antes de apensar os arquivos: [verification.json](verification.json). A publicação não altera Amulets nem distribui app mobile; V5-2 apresenta uma proposta didática com Samuel e Vinícius como aprovadores, separada dos atores históricos Israel/Fabrícia do LAB.

[archive-source-verification.json](archive-source-verification.json) registra **21 arquivos reais por Site**, sem divergências: 20 arquivos de conteúdo comparados byte a byte e um manifesto relocado pelo helper comparado como JSON. As 24 entradas AppleDouble de cada pacote local ficam separadas da contagem real. O hash do tar local **não foi equiparado** ao `content_hash` do arquivo normalizado pelo serviço. Nenhum tar foi incluído neste complemento; os nomes de arquivos de archive permanecem somente como metadados nas fontes.

[AGENT-QA.md](AGENT-QA.md) conserva a validação local e seus limites. A [captura 19](19-v5-2-proposal-final-local.jpg) mostra a interface local final da proposta V5-2, sem comprovar uma sessão autenticada hospedada. A imagem foi inspecionada visualmente antes da preservação.

O [pacote original dos ensaios](https://github.com/israelhudson/flutter_code_push_example/blob/d162f208535d9b75d8172fe0c8dbc8ce5ac6273d/release-lab/evidencias/2026-10-09-slack-rondas/README.md) e o [complemento do PR23](https://github.com/israelhudson/flutter_code_push_example/blob/773fe2de398893bf91ec29fa7fb675d4750093e5/release-lab/evidencias/2026-10-09-slack-rondas/followup-pr23/README.md) permanecem congelados. Este complemento acrescenta evidência em `followup-sites-private/`, sem modificar arquivos anteriores, state ou outbox. [manifest.json](manifest.json) e [SHA256SUMS](SHA256SUMS) registram os bytes preservados.
