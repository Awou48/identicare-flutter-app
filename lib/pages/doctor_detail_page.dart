import 'package:flutter/material.dart';

class DoctorDetailPage extends StatelessWidget {
  final Map<String, dynamic> doctor;
  const DoctorDetailPage({super.key, required this.doctor});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(doctor['name']!),
      ),
      body: ListView(
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(24),
            color: Colors.white,
            child: Row(
              children: [
                CircleAvatar(
                  radius: 50,
                  backgroundColor: Colors.blue.shade50,
                  child: Text(
                    doctor['name']!.substring(0, 2).toUpperCase(),
                    style: TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: Theme.of(context).colorScheme.primary),
                  ),
                ),
                const SizedBox(width: 20),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(doctor['name']!, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 22)),
                      const SizedBox(height: 8),
                      Text(doctor['specialty']!, style: TextStyle(color: Colors.grey.shade700, fontSize: 18)),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Icon(Icons.star, color: Colors.amber, size: 20),
                          const SizedBox(width: 4),
                          Text('${doctor['rating']!} (120 ulasan)', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                        ],
                      )
                    ],
                  ),
                )
              ],
            ),
          ),
          const Divider(height: 1),
          // Jadwal
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Pilih Jadwal', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold)),
                const SizedBox(height: 16),
                _buildScheduleChips(),
              ],
            ),
          )
        ],
      ),
      bottomNavigationBar: Padding(
        padding: const EdgeInsets.all(16.0),
        child: ElevatedButton(
          onPressed: () {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Janji temu berhasil dibuat! (Simulasi)'), backgroundColor: Colors.green),
            );
            Navigator.of(context).pop();
          },
          child: const Text('Buat Janji Temu'),
        ),
      ),
    );
  }

  Widget _buildScheduleChips() {
    final schedules = ['09:00', '10:00', '11:00', '14:00', '15:00', '16:00'];
    return Wrap(
      spacing: 12.0,
      runSpacing: 12.0,
      children: schedules.map((time) => ChoiceChip(
        label: Text(time),
        selected: false, 
        onSelected: (selected) {},
        labelStyle: const TextStyle(fontWeight: FontWeight.w600),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      )).toList(),
    );
  }
}
