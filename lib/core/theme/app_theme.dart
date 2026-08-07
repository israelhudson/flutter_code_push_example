import 'package:flutter/material.dart';

abstract final class AppColors {
  static const espresso = Color(0xFF241A17);
  static const roastedCocoa = Color(0xFF4A3028);
  static const burgundy = Color(0xFF6B2635);
  static const champagne = Color(0xFFC6A15B);
  static const cream = Color(0xFFF8F1E7);
  static const porcelain = Color(0xFFFFFCF8);
}

abstract final class AppTheme {
  static ThemeData get light {
    final colorScheme =
        ColorScheme.fromSeed(
          seedColor: AppColors.champagne,
          brightness: Brightness.light,
        ).copyWith(
          primary: AppColors.espresso,
          onPrimary: AppColors.cream,
          secondary: AppColors.champagne,
          onSecondary: AppColors.espresso,
          surface: AppColors.porcelain,
          onSurface: AppColors.espresso,
          inversePrimary: AppColors.champagne,
        );

    return ThemeData(
      colorScheme: colorScheme,
      scaffoldBackgroundColor: AppColors.cream,
      useMaterial3: true,
      fontFamily: 'Georgia',
      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.espresso,
        foregroundColor: AppColors.cream,
        centerTitle: true,
        elevation: 0,
        titleTextStyle: TextStyle(
          color: AppColors.cream,
          fontFamily: 'Georgia',
          fontSize: 20,
          fontWeight: FontWeight.bold,
          letterSpacing: 0.4,
        ),
      ),
      textTheme: const TextTheme(
        bodyLarge: TextStyle(color: AppColors.espresso, fontSize: 18),
        bodyMedium: TextStyle(color: AppColors.roastedCocoa, fontSize: 16),
        headlineMedium: TextStyle(
          color: AppColors.espresso,
          fontSize: 30,
          fontWeight: FontWeight.bold,
          letterSpacing: 0.5,
        ),
      ),
      dividerTheme: const DividerThemeData(
        color: AppColors.champagne,
        thickness: 1,
      ),
    );
  }
}
