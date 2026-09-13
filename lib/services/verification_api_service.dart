import 'package:identicare_mobile/config/app_config.dart';
import 'package:identicare_mobile/models/api_result.dart';
import 'package:identicare_mobile/models/article.dart';
import 'package:identicare_mobile/models/override_request.dart';
import 'package:identicare_mobile/models/review_data.dart';
import 'package:identicare_mobile/models/step_results.dart';
import 'package:identicare_mobile/models/verification_history.dart';
import 'package:identicare_mobile/models/verification_session.dart';
import 'package:identicare_mobile/services/identicare_api_client.dart';

class VerificationApiService {
  VerificationApiService(this._client);

  final IdenticareApiClient _client;

  Future<ApiResult<VerificationSession>> startSession({
    required String noBpjs,
    required String kodeFaskes,
    required Map<String, dynamic> device,
    String jenisLayanan = 'RAWAT_JALAN',
    String poli = '',
    int estimasiBiaya = 0,
  }) async {
    final result = await _client.postJson(
      '/verification/sessions',
      includeFaskesKey: true,
      body: {
        'no_bpjs': noBpjs,
        'kode_faskes': kodeFaskes,
        'claim': {
          'jenis_layanan': jenisLayanan,
          'poli': poli,
          'estimasi_biaya': estimasiBiaya,
        },
        'device': device,
      },
    );
    return _map(result, VerificationSession.fromJson);
  }

  Future<ApiResult<Map<String, dynamic>>> enrollDevice(
      Map<String, dynamic> payload) {
    return _client.postJson('/enrollment/device', body: payload);
  }

  Future<ApiResult<SessionState>> getSession(
      String sessionId, String token) async {
    final result = await _client.getJson(
      '/verification/sessions/$sessionId',
      sessionToken: token,
    );
    return _map(result, SessionState.fromJson);
  }

  Future<ApiResult<LivenessChallenge>> requestChallenge(
    String sessionId,
    String token,
  ) async {
    final result = await _client.postJson(
      '/verification/sessions/$sessionId/liveness/challenge',
      sessionToken: token,
    );
    return _map(result, LivenessChallenge.fromJson);
  }

  Future<ApiResult<FaceStepResult>> submitFace({
    required String sessionId,
    required String token,
    required List<List<int>> frames,
    Map<String, dynamic> meta = const {},
  }) async {
    final result = await _client.postMultipart(
      '/verification/sessions/$sessionId/face',
      sessionToken: token,
      files: frames,
      fields: {'meta': _encodeMeta(meta)},
    );
    return _map(result, FaceStepResult.fromJson);
  }

  Future<ApiResult<FingerprintStepResult>> submitFingerprint({
    required String sessionId,
    required String token,
    required String method,
    required String nonce,
    required int timestamp,
    required String signatureB64,
    required String deviceUid,
    String? keyAlias,
  }) async {
    final result = await _client.postJson(
      '/verification/sessions/$sessionId/fingerprint',
      sessionToken: token,
      body: {
        'method': method,
        'nonce': nonce,
        'timestamp': timestamp,
        'signature_b64': signatureB64,
        'device_uid': deviceUid,
        if (keyAlias != null) 'key_alias': keyAlias,
        'biometric_type': 'fingerprint',
      },
    );
    return _map(result, FingerprintStepResult.fromJson);
  }

  Future<ApiResult<ReviewData>> fetchReview(
      String sessionId, String token) async {
    final result = await _client.getJson(
      '/verification/sessions/$sessionId/review',
      sessionToken: token,
    );
    return _map(result, ReviewData.fromJson);
  }

  Future<ApiResult<Map<String, dynamic>>> confirmReview({
    required String sessionId,
    required String token,
    Map<String, dynamic> corrections = const {},
  }) {
    return _client.postJson(
      '/verification/sessions/$sessionId/review',
      sessionToken: token,
      body: {'confirmed': true, 'corrections': corrections},
    );
  }

  Future<ApiResult<CommitResult>> commit({
    required String sessionId,
    required String token,
    required String idempotencyKey,
  }) async {
    final result = await _client.postJson(
      '/verification/sessions/$sessionId/commit',
      sessionToken: token,
      body: {'idempotency_key': idempotencyKey},
    );
    return _map(result, CommitResult.fromJson);
  }

  Future<ApiResult<Map<String, dynamic>>> cancel(
      String sessionId, String token) {
    return _client.postJson(
      '/verification/sessions/$sessionId/cancel',
      sessionToken: token,
    );
  }

  Future<ApiResult<VerificationHistoryPage>> fetchHistory({
    int limit = 20,
    String? cursor,
    String? status,
  }) async {
    final result = await _client.getJson('/verification/history', query: {
      'limit': '$limit',
      if (cursor != null) 'cursor': cursor,
      if (status != null) 'status': status,
    });
    return _map(result, VerificationHistoryPage.fromJson);
  }

  Future<ApiResult<Map<String, dynamic>>> fetchHistoryDetail(String sessionId) {
    return _client.getJson('/verification/history/$sessionId');
  }

  Future<ApiResult<List<String>>> fetchSymptomCatalog() async {
    final result = await _client.getJson('/symptoms/catalog');
    return _map(result,
        (json) => ((json['gejala'] as List?) ?? const []).cast<String>());
  }

  Future<ApiResult<Map<String, dynamic>>> analyzeSymptoms(List<String> gejala) {
    return _client.postJson('/symptoms/analyze', body: {'gejala': gejala});
  }

  Future<ApiResult<StaffSession>> staffLogin({
    required String nip,
    required String password,
  }) async {
    final result = await _client.postJson(
      '/staff/login',
      body: {'nip': nip, 'password': password},
    );
    return _map(result, StaffSession.fromJson);
  }

