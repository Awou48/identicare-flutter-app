import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/material.dart';
import 'package:identicare_mobile/widgets/common/app_components.dart';
import 'package:identicare_mobile/services/auth_service.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';

class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key});

  @override
  Widget build(BuildContext context) {
    final authService = Provider.of<AuthService>(context, listen: false);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Profil Saya'),
        backgroundColor: Theme.of(context).scaffoldBackgroundColor,
        elevation: 0,
      ),
      body: StreamBuilder<DocumentSnapshot>(
        stream: authService.userProfileStream,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            // "Terjadi kesalahan." tanpa detail tidak memberi apa pun untuk
            // ditindaklanjuti. Penyebab paling sering adalah aturan keamanan
            // Firestore menolak pembacaan, dan itu hanya terlihat kalau
            // pesan aslinya ditampilkan.
            final error = snapshot.error.toString();
            final denied = error.contains('permission-denied') ||
                error.contains('PERMISSION_DENIED');
            return AppEmptyState(
              icon: denied ? Icons.lock_outline_rounded : Icons.error_outline_rounded,
              title: denied ? 'Akses profil ditolak' : 'Tidak dapat memuat profil',
              message: denied
                  ? 'Aturan keamanan Firestore menolak pembacaan dokumen ini. '
                      'Terapkan firestore.rules dengan: '
                      'firebase deploy --only firestore:rules'
                  : 'Terjadi kesalahan saat membaca data profil dari Firestore.',
              detail: error,
            );
          }
          if (!snapshot.hasData || !snapshot.data!.exists) {
            return const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.person_off_outlined, color: Colors.grey, size: 60),
                  SizedBox(height: 16),
                  Text('Profil tidak ditemukan.', style: TextStyle(fontSize: 18, color: Colors.grey)),
                  Text('Silakan coba login ulang.', style: TextStyle(color: Colors.grey)),
                ],
              ),
            );
          }

          final data = snapshot.data!.data() as Map<String, dynamic>;
          final createdAt = (data['createdAt'] as Timestamp?)?.toDate();

          return ListView(
            padding: const EdgeInsets.all(16.0),
            children: [
              _buildProfileHeader(context, data),
              const SizedBox(height: 24),
              _buildInfoCard(context, [
                _buildInfoRow('Email', data['email'] ?? 'Tidak ada'),
                _buildInfoRow('Telepon', 'Belum diatur'),
                _buildInfoRow('Bergabung Sejak', createdAt != null ? DateFormat('dd MMMM yyyy', 'id_ID').format(createdAt) : 'Tidak diketahui'),
              ]),
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: () async {
                  await authService.signOut();
                },
                icon: const Icon(Icons.logout),
                label: const Text('Logout'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.red.shade50,
                  foregroundColor: Colors.red.shade700,
                  elevation: 0,
                  padding: const EdgeInsets.symmetric(vertical: 16)
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildProfileHeader(BuildContext context, Map<String, dynamic> data) {
    return Column(
      children: [
        CircleAvatar(
          radius: 60,
          backgroundColor: Theme.of(context).colorScheme.primary.withOpacity(0.1),
          child: const Icon(Icons.person_rounded, size: 70, color: Color(0xFF0A7E8C)),
        ),
        const SizedBox(height: 16),
        Text(
          data['displayName'] ?? 'Nama Belum Diatur',
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 24),
        ),
        const SizedBox(height: 8),
        Text(
          data['email'] ?? '',
          style: TextStyle(color: Colors.grey.shade600, fontSize: 16),
        ),
      ],
    );
  }

  Widget _buildInfoCard(BuildContext context, List<Widget> children) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(children: children),
      ),
    );
  }

  Widget _buildInfoRow(String title, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12.0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(title, style: TextStyle(fontSize: 16, color: Colors.grey.shade700)),
          Text(value, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
