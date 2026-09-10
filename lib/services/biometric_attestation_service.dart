import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:local_auth/local_auth.dart';
import 'package:local_auth_android/local_auth_android.dart';
import 'package:identicare_mobile/services/device_identity_service.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';

/// Langkah 2: sensor sidik jari perangkat.
///
/// PENTING soal apa yang benar-benar dibuktikan di sini.
///
/// `local_auth.authenticate()` hanya mengembalikan BOOLEAN. Boolean yang
/// melintasi jaringan bukan faktor kedua: perangkat yang di-root atau APK yang
/// dimodifikasi mengembalikan `true` secara cuma-cuma dan server tidak punya
/// cara membedakannya. Karena itu prompt sidik jari di sini hanya menjadi
/// GERBANG, dan yang dikirim ke server adalah TANDA TANGAN atas payload kanonik
/// berisi nonce sekali pakai dari server.
///
///   Tier A (implementasi ini) - HMAC-SHA256 dengan rahasia di secure storage.
///     Tanpa pengikatan perangkat keras. Server mencatatnya sebagai SOFTWARE dan
///     menaikkan sinyal fraud SOFTWARE_KEY_ONLY. Jujur, dan cukup untuk
///     membuktikan alurnya utuh.
///
///   Tier B (berikutnya) - kunci EC P-256 yang dibuat DI DALAM TEE dengan
///     setUserAuthenticationRequired(true), sehingga Android baru melepaskan
///     kunci untuk menandatangani setelah sensor sidik jari berhasil - dipaksa
///     oleh TEE, bukan oleh kode aplikasi. Membutuhkan handler Kotlin
///     (MethodChannel) dan tidak mengubah kontrak API sama sekali: hanya nilai
///     field `method` yang berbeda.
///
/// Sidik jarinya sendiri tidak pernah meninggalkan perangkat.
class BiometricAttestationService {
  BiometricAttestationService(this._deviceIdentity);

  final DeviceIdentityService _deviceIdentity;
  final LocalAuthentication _localAuth = LocalAuthentication();

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

  /// Minta sidik jari, lalu tandatangani payload kanonik.
  Future<AttestationResult> authenticateAndSign({
    required String sessionId,
    required String nonce,
    required String noBpjs,
  }) async {
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
    } on Exception catch (e) {
      final message = e.toString();
      final noHardware =
          message.contains('NotAvailable') || message.contains('NotEnrolled');
      return AttestationResult.failure(
        errorCode: noHardware ? 'NO_BIOMETRIC_HARDWARE' : 'BIOMETRIC_CANCELLED',
        message: noHardware
            ? 'Sensor sidik jari tidak tersedia di perangkat ini.'
            : 'Verifikasi sidik jari dibatalkan.',
      );
    }

    if (!authenticated) {
      return AttestationResult.failure(
        errorCode: 'BIOMETRIC_CANCELLED',
        message: 'Verifikasi sidik jari dibatalkan.',
      );
    }

    final deviceUid = await _deviceIdentity.deviceUid();
    final secret = await _deviceIdentity.deviceSecret();
    final timestamp = DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000;

    final payload = VerificationConstants.canonicalPayload(
      sessionId: sessionId,
      nonce: nonce,
      deviceUid: deviceUid,
      noBpjs: noBpjs,
      timestamp: timestamp,
    );

    final signature = Hmac(sha256, secret).convert(utf8.encode(payload)).bytes;

    return AttestationResult.success(
      method: VerificationConstants.methodHmac,
      signatureB64: base64Encode(signature),
      deviceUid: deviceUid,
      timestamp: timestamp,
    );
  }

  /// Payload pendaftaran perangkat untuk POST /enrollment/device.
  Future<Map<String, dynamic>> enrollmentPayload({String? firebaseUid}) async {
    final info = await _deviceIdentity.describe();
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

  const AttestationResult._({
    required this.ok,
    this.method,
    this.signatureB64,
    this.deviceUid,
    this.timestamp,
    this.errorCode,
    this.message,
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
  }) =>
      AttestationResult._(ok: false, errorCode: errorCode, message: message);
}
