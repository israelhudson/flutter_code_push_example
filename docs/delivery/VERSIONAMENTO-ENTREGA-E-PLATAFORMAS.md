# A tag identifica a entrega; cada plataforma registra sua versão

Sua proposta passa a ser a convenção do laboratório: **a tag e a Release do GitHub identificam a entrega e o código aprovado.** Android, iOS e web podem ter versões diferentes. O changelog mostra a relação entre a entrega e cada destino, sem transformar o número da tag em uma versão instalada.

O novo manifesto `version-manifest.json` acompanha o relatório da candidata. Ele tem hash próprio e também faz parte do conteúdo congelado e aprovado. A tabela do changelog é uma apresentação desse manifesto; a automação deve consultar os campos validados, nunca extrair um alvo de um texto livre ou de um resumo feito por IA.

## O que está implementado neste ajuste

1. **Identidade da entrega:** RC, futura tag estável e SHA completo. As tags existentes continuam com o formato `v1.6.0-rc.1` / `v1.6.0`; não é necessário renomeá-las para separar os conceitos.
2. **Metadado compilado web:** versão e build do `pubspec.yaml`, identificados explicitamente como metadados do build. Um valor como `1.1.0+2` não comprova a versão instalada nos celulares.
3. **Android e iOS separados:** bases configuradas, quando existirem, aparecem como alvos ainda não verificados. Neste laboratório, as bases estão ausentes e os campos ficam desconhecidos. Patch fica `null` / “não gerado”; distribuição fica “não realizada”.
4. **Web separado:** SHA do build, hash dos bytes e URL do preview verificado. Patch Shorebird é “não se aplica”. O preview não comprova publicação de um app mobile nem de um site de produção.
5. **Preview novo:** mostra a entrega de origem separadamente do metadado do app. Snapshots já publicados permanecem imutáveis. Se outra RC reutilizar o mesmo SHA, o cabeçalho preserva a candidata de origem e o relatório da nova RC informa a candidata atual.

`tools/delivery/version_manifest.py` só gera e valida registros. Não lê credenciais nem executa upload, release ou patch. A função `patch_identity` valida uma identificação completa para uso futuro; não prova que o patch existe.

## Exemplo da estratégia para o Amulets — ilustrativo

Os números abaixo são exemplos, não resultados do laboratório.

| Registro | Identificação | Resultado que seria documentado |
|---|---|---|
| Entrega | `v2.8.0-rc.2` → `v2.8.0`, mesmo SHA aprovado | Candidata preservada e entrega promovida |
| Android | App `2.4.0`, build `81`; base Shorebird `2.4.0+81` | Patch `3` somente depois de confirmado pelo provedor |
| iOS | App `2.3.2`, build `76`; base Shorebird `2.3.2+76` | Patch `2` somente depois de confirmado pelo provedor |
| Web | Metadado do app + SHA do build + hash dos bytes | URL e publicação web verificadas separadamente |

Essa entrega poderia atualizar o Dart das duas bases mobile e publicar o web. **Não é obrigatório que Android, iOS, web e a tag tenham o mesmo número.** Isso também permite documentar uma correção aplicada a uma versão instalada mais antiga, sem fingir que o usuário recebeu um novo binário de loja.

Um patch será sempre identificado por:

```text
{app_id Shorebird, flavor/ambiente, plataforma, release_version exata, patch_number}
```

O número `3` sozinho é insuficiente. Não presumimos que os números das plataformas estejam sincronizados nem usamos o maior número como versão global. A relação vem do app e da release-base do provedor, além da plataforma e dos artefatos efetivamente confirmados.

## Quando cada informação fica conhecida

| Momento | Registro congelado ou comprovado |
|---|---|
| Preparar RC | Tag da entrega, SHA, título, alvos e bases exatas pretendidas |
| Avaliar RC | Preview e hashes; análise por plataforma; patch ainda não gerado |
| Duas aprovações | Os revisores aprovam essa intenção e essas evidências. O comando final permanece separado |
| Comando final | Executa apenas os destinos autorizados, usando os alvos explícitos aprovados |
| Resultado do destino | Um recibo separado registra versão/build, número real do patch, track, artefato/hash e evidência do provedor |
| Changelog da Release | Apresenta o plano aprovado e os resultados confirmados por destino, com links para ambos |

