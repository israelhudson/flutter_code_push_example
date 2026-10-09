# Entrega com revisão, Slack e patch Android

## O caminho principal

1. Faça a alteração em uma branch de trabalho e abra PR para `main`.
2. Após testes e revisão, integre o PR. Em Actions, execute **LAB · Criar candidata**, com versão da entrega e título curto.
3. Abra o preview e leia o changelog. Aprovador 1 **e** Aprovador 2 decidem pela própria conta, em ambientes exclusivos.
4. Com 2/2, um dos dois confirma **PUBLICAR**. Isso cria a tag estável e a Release no GitHub no mesmo código aprovado.
5. Para o ensaio Android autorizado, execute o patch local na base exata e no SHA aprovado. Registre o recibo do provedor; só então informe o número no changelog. Instalação e reinício no dispositivo são provas separadas.
6. Se houve correção na branch de release, abra o PR de retorno para `main`; execute os testes e revise conflitos antes do merge.

Slack comunica. O botão de revisão abre o GitHub; não aprova nem publica pelo Slack. Preparar contexto e enviar avisos são etapas opcionais, fora do caminho de autorização.

## Uma candidata recusada

A tag RC1 permanece. Corrija em uma branch a partir de `release/<versão>` e abra PR para essa mesma branch de release. Após o merge, execute **LAB · Criar candidata** com a mesma versão: a próxima tag será RC2 e começará sem os avais da RC1. Repita para RC3/RC4 se necessário. A branch não muda a cada tentativa; as tags distinguem os cortes.

Depois da publicação/validação, o PR de retorno leva as correções à `main`. Conflitos são resolvidos em uma branch de integração, com testes e revisão. As tags publicadas permanecem no código aprovado; resolver o retorno não repete a publicação.

## Botões e nomes

- **LAB · Criar candidata:** corta uma RC nova. PR/merge sozinho não faz o corte.
- **LAB · Validar e publicar entrega:** testa, disponibiliza preview, exige dois avais e o comando final.
- **LAB · Recuperar publicação:** reconcilia uma publicação parcial com nova autorização final.
- **LAB · Conferir resultado:** registra o encerramento sem publicar.
- **LAB · Avisos no Slack:** envia a fila de eventos com deduplicação.

No desktop, o GitHub mostra **Approve and deploy**; no app, o print fornecido mostra **APROVAR**. Nos dois gates de revisão, isso libera apenas o registro do aval. A publicação ocorre no último gate separado.

## Leitura do changelog

Os novos cortes usam descrição breve, até quatro tópicos e links. Slack usa divisórias e três botões: **Abrir preview**, **Changelog** e **Revisar no GitHub**. As evidências técnicas ficam nos detalhes da Release. Mensagens e intenções antigas mantêm o formato original para preservar hashes e deduplicação.

A versão da tag identifica a entrega. Android, iOS e web têm identidades próprias. Neste ensaio, Android mira Shorebird `1.1.0+2`; o número do patch só existe depois da confirmação do provedor. Web tem build e preview do SHA da candidata; não usa patch Shorebird. iOS não tem base/dispositivo confirmado.

## Prevenção já comprovada

O primeiro dry-run detectou alteração na fonte Material Icons causada por novos ícones. A correção usa texto no botão de tema e preserva os assets da base. O segundo dry-run passou, sem liberar diferenças nativas ou de assets. Testar Dart não basta para provar elegibilidade de patch.

O build web continua isolado dos runners que gravam no GitHub. A sessão Shorebird local não é um segredo configurado no GitHub Actions: este ensaio não deve ser apresentado como distribuição mobile automática no CI.
