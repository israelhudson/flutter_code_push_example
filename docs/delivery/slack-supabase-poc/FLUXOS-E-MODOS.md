# Fluxos de entrega e modos de validação

## Dois caminhos coexistem

- **Entrega ·**: fluxo com aceites técnico e de negócio pelo bot exclusivo no Slack. Os arquivos ainda se chamam `poc-slack-*.yml` para preservar chamadas da API e validações de segurança. Usar `slack-main` em **Use workflow from**.
- **LAB ·**: alternativa com aprovação nos environments do GitHub. Continua disponível e preservada. Não substituímos sua política nem seus gatilhos.

O prefixo do workflow identifica a experiência de entrega, não o ambiente de produção. Os nomes do bot, branches, tags e tabelas internas permanecem compatíveis. O check obrigatório `Slack / Verificar contratos` conserva o identificador exigido pela proteção da branch.

## Formulário Entrega · Preparar candidata

| Campo | Opção | Efeito |
|---|---|---|
| Publicação após os aceites | `none` | Não publica Release GitHub |
| Publicação após os aceites | `github` | Permite criar Release GitHub após os dois aceites e demais controles |
| Validação | `controls_only` (padrão) | Ensaia candidata, cartão e controles, sem build/preview nem patches |
| Validação | `full` | Testa o app e gera preview Web, sem patches |

Para ensaio rápido de aprovação/publicação: `github` + `controls_only`. Para conferir o aplicativo no navegador: `github` + `full`. Para apenas revisar, sem Release final: `none` + qualquer modo. Informar versão sem prefixo e sem RC, por exemplo `1.16.0`, e título do que será conferido.

O formulário traduz `github` para o escopo interno existente `github_test`. Essa mudança de legenda não amplia permissões, não altera candidatas antigas e não transforma testes solo em revisão por duas pessoas. Integrações internas e relatórios congelados mantêm o identificador antigo.

Não há opção de produção mobile nesta lista. Um futuro destino homologação/produção exigirá base Shorebird, plataforma, track, permissões e comprovação de instalação. Nenhum patch é gerado por estas duas opções.

## CLI equivalente para o formulário novo

```bash
gh workflow run poc-slack-prepare.yml \
  --repo israelhudson/flutter_code_push_example --ref slack-main \
  -f scope=github -f validation_mode=controls_only \
  -f version=1.16.0 -f title='Ensaio rápido dos controles'
```

O comando é um exemplo, não foi executado para criar essa versão. Para reapresentar a 1.15.1 existente, usar a correção de metadados documentada em [Release final](RELEASE-FINAL.md), preservando seus aceites.
