# Entrega: tema escuro manual

Branch: `codex/manual-dark-theme`, criada a partir de `origin/main` no commit
`f9898028405e577ee8998b1c5f0274870089ffac`.

## Comportamento

- O botão de lua/sol no topo alterna entre claro e escuro.
- O tema escuro usa fundo azul petróleo; textos e aviso de atualização acompanham o tema.
- O app sempre inicia claro, inclusive quando o sistema está em modo escuro.
- A preferência dura apenas nesta execução, em memória. Fechar e abrir novamente
  restaura o claro; voltar do background não equivale a reiniciar o processo.
- Alternar o tema preserva o estado da tela e do serviço de atualização.

A implementação usa apenas Dart/Flutter. Não altera código nativo, dependências,
assets, versão do pubspec, workflows nem armazenamento. A compatibilidade de um
patch Shorebird ainda depende da comparação com a release-base real.

## Verificações locais

O arquivo [validation.json](validation.json) guarda os comandos, exit codes e
duração. Os logs originais de stdout e stderr são preservados separadamente para
cada comando: format, pub-get, analyze, flutter-test, delivery-test e build-web.
Todos terminaram com exit code 0: analyze sem problemas, cinco testes Flutter,
273 testes da esteira e build web release concluído.
O SDK conferido é Flutter 3.44.1, revisão
`924134a44c189315be2148659913dda1671cbe99`, conforme as entradas da esteira.

Os testes de widgets verificam a mensagem inicial, independência do sistema,
alternância nos dois sentidos, reset numa nova instância do app, preservação do
estado da tela, cores do aviso e interação em largura de 375 pixels.

No navegador local, o build release abriu claro, alternou para escuro e voltou
ao claro após recarregar. A árvore acessível foi registrada em
[browser-qa.json](browser-qa.json), junto destes prints:

- [Tema claro](01-tema-claro.jpg)
- [Tema escuro após concluir a animação](02-tema-escuro.jpg)
- [Novo início em tema claro](03-reinicio-tema-claro.jpg)

Essas evidências são locais. Não equivalem aos checks do futuro PR no GitHub,
a distribuição mobile ou a uma candidata aprovada.

## Próximo passo manual

1. Abrir PR de `codex/manual-dark-theme` para `main`.
2. Usar o título sugerido: **feat: adicionar tema escuro manual**.
3. Aguardar o check **Flutter analyze e test** e a revisão exigida pelo GitHub.
4. Fazer o merge somente depois desses requisitos; preparar RC1 em outro passo.

Não foi criado PR, tag RC, Release ou publicação nesta etapa. O usuário pediu
para conduzir manualmente o PR. A versão da próxima entrega será escolhida
quando formos preparar a candidata.

## Lição registrada

Um tema manual usa `ThemeMode` explícito e estado da raiz do aplicativo; não
precisa seguir a aparência do sistema nem persistir a escolha. Componentes
secundários, como o aviso de atualização, também precisam consumir as cores do
tema para manter legibilidade. Para testar reinício, desmontar e montar uma nova
instância do app: reconstruir a mesma árvore pode conservar seu estado.
