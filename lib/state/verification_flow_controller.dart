import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:identicare_mobile/models/review_data.dart';
import 'package:identicare_mobile/models/step_results.dart';
import 'package:identicare_mobile/models/verification_session.dart';
import 'package:identicare_mobile/services/biometric_attestation_service.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';

class VerificationFlowController extends ChangeNotifier {
  VerificationFlowController(this._api, this._attestation);

  final VerificationApiService _api;
  final BiometricAttestationService _attestation;

  String? _sessionId;
  String? _sessionToken;
  String? _noBpjs;
  String? _nonce;
  SessionStep _currentStep = SessionStep.face;
  PesertaPreview? _preview;
  DateTime? _expiresAt;

  bool _busy = false;
  String? _error;
  String? _errorCode;
  bool _disposed = false;

  LivenessChallenge? _challenge;
  FaceStepResult? _faceResult;
  FingerprintStepResult? _fingerprintResult;
  ReviewData? _reviewData;
  CommitResult? _commitResult;

  final String _idempotencyKey = _uuidV4();

  String? get sessionId => _sessionId;

  String? get sessionToken => _sessionToken;
  String? get noBpjs => _noBpjs;
  SessionStep get currentStep => _currentStep;
  int get stepIndex => _currentStep.index0;
  PesertaPreview? get preview => _preview;
  bool get isBusy => _busy;
  String? get error => _error;

  String? get errorCode => _errorCode;

  bool get needsEnrollment => _errorCode == 'BIOMETRIC_NOT_ENROLLED';

  bool get needsBpjsLink => _errorCode == 'PESERTA_NOT_FOUND';
  bool get hasSession => _sessionId != null && _sessionToken != null;

  LivenessChallenge? get challenge => _challenge;
  FaceStepResult? get faceResult => _faceResult;
  FingerprintStepResult? get fingerprintResult => _fingerprintResult;
  ReviewData? get reviewData => _reviewData;
  CommitResult? get commitResult => _commitResult;

  Duration? get remaining => _expiresAt?.difference(DateTime.now().toUtc());

  bool get isCommitted => _commitResult != null;

  bool get canRequestOverride =>
      hasSession &&
      !isCommitted &&
      ((_faceResult?.isExhausted ?? false) ||
          (_fingerprintResult?.isExhausted ?? false));

  void applyOverrideResult(Map<String, dynamic> body) {
    try {
      _commitResult = CommitResult.fromJson(body);
      _currentStep = SessionStep.commit;
      _error = null;
    } catch (e) {
      _error = 'Hasil override tidak dapat dibaca: $e';
    }
    _notify();
  }

  Future<bool> start({
    required String noBpjs,
    required String kodeFaskes,
    required Map<String, dynamic> device,
    String jenisLayanan = 'RAWAT_JALAN',
    String poli = '',
    int estimasiBiaya = 0,
  }) async {
    _setBusy(true);
    _noBpjs = noBpjs;

    final enrol =
        await _api.enrollDevice(await _attestation.enrollmentPayload());
    enrol.when(
      ok: (_) {},
      failure: (f) => debugPrint(
          'pendaftaran perangkat gagal: ${f.errorCode} ${f.message}'),
    );

    final result = await _api.startSession(
      noBpjs: noBpjs,
      kodeFaskes: kodeFaskes,
      device: device,
      jenisLayanan: jenisLayanan,
      poli: poli,
      estimasiBiaya: estimasiBiaya,
    );

    return result.when(
      ok: (session) {
        _sessionId = session.sessionId;
        _sessionToken = session.sessionToken;
        _nonce = session.nonce;
        _preview = session.pesertaPreview;
        _expiresAt = session.expiresAt;
        _currentStep = session.currentStep ?? SessionStep.face;
        _error = null;
        _setBusy(false);
        return true;
      },
      failure: (f) {
        _fail(f.message, f.errorCode);
        return false;
      },
    );
  }

  Future<void> loadChallenge() async {
    if (!hasSession) return;
    final result = await _api.requestChallenge(_sessionId!, _sessionToken!);
    result.when(
      ok: (challenge) {
        _challenge = challenge;
        _notify();
      },
      failure: (f) {
        debugPrint('tantangan liveness tidak tersedia: ${f.errorCode}');
      },
    );
  }

