import 'package:flutter/material.dart';

import 'update_service.dart';
import 'widgets/update_available_sheet.dart';

/// Envolve a árvore do app e avisa quando existe um patch pronto para uso.
///
/// Verifica ao abrir e sempre que o app volta do background. É o retorno do
/// background que faz o aviso chegar com o app já aberto, e que traz o aviso
/// de volta depois de o usuário dispensá-lo.
class UpdatePrompt extends StatefulWidget {
  const UpdatePrompt({required this.child, this.service, super.key});

  final Widget child;

  /// Injetável para teste; em produção o serviço padrão dá conta.
  final UpdateService? service;

  @override
  State<UpdatePrompt> createState() => _UpdatePromptState();
}

class _UpdatePromptState extends State<UpdatePrompt>
    with WidgetsBindingObserver {
  late final UpdateService _service = widget.service ?? UpdateService();

  bool _isChecking = false;
  bool _isSheetOpen = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _check());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _check();
  }

  Future<void> _check() async {
    // Evita empilhar verificações e sheets duplicados quando o app vai e volta
    // do background várias vezes seguidas.
    if (_isChecking || _isSheetOpen) return;
    _isChecking = true;

    final result = await _service.checkAndDownload();

    _isChecking = false;
    if (!mounted || result is! UpdateReady) return;

    _isSheetOpen = true;
    await showUpdateAvailableSheet(context, patchNumber: result.patchNumber);
    _isSheetOpen = false;
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
