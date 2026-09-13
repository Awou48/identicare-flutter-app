import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppConfig {
  AppConfig._();

  static const String _prefsKey = 'identicare_api_base_url_override';

  static const String _compiled = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static String? _override;

  static String get apiBaseUrl {
    final value =
        (_override != null && _override!.isNotEmpty) ? _override! : _compiled;
    return value.endsWith('/') ? value.substring(0, value.length - 1) : value;
  }

  static String get apiV1 => '$apiBaseUrl/api/v1';

  static bool get hasOverride => _override != null && _override!.isNotEmpty;
  static String get compiledDefault => _compiled;

  static Future<void> load() async {
    if (!kDebugMode) return;
    try {
      final prefs = await SharedPreferences.getInstance();
      _override = prefs.getString(_prefsKey);
    } catch (_) {
      _override = null;
    }
  }

  static Future<void> setOverride(String? url) async {
    if (!kDebugMode) return;
    _override = (url == null || url.trim().isEmpty) ? null : url.trim();
    try {
      final prefs = await SharedPreferences.getInstance();
      if (_override == null) {
        await prefs.remove(_prefsKey);
      } else {
        await prefs.setString(_prefsKey, _override!);
      }
    } catch (_) {}
  }

  static const int faceBurstFrames = 3;

  static const Duration faceBurstInterval = Duration(milliseconds: 340);

  static const Duration faceNeutralHold = Duration(milliseconds: 900);
  static const Duration faceChallengeHold = Duration(milliseconds: 1100);

  static const int uploadMaxDimension = 640;
  static const int uploadJpegQuality = 85;

  static const Duration jsonTimeout = Duration(seconds: 20);
  static const Duration uploadTimeout = Duration(seconds: 45);

  static const String faskesApiKey = String.fromEnvironment(
    'FASKES_API_KEY',
    defaultValue: 'abc123',
  );

  static const String defaultKodeFaskes = String.fromEnvironment(
    'KODE_FASKES',
    defaultValue: '0110R001',
  );
}
