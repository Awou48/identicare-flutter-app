import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:identicare_mobile/config/app_config.dart';
import 'package:identicare_mobile/models/api_result.dart';
import 'package:identicare_mobile/services/auth_service.dart';

/// Satu-satunya jalur keluar jaringan aplikasi.
///
/// Semua permintaan lewat sini supaya penanganan token, timeout, dan amplop
/// error konsisten. Yang lama (`api_service.dart`) menelan setiap exception
/// menjadi satu string, sehingga timeout tidak bisa dibedakan dari 500.
class IdenticareApiClient {
  IdenticareApiClient(this._authService, {http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final AuthService _authService;
  final http.Client _http;

  void dispose() => _http.close();

  Future<Map<String, String>> _headers({
    String? sessionToken,
    String? staffToken,
    bool json = true,
    bool includeFaskesKey = false,
  }) async {
    final headers = <String, String>{};
    if (json) headers['Content-Type'] = 'application/json';

    final token = await _authService.getIdToken();
    if (token != null) headers['Authorization'] = 'Bearer $token';

    if (sessionToken != null) headers['X-Session-Token'] = sessionToken;
    // Header terpisah dari Authorization: satu permintaan bisa sah membawa
    // token peserta DAN token petugas sekaligus - pasien hadir di meja sementara
    // petugas yang bertindak - dan menyatukannya akan membuat itu ambigu.
    if (staffToken != null) headers['X-Staff-Token'] = staffToken;
    if (includeFaskesKey) headers['X-Api-Key'] = AppConfig.faskesApiKey;
    return headers;
  }

  // ------------------------------------------------------------------ //
  Future<ApiResult<Map<String, dynamic>>> getJson(
    String path, {
    String? sessionToken,
    String? staffToken,
    Map<String, String>? query,
  }) async {
    return _guard(() async {
      final uri = Uri.parse('${AppConfig.apiV1}$path')
          .replace(queryParameters: query?.isEmpty ?? true ? null : query);
      final response = await _http
          .get(uri,
              headers: await _headers(
                  sessionToken: sessionToken, staffToken: staffToken, json: false))
          .timeout(AppConfig.jsonTimeout);
      return _decode(response);
    });
  }

  Future<ApiResult<Map<String, dynamic>>> postJson(
    String path, {
    Map<String, dynamic>? body,
    String? sessionToken,
    String? staffToken,
    bool includeFaskesKey = false,
  }) async {
    return _guard(() async {
      final response = await _http
          .post(
            Uri.parse('${AppConfig.apiV1}$path'),
            headers: await _headers(
              sessionToken: sessionToken,
              staffToken: staffToken,
              includeFaskesKey: includeFaskesKey,
            ),
            body: jsonEncode(body ?? const {}),
          )
          .timeout(AppConfig.jsonTimeout);
      return _decode(response);
    });
  }

  /// Unggah multipart untuk frame wajah.
  ///
  /// Multipart, bukan base64 di dalam JSON: base64 membengkakkan tiap JPEG 33%
  /// (sekitar 120 KB ekstra per percobaan untuk burst 3 frame), menambah satu
  /// putaran encode/decode di kedua sisi, dan memaksa server menahan seluruh
  /// request sebagai string sebelum diurai.
  Future<ApiResult<Map<String, dynamic>>> postMultipart(
    String path, {
    List<List<int>> files = const [],
    String fileField = 'frames',
    /// Berkas dengan nama field masing-masing, mis. evidence_bpjs / evidence_ktp.
    Map<String, List<int>> namedFiles = const {},
    Map<String, String> fields = const {},
    String? sessionToken,
    String? staffToken,
    bool includeFaskesKey = false,
  }) async {
    return _guard(() async {
      final request = http.MultipartRequest('POST', Uri.parse('${AppConfig.apiV1}$path'))
        ..headers.addAll(await _headers(
          sessionToken: sessionToken,
          staffToken: staffToken,
          json: false,
          includeFaskesKey: includeFaskesKey,
        ))
        ..fields.addAll(fields);

      for (var i = 0; i < files.length; i++) {
        request.files.add(http.MultipartFile.fromBytes(
          fileField,
          files[i],
          filename: 'frame_$i.jpg',
        ));
      }
      namedFiles.forEach((field, bytes) {
        request.files.add(http.MultipartFile.fromBytes(
          field,
          bytes,
          filename: '$field.jpg',
        ));
      });

      final streamed = await request.send().timeout(AppConfig.uploadTimeout);
      return _decode(await http.Response.fromStream(streamed));
    });
  }

  // ------------------------------------------------------------------ //
  Future<ApiResult<Map<String, dynamic>>> _guard(
    Future<ApiResult<Map<String, dynamic>>> Function() action,
  ) async {
    try {
      return await action();
    } on SocketException catch (e) {
      return _networkFailure(e.message);
    } on HttpException catch (e) {
      return _networkFailure(e.message);
    } on http.ClientException catch (e) {
      return _networkFailure(e.message);
    } on FormatException catch (e) {
      return ApiFailure(
        errorCode: 'BAD_RESPONSE',
        message: 'Respons server tidak dapat dibaca.',
        details: {'detail': e.message},
      );
    } catch (e) {
      // Timeout dan sisanya. Dibedakan supaya pengguna tahu harus menunggu,
      // bukan mengira datanya salah.
      final isTimeout = e.toString().toLowerCase().contains('timeout');
      return ApiFailure(
        errorCode: isTimeout ? 'TIMEOUT' : 'UNKNOWN_ERROR',
        message: isTimeout
            ? 'Server tidak merespons tepat waktu. Coba lagi.'
            : 'Terjadi kesalahan tak terduga.',
        details: {'detail': e.toString()},
      );
    }
  }

  ApiFailure<Map<String, dynamic>> _networkFailure(String detail) {
    if (kDebugMode) {
      debugPrint('[IdenticareApiClient] tidak dapat menjangkau ${AppConfig.apiBaseUrl}: $detail');
    }
    return ApiFailure(
      errorCode: 'NETWORK_ERROR',
      message: 'Tidak dapat terhubung ke server IdentiCare.\n'
          'Periksa koneksi dan alamat server (${AppConfig.apiBaseUrl}).',
      details: {'detail': detail},
    );
  }

  ApiResult<Map<String, dynamic>> _decode(http.Response response) {
    Map<String, dynamic> body;
    try {
      body = response.body.isEmpty
          ? <String, dynamic>{}
          : jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    } on FormatException {
      return ApiFailure(
        errorCode: 'BAD_RESPONSE',
        message: 'Respons server tidak valid.',
        statusCode: response.statusCode,
      );
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return Ok(body);
    }

    // Amplop error bersama dari backend.
    return ApiFailure(
      errorCode: body['error_code'] as String? ?? 'HTTP_${response.statusCode}',
      message: body['message'] as String? ?? 'Terjadi kesalahan pada server.',
      statusCode: response.statusCode,
      requestId: body['request_id'] as String?,
      details: (body['details'] as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }

  /// Cek kesehatan server. Dipakai layar diagnostik override base URL.
  Future<ApiResult<Map<String, dynamic>>> health() => getJson('/health');
}
