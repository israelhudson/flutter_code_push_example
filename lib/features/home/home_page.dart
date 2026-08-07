import 'package:flutter/material.dart';
import 'package:shorebird_code_push/shorebird_code_push.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _updater = ShorebirdUpdater();

  String _status = 'Carregando...';
  int? _currentPatchNumber;
  bool _isBusy = false;

  @override
  void initState() {
    super.initState();
    _loadCurrentPatch();
  }

  Future<void> _loadCurrentPatch() async {
    if (!_updater.isAvailable) {
      setState(() {
        _status =
            'Shorebird indisponível neste build (rode com "shorebird run" '
            'ou instale um build gerado por "shorebird release").';
      });
      return;
    }

    final patch = await _updater.readCurrentPatch();
    setState(() {
      _currentPatchNumber = patch?.number;
      _status = patch == null
          ? 'Nenhum patch aplicado ainda (release base).'
          : 'Patch atual: ${patch.number}';
    });
  }

  Future<void> _checkForUpdate() async {
    setState(() => _isBusy = true);
    final status = await _updater.checkForUpdate();
    setState(() {
      _isBusy = false;
      _status = switch (status) {
        UpdateStatus.upToDate => 'App já está atualizado.',
        UpdateStatus.outdated => 'Atualização disponível! Toque em "Baixar atualização".',
        UpdateStatus.restartRequired =>
          'Atualização já baixada — reinicie o app para aplicar.',
        UpdateStatus.unavailable => 'Serviço de atualização indisponível no momento.',
      };
    });
  }

  Future<void> _downloadUpdate() async {
    setState(() => _isBusy = true);
    try {
      await _updater.update();
      setState(() => _status = 'Patch baixado! Feche e reabra o app para aplicar.');
    } on UpdateException catch (e) {
      setState(() => _status = 'Erro ao atualizar: ${e.message}');
    } finally {
      setState(() => _isBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Flutter Code Push Example')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'Hello World',
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
                Wrap(
                  spacing: 12,
                  alignment: WrapAlignment.center,
                  children: [
                    ElevatedButton(
                      onPressed: _checkForUpdate,
                      child: const Text('Verificar atualização'),
                    ),
                    ElevatedButton(
                      onPressed: _downloadUpdate,
                      child: const Text('Baixar atualização'),
                    ),
                  ],
                ),
            ],
          ),
        ),
      ),
    );
  }
}
