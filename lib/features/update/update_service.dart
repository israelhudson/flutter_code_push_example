import 'package:shorebird_code_push/shorebird_code_push.dart';

/// Resultado de uma verificação de atualização.
sealed class UpdateCheckResult {
  const UpdateCheckResult();
}

/// O app já roda a versão mais recente.
class UpdateUpToDate extends UpdateCheckResult {
  const UpdateUpToDate();
}

/// Existe um patch baixado, aguardando o próximo cold start.
class UpdateReady extends UpdateCheckResult {
  const UpdateReady(this.patchNumber);

  final int? patchNumber;
}

/// O updater não está disponível: build sem Shorebird ou serviço fora do ar.
class UpdateUnavailable extends UpdateCheckResult {
  const UpdateUnavailable();
}

/// A verificação ou o download falhou.
class UpdateFailed extends UpdateCheckResult {
  const UpdateFailed(this.message);

  final String message;
}

/// Isola o `ShorebirdUpdater` do resto do app.
///
/// O `shorebird.yaml` está com `auto_update: false`, então nada é baixado
/// automaticamente — todo download de patch passa por aqui.
class UpdateService {
  UpdateService({ShorebirdUpdater? updater})
    : _updater = updater ?? ShorebirdUpdater();

  final ShorebirdUpdater _updater;

  /// `false` em builds sem Shorebird, como `flutter run` em debug e testes.
  bool get isAvailable => _updater.isAvailable;

  /// Número do patch em execução, ou `null` se o app roda a release base.
  Future<int?> currentPatchNumber() async {
    if (!isAvailable) return null;
    final patch = await _updater.readCurrentPatch();
    return patch?.number;
  }

  /// Verifica se há patch novo e, se houver, baixa.
  ///
  /// O patch baixado só passa a valer no próximo cold start: o Shorebird não
  /// aplica código novo com o processo já rodando.
  Future<UpdateCheckResult> checkAndDownload() async {
    if (!isAvailable) return const UpdateUnavailable();

    try {
      final status = await _updater.checkForUpdate();

      if (status == UpdateStatus.upToDate) return const UpdateUpToDate();
      if (status == UpdateStatus.unavailable) return const UpdateUnavailable();

      // `outdated` ainda precisa baixar; `restartRequired` já tem o patch em
      // disco e só espera o restart.
      if (status == UpdateStatus.outdated) {
        await _updater.update();
      }

      final next = await _updater.readNextPatch();
      return UpdateReady(next?.number);
    } on UpdateException catch (e) {
      return UpdateFailed(e.message);
    }
  }
}
