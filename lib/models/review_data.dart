/// Data langkah 3 (Periksa Ulang Data).
///
/// Ini titik pertama alur yang menampilkan data peserta sebenarnya, dan hanya
/// setelah KEDUA faktor biometrik lolos. Sebelum itu server hanya mengirim versi
/// bertopeng. NIK pun tetap dimasking di sini.
library;

class PesertaFull {
  final String namaLengkap;
  final String noBpjs;
  final String nikMasked;
  final DateTime? tanggalLahir;
  final String? jenisKelamin;
  final int? kelasRawat;
  final String? jenisPeserta;
  final String statusKepesertaan;
  final int tunggakanBulan;
  final String? faskesTingkat1;

  const PesertaFull({
    required this.namaLengkap,
    required this.noBpjs,
    required this.nikMasked,
    required this.statusKepesertaan,
    this.tanggalLahir,
    this.jenisKelamin,
    this.kelasRawat,
    this.jenisPeserta,
    this.tunggakanBulan = 0,
    this.faskesTingkat1,
  });

  factory PesertaFull.fromJson(Map<String, dynamic> json) => PesertaFull(
        namaLengkap: json['nama_lengkap'] as String? ?? '',
        noBpjs: json['no_bpjs'] as String? ?? '',
        nikMasked: json['nik_masked'] as String? ?? '',
        statusKepesertaan: json['status_kepesertaan'] as String? ?? '',
        tanggalLahir: json['tanggal_lahir'] != null
            ? DateTime.tryParse(json['tanggal_lahir'] as String)
            : null,
        jenisKelamin: json['jenis_kelamin'] as String?,
        kelasRawat: (json['kelas_rawat'] as num?)?.toInt(),
        jenisPeserta: json['jenis_peserta'] as String?,
        tunggakanBulan: (json['tunggakan_bulan'] as num?)?.toInt() ?? 0,
        faskesTingkat1: json['faskes_tingkat1'] as String?,
      );

  String get jenisKelaminLabel => switch (jenisKelamin) {
        'L' => 'Laki-laki',
        'P' => 'Perempuan',
        _ => '-',
      };

  bool get isAktif => statusKepesertaan == 'AKTIF';
}

class ReviewClaim {
  final String? claimRef;
  final String jenisLayanan;
  final String poli;
  final int estimasiBiaya;
  final String faskes;

  const ReviewClaim({
    required this.jenisLayanan,
    required this.poli,
    required this.estimasiBiaya,
    required this.faskes,
    this.claimRef,
  });

  factory ReviewClaim.fromJson(Map<String, dynamic> json) => ReviewClaim(
        claimRef: json['claim_ref'] as String?,
        jenisLayanan: json['jenis_layanan'] as String? ?? '',
        poli: json['poli'] as String? ?? '',
        estimasiBiaya: (json['estimasi_biaya'] as num?)?.toInt() ?? 0,
        faskes: json['faskes'] as String? ?? '',
      );

  String get jenisLayananLabel => switch (jenisLayanan) {
        'RAWAT_JALAN' => 'Rawat Jalan',
        'RAWAT_INAP' => 'Rawat Inap',
        'IGD' => 'Gawat Darurat',
        'FARMASI' => 'Farmasi',
        _ => jenisLayanan,
      };
}

class ReviewData {
  final PesertaFull peserta;
  final ReviewClaim claim;
  final Map<String, dynamic> wajah;
  final Map<String, dynamic> sidikJari;
  final Map<String, dynamic> risk;

  const ReviewData({
    required this.peserta,
    required this.claim,
    required this.wajah,
    required this.sidikJari,
    required this.risk,
  });

  factory ReviewData.fromJson(Map<String, dynamic> json) {
    final bio = (json['biometrik'] as Map?)?.cast<String, dynamic>() ?? const {};
    return ReviewData(
      peserta: PesertaFull.fromJson(json['peserta'] as Map<String, dynamic>),
      claim: ReviewClaim.fromJson(json['claim'] as Map<String, dynamic>),
      wajah: (bio['wajah'] as Map?)?.cast<String, dynamic>() ?? const {},
      sidikJari: (bio['sidik_jari'] as Map?)?.cast<String, dynamic>() ?? const {},
      risk: (json['risk'] as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }
}

class CommitResult {
  /// APPROVED | REVIEW | REJECTED
  final String decision;
  final String? receiptNo;
  final DateTime decidedAt;
  final int riskScore;
  final String riskBand;
  final List<FraudSignal> signals;
  final Map<String, dynamic> summary;

  const CommitResult({
    required this.decision,
    required this.decidedAt,
    required this.riskScore,
    required this.riskBand,
    this.receiptNo,
    this.signals = const [],
    this.summary = const {},
  });

  factory CommitResult.fromJson(Map<String, dynamic> json) {
    final risk = (json['risk'] as Map?)?.cast<String, dynamic>() ?? const {};
    return CommitResult(
      decision: json['decision'] as String? ?? 'REVIEW',
      receiptNo: json['receipt_no'] as String?,
      decidedAt: DateTime.parse(json['decided_at'] as String),
      riskScore: (risk['score'] as num?)?.toInt() ?? 0,
      riskBand: risk['band'] as String? ?? 'LOW',
      signals: ((risk['signals'] as List?) ?? const [])
          .map((s) => FraudSignal.fromJson((s as Map).cast<String, dynamic>()))
          .toList(),
      summary: (json['summary'] as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }

  bool get isApproved => decision == 'APPROVED';
  bool get isRejected => decision == 'REJECTED';
  bool get needsReview => decision == 'REVIEW';
}

class FraudSignal {
  final String ruleId;
  final String severity;
  final int weight;
  final String title;
  final Map<String, dynamic> detail;

  const FraudSignal({
    required this.ruleId,
    required this.severity,
    required this.weight,
    required this.title,
    this.detail = const {},
  });

  factory FraudSignal.fromJson(Map<String, dynamic> json) => FraudSignal(
        ruleId: json['rule_id'] as String? ?? '',
        severity: json['severity'] as String? ?? 'info',
        weight: (json['weight'] as num?)?.toInt() ?? 0,
        title: json['title'] as String? ?? '',
        detail: (json['detail'] as Map?)?.cast<String, dynamic>() ?? const {},
      );

  bool get isCritical => severity == 'critical';
}
