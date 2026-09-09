/// Riwayat verifikasi: tanggal, metode, status, lokasi.
///
/// Ini yang menggantikan koleksi hardcoded di aplikasi lama. Sumbernya MongoDB
/// lewat API Python, terpisah dari `riwayat_konsultasi` yang tetap di Firestore.
library;

class VerificationHistoryEntry {
  final String sessionId;
  final String? receiptNo;
  final DateTime tanggal;

  /// ['wajah', 'sidik_jari']
  final List<String> metode;

  /// APPROVED | REVIEW | REJECTED
  final String status;

  final String? faskes;
  final String? kodeFaskes;
  final double? skorWajah;
  final double? skorLiveness;
  final String riskBand;

  const VerificationHistoryEntry({
    required this.sessionId,
    required this.tanggal,
    required this.status,
    required this.metode,
    required this.riskBand,
    this.receiptNo,
    this.faskes,
    this.kodeFaskes,
    this.skorWajah,
    this.skorLiveness,
  });

  factory VerificationHistoryEntry.fromJson(Map<String, dynamic> json) {
    final lokasi = (json['lokasi'] as Map?)?.cast<String, dynamic>() ?? const {};
    final skor = (json['skor'] as Map?)?.cast<String, dynamic>() ?? const {};
    return VerificationHistoryEntry(
      sessionId: json['session_id'] as String,
      receiptNo: json['receipt_no'] as String?,
      tanggal: DateTime.parse(json['tanggal'] as String),
      metode: ((json['metode'] as List?) ?? const []).cast<String>(),
      status: json['status'] as String? ?? '',
      faskes: lokasi['faskes'] as String?,
      kodeFaskes: lokasi['kode_faskes'] as String?,
      skorWajah: (skor['wajah'] as num?)?.toDouble(),
      skorLiveness: (skor['liveness'] as num?)?.toDouble(),
      riskBand: json['risk_band'] as String? ?? 'LOW',
    );
  }

  String get metodeLabel => metode
      .map((m) => switch (m) {
            'wajah' => 'Wajah',
            'sidik_jari' => 'Sidik Jari',
            _ => m,
          })
      .join(' + ');

  String get statusLabel => switch (status) {
        'APPROVED' => 'Disetujui',
        'REVIEW' => 'Ditinjau',
        'REJECTED' => 'Ditolak',
        _ => status,
      };
}

class VerificationHistoryPage {
  final List<VerificationHistoryEntry> items;

  /// Kursor untuk halaman berikutnya. Bukan offset: paging berbasis offset akan
  /// melewatkan atau menggandakan baris kalau ada data baru masuk di tengah.
  final String? nextCursor;
  final bool hasMore;

  const VerificationHistoryPage({
    required this.items,
    this.nextCursor,
    this.hasMore = false,
  });

  factory VerificationHistoryPage.fromJson(Map<String, dynamic> json) =>
      VerificationHistoryPage(
        items: ((json['items'] as List?) ?? const [])
            .map((e) =>
                VerificationHistoryEntry.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        nextCursor: json['next_cursor'] as String?,
        hasMore: json['has_more'] as bool? ?? false,
      );
}

/// Satu baris jejak audit di halaman detail.
class VerificationEvent {
  final int seq;
  final String step;
  final String outcome;
  final String? method;
  final Map<String, dynamic> scores;
  final String? errorCode;
  final int? latencyMs;
  final DateTime at;

  const VerificationEvent({
    required this.seq,
    required this.step,
    required this.outcome,
    required this.at,
    this.method,
    this.scores = const {},
    this.errorCode,
    this.latencyMs,
  });

  factory VerificationEvent.fromJson(Map<String, dynamic> json) => VerificationEvent(
        seq: (json['seq'] as num).toInt(),
        step: json['step'] as String,
        outcome: json['outcome'] as String,
        method: json['method'] as String?,
        scores: (json['scores'] as Map?)?.cast<String, dynamic>() ?? const {},
        errorCode: json['error_code'] as String?,
        latencyMs: (json['latency_ms'] as num?)?.toInt(),
        at: DateTime.parse(json['at'] as String),
      );

  bool get isFailure => outcome == 'failed';

  String get stepLabel => switch (step) {
        'session' => 'Sesi',
        'face' => 'Scan Wajah',
        'fingerprint' => 'Scan Sidik Jari',
        'review' => 'Periksa Data',
        'commit' => 'Verifikasi',
        _ => step,
      };
}
