import 'package:flutter/material.dart';

class RadiologyDetailPage extends StatelessWidget {
  const RadiologyDetailPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Laporan Radiologi')),
      body: ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          const Text('X-Ray Dada (Thorax)',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          const Text('Tanggal: 15 Mei 2025',
              style: TextStyle(color: Colors.grey)),
          const SizedBox(height: 24),
          Container(
            height: 300,
            decoration: BoxDecoration(
              color: Colors.black,
              borderRadius: BorderRadius.circular(12),
              image: const DecorationImage(
                image: NetworkImage('https://i.ibb.co/6g2Z1k8/xray.jpg'),
                fit: BoxFit.contain,
              ),
            ),
          ),
          const SizedBox(height: 24),
          const Text('Kesan Dokter Radiologi',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          const Text(
            'Cor dan pulmo dalam batas normal. Tidak tampak adanya infiltrat maupun efusi pleura. Tulang-tulang intak.',
            style: TextStyle(fontSize: 16, height: 1.5),
          ),
        ],
      ),
    );
  }
}
