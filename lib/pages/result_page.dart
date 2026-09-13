import 'package:flutter/material.dart';

class ResultPage extends StatelessWidget {
  final Map<String, dynamic> analysisResult;

  const ResultPage({super.key, required this.analysisResult});

  @override
  Widget build(BuildContext context) {
    final bool isError = analysisResult['status'] != 'ok';
    final String resultText = analysisResult['result'] ??
        analysisResult['message'] ??
        "Tidak ada data untuk ditampilkan.";

    return Scaffold(
      appBar: AppBar(
        title: const Text('Hasil Analisis AI'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (isError)
              Icon(Icons.error_outline, color: Colors.red.shade700, size: 48),
            if (!isError)
              Icon(Icons.lightbulb_outline,
                  color: Colors.green.shade700, size: 48),
            const SizedBox(height: 16),
            Text(
              isError ? 'Terjadi Kesalahan' : 'Informasi Awal Berbasis AI',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: isError ? Colors.red.shade700 : Colors.black87,
                    fontWeight: FontWeight.bold,
                  ),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.grey.shade200)),
              child: SelectableText(
                resultText,
                style: const TextStyle(fontSize: 16, height: 1.6),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
