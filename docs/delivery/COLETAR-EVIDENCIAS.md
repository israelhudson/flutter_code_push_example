# Coletar os logs sem repetir a operação

O coletor `tools/delivery/collect_evidence.py` consulta somente endpoints GET do laboratório. Não aprova, dispara, cancela ou publica. Salva a execução, reviews, páginas de jobs, logs disponíveis e os erros originais de coleta. Cada resposta tem tamanho, exit code e hash; os logs preservam os bytes, incluindo ANSI, sem executá-los.

```bash
python3 tools/delivery/collect_evidence.py \
  --run-id 37863610149 \
  --output build/evidencias/minha-captura-01
```

Use uma **pasta nova para cada observação**. Uma pasta existente é recusada: capturas intermediárias não substituem as terminais. O diretório `build/` é ignorado pelo Git; exporte somente os arquivos auditados para a pasta de evidências que será versionada. Não adicionar dumps privados de outros projetos a este laboratório público.

O resumo diferencia:

| Campo | Significado |
|---|---|
| `run_conclusion` | Resultado do workflow real; não é alterado pelo coletor |
| `collection_status: complete` | Todas as consultas necessárias disponíveis foram coletadas |
| `collection_status: pending` | Um job ainda não terminou; os logs dele não foram pedidos |
| `collection_status: partial` | Uma consulta falhou ou devolveu JSON inválido; stdout/stderr preservados |
| `not_applicable_skipped` | Job pulado, sem log a buscar |
| `scenario_result: not_evaluated` | A coleta não declara um cenário aprovado |

O CLI sai com código 2 para coleta parcial, 1 para entrada/pasta inválida e 0 para coleta completa ou pendente. Um gate rejeitado pode não iniciar runner: log indisponível é lacuna explícita, mesmo quando a rejeição foi esperada. Metadados/reviews e ausência de efeitos continuam necessários para avaliar o cenário.

Na validação de 08/10/2026, Fortaleza, a execução 37863610149 teve as oito consultas de logs concluídas. Isso confirma a coleta da publicação GitHub 1.6.0; não comprova os cinco testes remotos adversariais que continuam pendentes, nem distribuição mobile.

O futuro orquestrador de negativos deve comparar objetivo, esperado, resultado e efeitos antes de registrar PASS. Não deve esconder falha da publicação com `continue-on-error` nem tratar a existência de um log como prova de sucesso.
