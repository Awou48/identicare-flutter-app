import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  final String _baseUrl = "http://192.168.0.101:5000"; 

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
