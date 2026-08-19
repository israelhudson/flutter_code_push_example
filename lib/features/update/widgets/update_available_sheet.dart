import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// Sobe o aviso de atualização ocupando 40% da altura da tela.
///
/// É dispensável de propósito: o patch entra sozinho no próximo cold start, e
/// prender o usuário aqui não deixaria isso mais rápido.
Future<void> showUpdateAvailableSheet(
  BuildContext context, {
  int? patchNumber,
}) {
  return showModalBottomSheet<void>(
    context: context,
    // Sem isso o sheet fica preso na altura máxima padrão e não chega aos 40%.
    isScrollControlled: true,
    backgroundColor: AppColors.porcelain,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (_) => FractionallySizedBox(
      heightFactor: 0.4,
      child: _UpdateAvailableSheet(patchNumber: patchNumber),
    ),
  );
}

class _UpdateAvailableSheet extends StatelessWidget {
  const _UpdateAvailableSheet({this.patchNumber});

  final int? patchNumber;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
      child: Column(
        children: [
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: AppColors.champagne,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(height: 24),
          const Icon(
            Icons.system_update_alt,
            size: 36,
            color: AppColors.burgundy,
          ),
          const SizedBox(height: 12),
          Text(
            'Nova versão disponível',
            style: textTheme.headlineMedium?.copyWith(fontSize: 22),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 12),
          Expanded(
            child: SingleChildScrollView(
              child: Text(
                patchNumber == null
                    ? 'A atualização já foi baixada. Feche o aplicativo e abra '
                          'novamente para começar a usar a nova versão.'
                    : 'A atualização (patch $patchNumber) já foi baixada. '
                          'Feche o aplicativo e abra novamente para começar a '
                          'usar a nova versão.',
                style: textTheme.bodyMedium,
                textAlign: TextAlign.center,
              ),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Entendi'),
            ),
          ),
        ],
      ),
    );
  }
}
