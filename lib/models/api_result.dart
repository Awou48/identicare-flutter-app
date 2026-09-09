/// Hasil pemanggilan API: berhasil, gagal karena aturan bisnis, atau error.
///
/// Backend sengaja membedakan dua hal (lihat backend/README.md):
///   * Error protokol  -> HTTP 4xx/5xx  -> [ApiFailure]
///   * Hasil bisnis    -> HTTP 200 dengan result:"failed" -> [Ok] berisi data
///     yang statusnya "failed"
///
/// Kegagalan verifikasi wajah BUKAN error. UI harus menampilkan skornya dan sisa
/// percobaan, jadi ia tetap datang sebagai [Ok] dan bukan [ApiFailure].
sealed class ApiResult<T> {
  const ApiResult();

  bool get isOk => this is Ok<T>;

  T? get valueOrNull => switch (this) {
        Ok<T>(value: final v) => v,
        ApiFailure<T>() => null,
      };

  R when<R>({
    required R Function(T value) ok,
    required R Function(ApiFailure<T> failure) failure,
  }) {
    return switch (this) {
      Ok<T>(value: final v) => ok(v),
      ApiFailure<T> f => failure(f),
    };
  }
}

class Ok<T> extends ApiResult<T> {
  final T value;
  const Ok(this.value);
}

class ApiFailure<T> extends ApiResult<T> {
  /// Kode mesin, mis. SESSION_EXPIRED. Dipakai untuk logika, bukan ditampilkan.
  final String errorCode;

  /// Pesan bahasa Indonesia dari server, aman untuk ditampilkan ke pengguna.
  final String message;

  final int? statusCode;
  final String? requestId;
  final Map<String, dynamic> details;

  const ApiFailure({
    required this.errorCode,
    required this.message,
    this.statusCode,
    this.requestId,
    this.details = const {},
  });

  /// Tidak ada koneksi ke server sama sekali.
  bool get isNetworkError => errorCode == 'NETWORK_ERROR';

  /// Sesi kedaluwarsa atau sudah ditutup: alur harus diulang dari awal.
  bool get isSessionGone =>
      errorCode == 'SESSION_EXPIRED' ||
      errorCode == 'SESSION_NOT_FOUND' ||
      errorCode == 'SESSION_CLOSED';

  @override
  String toString() => 'ApiFailure($errorCode: $message)';
}
