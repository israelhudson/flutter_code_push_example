import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_code_push_example/app/app.dart';
import 'package:flutter_code_push_example/features/home/home_page.dart';
import 'package:flutter_code_push_example/features/update/widgets/update_available_sheet.dart';

void main() {
  testWidgets('exibe a mensagem inicial', (WidgetTester tester) async {
    await tester.pumpWidget(const App());

    expect(find.text('Flutter Code Push Example'), findsOneWidget);
    expect(find.text('Laboratório de entregas'), findsOneWidget);
    expect(find.text('CORAL · 02'), findsOneWidget);
  });

  testWidgets('inicia claro e ignora mudanças do tema do sistema', (
    WidgetTester tester,
  ) async {
    tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
    addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);

    await tester.pumpWidget(const App());
    await tester.pumpAndSettle();

    expect(_brightness(tester), Brightness.light);
    expect(find.byTooltip('Ativar tema escuro'), findsOneWidget);

    await tester.tap(find.byTooltip('Ativar tema escuro'));
    await tester.pumpAndSettle();

    tester.platformDispatcher.platformBrightnessTestValue = Brightness.light;
    await tester.pumpAndSettle();

    expect(_brightness(tester), Brightness.dark);
    expect(find.byTooltip('Ativar tema claro'), findsOneWidget);
  });

  testWidgets('alterna pelo botão e reinicia claro sem persistir a escolha', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const App());
    await tester.pumpAndSettle();

    final homeState = tester.state(find.byType(HomePage));

    await tester.tap(find.byTooltip('Ativar tema escuro'));
    await tester.pumpAndSettle();
    expect(_brightness(tester), Brightness.dark);
    expect(tester.state(find.byType(HomePage)), same(homeState));

    await tester.tap(find.byTooltip('Ativar tema claro'));
    await tester.pumpAndSettle();
    expect(_brightness(tester), Brightness.light);

    await tester.tap(find.byTooltip('Ativar tema escuro'));
    await tester.pumpAndSettle();
    expect(_brightness(tester), Brightness.dark);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(const App());
    await tester.pumpAndSettle();

    expect(_brightness(tester), Brightness.light);
    expect(find.byTooltip('Ativar tema escuro'), findsOneWidget);
  });

  testWidgets('aviso de atualização acompanha as cores do tema escuro', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const App());
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Ativar tema escuro'));
    await tester.pumpAndSettle();

    final context = tester.element(find.byType(HomePage));
    final colors = Theme.of(context).colorScheme;
    final closed = showUpdateAvailableSheet(context, patchNumber: 2);
    await tester.pumpAndSettle();

    expect(find.text('Nova versão disponível'), findsOneWidget);
    expect(
      tester.widget<BottomSheet>(find.byType(BottomSheet)).backgroundColor,
      colors.surface,
    );
    expect(
      tester.widget<Icon>(find.byIcon(Icons.system_update_alt)).color,
      colors.primary,
    );
    expect(tester.takeException(), isNull);

    await tester.tap(find.text('Entendi'));
    await tester.pumpAndSettle();
    await closed;
  });

  testWidgets('botão de tema funciona em tela estreita', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(375, 667);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const App());
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Ativar tema escuro'));
    await tester.pumpAndSettle();

    expect(_brightness(tester), Brightness.dark);
    expect(tester.takeException(), isNull);
  });

  testWidgets('texto do botão de tema tem contraste nos dois temas', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const App());
    await tester.pumpAndSettle();

    for (final label in ['Tema escuro', 'Tema claro']) {
      final context = tester.element(find.text(label));
      final foreground = DefaultTextStyle.of(context).style.color!;
      final background = Theme.of(context).appBarTheme.backgroundColor!;
      final first = foreground.computeLuminance();
      final second = background.computeLuminance();
      final lighter = first > second ? first : second;
      final darker = first < second ? first : second;
      expect((lighter + 0.05) / (darker + 0.05), greaterThanOrEqualTo(4.5));

      await tester.tap(find.text(label));
      await tester.pumpAndSettle();
    }
  });

  testWidgets(
    'entrega visível pode ser lida com texto ampliado em tela baixa',
    (WidgetTester tester) async {
      tester.view.physicalSize = const Size(320, 480);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 1.5;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await tester.pumpWidget(const App());
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Verificar atualização agora'));
      expect(tester.takeException(), isNull);
      await tester.tap(find.byTooltip('Ativar tema escuro'));
      await tester.pumpAndSettle();
      expect(find.text('CORAL · 02'), findsOneWidget);
      expect(_brightness(tester), Brightness.dark);
    },
  );
}

Brightness _brightness(WidgetTester tester) {
  return Theme.of(tester.element(find.byType(HomePage))).brightness;
}
