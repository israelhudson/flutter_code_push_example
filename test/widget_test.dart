import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_code_push_example/app/app.dart';

void main() {
  testWidgets('exibe a mensagem inicial', (WidgetTester tester) async {
    await tester.pumpWidget(const App());

    expect(find.text('Flutter Code Push Example'), findsOneWidget);
    expect(find.text('Laboratório de atualizações'), findsOneWidget);
  });
}
