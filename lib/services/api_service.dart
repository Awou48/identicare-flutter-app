import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:identicare_mobile/config/app_config.dart';

/// Klien lama untuk analisis gejala.
///
/// Base URL-nya dulu IP LAN hardcoded (`http://192.168.0.101:5000`) yang
/// menunjuk ke server Flask yang sudah tidak ada di mana pun. Sekarang ia
/// mengambil alamat dari [AppConfig], dan backend FastAPI baru tetap melayani
/// path `/analyze_symptoms` yang sama supaya kontrak lamanya tidak berubah.
///
/// Untuk kode baru, gunakan VerificationApiService.analyzeSymptoms yang
/// melewati IdenticareApiClient dan memberi error terstruktur.
class ApiService {
  String get _baseUrl => AppConfig.apiBaseUrl;

  Future<Map<String, dynamic>> analyzeSymptoms(List<String> symptoms) async {
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/analyze_symptoms'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'gejala': symptoms}),
      ).timeout(const Duration(seconds: 90));

      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        return {'status': 'error', 'message': 'Server AI gagal merespons (Status: ${response.statusCode}).'};
      }
    } catch (e) {
      return {'status': 'error', 'message': 'Koneksi ke server AI gagal. Pastikan server Python berjalan dan IP sudah benar.'};
    }
  }
}
