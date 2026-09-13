import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Jembatan ke `KeystoreSigner.kt`: kunci EC P-256 di dalam TEE ponsel.
///
/// Semua yang penting terjadi di sisi Kotlin dan di perangkat keras. Kelas ini
/// hanya meneruskan panggilan dan menerjemahkan kode kesalahan platform menjadi
/// [KeystoreException] yang bisa diputuskan oleh pemanggil.
class KeystoreSigner {
  static const _channel = MethodChannel('identicare/keystore');

  /// Hanya Android. Di platform lain, pemanggil jatuh ke Tier A.
  bool get isSupported {
    if (kIsWeb) return false;
    try {
      return Platform.isAndroid;
    } catch (_) {
      return false;
    }
  }

  Future<bool> hasKey(String alias) async {
    return await _invoke<bool>('hasKey', {'alias': alias}) ?? false;
  }

  /// Buat pasangan kunci baru di TEE. Tidak butuh sidik jari saat pembuatan,
  /// tetapi GAGAL (NO_BIOMETRICS) kalau perangkat belum punya satu pun sidik
  /// jari terdaftar - kunci yang mensyaratkan autentikasi tidak bisa ada
  /// tanpa cara untuk mengautentikasi.
  Future<GeneratedKey> generateKey(String alias, {required List<int> challenge}) async {
    final map = await _invoke<Map>('generateKey', {
      'alias': alias,
      'challengeB64': base64Encode(challenge),
    });
    return GeneratedKey(
      publicKeyDerB64: map!['publicKeyDerB64'] as String,
      attestationChainB64: (map['attestationChainB64'] as List?)?.cast<String>() ?? const [],
      securityLevel: map['securityLevel'] as String? ?? 'UNKNOWN',
    );
  }

  /// Kunci publik + rantai attestation dari kunci yang sudah ada, atau null.
  Future<GeneratedKey?> getKey(String alias) async {
    final map = await _invoke<Map>('getKey', {'alias': alias});
    if (map == null) return null;
    return GeneratedKey(
      publicKeyDerB64: map['publicKeyDerB64'] as String,
      attestationChainB64: (map['attestationChainB64'] as List?)?.cast<String>() ?? const [],
      securityLevel: map['securityLevel'] as String? ?? 'UNKNOWN',
    );
  }

  Future<void> deleteKey(String alias) => _invoke<bool>('deleteKey', {'alias': alias});

  /// Tampilkan prompt sidik jari dan, hanya kalau berhasil, tanda tangani
  /// [payload]. Hasilnya tanda tangan ECDSA (DER) dalam base64.
  Future<String> sign(
    String alias,
    String payload, {
    required String title,
    String subtitle = '',
    String negativeButton = 'Batal',
  }) async {
    final map = await _invoke<Map>('sign', {
      'alias': alias,
      'payload': payload,
      'title': title,
      'subtitle': subtitle,
      'negativeButton': negativeButton,
    });
    return map!['signatureB64'] as String;
  }

  Future<T?> _invoke<T>(String method, Map<String, Object?> args) async {
    try {
      return await _channel.invokeMethod<T>(method, args);
    } on PlatformException catch (e) {
      throw KeystoreException(e.code, e.message);
    } on MissingPluginException {
      throw const KeystoreException('UNSUPPORTED', 'saluran keystore tidak tersedia');
    }
  }
}

class GeneratedKey {
  const GeneratedKey({
    required this.publicKeyDerB64,
    required this.attestationChainB64,
    required this.securityLevel,
  });

  final String publicKeyDerB64;
  final List<String> attestationChainB64;
  final String securityLevel;
}

/// Kode: USER_CANCELLED, LOCKED_OUT, NO_BIOMETRICS, HW_UNAVAILABLE, TIMEOUT,
/// KEY_INVALIDATED, NO_KEY, UNSUPPORTED, ERROR.
class KeystoreException implements Exception {
  const KeystoreException(this.code, this.message);

  final String code;
  final String? message;

  /// Kegagalan yang berarti Tier B memang tidak bisa dipakai di perangkat ini,
  /// bukan keputusan pengguna. Hanya ini yang boleh jatuh ke Tier A.
  bool get isStructural =>
      code == 'UNSUPPORTED' || code == 'HW_UNAVAILABLE' || code == 'ERROR';

  @override
  String toString() => 'KeystoreException($code, $message)';
}
