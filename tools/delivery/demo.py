"""Test-only fixture report. Never sends fake reviews or publishes anything."""
from policy import REQUIRED, decide


def review(user, n):
    return {'id': n, 'user': {'login': user}, 'state': 'APPROVED', 'commit_id': 'fixture-only'}


if __name__ == '__main__':
    print('# Política 2 de 2 — demonstração com dados sintéticos\n')
    print('**TESTES, NÃO APROVAÇÕES REAIS. Nenhuma release ou patch é publicado.**\n')
    print('| Cenário simulado | Resultado da mesma política usada no gate |\n|---|---|')
    for count in range(3):
        result = decide([review(u, i) for i, u in enumerate(REQUIRED[:count])], 'fixture-only', 'fixture-author')
        print(f'| {count}/2 | {"LIBERADO para laboratório" if result["allowed"] else "BLOQUEADO"} |')
