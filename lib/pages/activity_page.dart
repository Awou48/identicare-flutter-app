import 'package:flutter/material.dart';
import 'package:identicare_mobile/pages/history_page.dart';
import 'package:identicare_mobile/pages/verification/verification_history_page.dart';

/// Tab "Aktivitas": dua sumber data, dua tab.
///
/// Di sinilah keputusan database hibrida terlihat di UI. "Konsultasi" membaca
/// `riwayat_konsultasi` dari Firestore (fitur lama, tetap bekerja), sedangkan
/// "Verifikasi" membaca log verifikasi biometrik dari MongoDB lewat API Python.
class ActivityPage extends StatelessWidget {
  const ActivityPage({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Aktivitas'),
          backgroundColor: Theme.of(context).scaffoldBackgroundColor,
          elevation: 0,
          bottom: const TabBar(
            tabs: [
              Tab(icon: Icon(Icons.chat_outlined), text: 'Konsultasi'),
              Tab(icon: Icon(Icons.verified_user_outlined), text: 'Verifikasi'),
            ],
          ),
        ),
        body: const TabBarView(
          children: [
            HistoryPage(embedded: true),
            VerificationHistoryPage(),
          ],
        ),
      ),
    );
  }
}
