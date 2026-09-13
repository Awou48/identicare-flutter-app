import 'package:flutter/material.dart';
import 'package:identicare_mobile/pages/medical_records/diagnosis_detail_page.dart';
import 'package:identicare_mobile/pages/medical_records/lab_result_detail_page.dart';
import 'package:identicare_mobile/pages/medical_records/prescription_detail_page.dart';
import 'package:identicare_mobile/pages/medical_records/radiology_detail_page.dart';
import 'package:identicare_mobile/pages/medical_records/vaccination_detail_page.dart';

class MedicalRecordsPage extends StatelessWidget {
  const MedicalRecordsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final List<Map<String, dynamic>> records = [
      {
        'title': 'Hasil Laboratorium',
        'subtitle': 'Pemeriksaan Darah Lengkap',
        'date': '01 Jul 2025',
        'icon': Icons.science_outlined,
        'color': Colors.orange,
        'page': const LabResultDetailPage()
      },
      {
        'title': 'Resep Digital',
        'subtitle': 'Amoxicillin & Paracetamol',
        'date': '28 Jun 2025',
        'icon': Icons.medication_outlined,
        'color': Colors.green,
        'page': const PrescriptionDetailPage()
      },
      {
        'title': 'Catatan Diagnosa',
        'subtitle': 'Konsultasi dengan Dr. Budi',
        'date': '28 Jun 2025',
        'icon': Icons.assignment_ind_outlined,
        'color': Colors.blue,
        'page': const DiagnosisDetailPage()
      },
      {
        'title': 'Laporan Radiologi',
        'subtitle': 'X-Ray Dada',
        'date': '15 Mei 2025',
        'icon': Icons.document_scanner_outlined,
        'color': Colors.purple,
        'page': const RadiologyDetailPage()
      },
      {
        'title': 'Riwayat Vaksinasi',
        'subtitle': 'Vaksin Influenza',
        'date': '10 Jan 2025',
        'icon': Icons.vaccines_outlined,
        'color': Colors.red,
        'page': const VaccinationDetailPage()
      },
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text('Rekam Medis'),
        backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          _buildHighlightCard(context, records[0]),
          const SizedBox(height: 24),
          Text(
            'Semua Riwayat',
            style: Theme.of(context)
                .textTheme
                .headlineSmall
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),
          ListView.separated(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: records.length,
            separatorBuilder: (context, index) => const SizedBox(height: 12),
            itemBuilder: (context, index) {
              final record = records[index];
              return _buildRecordListTile(context, record);
            },
          ),
        ],
      ),
    );
  }

  Widget _buildHighlightCard(
      BuildContext context, Map<String, dynamic> record) {
    return Card(
      elevation: 4,
      shadowColor: (record['color'] as Color).withValues(alpha: 0.2),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      color: record['color'] as Color,
      child: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(record['icon'] as IconData, color: Colors.white, size: 28),
                const SizedBox(width: 8),
                Text(
                  'Hasil Terbaru',
                  style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.9),
                      fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              record['title'] as String,
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                fontSize: 22,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'Tanggal: ${record['date'] as String}',
              style: TextStyle(color: Colors.white.withValues(alpha: 0.8)),
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () {
                  Navigator.push(context,
                      MaterialPageRoute(builder: (_) => record['page']));
                },
                style: TextButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: record['color'] as Color,
                ),
                child: const Text('Lihat Detail'),
              ),
            )
          ],
        ),
      ),
    );
  }

  Widget _buildRecordListTile(
      BuildContext context, Map<String, dynamic> record) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.grey.withValues(alpha: 0.08),
            blurRadius: 10,
          )
        ],
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
        leading: CircleAvatar(
          backgroundColor: (record['color'] as Color).withValues(alpha: 0.1),
          child:
              Icon(record['icon'] as IconData, color: record['color'] as Color),
        ),
        title: Text(record['title'] as String,
            style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text(record['subtitle'] as String),
        trailing: Text(
          record['date'] as String,
          style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
        ),
        onTap: () {
          Navigator.push(
              context, MaterialPageRoute(builder: (_) => record['page']));
        },
      ),
    );
  }
}
