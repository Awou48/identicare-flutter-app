import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Konfigurasi runtime aplikasi.
///
/// Menggantikan IP LAN hardcoded di `api_service.dart` yang lama
/// (`http://192.168.0.101:5000`). Urutan prioritas:
///
///   1. Override debug dari SharedPreferences  (bisa diubah tanpa rebuild)
///   2. --dart-define=API_BASE_URL=...          (dipilih saat build)
///   3. Default 10.0.2.2:8000                   (alias emulator ke localhost host)
///
/// Poin 1 yang paling berharga di lapangan: kalau Wi-Fi lokasi lomba memberi
/// subnet berbeda, base URL bisa diarahkan ulang dari dalam aplikasi tanpa
/// menyusun ulang APK.
class AppConfig {
  AppConfig._();

  static const String _prefsKey = 'identicare_api_base_url_override';

  /// 10.0.2.2 adalah alias emulator Android untuk localhost mesin host, jadi
  /// `flutter run` di emulator langsung jalan tanpa konfigurasi apa pun.
  /// Perangkat fisik memakai --dart-define atau override di bawah.
  static const String _compiled = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static String? _override;

  /// Base URL yang sedang dipakai.
  static String get apiBaseUrl {
    final value = (_override != null && _override!.isNotEmpty) ? _override! : _compiled;
    return value.endsWith('/') ? value.substring(0, value.length - 1) : value;
  }

  static String get apiV1 => '$apiBaseUrl/api/v1';

  static bool get hasOverride => _override != null && _override!.isNotEmpty;
  static String get compiledDefault => _compiled;

  /// Dipanggil sekali di `main()` sebelum runApp.
  static Future<void> load() async {
    if (!kDebugMode) return; // override hanya untuk build debug
    try {
      final prefs = await SharedPreferences.getInstance();
      _override = prefs.getString(_prefsKey);
    } catch (_) {
      // SharedPreferences bisa gagal di beberapa konteks. Bukan alasan untuk
      // menggagalkan startup - cukup pakai nilai kompilasi.
      _override = null;
    }
  }

  /// Ganti base URL saat runtime (hanya debug). Kirim null untuk mengembalikan
  /// ke nilai kompilasi.
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
    } catch (_) {
      // Tetap berlaku untuk sesi ini walaupun gagal disimpan.
    }
  }

  // --- Batas yang harus sejalan dengan server --- //

  /// Jumlah frame yang dikirim per percobaan scan wajah.
  static const int faceBurstFrames = 3;

  /// Jeda antar frame dalam burst.
  static const Duration faceBurstInterval = Duration(milliseconds: 340);
  // Koreografi liveness: waktu untuk menghadap lurus sebelum frame 1, dan
  // waktu untuk menoleh setelah instruksi muncul, sebelum frame 2-3.
  static const Duration faceNeutralHold = Duration(milliseconds: 900);
  static const Duration faceChallengeHold = Duration(milliseconds: 1100);

  /// Sisi terpanjang gambar sebelum diunggah. Jangan kirim frame 12 MP:
  /// server hanya butuh wajah >= 112 px dan uploadnya jauh lebih lambat.
  static const int uploadMaxDimension = 640;
  static const int uploadJpegQuality = 85;

  static const Duration jsonTimeout = Duration(seconds: 20);
  static const Duration uploadTimeout = Duration(seconds: 45);

  /// Alias kunci API faskes untuk demo. Di produksi ini datang dari
  /// provisioning perangkat kios, bukan dikompilasi ke dalam aplikasi peserta.
  static const String faskesApiKey = String.fromEnvironment(
    'FASKES_API_KEY',
    defaultValue: 'abc123',
  );

  static const String defaultKodeFaskes = String.fromEnvironment(
    'KODE_FASKES',
    defaultValue: '0110R001',
  );
}
