import 'package:flutter/material.dart';

class UpcomingAppointmentCard extends StatelessWidget {
  const UpcomingAppointmentCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Janji Temu Berikutnya',
              style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                const CircleAvatar(
                  radius: 30,
                  backgroundColor: Colors.blue,
                  child: Text('BS', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                ),
                const SizedBox(width: 12),
                const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Dr. Budi Santoso', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                    Text('Dokter Jantung', style: TextStyle(color: Colors.grey)),
                  ],
                ),
                const Spacer(),
                Icon(Icons.arrow_forward_ios, color: Colors.grey.shade400, size: 16),
              ],
            ),
            const Divider(height: 24),
            const Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Icon(Icons.calendar_today, size: 16, color: Colors.grey),
                    SizedBox(width: 8),
                    Text('Besok, 07 Jul 2025'),
                  ],
                ),
                Row(
                  children: [
                    Icon(Icons.access_time, size: 16, color: Colors.grey),
                    SizedBox(width: 8),
                    Text('10:00 WIB'),
                  ],
                )
              ],
            )
          ],
        ),
      ),
    );
  }
}
