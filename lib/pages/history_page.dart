import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:identicare_mobile/services/auth_service.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

class HistoryPage extends StatelessWidget {
  const HistoryPage({super.key, this.embedded = false});

  final bool embedded;

  @override
  Widget build(BuildContext context) {
    final user = Provider.of<AuthService>(context, listen: false).currentUser;

    if (user == null) {
      const message =
          Center(child: Text('Silakan login untuk melihat riwayat.'));
      return embedded
          ? message
          : Scaffold(
              appBar: AppBar(title: const Text('Riwayat Konsultasi')),
              body: message,
            );
    }

    final body = StreamBuilder<QuerySnapshot>(
      stream: FirebaseFirestore.instance
          .collection('riwayat_konsultasi')
          .where('userId', isEqualTo: user.uid)
          .orderBy('timestamp', descending: true)
          .snapshots(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }

        if (!snapshot.hasData || snapshot.data!.docs.isEmpty) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.history_toggle_off,
                    size: 80, color: Colors.grey.shade400),
                const SizedBox(height: 16),
                const Text(
                  'Belum ada riwayat konsultasi.',
                  style: TextStyle(fontSize: 18, color: Colors.grey),
                ),
              ],
            ),
          );
        }

        return ListView.builder(
          padding: const EdgeInsets.all(8.0),
          itemCount: snapshot.data!.docs.length,
          itemBuilder: (context, index) {
            final doc = snapshot.data!.docs[index];
            final data = doc.data() as Map<String, dynamic>;
            final gejala = data['gejala'] as List<dynamic>;
            final timestamp = data['timestamp'] as Timestamp?;

            final formattedDate = timestamp != null
                ? DateFormat('EEEE, dd MMMM yyyy', 'id_ID')
                    .format(timestamp.toDate())
                : 'Tanggal tidak tersedia';

            return Card(
              elevation: 2,
              margin:
                  const EdgeInsets.symmetric(vertical: 8.0, horizontal: 8.0),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
              child: ListTile(
                contentPadding:
                    const EdgeInsets.symmetric(vertical: 10, horizontal: 16),
                leading: Icon(Icons.receipt_long_outlined,
                    color: Theme.of(context).colorScheme.primary),
                title: Text(
                  formattedDate,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                subtitle: Text(
                  'Gejala: ${gejala.take(3).join(', ')}...',
                  overflow: TextOverflow.ellipsis,
                ),
                trailing: const Icon(Icons.arrow_forward_ios, size: 16),
                onTap: () {
                  showDialog(
                    context: context,
                    builder: (ctx) => AlertDialog(
                      title: const Text('Detail Hasil AI'),
                      content: SingleChildScrollView(
                          child: SelectableText(
                              data['hasilAI'] ?? 'Tidak ada hasil.')),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.of(ctx).pop(),
                          child: const Text('Tutup'),
                        )
                      ],
                    ),
                  );
                },
              ),
            );
          },
        );
      },
    );

    return embedded
        ? body
        : Scaffold(
            appBar: AppBar(title: const Text('Riwayat Konsultasi')),
            body: body,
          );
  }
}
