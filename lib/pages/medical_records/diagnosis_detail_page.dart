import 'package:flutter/material.dart';

class DiagnosisDetailPage extends StatelessWidget {
  const DiagnosisDetailPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Detail Catatan Diagnosa')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Card(
          elevation: 2,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: Padding(
            padding: const EdgeInsets.all(20.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                _buildHeader(context),
                const Divider(height: 32, thickness: 1),
                _buildSection('Keluhan Utama', 'Pasien datang dengan keluhan demam selama 3 hari, disertai batuk dan nyeri otot.'),
                const SizedBox(height: 24),
                _buildSection('Diagnosa Dokter', 'Influenza (Flu) - J11'),
                const SizedBox(height: 24),
                _buildSection('Rencana Penanganan', 'Diberikan resep obat Amoxicillin dan Paracetamol. Disarankan untuk istirahat cukup dan menjaga hidrasi.'),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Row(
      children: [
        Icon(Icons.assignment_ind_outlined, size: 40, color: Theme.of(context).colorScheme.primary),
        const SizedBox(width: 16),
        // Expanded, bukan Column telanjang. Tanpa ini Column mengambil lebar
        // intrinsiknya dan judul 18px bold meluap 22 piksel ke kanan pada layar
        // sempit - persis garis kuning-hitam yang terlihat.
        const Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'Konsultasi dengan Dr. Budi',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              SizedBox(height: 4),
              Text('Tanggal: 28 Juni 2025', style: TextStyle(color: Colors.grey)),
            ],
          ),
        )
      ],
    );
  }

  Widget _buildSection(String title, String content) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: const TextStyle(fontSize: 14, color: Colors.grey, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Text(content, style: const TextStyle(fontSize: 16, height: 1.5)),
      ],
    );
  }
}
