# Operar no GitHub

Esta versão é um laboratório de um operador. O GitHub autentica Israel; Ian,
Samuel e Vinícius são papéis **simulados por Israel**. Dois papéis aprovados não
representam duas pessoas reais. O fluxo nativo de reviews reais continua separado.

## Preview que abre no navegador

Abra **Actions → Web - Preview Pages por snapshot → Run workflow**, escolha
`main` e informe o SHA completo do commit. Push em `main` também publica o preview.

- [Último preview](https://israelhudson.github.io/flutter_code_push_example/)
- Cada commit tem seu próprio endereço: `/snapshots/<SHA40>/`.
- A página mostra versão, SHA e identidade do build. Os snapshots anteriores
  permanecem na branch `codex/pages-previews`.
- O build tem a base URL do Pages, por isso seus bytes/hash diferem do ZIP do CI.
  A fonte e o SDK ficam fixados; não se afirma equivalência de bytes com o ZIP.
- O site é público. Somente o build web e sua identidade vão para o Pages.
  Aprovações, bancos, recibos e credenciais ficam fora do site.
- O preview web não valida atualização Shorebird, Android ou iOS.

## Controles de entrega

Abra **Actions → Delivery - controle persistente do laboratorio → Run workflow**.
Use `main`. O resumo de cada execução mostra o estado, a candidata e o hash que
precisa ser copiado para a próxima ação.

| Ordem | operation | Preencher | Resultado |
|---|---|---|---|
| 1, apenas uma vez | `initialize` | `source_sha` da base escolhida | Produção e release-bases simuladas |
| 2 | `technical-review` | `source_sha`, role `ian` | Revisão técnica simulada; 0 aprovações |
| 3 | `prepare` | mesmo SHA, `delivery_id` ex. `entrega-0042`, `rc=1` | Builds web/Android/iOS; RC imutável em 0/2 |
| 4 | `approve` | candidata, hash, role `samuel` | 1/2, sem publicação |
| 5 | `approve` | candidata, mesmo hash, role `vinicius` | 2/2 autorizada, sem publicação |
| 6 | `publish` | candidata e mesmo hash | Recibos **fictícios**; produção simulada só avança se todos concluírem |
| Consulta | `status` | candidata opcional | Estado recuperado em outro runner |

`prepare` compila Android AAB de laboratório e iOS XCArchive sem assinatura.
Os artifacts têm SHA e hashes próprios; iOS não gera IPA instalável. Nenhum build
é enviado ao Shorebird, Play Console, App Store Connect ou TestFlight.

Para corrigir, revise o SHA novo e prepare a próxima `rc` da mesma entrega.
As aprovações da RC anterior não aprovam a nova. Outra entrega entra na fila.
`next` ativa a próxima quando não houver candidata ativa; se a base mudou,
ela fica bloqueada e exige nova preparação.

## Falha e recuperação

No `publish`, `fail_destination=ios-after` grava um recibo fictício e simula
timeout. Depois execute `reconcile`: ele consulta o journal preservado, confirma
o iOS já processado e mantém os demais destinos pendentes. Um novo `publish`
retoma somente os destinos restantes. Não usar outro banco/provedor para fingir
que os efeitos anteriores desapareceram.

`abandon` encerra apenas uma tentativa comprovadamente sem efeitos no provedor
falso síncrono. Qualquer recibo impede esse encerramento. A próxima tentativa
precisa de outra RC e novas aprovações.

## Persistência e avisos

`codex/delivery-state` guarda snapshots atômicos de estado, journal do provedor,
outbox do Slack e ZIPs congelados. Um commit preserva todos juntos; conflitos
não são resolvidos reaplicando o comando silenciosamente. O workflow inteiro
usa uma única fila de concorrência. Os commits avançam sem force push.

Os runners Linux usam `/tmp/flutter-code-push-lab/repository` e
`/tmp/flutter-code-push-lab/state`. Os caminhos fazem parte da identidade imutável;
a importação não reescreve manifests ou hashes de aprovação.

O bot `Flutter Deploy LAB` usa `chat:write` e `groups:read`. Sua credencial fica
no secret `SLACK_BOT_TOKEN` deste repositório, nunca em código ou artifact. Antes
do envio, o bot verifica que `app-deploy-test-isr` é privado e contém somente
Israel e ele próprio. Os avisos trazem um link para o run; aprovações continuam
nos controles GitHub.

A outbox `unknown` é preservada remotamente **antes** de enviar ao Slack. Se a
resposta se perder, não há reenvio automático: é necessário conferir a mensagem
e reconciliar a incerteza. Aviso Slack não altera o estado de aprovação.

Se a confirmação do commit de estado se perder, o artifact do run conserva
`remote-commit-checkpoint.json`. Conferir o mesmo `proposed_head` com
`remote_state.py confirm --checkpoint <arquivo>` antes de qualquer novo efeito.
Não reinicializar uma branch/banco ausente como recuperação de falha.
