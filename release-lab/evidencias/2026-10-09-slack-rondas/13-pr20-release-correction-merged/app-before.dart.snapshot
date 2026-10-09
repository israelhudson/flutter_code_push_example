import 'package:flutter/material.dart';

import '../update/update_service.dart';
import '../update/widgets/update_available_sheet.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key, this.service, required this.onToggleTheme});

  final VoidCallback onToggleTheme;

  /// Injetável para teste; em produção o serviço padrão dá conta.
  final UpdateService? service;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  late final UpdateService _service = widget.service ?? UpdateService();

  String _status = 'Carregando...';
  int? _currentPatchNumber;
  bool _isBusy = false;

  @override
  void initState() {
    super.initState();
    _loadCurrentPatch();
  }

  Future<void> _loadCurrentPatch() async {
    if (!_service.isAvailable) {
      setState(() {
        _status =
            'Shorebird indisponível neste build — instale um build gerado '
            'por "shorebird release".';
      });
      return;
    }

    final number = await _service.currentPatchNumber();
    if (!mounted) return;

    setState(() {
      _currentPatchNumber = number;
      _status = number == null
          ? 'Nenhum patch aplicado ainda (release base).'
          : 'Rodando o patch $number.';
    });
  }

  /// Mesma verificação que o [UpdatePrompt] faz sozinho ao abrir o app e ao
  /// voltar do background — aqui só é disparada na mão.
  Future<void> _checkNow() async {
    setState(() => _isBusy = true);

    final result = await _service.checkAndDownload();
    if (!mounted) return;

    setState(() {
      _isBusy = false;
      _status = switch (result) {
        UpdateUpToDate() => 'Nenhuma atualização disponível.',
        UpdateReady() => 'Atualização baixada, aguardando reinício.',
        UpdateUnavailable() =>
          'Serviço de atualização indisponível no momento.',
        UpdateFailed(:final message) => 'Erro ao atualizar: $message',
      };
    });

    if (result is UpdateReady) {
      await showUpdateAvailableSheet(context, patchNumber: result.patchNumber);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Flutter Code Push Example'),
        actions: [
          IconButton(
            tooltip: isDark ? 'Ativar tema claro' : 'Ativar tema escuro',
            onPressed: widget.onToggleTheme,
            icon: Icon(isDark ? Icons.light_mode : Icons.dark_mode),
          ),
        ],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'Laboratório de atualizações',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 24),
              Text(
                _currentPatchNumber == null
                    ? 'Patch: nenhum (release base)'
                    : 'Patch: $_currentPatchNumber',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Text(_status, textAlign: TextAlign.center),
              const SizedBox(height: 24),
              if (_isBusy)
                const CircularProgressIndicator()
              else
                ElevatedButton(
                  onPressed: _checkNow,
                  child: const Text('Verificar atualização agora'),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
