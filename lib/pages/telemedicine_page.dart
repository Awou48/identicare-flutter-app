import 'package:flutter/material.dart';
import 'package:identicare_mobile/pages/chat_page.dart';

class TelemedicinePage extends StatelessWidget {
  const TelemedicinePage({super.key});

  @override
  Widget build(BuildContext context) {
    final List<Map<String, dynamic>> doctors = [
      {
        'name': 'Dr. Rina Wulandari',
        'specialty': 'Dokter Umum',
        'status': 'Online'
      },
      {'name': 'Dr. Anisa Rahma', 'specialty': 'Psikolog', 'status': 'Online'},
      {
        'name': 'Dr. Hendra Wijaya',
        'specialty': 'Psikiater',
        'status': 'Offline'
      },
      {
        'name': 'Dr. Kevin Tan',
        'specialty': 'Dokter Anak',
        'status': 'Sedang Konsultasi'
      },
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text('Konsultasi Online'),
        backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          Text(
            'Dokter Tersedia',
            style: Theme.of(context)
                .textTheme
                .headlineSmall
                ?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text(
            'Mulai konsultasi dengan dokter yang tersedia.',
            style: TextStyle(color: Colors.grey.shade700, fontSize: 16),
          ),
          const SizedBox(height: 20),
          ...doctors
              .map((doctor) => _buildTelemedicineDoctorCard(context, doctor)),
        ],
      ),
    );
  }

  Color _getStatusColor(String status) {
    switch (status) {
      case 'Online':
        return Colors.green;
      case 'Sedang Konsultasi':
        return Colors.orange;
      default:
        return Colors.grey;
    }
  }

  Widget _buildTelemedicineDoctorCard(
      BuildContext context, Map<String, dynamic> doctor) {
    bool isOnline = doctor['status'] == 'Online';
    return Card(
      elevation: 2,
      margin: const EdgeInsets.only(bottom: 16),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            Row(
              children: [
                Stack(
                  children: [
                    CircleAvatar(
                      radius: 35,
                      backgroundColor: Colors.blue.shade50,
                      child: Text(
                        doctor['name']!.substring(0, 2).toUpperCase(),
                        style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Theme.of(context).colorScheme.primary),
                      ),
                    ),
                    Positioned(
                      bottom: 0,
                      right: 0,
                      child: Container(
                        width: 18,
                        height: 18,
                        decoration: BoxDecoration(
                          color: _getStatusColor(doctor['status']),
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.white, width: 2),
                        ),
                      ),
                    )
                  ],
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(doctor['name']!,
                          style: const TextStyle(
                              fontWeight: FontWeight.bold, fontSize: 18)),
                      const SizedBox(height: 4),
                      Text(doctor['specialty']!,
                          style: TextStyle(
                              color: Colors.grey.shade700, fontSize: 15)),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: isOnline
                    ? () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(
                              builder: (_) => ChatPage(doctor: doctor)),
                        );
                      }
                    : null,
                icon: const Icon(Icons.chat_bubble_outline),
                label: const Text('Mulai Chat'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: isOnline
                      ? Theme.of(context).colorScheme.secondary
                      : Colors.grey.shade300,
                  foregroundColor:
                      isOnline ? Colors.white : Colors.grey.shade600,
                ),
              ),
            )
          ],
        ),
      ),
    );
  }
}
