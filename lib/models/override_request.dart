/// Override petugas (break-glass) ketika biometrik memang tidak bisa lolos.
///
/// Ini bukan jalan pintas. Alur normal tiga kali gagal lalu berhenti, dan itu
/// berarti pasien dengan wajah memar atau jari luka bakar ditolak - justru
/// kelompok yang paling membutuhkan layanan. Override ada untuk itu, dan
/// sengaja dibuat lebih mahal serta lebih terlihat daripada alur normal:
/// dua petugas berbeda, alasan dari daftar tertutup, dan bukti foto.
library;

enum OverrideReason {
  cederaWajah('CEDERA_WAJAH', 'Wajah cedera / memar / bengkak'),
  lukaBakarJari('LUKA_BAKAR_JARI', 'Sidik jari tidak terbaca (luka bakar)'),
  disabilitas('DISABILITAS', 'Keterbatasan fisik peserta'),
  kegagalanPerangkat('KEGAGALAN_PERANGKAT', 'Perangkat / sensor bermasalah'),
  pencahayaanBuruk('PENCAHAYAAN_BURUK', 'Pencahayaan tidak memadai'),
  lainnya('LAINNYA', 'Lainnya (wajib dijelaskan)');

  const OverrideReason(this.code, this.label);

  final String code;
  final String label;

  /// Hanya LAINNYA yang mewajibkan penjelasan bebas. Alasan lain sudah cukup
  /// spesifik untuk dianalisis lintas petugas dan faskes.
  bool get requiresNote => this == OverrideReason.lainnya;

  static OverrideReason? fromCode(String? code) {
    if (code == null) return null;
    for (final r in OverrideReason.values) {
      if (r.code == code) return r;
    }
    return null;
  }
}

enum OverrideStatus {
  pending,
  approved,
  rejected;

  static OverrideStatus? fromWire(String? value) => switch (value) {
        'pending' => OverrideStatus.pending,
        'approved' => OverrideStatus.approved,
        'rejected' => OverrideStatus.rejected,
        _ => null,
      };
}

class OverrideRecord {
  final OverrideStatus? status;
  final OverrideReason? reason;
  final String? reasonNote;
  final String? requestedByNama;
  final DateTime? requestedAt;
  final String? approvedByNama;
  final DateTime? approvedAt;

  /// Label bukti yang terlampir ('bpjs_card', 'ktp'). Blob-nya sendiri tidak
  /// pernah dikirim ke klien - hanya dibaca lewat konsol auditor.
  final List<String> evidenceAttached;

  /// Ringkasan mengapa biometrik gagal, supaya peninjau tidak perlu
  /// merekonstruksinya dari log kejadian.
  final Map<String, dynamic> failedEvidence;

  const OverrideRecord({
    this.status,
    this.reason,
    this.reasonNote,
    this.requestedByNama,
    this.requestedAt,
    this.approvedByNama,
    this.approvedAt,
    this.evidenceAttached = const [],
    this.failedEvidence = const {},
  });

  factory OverrideRecord.fromJson(Map<String, dynamic> json) => OverrideRecord(
        status: OverrideStatus.fromWire(json['status'] as String?),
        reason: OverrideReason.fromCode(json['reason_code'] as String?),
        reasonNote: json['reason_note'] as String?,
        requestedByNama: json['requested_by_nama'] as String?,
        requestedAt: json['requested_at'] != null
            ? DateTime.tryParse(json['requested_at'] as String)
            : null,
        approvedByNama: json['approved_by_nama'] as String?,
        approvedAt: json['approved_at'] != null
            ? DateTime.tryParse(json['approved_at'] as String)
            : null,
        evidenceAttached:
            ((json['evidence_attached'] as List?) ?? const []).cast<String>(),
        failedEvidence:
            (json['failed_evidence'] as Map?)?.cast<String, dynamic>() ?? const {},
      );

  bool get isPending => status == OverrideStatus.pending;
  bool get isApproved => status == OverrideStatus.approved;
}

/// Sesi petugas. Token disimpan di memori saja, tidak pernah ke disk - petugas
/// login ulang setiap shift, dan token yang tertinggal di penyimpanan perangkat
/// adalah kredensial yang bisa dipakai orang lain di meja yang sama.
class StaffSession {
  final String token;
  final String staffId;
  final String nama;
  final String role;

  const StaffSession({
    required this.token,
    required this.staffId,
    required this.nama,
    required this.role,
  });

  factory StaffSession.fromJson(Map<String, dynamic> json) {
    final staff = (json['staff'] as Map?)?.cast<String, dynamic>() ?? const {};
    return StaffSession(
      token: json['token'] as String,
      staffId: staff['staff_id'] as String? ?? '',
      nama: staff['nama'] as String? ?? '',
      role: staff['role'] as String? ?? '',
    );
  }

  bool get isSupervisor => role == 'supervisor' || role == 'admin';
}
