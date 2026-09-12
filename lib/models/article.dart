/// Artikel kesehatan, dari MongoDB lewat API.
///
/// Menggantikan satu artikel yang di-hardcode di home_page.dart beserta URL
/// gambar Unsplash-nya - mengubah isinya dulu berarti merilis ulang aplikasi.
library;

class Article {
  final String slug;
  final String judul;
  final String ringkasan;
  final String kategori;
  final String? imageUrl;
  final String? penulis;
  final DateTime? publishedAt;
  final int readingMinutes;
  final bool featured;

  /// Hanya terisi pada endpoint detail; daftar tidak mengirim isi penuh.
  final String? konten;
  final String? sumber;

  const Article({
    required this.slug,
    required this.judul,
    required this.ringkasan,
    required this.kategori,
    this.imageUrl,
    this.penulis,
    this.publishedAt,
    this.readingMinutes = 1,
    this.featured = false,
    this.konten,
    this.sumber,
  });

  factory Article.fromJson(Map<String, dynamic> json) => Article(
        slug: json['slug'] as String,
        judul: json['judul'] as String? ?? '',
        ringkasan: json['ringkasan'] as String? ?? '',
        kategori: json['kategori'] as String? ?? '',
        imageUrl: json['image_url'] as String?,
        penulis: json['penulis'] as String?,
        publishedAt: json['published_at'] != null
            ? DateTime.tryParse(json['published_at'] as String)
            : null,
        readingMinutes: (json['reading_minutes'] as num?)?.toInt() ?? 1,
        featured: json['featured'] as bool? ?? false,
        konten: json['konten'] as String?,
        sumber: json['sumber'] as String?,
      );
}

class ArticlePage {
  final List<Article> items;
  final int total;
  final bool hasMore;

  const ArticlePage({required this.items, this.total = 0, this.hasMore = false});

  factory ArticlePage.fromJson(Map<String, dynamic> json) => ArticlePage(
        items: ((json['items'] as List?) ?? const [])
            .map((e) => Article.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        total: (json['total'] as num?)?.toInt() ?? 0,
        hasMore: json['has_more'] as bool? ?? false,
      );
}

/// Status peserta milik pengguna yang sedang login.
class PesertaStatus {
  final String namaLengkap;
  final String noBpjsMasked;
  final String? statusKepesertaan;
  final int? kelasRawat;
  final String? jenisPeserta;
  final int tunggakanBulan;
  final String? faskesTingkat1;
  final bool biometricEnrolled;
  final DateTime? biometricEnrolledAt;

  /// SELF_ASSERTED / DUKCAPIL_VERIFIED / ASSISTED_DUAL_CONTROL, atau null untuk
  /// template yang mendahului pipeline identity-proofing.
  final String? assurance;

  const PesertaStatus({
    required this.namaLengkap,
    required this.noBpjsMasked,
    required this.biometricEnrolled,
    this.statusKepesertaan,
    this.kelasRawat,
    this.jenisPeserta,
    this.tunggakanBulan = 0,
    this.faskesTingkat1,
    this.biometricEnrolledAt,
    this.assurance,
  });

  factory PesertaStatus.fromJson(Map<String, dynamic> json) => PesertaStatus(
        namaLengkap: json['nama_lengkap'] as String? ?? '',
        noBpjsMasked: json['no_bpjs_masked'] as String? ?? '',
        biometricEnrolled: json['biometric_enrolled'] as bool? ?? false,
        statusKepesertaan: json['status_kepesertaan'] as String?,
        kelasRawat: (json['kelas_rawat'] as num?)?.toInt(),
        jenisPeserta: json['jenis_peserta'] as String?,
        tunggakanBulan: (json['tunggakan_bulan'] as num?)?.toInt() ?? 0,
        faskesTingkat1: json['faskes_tingkat1'] as String?,
        biometricEnrolledAt: json['biometric_enrolled_at'] != null
            ? DateTime.tryParse(json['biometric_enrolled_at'] as String)
            : null,
        assurance: json['assurance'] as String?,
      );

  String get assuranceLabel => switch (assurance) {
        'DUKCAPIL_VERIFIED' => 'Terverifikasi Dukcapil',
        'ASSISTED_DUAL_CONTROL' => 'Terverifikasi Petugas',
        'SELF_ASSERTED' => 'Pendaftaran Mandiri',
        _ => 'Tingkat verifikasi tidak diketahui',
      };
}
