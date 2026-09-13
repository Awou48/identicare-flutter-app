library;

enum SessionStep {
  face('face', 'Scan Wajah'),
  fingerprint('fingerprint', 'Scan Sidik Jari'),
  review('review', 'Periksa Ulang Data'),
  commit('commit', 'Verifikasi Data');

  const SessionStep(this.wire, this.label);

  final String wire;

  final String label;

  static SessionStep? fromWire(String? value) {
    if (value == null) return null;
    for (final step in SessionStep.values) {
      if (step.wire == value) return step;
    }
    return null;
  }

  int get index0 => SessionStep.values.indexOf(this);
}

enum SessionStatus {
  created,
  facePassed,
  fingerprintPassed,
  reviewed,
  committed,
  rejected,
  expired,
  cancelled;

  static SessionStatus fromWire(String value) => switch (value) {
        'created' => SessionStatus.created,
        'face_passed' => SessionStatus.facePassed,
        'fingerprint_passed' => SessionStatus.fingerprintPassed,
        'reviewed' => SessionStatus.reviewed,
        'committed' => SessionStatus.committed,
        'rejected' => SessionStatus.rejected,
        'expired' => SessionStatus.expired,
        _ => SessionStatus.cancelled,
      };

  bool get isTerminal => const {
        SessionStatus.committed,
        SessionStatus.rejected,
        SessionStatus.expired,
        SessionStatus.cancelled,
      }.contains(this);
}

class PesertaPreview {
  final String namaMasked;
  final String noBpjsMasked;
  final bool biometricEnrolled;

  const PesertaPreview({
    required this.namaMasked,
    required this.noBpjsMasked,
    required this.biometricEnrolled,
  });

  factory PesertaPreview.fromJson(Map<String, dynamic> json) => PesertaPreview(
        namaMasked: json['nama_masked'] as String? ?? '',
        noBpjsMasked: json['no_bpjs_masked'] as String? ?? '',
        biometricEnrolled: json['biometric_enrolled'] as bool? ?? false,
      );
}

class VerificationSession {
  final String sessionId;

  final String sessionToken;

  final DateTime expiresAt;
  final List<String> requiredSteps;
  final SessionStep? currentStep;

  final String? nonce;
  final DateTime? nonceExpiresAt;

  final PesertaPreview? pesertaPreview;

  const VerificationSession({
    required this.sessionId,
    required this.sessionToken,
    required this.expiresAt,
    required this.requiredSteps,
    required this.currentStep,
    this.nonce,
    this.nonceExpiresAt,
    this.pesertaPreview,
  });

  factory VerificationSession.fromJson(Map<String, dynamic> json) {
    return VerificationSession(
      sessionId: json['session_id'] as String,
      sessionToken: json['session_token'] as String,
      expiresAt: DateTime.parse(json['expires_at'] as String),
      requiredSteps: (json['required_steps'] as List?)?.cast<String>() ??
          const ['face', 'fingerprint', 'review'],
      currentStep: SessionStep.fromWire(json['current_step'] as String?),
      nonce: json['nonce'] as String?,
      nonceExpiresAt: json['nonce_expires_at'] != null
          ? DateTime.parse(json['nonce_expires_at'] as String)
          : null,
      pesertaPreview: json['peserta_preview'] != null
          ? PesertaPreview.fromJson(
              json['peserta_preview'] as Map<String, dynamic>)
          : null,
    );
  }

  Duration get remaining => expiresAt.difference(DateTime.now().toUtc());
  bool get isExpired => remaining.isNegative;
}

class SessionState {
  final String sessionId;
  final SessionStatus status;
  final SessionStep? currentStep;
  final DateTime expiresAt;
  final Map<String, dynamic> steps;
  final Map<String, dynamic> risk;
  final Map<String, dynamic>? result;

  const SessionState({
    required this.sessionId,
    required this.status,
    required this.currentStep,
    required this.expiresAt,
    required this.steps,
    required this.risk,
    this.result,
  });

  factory SessionState.fromJson(Map<String, dynamic> json) => SessionState(
        sessionId: json['session_id'] as String,
        status: SessionStatus.fromWire(json['status'] as String),
        currentStep: SessionStep.fromWire(json['current_step'] as String?),
        expiresAt: DateTime.parse(json['expires_at'] as String),
        steps: (json['steps'] as Map?)?.cast<String, dynamic>() ?? const {},
        risk: (json['risk'] as Map?)?.cast<String, dynamic>() ?? const {},
        result: (json['result'] as Map?)?.cast<String, dynamic>(),
      );
}
