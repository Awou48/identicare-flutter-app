import 'package:flutter/material.dart';

class PrescriptionDetailPage extends StatelessWidget {
  const PrescriptionDetailPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Detail Resep Digital')),
      body: ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          _buildInfoSection(context),
          const SizedBox(height: 24),
          _buildDrugCard(context, 'Amoxicillin 500mg',
              '3 x sehari, sesudah makan', 'Habiskan'),
          const SizedBox(height: 12),
          _buildDrugCard(context, 'Paracetamol 500mg', '3 x sehari, jika perlu',
              'Jika demam/nyeri'),
        ],
      ),
    );
  }

  Widget _buildInfoSection(BuildContext context) {
    return Card(
      elevation: 0,
      color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.05),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Informasi Resep',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const Divider(height: 24),
            _buildInfoRow('Dokter', 'Dr. Budi Santoso'),
            _buildInfoRow('Tanggal', '28 Juni 2025'),
            _buildInfoRow('No. Resep', 'E-RX-20250628-001'),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String title, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4.0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(title, style: const TextStyle(color: Colors.grey)),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  Widget _buildDrugCard(
      BuildContext context, String name, String dosage, String note) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(name,
                style:
                    const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            Row(children: [
              const Icon(Icons.schedule, size: 18, color: Colors.grey),
              const SizedBox(width: 8),
              Text(dosage),
            ]),
            const SizedBox(height: 8),
            Row(children: [
              const Icon(Icons.info_outline, size: 18, color: Colors.grey),
              const SizedBox(width: 8),
              Text(note),
            ]),
          ],
        ),
      ),
    );
  }
}
