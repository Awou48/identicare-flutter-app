import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:local_auth/local_auth.dart';
import 'package:local_auth_android/local_auth_android.dart';
import 'package:identicare_mobile/services/device_identity_service.dart';
import 'package:identicare_mobile/services/keystore_signer.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';

class BiometricAttestationService {
  BiometricAttestationService(this._deviceIdentity);

  final DeviceIdentityService _deviceIdentity;
  final LocalAuthentication _localAuth = LocalAuthentication();
  final KeystoreSigner _keystore = KeystoreSigner();

  GeneratedKey? _tierBKey;
  bool _tierBProbed = false;

  Future<BiometricAvailability> availability() async {
    try {
      final supported = await _localAuth.isDeviceSupported();
      if (!supported) {
        return const BiometricAvailability(
          available: false,
          reason: 'Perangkat ini tidak mendukung autentikasi biometrik.',
        );
      }
      final canCheck = await _localAuth.canCheckBiometrics;
      final enrolled = await _localAuth.getAvailableBiometrics();
      if (!canCheck || enrolled.isEmpty) {
        return const BiometricAvailability(
          available: false,
          reason: 'Belum ada sidik jari terdaftar di perangkat ini. '
              'Daftarkan lewat Pengaturan > Keamanan.',
        );
      }
      return BiometricAvailability(
        available: true,
        hasFingerprint: enrolled.contains(BiometricType.fingerprint) ||
            enrolled.contains(BiometricType.strong),
      );
    } on Exception catch (e) {
      debugPrint('cek biometrik gagal: $e');
      return BiometricAvailability(
        available: false,
        reason: 'Tidak dapat memeriksa sensor biometrik.',
        detail: e.toString(),
      );
    }
  }

  Future<GeneratedKey?> _ensureTierBKey({bool regenerate = false}) async {
    if (!_keystore.isSupported) return null;
    if (_tierBProbed && !regenerate) return _tierBKey;
    _tierBProbed = true;

    const alias = VerificationConstants.keyAlias;
    final deviceUid = await _deviceIdentity.deviceUid();
    try {
      if (regenerate) await _keystore.deleteKey(alias);
      if (!regenerate) {
        final existing = await _keystore.getKey(alias);
        if (existing != null) {
          _tierBKey = existing;
          return existing;
        }
      }

      _tierBKey =
          await _keystore.generateKey(alias, challenge: utf8.encode(deviceUid));
      debugPrint('kunci TEE dibuat: securityLevel=${_tierBKey!.securityLevel}');
      return _tierBKey;
    } on KeystoreException catch (e) {
      debugPrint('Tier B tidak tersedia: $e');
      _tierBKey = null;
      return null;
    }
  }

  Future<AttestationResult> authenticateAndSign({
    required String sessionId,
    required String nonce,
    required String noBpjs,
  }) async {
    final deviceUid = await _deviceIdentity.deviceUid();
    final timestamp = DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000;
    final payload = VerificationConstants.canonicalPayload(
      sessionId: sessionId,
      nonce: nonce,
      deviceUid: deviceUid,
      noBpjs: noBpjs,
      timestamp: timestamp,
    );

    if (await _ensureTierBKey() != null) {
      tierB:
      {
        try {
          final signature = await _keystore.sign(
            VerificationConstants.keyAlias,
            payload,
            title: 'Verifikasi Sidik Jari',
            subtitle: 'Klaim BPJS ditandatangani di dalam perangkat Anda',
          );
          return AttestationResult.success(
            method: VerificationConstants.methodKeystore,
            signatureB64: signature,
            deviceUid: deviceUid,
            timestamp: timestamp,
          );
        } on KeystoreException catch (e) {
          if (e.code == 'KEY_INVALIDATED') {
            await _ensureTierBKey(regenerate: true);
            return AttestationResult.failure(
              errorCode: 'KEY_MISMATCH',
              message:
                  'Sidik jari perangkat berubah. Kunci dibuat ulang - mulai ulang verifikasi.',
              detail: e.toString(),
            );
          }
          if (e.isStructural) {
            debugPrint('Tier B gagal secara struktural, jatuh ke Tier A: $e');
            _tierBKey = null;
            break tierB;
          }
          return AttestationResult.failure(
            errorCode: _keystoreCodeFor(e.code),
            message: _keystoreMessageFor(e.code),
            detail: e.toString(),
          );
        }
      }
    }

    final bool authenticated;
    try {
      authenticated = await _localAuth.authenticate(
        localizedReason: 'Verifikasi sidik jari untuk melanjutkan klaim BPJS',
        options: const AuthenticationOptions(
          biometricOnly: true,
          stickyAuth: true,
          useErrorDialogs: true,
        ),
        authMessages: const [
          AndroidAuthMessages(
            signInTitle: 'Verifikasi Sidik Jari',
            biometricHint: 'Sentuh sensor sidik jari',
            cancelButton: 'Batal',
            biometricNotRecognized: 'Sidik jari tidak dikenali, coba lagi',
            biometricRequiredTitle: 'Sidik jari diperlukan',
            goToSettingsButton: 'Pengaturan',
            goToSettingsDescription:
                'Daftarkan sidik jari Anda di pengaturan perangkat.',
          ),
        ],
      );
    } on PlatformException catch (e) {
      return AttestationResult.failure(
        errorCode: _codeFor(e.code),
        message: _messageFor(e.code),
        detail: '${e.code}: ${e.message}',
      );
    } on Exception catch (e) {
      return AttestationResult.failure(
        errorCode: 'BIOMETRIC_CANCELLED',
        message: 'Verifikasi sidik jari gagal dijalankan.',
        detail: e.toString(),
      );
    }

    if (!authenticated) {
      return AttestationResult.failure(
        errorCode: 'BIOMETRIC_CANCELLED',
        message: 'Verifikasi sidik jari dibatalkan.',
      );
    }

    final secret = await _deviceIdentity.deviceSecret();
    final signature = Hmac(sha256, secret).convert(utf8.encode(payload)).bytes;

    return AttestationResult.success(
      method: VerificationConstants.methodHmac,
      signatureB64: base64Encode(signature),
      deviceUid: deviceUid,
      timestamp: timestamp,
    );
  }

