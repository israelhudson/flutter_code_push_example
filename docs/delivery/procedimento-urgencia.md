# Corrigir uma urgência no laboratório

**Primeira ação: consultar a candidata ativa e os destinos já publicados.**
Israel opera todas as etapas abaixo, representando Ian, Samuel e Vinícius
explicitamente. O ensaio local não envia reviews, patches ou mensagens reais.

```bash
python3 tools/delivery/lab.py status
python3 tools/delivery/lab.py events --candidate CANDIDATA_ANTERIOR
```

## 1 Resolver a publicação anterior

Se a anterior está apenas em aprovação, a preparação urgente pode bloqueá-la.
Se houve tentativa de publicar, primeiro reconciliar todos os resultados:

```bash
python3 tools/delivery/lab.py reconcile --candidate CANDIDATA_ANTERIOR --repo REPOSITORIO_LOCAL
```

Registrar por destino o que está confirmado, pendente, falhou ou permanece
desconhecido. Resultado desconhecido bloqueia a troca de candidata. Se Android,
iOS e web estão em versões diferentes, não escolher uma “última produção” única
por conveniência. Recuperar a operação anterior e confirmar a base por destino
antes de autorizar outra entrega. Se a recuperação exigir mudar código ou bases,
documentar outro plano e obter novos avais.

**Evidência:** estado do banco, recibos do provedor falso e eventos de reconciliação.
Uma publicação parcial nunca recebe estado de sucesso total.

## 2 Preparar o conserto a partir da produção confirmada

1. Identificar o SHA-base e as releases exatas confirmadas por destino.
2. Em repositório isolado do ensaio, criar uma branch de correção nessa base.
3. Aplicar somente o conserto. Se vier da main, avaliar dependências do cherry-pick;
   resolver conflitos e testar antes de disponibilizar a candidata.
4. Produzir novo preview web, changelog e manifesto; pré-analisar cada base exata.

Exemplo: produção B, main C/D pendente. A urgente deve ser B mais o conserto F′;
C e D ficam fora até uma decisão explícita de incluí-los numa nova candidata.
Tags anteriores não se movem.

**Evidência:** diff desde produção, árvore completa de F′ e testes que confirmam
a ausência de C/D. Nenhum patch é gerado ao preparar.

## 3 Bloquear a anterior e avaliar a urgente

```bash
python3 tools/delivery/lab.py technical-review --sha SHA_URGENTE --role ian
python3 tools/delivery/lab.py prepare --manifest urgent.json --request-id preparar-urgente-0043 --urgent
```

A operação urgente invalida a candidata anterior, seus avais e comandos antigos.
A nova começa em 0/2. Copiar o hash do novo manifesto e representar as aprovações:

```bash
python3 tools/delivery/lab.py approve --candidate RC_URGENTE --role samuel --hash HASH_URGENTE --request-id samuel-urgente-0043
python3 tools/delivery/lab.py approve --candidate RC_URGENTE --role vinicius --hash HASH_URGENTE --request-id vinicius-urgente-0043
```

**Evidência:** evento de bloqueio da anterior, revisão técnica, duas aprovações
simuladas do mesmo hash e identidade real Israel preservada.

## 4 Autorizar e conferir a publicação urgente

```bash
python3 tools/delivery/lab.py publish --candidate RC_URGENTE --hash HASH_URGENTE --command-id publicar-urgente-0043 --repo REPOSITORIO_LOCAL
python3 tools/delivery/lab.py status --candidate RC_URGENTE
```

Usar o SHA aprovado, com checkout isolado. O avanço posterior da main ou da branch
release não troca o snapshot. Em falha parcial, retornar à reconciliação e retomar
somente os destinos pendentes. Concluir após confirmar todos os destinos requeridos.
Registrar tags/resultados no mesmo SHA sem publicar de novo por falha de registro.

**Evidência:** recibo individual por destino, SHA, hashes e identificadores
fictícios retornados pelo provedor; estado final completo somente após todos.

## 5 Incorporar o conserto e retomar o lote

1. Incorporar o conserto na linha de desenvolvimento do ensaio.
2. Resolver conflitos e testar antes de preparar outro lote.
3. Preparar uma nova RC considerando a produção após a urgente.
4. Reconstruir/verificar preview e changelog; registrar novas aprovações desde 0/2.
5. Dar um novo comando final para essa nova RC.

Não reativar a RC antiga ou aproveitar seus avais. O snapshot e a base de produção
mudaram. Uma candidata da fila preparada na produção anterior pode estar obsoleta.

**Aceite do ensaio:** a antiga nunca é publicada depois do bloqueio; urgente sai
de B mais o conserto; C/D não vazam; falhas parciais não repetem sucessos; lote
retomado tem nova RC/hash/avais e publica seu próprio SHA aprovado.

Na operação real, usar os mesmos controles com identidades distintas, acesso
verificado e recibos do provedor real. Este procedimento local não comprova essa
segregação nem confirma disponibilidade de patches em dispositivos.
