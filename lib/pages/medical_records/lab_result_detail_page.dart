import 'package:flutter/material.dart';

class LabResultDetailPage extends StatelessWidget {
  const LabResultDetailPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Hasil Laboratorium')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Card(
          elevation: 2,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Pemeriksaan Darah Lengkap', style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                const Text('Tanggal: 01 Juli 2025', style: TextStyle(color: Colors.grey)),
                const Divider(height: 32),
                _buildResultRow('Hemoglobin', '14.5 g/dL', '13.5-17.5', true),
                _buildResultRow('Leukosit', '8,500 /uL', '4,500-11,000', true),
                _buildResultRow('Trombosit', '250,000 /uL', '150,000-450,000', true),
                _buildResultRow('Gula Darah Puasa', '115 mg/dL', '70-99', false),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildResultRow(String test, String result, String normalRange, bool isNormal) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: Row(
        children: [
          Expanded(
            flex: 2,
            child: Text(test, style: const TextStyle(fontWeight: FontWeight.w600)),
          ),
          Expanded(
            flex: 1,
            child: Text(result, style: TextStyle(fontWeight: FontWeight.bold, color: isNormal ? Colors.black87 : Colors.red)),
          ),
          Expanded(
            flex: 2,
            child: Text(normalRange, style: const TextStyle(color: Colors.grey), textAlign: TextAlign.right),
          ),
        ],
      ),
    );
  }
}
