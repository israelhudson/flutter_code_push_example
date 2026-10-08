# Qualidade e escopo da apresentação V2

Entrega: `output/workflow-lab-validado-v2.pptx`, 13 slides em português, com
notas detalhadas e fontes por slide. A V2 preserva os decks anteriores.

As quatro tabelas e os dois diagramas são objetos nativos editáveis. Texto
do slide também permanece editável. Os cinco prints são imagens originais
embutidas, com recortes nativos que destacam o assunto e preservam os bytes.

## Verificações

- Pacote, geometria, heading fit e política de fonte: PASS, sem achados.
- Reimportação do PPTX final pelo Artifact Tool: PASS, 13 slides.
- Os 13 slides finais foram renderizados e inspecionados individualmente em
  tamanho completo. O contact sheet está em `renders-final/montage.webp`.
- Direção das setas, proporção e foco dos prints foram corrigidos durante a
  revisão. Versões intermediárias e logs permanecem em `build`.
- Tipos dos cinco arquivos de mídia correspondem aos bytes JPEG/PNG.
- A cópia final tem os mesmos bytes do export validado. Hash e fontes constam
  em `QUALITY.json`.
- O arquivo não foi aberto no aplicativo Microsoft PowerPoint. A revisão usa
  o Artifact Tool, seus verificadores e os renders do arquivo reimportado.

## Limites que aparecem na apresentação

A Release GitHub v1.5.0 é real, da RC2 corrigida. RC1/RC2 foram preservadas.
Os nove cenários offline PASS ficam separados das 15 de 20 verificações GitHub
PASS. A apresentação não infere os cinco subcasos pendentes no serviço real.
Os prints e as notas deixam explícita a automação autorizada por contas do LAB,
sem afirmar revisão humana independente. Nenhum aplicativo ou patch foi
distribuído. Os bloqueios vermelhos esperados ficam separados dos erros reais
corrigidos e dos limites de coleta apenas tratados.

## Reprodução local

As fontes estão em `build/create-deck.mjs` e `build/render-final.mjs`.
Use o Node e os pacotes do runtime oficial carregado para esta sessão, recriando
o symlink `build/node_modules` para os pacotes e definindo `RUNTIME_NODE_MODULES`.
Antes de uma nova exportação, escolha nomes novos de draft, final e receipt,
pois o finalizer não sobrescreve a saída existente.

Nenhum código do app, documento fora desta subpasta ou objeto GitHub foi
alterado por este agente de apresentação.
