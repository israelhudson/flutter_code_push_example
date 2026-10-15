# Validação do banco — 14/10/2026 (Fortaleza)

Código testado: merge `fb4891d715f95f2d40ed3ce1b5979c9aab142b4f` do PR #53.
Projeto exclusivo: `xtvueqciogzkyjkkqxcx`. Amulets não foi modificada.

## Resultado

- Backup lógico privado das oito tabelas: 67 registros, definições das sete funções, colunas, constraints, índices, grants, RLS, policies e sequência de eventos.
- Restauração dos registros em PostgreSQL local PGlite com as migrations versionadas: passou. Nenhuma divergência nas sete funções. Não é um teste de restauração completa do cluster Supabase/Auth.
- Aplicada remotamente a migration aditiva `delivery_two_table_control`, correspondente a `20261015003023_delivery_two_table_control.sql`. Oito tabelas antigas preservadas; duas novas adicionadas.
- Teste remoto com `service_role`, em uma transação com `ROLLBACK`: passou. Ao terminar, `delivery_control=0` e `delivery_outbox=0`.
- Comparação antes/depois: todos os registros e metadados legados capturados permaneceram iguais. Os arquivos têm hashes diferentes porque a captura inclui timestamp.
- 52 testes Deno, lint, formatação e type check: passaram. 31 contratos Python: passaram.
- Auditor de segurança: apenas INFO de RLS sem policies nas dez tabelas. É intencional neste desenho server-only: `anon`/`authenticated` não têm acesso; acesso de servidor via `service_role`. Não criar policy pública para eliminar esse aviso. Referência: https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy

## Cenários comprovados no PostgreSQL remoto

1. RLS habilitado e ausência de permissões públicas verificadas no catálogo.
2. Pessoa errada não registra aceite técnico.
3. Um aceite mantém estado pendente e bloqueia publicação.
4. Aceite repetido não cria nova revisão.
5. Rejeição encerra RC1; RC2 começa sem aceites.
6. Dois aceites fecham avaliação, mas histórico pendente bloqueia publicação.
7. Publicação pertence a uma execução; outra execução é recusada.
8. Conclusão repetida pela mesma execução é idempotente.
9. Lease externo vencido fica incerto, sem reenvio automático.
10. Compactação não remove efeitos pendentes.

Os recibos usados nesses testes são fictícios e existem somente dentro da transação desfeita. Nenhuma tag, Release, DM, mensagem Slack, preview ou patch foi criado. Sequências PostgreSQL podem avançar mesmo com rollback; lacunas no ID da outbox são normais.

## Estado de ativação e pendências

A flag GitHub `DELIVERY_V2_ENABLED` continua ausente. Nenhuma Edge Function foi publicada nem flag remota alterada nesta validação. O novo fluxo permanece sem ativação.

Ainda faltam: concorrência real entre duas conexões; implantação das funções com flag desligada; proteção da branch de histórico; worker na main; ensaio ponta a ponta autorizado de DMs, retomada do worker e recibos reais. Os testes atuais não comprovam essas etapas. As tabelas antigas não devem ser removidas ainda.

## Reproduzir

Backup privado, com `umask 077`:

```sh
supabase db query --linked --project-ref xtvueqciogzkyjkkqxcx --output json --file tools/delivery/backup_legacy_database.sql > /caminho/privado/backup.json
deno run -A tools/delivery/verify_database_backup.ts /caminho/privado/backup.json /caminho/privado/resultado.json
supabase db query --linked --project-ref xtvueqciogzkyjkkqxcx --output json --file tests/database/delivery_rollback.sql
```

O SQL remoto exige controles v2 vazios e usa rollback. Não executar em Amulets. Backup bruto guardado fora do repositório; aqui há somente resultados e logs sem linhas privadas.