  static String _keystoreCodeFor(String code) {
    switch (code) {
      case 'NO_BIOMETRICS':
        return 'NO_BIOMETRIC_HARDWARE';
      case 'LOCKED_OUT':
        return 'BIOMETRIC_LOCKED_OUT';
      case 'TIMEOUT':
      case 'USER_CANCELLED':
      default:
        return 'BIOMETRIC_CANCELLED';
    }
  }

  static String _keystoreMessageFor(String code) {
    switch (code) {
      case 'NO_BIOMETRICS':
        return 'Belum ada sidik jari terdaftar. Daftarkan lewat Pengaturan > Keamanan.';
      case 'LOCKED_OUT':
        return 'Terlalu banyak percobaan. Sensor terkunci sementara.';
      case 'TIMEOUT':
        return 'Waktu habis. Coba lagi.';
      default:
        return 'Verifikasi sidik jari dibatalkan.';
    }
  }

  static String _codeFor(String platformCode) {
    switch (platformCode) {
      case 'NotAvailable':
      case 'NotEnrolled':
      case 'PasscodeNotSet':
        return 'NO_BIOMETRIC_HARDWARE';
      case 'LockedOut':
      case 'PermanentlyLockedOut':
        return 'BIOMETRIC_LOCKED_OUT';
      case 'no_fragment_activity':
      case 'auth_in_progress':
        return 'BIOMETRIC_UNAVAILABLE';
      default:
        return 'BIOMETRIC_CANCELLED';
    }
  }

  static String _messageFor(String platformCode) {
    switch (platformCode) {
      case 'NotAvailable':
        return 'Sensor sidik jari tidak tersedia di perangkat ini.';
      case 'NotEnrolled':
        return 'Belum ada sidik jari terdaftar. Daftarkan lewat Pengaturan > Keamanan.';
      case 'PasscodeNotSet':
        return 'Kunci layar belum diatur. Atur PIN/pola dan daftarkan sidik jari.';
      case 'LockedOut':
        return 'Terlalu banyak percobaan. Sensor terkunci 30 detik.';
      case 'PermanentlyLockedOut':
        return 'Sensor terkunci. Buka kunci perangkat dengan PIN/pola, lalu coba lagi.';
      case 'no_fragment_activity':
        return 'Kesalahan konfigurasi aplikasi: prompt biometrik tidak dapat ditampilkan.';
      case 'auth_in_progress':
        return 'Prompt sidik jari masih terbuka.';
      default:
        return 'Verifikasi sidik jari dibatalkan.';
    }
  }

  Future<Map<String, dynamic>> enrollmentPayload({String? firebaseUid}) async {
    final info = await _deviceIdentity.describe();
    final key = await _ensureTierBKey();

    if (key != null) {
      return {
        ...info,
        'method': VerificationConstants.methodKeystore,
        'key_alias': VerificationConstants.keyAlias,
        'public_key_der_b64': key.publicKeyDerB64,
        if (key.attestationChainB64.isNotEmpty)
          'attestation_chain_b64': key.attestationChainB64,
        'client_security_level': key.securityLevel,
        if (firebaseUid != null) 'firebase_uid': firebaseUid,
      };
    }

    final secret = await _deviceIdentity.deviceSecret();
    return {
      ...info,
      'method': VerificationConstants.methodHmac,
      'shared_secret_b64': base64Encode(secret),
      if (firebaseUid != null) 'firebase_uid': firebaseUid,
    };
  }
}

class BiometricAvailability {
  final bool available;
  final bool hasFingerprint;
  final String? reason;
  final String? detail;

  const BiometricAvailability({
    required this.available,
    this.hasFingerprint = false,
    this.reason,
    this.detail,
  });
}

class AttestationResult {
  final bool ok;
  final String? method;
  final String? signatureB64;
  final String? deviceUid;
  final int? timestamp;
  final String? errorCode;
  final String? message;

  final String? detail;

  const AttestationResult._({
    required this.ok,
    this.method,
    this.signatureB64,
    this.deviceUid,
    this.timestamp,
    this.errorCode,
    this.message,
    this.detail,
  });

  factory AttestationResult.success({
    required String method,
    required String signatureB64,
    required String deviceUid,
    required int timestamp,
  }) =>
      AttestationResult._(
        ok: true,
        method: method,
        signatureB64: signatureB64,
        deviceUid: deviceUid,
        timestamp: timestamp,
      );

  factory AttestationResult.failure({
    required String errorCode,
    required String message,
    String? detail,
  }) =>
      AttestationResult._(
          ok: false, errorCode: errorCode, message: message, detail: detail);
}
