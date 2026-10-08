import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';
import '../features/home/home_page.dart';
import '../features/update/update_prompt.dart';

class App extends StatefulWidget {
  const App({super.key});

  @override
  State<App> createState() => _AppState();
}

class _AppState extends State<App> {
  // A escolha dura somente nesta execução. Todo novo início usa o tema claro.
  ThemeMode _themeMode = ThemeMode.light;

  void _toggleTheme() {
    setState(() {
      _themeMode = _themeMode == ThemeMode.light
          ? ThemeMode.dark
          : ThemeMode.light;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Code Push Example',
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: _themeMode,
      debugShowCheckedModeBanner: false,
      home: UpdatePrompt(child: HomePage(onToggleTheme: _toggleTheme)),
    );
  }
}
