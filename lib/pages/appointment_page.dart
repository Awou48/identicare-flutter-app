import 'package:flutter/material.dart';
import 'package:identicare_mobile/pages/doctor_detail_page.dart';

class AppointmentPage extends StatefulWidget {
  const AppointmentPage({super.key});

  @override
  State<AppointmentPage> createState() => _AppointmentPageState();
}

class _AppointmentPageState extends State<AppointmentPage> {
  String _selectedSpecialty = 'Semua';

  final List<Map<String, dynamic>> allDoctors = [
    {
      'name': 'Dr. Budi Santoso',
      'specialty': 'Jantung',
      'rating': 4.9,
      'bio':
          'Spesialis Jantung dan Pembuluh Darah dengan pengalaman 15 tahun di RS Jantung Harapan Kita.'
    },
    {
      'name': 'Dr. Siti Aminah',
      'specialty': 'Anak',
      'rating': 4.8,
      'bio':
          'Dokter spesialis anak yang ramah dan berpengalaman dalam menangani tumbuh kembang.'
    },
    {
      'name': 'Dr. Eko Prasetyo',
      'specialty': 'Umum',
      'rating': 4.7,
      'bio':
          'Dokter umum yang siap melayani konsultasi kesehatan primer untuk segala usia.'
    },
    {
      'name': 'Dr. Rina Wulandari',
      'specialty': 'Kulit',
      'rating': 4.9,
      'bio':
          'Ahli dermatologi untuk masalah kulit dan estetika dengan sertifikasi internasional.'
    },
  ];

  @override
  Widget build(BuildContext context) {
    final filteredDoctors = _selectedSpecialty == 'Semua'
        ? allDoctors
        : allDoctors
            .where((d) => d['specialty'] == _selectedSpecialty)
            .toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Konsultasi Dokter'),
        backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      ),
      body: Column(
        children: [
          _buildSpecialtyFilter(),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16.0),
              itemCount: filteredDoctors.length,
              itemBuilder: (context, index) {
                final doctor = filteredDoctors[index];
                return _buildDoctorCard(context, doctor);
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSpecialtyFilter() {
    final specialties = ['Semua', 'Jantung', 'Anak', 'Umum', 'Kulit'];
    return SizedBox(
      height: 50,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: specialties.length,
        itemBuilder: (context, index) {
          final specialty = specialties[index];
          final isSelected = _selectedSpecialty == specialty;
          return Padding(
            padding: const EdgeInsets.only(right: 8.0),
            child: ChoiceChip(
              label: Text(specialty),
              selected: isSelected,
              onSelected: (selected) {
                setState(() {
                  _selectedSpecialty = specialty;
                });
              },
              selectedColor: Theme.of(context).colorScheme.primary,
              labelStyle: TextStyle(
                color: isSelected ? Colors.white : Colors.black,
                fontWeight: FontWeight.w600,
              ),
              backgroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20),
                  side: BorderSide(
                      color: isSelected
                          ? Colors.transparent
                          : Colors.grey.shade300)),
            ),
          );
        },
      ),
    );
  }

  Widget _buildDoctorCard(BuildContext context, Map<String, dynamic> doctor) {
    return Card(
      elevation: 2,
      margin: const EdgeInsets.only(bottom: 16),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => DoctorDetailPage(doctor: doctor)),
          );
        },
        child: Padding(
          padding: const EdgeInsets.all(12.0),
          child: Row(
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
                        style: TextStyle(color: Colors.grey.shade700)),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        const Icon(Icons.star, color: Colors.amber, size: 18),
                        const SizedBox(width: 4),
                        Text(doctor['rating']!.toString(),
                            style:
                                const TextStyle(fontWeight: FontWeight.bold)),
                      ],
                    )
                  ],
                ),
              ),
              const Icon(Icons.arrow_forward_ios, size: 18, color: Colors.grey),
            ],
          ),
        ),
      ),
    );
  }
}
