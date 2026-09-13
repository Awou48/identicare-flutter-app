import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:local_auth/local_auth.dart';
import 'package:local_auth_android/local_auth_android.dart';
import 'package:identicare_mobile/services/device_identity_service.dart';
import 'package:identicare_mobile/services/keystore_signer.dart';
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
///   Tier B (default di Android) - kunci EC P-256 yang dibuat DI DALAM TEE
///     dengan setUserAuthenticationRequired(true). Android baru melepaskan
///     kunci untuk menandatangani setelah sensor sidik jari berhasil - dipaksa
///     oleh perangkat keras, bukan oleh kode aplikasi. Kuncinya tidak bisa
///     diekstrak, dan rantai sertifikat attestation-nya dikirim ke server saat
///     pendaftaran supaya server tahu tingkat keamanannya (TEE / StrongBox)
///     dari sertifikat, bukan dari klaim aplikasi. Lihat KeystoreSigner.kt.
///
///   Tier A (cadangan) - HMAC-SHA256 dengan rahasia di secure storage. Dipakai
///     hanya kalau Tier B secara STRUKTURAL tidak bisa (bukan Android, TEE tidak
///     tersedia). Server mencatatnya sebagai SOFTWARE dan menaikkan sinyal
///     fraud SOFTWARE_KEY_ONLY - sistem jujur tentang kekuatannya sendiri.
///
/// Pembatalan oleh pengguna atau sensor terkunci TIDAK memicu jatuh ke Tier A:
/// itu akan menjadikan "tekan Batal" sebagai cara menurunkan tingkat keamanan.
///
/// Sidik jarinya sendiri tidak pernah meninggalkan perangkat, di kedua tier.
class BiometricAttestationService {
  BiometricAttestationService(this._deviceIdentity);

  final DeviceIdentityService _deviceIdentity;
  final LocalAuthentication _localAuth = LocalAuthentication();
  final KeystoreSigner _keystore = KeystoreSigner();

  /// Kunci Tier B yang siap dipakai di perangkat ini, dibuat kalau belum ada.
  /// Null berarti Tier B tidak tersedia secara struktural.
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

  /// Pastikan kunci TEE ada. Mengembalikan null kalau Tier B tidak bisa dipakai
  /// di perangkat ini; alasannya dicatat ke log, bukan disembunyikan.
  Future<GeneratedKey?> _ensureTierBKey({bool regenerate = false}) async {
    if (!_keystore.isSupported) return null;
    if (_tierBProbed && !regenerate) return _tierBKey;
    _tierBProbed = true;

    final alias = VerificationConstants.keyAlias;
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
      // Tantangan attestation = device_uid: mengikat rantai sertifikat ke
      // identitas perangkat yang didaftarkan. Bukan nonce server (belum ada
      // pada saat ini), jadi server memeriksanya sebagai pengikatan, bukan
      // sebagai bukti kesegaran.
      _tierBKey = await _keystore.generateKey(alias, challenge: utf8.encode(deviceUid));
      debugPrint('kunci TEE dibuat: securityLevel=${_tierBKey!.securityLevel}');
      return _tierBKey;
    } on KeystoreException catch (e) {
      debugPrint('Tier B tidak tersedia: $e');
      _tierBKey = null;
      return null;
    }
  }

  /// Minta sidik jari, lalu tandatangani payload kanonik.
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

    // ---- Tier B ---------------------------------------------------------- //
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
            // Sidik jari baru didaftarkan di perangkat; Android menghancurkan
            // kuncinya. Buat kunci baru - pendaftaran ulang ke server terjadi
            // saat alur berikutnya dimulai, jadi TANDA TANGAN INI akan ditolak
            // KEY_MISMATCH. Itu benar: perangkat harus didaftar ulang dulu.
            await _ensureTierBKey(regenerate: true);
            return AttestationResult.failure(
              errorCode: 'KEY_MISMATCH',
              message: 'Sidik jari perangkat berubah. Kunci dibuat ulang - mulai ulang verifikasi.',
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

    // ---- Tier A ---------------------------------------------------------- //
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
      // Setiap kode punya artinya sendiri. Sebelumnya semuanya - termasuk
      // kesalahan konfigurasi aplikasi - dilaporkan sebagai "dibatalkan",
      // sehingga tidak ada yang bisa didiagnosis dari layar.
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

  /// Payload pendaftaran perangkat untuk POST /enrollment/device.
  ///
  /// Tier B kalau kunci TEE bisa dibuat: kunci publik + rantai sertifikat
  /// attestation, dikirim ulang setiap kali (upsert) supaya server yang
  /// databasenya di-reset tetap tahu kunci ini.
  Future<Map<String, dynamic>> enrollmentPayload({String? firebaseUid}) async {
    final info = await _deviceIdentity.describe();
    final key = await _ensureTierBKey();

    if (key != null) {
      return {
        ...info,
        'method': VerificationConstants.methodKeystore,
        'key_alias': VerificationConstants.keyAlias,
        'public_key_der_b64': key.publicKeyDerB64,
        if (key.attestationChainB64.isNotEmpty) 'attestation_chain_b64': key.attestationChainB64,
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

  /// Kode mentah dari platform - untuk log, bukan untuk pengguna.
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
      AttestationResult._(ok: false, errorCode: errorCode, message: message, detail: detail);
}
