/// Hasil tiap langkah biometrik.
///
/// Semua ini datang sebagai HTTP 200 walaupun [passed] bernilai false: wajah
/// yang tidak cocok adalah keputusan sistem yang benar, bukan error, dan UI
/// harus menampilkan skor serta sisa percobaannya.
library;

class LivenessInfo {
  final bool passed;
  final double score;
  final String method;
  final Map<String, double> signals;
  final String? reason;

  const LivenessInfo({
    required this.passed,
    required this.score,
    required this.method,
    this.signals = const {},
    this.reason,
  });

  factory LivenessInfo.fromJson(Map<String, dynamic> json) => LivenessInfo(
        passed: json['passed'] as bool? ?? false,
        score: (json['score'] as num?)?.toDouble() ?? 0,
        method: json['method'] as String? ?? '',
        signals: ((json['signals'] as Map?) ?? const {})
            .map((k, v) => MapEntry(k as String, (v as num).toDouble())),
        reason: json['reason'] as String?,
      );
}

class FaceQuality {
  final double blurVar;
  final double brightness;
  final int facePx;
  final double detScore;

  const FaceQuality({
    this.blurVar = 0,
    this.brightness = 0,
    this.facePx = 0,
    this.detScore = 0,
  });

  factory FaceQuality.fromJson(Map<String, dynamic> json) => FaceQuality(
        blurVar: (json['blur_var'] as num?)?.toDouble() ?? 0,
        brightness: (json['brightness'] as num?)?.toDouble() ?? 0,
        facePx: (json['face_px'] as num?)?.toInt() ?? 0,
        detScore: (json['det_score'] as num?)?.toDouble() ?? 0,
      );
}

class FaceStepResult {
  final bool passed;
  final String? errorCode;
  final String? message;
  final double? matchScore;
  final double? threshold;
  final LivenessInfo? liveness;
  final FaceQuality? quality;
  final int? latencyMs;
  final int? attemptsUsed;
  final int? attemptsLeft;

  /// Nonce baru untuk langkah sidik jari, hanya ada kalau langkah ini lolos.
  final String? nonce;

  const FaceStepResult({
    required this.passed,
    this.errorCode,
    this.message,
    this.matchScore,
    this.threshold,
    this.liveness,
    this.quality,
    this.latencyMs,
    this.attemptsUsed,
    this.attemptsLeft,
    this.nonce,
  });

  factory FaceStepResult.fromJson(Map<String, dynamic> json) => FaceStepResult(
        passed: json['result'] == 'passed',
        errorCode: json['error_code'] as String?,
        message: json['message'] as String?,
        matchScore: (json['match_score'] as num?)?.toDouble(),
        threshold: (json['threshold'] as num?)?.toDouble(),
        liveness: json['liveness'] != null
            ? LivenessInfo.fromJson(json['liveness'] as Map<String, dynamic>)
            : null,
        quality: json['quality'] != null
            ? FaceQuality.fromJson(json['quality'] as Map<String, dynamic>)
            : null,
        latencyMs: (json['latency_ms'] as num?)?.toInt(),
        attemptsUsed: (json['attempts_used'] as num?)?.toInt(),
        attemptsLeft: (json['attempts_left'] as num?)?.toInt(),
        nonce: json['nonce'] as String?,
      );

  /// Batas percobaan habis: sesi sudah ditolak server, tidak bisa diulang.
  bool get isExhausted => errorCode == 'MAX_ATTEMPTS' || attemptsLeft == 0;
}

class FingerprintStepResult {
  final bool passed;
  final String? errorCode;
  final String? message;
  final bool signatureVerified;

  /// TEE / STRONGBOX / SOFTWARE. SOFTWARE berarti jalur HMAC tanpa pengikatan
  /// perangkat keras, dan memicu sinyal fraud SOFTWARE_KEY_ONLY.
  final String? securityLevel;

  final int? attemptsUsed;
  final int? attemptsLeft;

  const FingerprintStepResult({
    required this.passed,
    this.errorCode,
    this.message,
    this.signatureVerified = false,
    this.securityLevel,
    this.attemptsUsed,
    this.attemptsLeft,
  });

  factory FingerprintStepResult.fromJson(Map<String, dynamic> json) =>
      FingerprintStepResult(
        passed: json['result'] == 'passed',
        errorCode: json['error_code'] as String?,
        message: json['message'] as String?,
        signatureVerified: json['signature_verified'] as bool? ?? false,
        securityLevel: json['security_level'] as String?,
        attemptsUsed: (json['attempts_used'] as num?)?.toInt(),
        attemptsLeft: (json['attempts_left'] as num?)?.toInt(),
      );

  bool get isHardwareBacked =>
      securityLevel == 'TEE' || securityLevel == 'STRONGBOX';

  /// Batas percobaan habis: server sudah menolak sesi, tidak bisa diulang.
  bool get isExhausted => errorCode == 'MAX_ATTEMPTS' || attemptsLeft == 0;
}

class LivenessChallenge {
  final String challengeId;
  final String challenge;
  final String instruction;
  final DateTime expiresAt;

  const LivenessChallenge({
    required this.challengeId,
    required this.challenge,
    required this.instruction,
    required this.expiresAt,
  });

  factory LivenessChallenge.fromJson(Map<String, dynamic> json) => LivenessChallenge(
        challengeId: json['challenge_id'] as String,
        challenge: json['challenge'] as String,
        instruction: json['instruction'] as String,
        expiresAt: DateTime.parse(json['expires_at'] as String),
      );
}
