# [002] Firebase Remote Config (Package of the Week)

| Campo | Valor |
|-------|-------|
| **Fonte** | https://youtu.be/34ExOdNEMXI |
| **Autor/Canal** | Flutter (canal oficial) |
| **Publicado em** | 2022-12-29 |
| **Duração** | 2min22s |
| **Adicionado em** | 2026-08-18 |
| **Tema** | Remote Config — visão canônica do produto |
| **Idade** | 🟢 atual — conceitual, sem superfície de API que envelheça |
| **Transcrição** | [002-transcricao-bruta.md](002-transcricao-bruta.md) (ASR `en-orig`) |

## Por que está aqui

É a **fonte canônica** do tema da [001](001-firebase-remote-config-flutter.md), vinda
do canal oficial do Flutter. Dois minutos, sem uma linha de código — serve para
confirmar o *modelo mental* e o vocabulário oficial, não para implementar.

Vale como contraponto à 001 justamente por não mostrar código: onde a 001 é
implementação sem visão de produto, esta é visão de produto sem implementação. As
duas juntas fecham o assunto.

## Fonte verificada

### O problema que Remote Config resolve

O vídeo abre pelo problema, não pela feature [00:01]:

> "Mesmo depois de testar a feature, como ter certeza de que funciona antes de chegar
> às mãos dos usuários — e como ter certeza de que os usuários vão gostar dela?"

A resposta oficial: habilitar a feature **para um segmento pequeno** de usuários.
Note que o enquadramento oficial não é "ligar/desligar" — é **segmentação**.

### Definição

> "Remote Config é um key-value store que vive na nuvem — e porque vive na nuvem,
> permite mudar e customizar seu app sem fazer o usuário baixar uma atualização." [00:25]

### Os dois casos de uso apresentados

1. **Rollout gradual** — lançar primeiro para um número pequeno dos *usuários mais
   fiéis*, e só depois abrir para o resto [00:25].
2. **Teste A/B** — o exemplo é literalmente o mesmo da [001] (botão vermelho converte
   mais?). Cria-se um par chave-valor booleano, define-se `true` para uma
   porcentagem de usuários, e o app mostra o botão correspondente ao segmento [00:47].

### Condições de segmentação nativas

O vídeo lista as condições prontas [01:09–01:31]:

- idioma do dispositivo (ex.: só quem usa inglês)
- plataforma (ex.: só iOS)
- versão do app (ex.: só quem está na mais recente)
- data/hora da requisição
- **porcentagem aleatória** de usuários
- via **Google Analytics**: qualquer traço já rastreado — o exemplo dado é
  "usuários que fizeram compras no passado"

### Tipos de valor

`string`, `boolean`, `number` e **JSON blob** [01:31].

> 🔎 O JSON blob não aparece na [001] — o `getValueOrDefault` de lá cobre só os quatro
> tipos primitivos. É a lacuna mais concreta daquela implementação.

### Cache e defaults

> "Seus usuários verão o novo valor **no próximo fetch**. E você pode fazer fetch com a
> frequência que quiser." [01:53]

E a recomendação, que é o mesmo ponto da [001] dito por outro ângulo:

> "Remote Config faz cache dos valores mais recentes e suporta valores default — e é
> importante fornecer um valor default **para que seu app ainda funcione offline**."

Onde a [001] justifica o default pelo zero-value (não existe null), a oficial justifica
pelo **offline**. São dois motivos independentes para a mesma prática.

## Complemento

Nada a acrescentar — o vídeo é curto, oficial e conceitual. Para implementação, ver
[001 › Complemento](001-firebase-remote-config-flutter.md#complemento) e a
[doc oficial](https://firebase.google.com/docs/remote-config/flutter/get-started).

## Aplicação neste projeto

Confirma que o desenho da [001] está alinhado com a intenção oficial do produto. Duas
coisas para incorporar se este projeto implementar Remote Config:

- **Suporte a JSON blob** no `getValueOrDefault` — permite entregar objeto de
  configuração inteiro numa chave só, em vez de N chaves primitivas.
- **Condição por versão do app** — relevante para quem usa Shorebird: o patch muda o
  código Dart mas **não muda a versão do app**. Uma condição de Remote Config baseada
  em versão não distingue quem já recebeu o patch de quem não recebeu. Ponto de
  atenção real na combinação dos dois, anotado nas pendências.

## Pendências

- [ ] Confirmar experimentalmente se a versão reportada ao Firebase muda (ou não) após
      um patch do Shorebird — determina se dá para segmentar por "recebeu o patch"