**Não prever o próximo número do patch.** Outra operação pode consumir esse número. Na candidata, escrevemos “a gerar” quando o futuro adaptador mobile estiver habilitado; o número definitivo vem da resposta consultada e verificada após a operação. No adaptador atual, escrevemos “não gerado”, porque nenhuma distribuição mobile faz parte do modo `github_release_only`.

O plano aprovado não será reescrito para incluir o resultado. O recibo de publicação será outro documento, vinculado por tag, SHA e hash do plano. O changelog pode mostrar os dois sem apagar o material que os revisores viram. Resumo tardio de IA também não modifica o plano congelado.

## Se uma plataforma falhar

Não declarar a entrega inteira distribuída porque Android terminou. Android, iOS e web têm estados e recibos próprios. Exemplo: Android confirmado, iOS falhou, web não iniciado. A Release deve mostrar esses resultados sem mover tags, ocultar falhas ou repetir uma operação já confirmada.

Essa recuperação mobile ainda precisa de adaptador e validação real. Antes de repetir uma tentativa, consultar o provedor e os recibos para distinguir falha de uma resposta perdida. O código atual não implementa recuperação Shorebird nem autoriza uma publicação de loja.

## RC rejeitada e correção

```text
main → branch release/2.8.0
             ├─ tag v2.8.0-rc.1 (SHA A, rejeitada, preservada)
             └─ PR de correção → merge na mesma release/2.8.0
                                 └─ tag v2.8.0-rc.2 (SHA B, novos avais)
                                                         └─ tag v2.8.0 (SHA B)
```

A branch representa a linha da entrega. A tag identifica cada corte imutável. A tag RC2 nasce depois do merge da correção, quando o workflow prepara o corte; não é um artefato que o PR deveria criar antecipadamente. Rejeitar RC1 não exige apagar sua branch/tag nem reutilizar seus avais. As versões de destino e bases Shorebird devem ser revistas no novo plano quando a correção afetar compatibilidade.

## O que falta antes de distribuir pelo Shorebird

- Confirmar app_id/flavor, releases-base reais, plataformas, toolchain e credenciais autorizadas para cada destino.
- Fazer a pré-análise real do patch contra a base exata, sem `latest` e sem ignorar diferenças nativas/assets.
- Capturar e consultar resultados reais do provedor; registrar número do patch, track e hashes em recibos por destino.
- Separar upload do binário, disponibilização para testers, instalação, patch recebido e publicação final. Cada uma exige sua evidência.
- Testar resultado parcial e recuperação por plataforma. No iOS, a comprovação de um patch precisa de dispositivo físico.

No Amulets, Samuel precisa definir quem pode preparar a RC e operar cada destino. As duas aprovações e o comando final continuam valendo; escolher nomes de tags ou números de versões não substitui autorização.

## Fonte verificada e decisões do laboratório

A referência local [004](../../referencias/docs/004-shorebird-patch-e-elegibilidade.md) foi lida antes da implementação. A documentação oficial foi reconferida em 08/10/2026:

- A [FAQ Shorebird](https://docs.shorebird.dev/code-push/faq/) distingue versão da release de número do patch, informa que um patch não altera a versão da release, permite decisões independentes por plataforma e explica que web não usa o Code Push mobile. Também distingue preparação pelo Shorebird da submissão às lojas e exige dispositivo físico para patches iOS.
- [Create a Patch](https://docs.shorebird.dev/code-push/patch/) documenta a seleção de release-base, a validação sem upload e a existência de tracks. Qualquer implementação da CLI deve conferir novamente a ajuda da versão instalada antes de executar comandos.
- [Create a Release](https://docs.shorebird.dev/code-push/release/) confirma que preparar a base Shorebird e enviar o artefato à loja são passos distintos.

A tag da entrega, o formato do manifesto, a tabela por plataforma e o recibo separado são **decisões propostas para este laboratório e para o Amulets**. Elas não são imposições da documentação Shorebird. Não foi executado nenhum comando Shorebird neste ajuste.
