import 'package:flutter/material.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Flutter Code Push Example')),
      body: Center(
        child: Text(
          'Hello World',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
      ),
    );
  }
}