  Future<ApiResult<Map<String, dynamic>>> requestOverride({
    required String sessionId,
    required String sessionToken,
    required String staffToken,
    required OverrideReason reason,
    String note = '',
    List<int>? evidenceBpjs,
    List<int>? evidenceKtp,
  }) {
    return _client.postMultipart(
      '/verification/sessions/$sessionId/override/request',
      sessionToken: sessionToken,
      staffToken: staffToken,
      namedFiles: {
        if (evidenceBpjs != null) 'evidence_bpjs': evidenceBpjs,
        if (evidenceKtp != null) 'evidence_ktp': evidenceKtp,
      },
      fields: {'reason_code': reason.code, 'reason_note': note},
    );
  }

  Future<ApiResult<Map<String, dynamic>>> approveOverride({
    required String sessionId,
    required String sessionToken,
    required String supervisorToken,
    String note = '',
  }) {
    return _client.postJson(
      '/verification/sessions/$sessionId/override/approve',
      sessionToken: sessionToken,
      staffToken: supervisorToken,
      body: {'note': note},
    );
  }

  Future<ApiResult<Map<String, dynamic>>> rejectOverride({
    required String sessionId,
    required String sessionToken,
    required String supervisorToken,
    String note = '',
  }) {
    return _client.postJson(
      '/verification/sessions/$sessionId/override/reject',
      sessionToken: sessionToken,
      staffToken: supervisorToken,
      body: {'note': note},
    );
  }

  Future<ApiResult<OverrideRecord>> fetchOverride({
    required String sessionId,
    required String sessionToken,
  }) async {
    final result = await _client.getJson(
      '/verification/sessions/$sessionId/override',
      sessionToken: sessionToken,
    );
    return _map(
      result,
      (json) => OverrideRecord.fromJson(
        (json['override'] as Map).cast<String, dynamic>(),
      ),
    );
  }

  Future<ApiResult<ArticlePage>> fetchArticles({
    int limit = 20,
    int skip = 0,
    String? kategori,
    bool featuredOnly = false,
    String? query,
  }) async {
    final result = await _client.getJson('/articles', query: {
      'limit': '$limit',
      'skip': '$skip',
      if (kategori != null) 'kategori': kategori,
      if (featuredOnly) 'featured_only': 'true',
      if (query != null && query.isNotEmpty) 'q': query,
    });
    return _map(result, ArticlePage.fromJson);
  }

  Future<ApiResult<Article>> fetchArticle(String slug) async {
    final result = await _client.getJson('/articles/$slug');
    return _map(
      result,
      (json) =>
          Article.fromJson((json['article'] as Map).cast<String, dynamic>()),
    );
  }

  Future<ApiResult<List<String>>> fetchArticleCategories() async {
    final result = await _client.getJson('/articles/categories');
    return _map(result,
        (json) => ((json['kategori'] as List?) ?? const []).cast<String>());
  }

  Future<ApiResult<PesertaStatus>> pesertaMe() async {
    final result = await _client.getJson('/peserta/me');
    return _map(result, PesertaStatus.fromJson);
  }

  Future<ApiResult<Map<String, dynamic>>> linkBpjs({
    required String noBpjs,
    required String nik,
    required String tanggalLahir,
  }) {
    return _client.postJson('/peserta/link', body: {
      'no_bpjs': noBpjs,
      'nik': nik,
      'tanggal_lahir': tanggalLahir,
    });
  }

  Future<ApiResult<Map<String, dynamic>>> enrollSelf(List<List<int>> frames) {
    return _client.postMultipart('/enrollment/self', files: frames);
  }

  Future<ApiResult<Map<String, dynamic>>> health() => _client.health();

  ApiResult<T> _map<T>(
    ApiResult<Map<String, dynamic>> result,
    T Function(Map<String, dynamic>) parse,
  ) {
    return result.when(
      ok: (json) {
        try {
          return Ok(parse(json));
        } catch (e) {
          return ApiFailure<T>(
            errorCode: 'PARSE_ERROR',
            message: 'Format data dari server tidak sesuai.',
            details: {'detail': e.toString()},
          );
        }
      },
      failure: (f) => ApiFailure<T>(
        errorCode: f.errorCode,
        message: f.message,
        statusCode: f.statusCode,
        requestId: f.requestId,
        details: f.details,
      ),
    );
  }

  String _encodeMeta(Map<String, dynamic> meta) {
    if (meta.isEmpty) return '{}';
    final buffer = StringBuffer('{');
    var first = true;
    meta.forEach((key, value) {
      if (!first) buffer.write(',');
      first = false;
      buffer.write('"$key":');
      if (value is String) {
        buffer.write('"$value"');
      } else if (value is List) {
        buffer.write('[${value.join(',')}]');
      } else {
        buffer.write('$value');
      }
    });
    buffer.write('}');
    return buffer.toString();
  }
}

class VerificationConstants {
  VerificationConstants._();

  static const String methodHmac = 'hmac_sha256_shared_secret';
  static const String methodKeystore = 'android_keystore_ec_p256';
  static const String keyAlias = 'identicare_bpjs_v1';

  static const String payloadPrefix = 'identicare-v1';

  static String canonicalPayload({
    required String sessionId,
    required String nonce,
    required String deviceUid,
    required String noBpjs,
    required int timestamp,
  }) =>
      '$payloadPrefix|$sessionId|$nonce|$deviceUid|$noBpjs|$timestamp';

  static String get defaultKodeFaskes => AppConfig.defaultKodeFaskes;
}
