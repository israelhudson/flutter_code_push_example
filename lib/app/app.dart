import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';
import '../features/home/home_page.dart';
import '../features/update/update_prompt.dart';

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Code Push Example',
      theme: AppTheme.light,
      debugShowCheckedModeBanner: false,
      home: const UpdatePrompt(child: HomePage()),
    );
  }
}
