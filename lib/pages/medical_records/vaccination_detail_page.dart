import 'package:flutter/material.dart';

class VaccinationDetailPage extends StatelessWidget {
  const VaccinationDetailPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Riwayat Vaksinasi')),
      body: ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          _buildVaccineCard(
            context,
            vaccineName: 'Influenza (Flu)',
            date: '10 Januari 2025',
            location: 'RS IdentiCare Sehat',
            batchNo: 'FLU2025-XYZ',
          ),
          const SizedBox(height: 12),
          _buildVaccineCard(
            context,
            vaccineName: 'COVID-19 (Booster 1)',
            date: '15 Agustus 2024',
            location: 'Puskesmas Sejahtera',
            batchNo: 'PFZ-B1-12345',
          ),
        ],
      ),
    );
  }

  Widget _buildVaccineCard(BuildContext context, {required String vaccineName, required String date, required String location, required String batchNo}) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.vaccines_outlined, color: Theme.of(context).colorScheme.primary, size: 32),
                const SizedBox(width: 12),
                Text(vaccineName, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              ],
            ),
            const Divider(height: 24),
            _buildInfoRow('Tanggal Pemberian', date),
            _buildInfoRow('Lokasi', location),
            _buildInfoRow('No. Batch', batchNo),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String title, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120, // Memberi lebar tetap untuk judul
            child: Text(
              title,
              style: const TextStyle(color: Colors.grey),
            ),
          ),
          const Text(': '),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
