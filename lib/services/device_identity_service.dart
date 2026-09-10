import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:package_info_plus/package_info_plus.dart';

/// Identitas perangkat yang stabil, dipakai untuk mendeteksi satu ponsel yang
/// memverifikasi banyak peserta (sinyal fraud SHARED_DEVICE).
///
/// device_uid = sha256(ANDROID_ID + salt instalasi). Salt-nya acak per instalasi
/// dan disimpan di secure storage, sehingga ID-nya tidak dapat dikorelasikan
/// dengan aplikasi lain di ponsel yang sama.
class DeviceIdentityService {
  DeviceIdentityService({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const _saltKey = 'identicare_install_salt';
  static const _secretKey = 'identicare_device_secret';

  final FlutterSecureStorage _storage;
  final DeviceInfoPlugin _deviceInfo = DeviceInfoPlugin();

  String? _cachedUid;
  Map<String, dynamic>? _cachedInfo;

  Future<String> deviceUid() async {
    if (_cachedUid != null) return _cachedUid!;

    final salt = await _readOrCreate(_saltKey, () => _randomHex(16));
    final raw = await _platformId();
    _cachedUid = sha256.convert(utf8.encode('$raw:$salt')).toString();
    return _cachedUid!;
  }

  /// Rahasia bersama 32 byte untuk attestation Tier A (HMAC).
  ///
  /// Ini BUKAN pengikatan perangkat keras. Kuncinya dapat diekstraksi oleh
  /// penyerang yang menguasai perangkat, dan itulah sebabnya server mencatatnya
  /// sebagai security_level SOFTWARE dan menaikkan sinyal SOFTWARE_KEY_ONLY.
  /// Tier B (Android Keystore) menggantikannya tanpa mengubah kontrak API.
  Future<List<int>> deviceSecret() async {
    final hex = await _readOrCreate(_secretKey, () => _randomHex(32));
    return _hexToBytes(hex);
  }

  Future<Map<String, dynamic>> describe() async {
    if (_cachedInfo != null) return _cachedInfo!;

    final uid = await deviceUid();
    String? model;
    String? osVersion;
    String platform = defaultTargetPlatform.name;

    try {
      if (defaultTargetPlatform == TargetPlatform.android) {
        final android = await _deviceInfo.androidInfo;
        model = android.model;
        osVersion = android.version.release;
        platform = 'android';
      }
    } catch (e) {
      debugPrint('device_info gagal: $e');
    }

    String? appVersion;
    try {
      final info = await PackageInfo.fromPlatform();
      appVersion = '${info.version}+${info.buildNumber}';
    } catch (_) {
      appVersion = null;
    }

    _cachedInfo = {
      'device_uid': uid,
      'platform': platform,
      if (osVersion != null) 'os_version': osVersion,
      if (model != null) 'model': model,
      if (appVersion != null) 'app_version': appVersion,
    };
    return _cachedInfo!;
  }

  Future<String> _platformId() async {
    try {
      if (defaultTargetPlatform == TargetPlatform.android) {
        final android = await _deviceInfo.androidInfo;
        return android.id;
      }
    } catch (e) {
      debugPrint('platform id gagal: $e');
    }
    // Fallback: salt saja sudah cukup untuk ID yang stabil per instalasi.
    return 'unknown-platform';
  }

  Future<String> _readOrCreate(String key, String Function() generate) async {
    try {
      final existing = await _storage.read(key: key);
      if (existing != null && existing.isNotEmpty) return existing;
      final created = generate();
      await _storage.write(key: key, value: created);
      return created;
    } catch (e) {
      // Secure storage dapat gagal (mis. keystore rusak setelah restore backup).
      // Jangan sampai menggagalkan alur; nilai sementara tetap konsisten selama
      // proses berjalan, dan server akan memperlakukannya sebagai perangkat baru.
      debugPrint('secure storage gagal untuk $key: $e');
      return generate();
    }
  }

  static String _randomHex(int bytes) {
    final rng = Random.secure();
    return List.generate(bytes, (_) => rng.nextInt(256).toRadixString(16).padLeft(2, '0'))
        .join();
  }

  static List<int> _hexToBytes(String hex) {
    final out = <int>[];
    for (var i = 0; i + 1 < hex.length; i += 2) {
      out.add(int.parse(hex.substring(i, i + 2), radix: 16));
    }
    return out;
  }
}