  Future<bool> submitFace(List<List<int>> frames) async {
    if (!hasSession) return false;
    _setBusy(true);

    final result = await _api.submitFace(
      sessionId: _sessionId!,
      token: _sessionToken!,
      frames: frames,
      meta: {
        'front_camera': true,
        if (_challenge != null) 'challenge_id': _challenge!.challengeId,
      },
    );

    return result.when(
      ok: (face) {
        _faceResult = face;
        if (face.passed) {
          _nonce = face.nonce ?? _nonce;
          _currentStep = SessionStep.fingerprint;
          _error = null;
        } else {
          _error = face.message;
        }
        _setBusy(false);
        return face.passed;
      },
      failure: (f) {
        _fail(f.message, f.errorCode);
        return false;
      },
    );
  }

  Future<bool> submitFingerprint() async {
    if (!hasSession) return false;
    if (_nonce == null) {
      _fail('Kode verifikasi tidak tersedia. Ulangi scan wajah.');
      return false;
    }
    _setBusy(true);

    final attestation = await _attestation.authenticateAndSign(
      sessionId: _sessionId!,
      nonce: _nonce!,
      noBpjs: _noBpjs ?? '',
    );

    if (!attestation.ok) {
      debugPrint(
          'attestation gagal: ${attestation.errorCode} ${attestation.detail}');
      _fail(attestation.message ?? 'Verifikasi sidik jari gagal.',
          attestation.errorCode);
      return false;
    }

    final result = await _api.submitFingerprint(
      sessionId: _sessionId!,
      token: _sessionToken!,
      method: attestation.method!,
      nonce: _nonce!,
      timestamp: attestation.timestamp!,
      signatureB64: attestation.signatureB64!,
      deviceUid: attestation.deviceUid!,
      keyAlias: VerificationConstants.keyAlias,
    );

    return result.when(
      ok: (fp) {
        _fingerprintResult = fp;
        if (fp.passed) {
          _currentStep = SessionStep.review;
          _error = null;

          _nonce = null;
        } else {
          _error = fp.message;
        }
        _setBusy(false);
        return fp.passed;
      },
      failure: (f) {
        _fail(f.message, f.errorCode);
        return false;
      },
    );
  }

  Future<bool> loadReview() async {
    if (!hasSession) return false;
    _setBusy(true);
    final result = await _api.fetchReview(_sessionId!, _sessionToken!);
    return result.when(
      ok: (data) {
        _reviewData = data;
        _error = null;
        _setBusy(false);
        return true;
      },
      failure: (f) {
        _fail(f.message, f.errorCode);
        return false;
      },
    );
  }

  Future<bool> confirmReview() async {
    if (!hasSession) return false;
    _setBusy(true);
    final result = await _api.confirmReview(
      sessionId: _sessionId!,
      token: _sessionToken!,
    );
    return result.when(
      ok: (_) {
        _currentStep = SessionStep.commit;
        _error = null;
        _setBusy(false);
        return true;
      },
      failure: (f) {
        _fail(f.message, f.errorCode);
        return false;
      },
    );
  }

  Future<bool> commit() async {
    if (!hasSession) return false;
    _setBusy(true);
    final result = await _api.commit(
      sessionId: _sessionId!,
      token: _sessionToken!,
      idempotencyKey: _idempotencyKey,
    );
    return result.when(
      ok: (commit) {
        _commitResult = commit;
        _error = null;
        _setBusy(false);
        return true;
      },
      failure: (f) {
        _fail(f.message, f.errorCode);
        return false;
      },
    );
  }

  Future<void> cancel() async {
    if (!hasSession || isCommitted) return;
    try {
      await _api.cancel(_sessionId!, _sessionToken!);
    } catch (_) {}
  }

  void clearError() {
    _error = null;
    _errorCode = null;
    _notify();
  }

  void _setBusy(bool value) {
    _busy = value;
    _notify();
  }

  void _fail(String message, [String? code]) {
    _error = message;
    _errorCode = code;
    _busy = false;
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  static String _uuidV4() {
    final rng = Random.secure();
    String hex(int n) => List.generate(
          n,
          (_) => rng.nextInt(256).toRadixString(16).padLeft(2, '0'),
        ).join();
    return '${hex(4)}-${hex(2)}-${hex(2)}-${hex(2)}-${hex(6)}';
  }
}
