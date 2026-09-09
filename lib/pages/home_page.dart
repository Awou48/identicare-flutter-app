import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/material.dart';
import 'package:identicare_mobile/config/app_config.dart';
import 'package:identicare_mobile/pages/appointment_page.dart';
import 'package:identicare_mobile/pages/hospital_info_page.dart';
import 'package:identicare_mobile/pages/medical_records_page.dart';
import 'package:identicare_mobile/pages/symptom_checker_page.dart';
import 'package:identicare_mobile/pages/telemedicine_page.dart';
import 'package:identicare_mobile/pages/verification/claim_verification_flow_page.dart';
import 'package:identicare_mobile/services/biometric_attestation_service.dart';
import 'package:identicare_mobile/services/device_identity_service.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:identicare_mobile/state/verification_flow_controller.dart';
import 'package:identicare_mobile/services/auth_service.dart';
import 'package:identicare_mobile/widgets/service_card.dart';
import 'package:provider/provider.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    final authService = Provider.of<AuthService>(context, listen: false);

    return Scaffold(
      body: Column(
        children: [

          _buildHeader(context, authService),
          
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(16.0),
              children: [
                Text(
                  'Layanan Kami',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 16),

                _buildMainFeatureCard(context),
                const SizedBox(height: 16),
                
                _buildServicesGrid(context),
                const SizedBox(height: 24),

                Text(
                  'Artikel Kesehatan',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 16),
                _buildHealthTipCard(context),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader(BuildContext context, AuthService authService) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 50, 16, 24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [Theme.of(context).colorScheme.primary, Theme.of(context).colorScheme.secondary],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Image.asset('assets/images/logo.jpg', height: 35, color: Colors.white, errorBuilder: (c,e,s) => const Icon(Icons.local_hospital, color: Colors.white, size: 35)),
                  const SizedBox(width: 8),
                  const Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text('IDENTICARE', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Colors.white, letterSpacing: 1.1)),
                      Text('Solusi Kesehatan Anda', style: TextStyle(fontSize: 10, color: Colors.white70)),
                    ],
                  )
                ],
              ),
              Row(
                children: [
                  IconButton(icon: const Icon(Icons.notifications_none_outlined, color: Colors.white), onPressed: () {}),
                  IconButton(icon: const Icon(Icons.settings_outlined, color: Colors.white), onPressed: () {}),
                ],
              ),
            ],
          ),
          const SizedBox(height: 16),
          StreamBuilder<DocumentSnapshot>(
            stream: authService.userProfileStream,
            builder: (context, snapshot) {
              // Sebelumnya nama pengguna default-nya 'MARCEL SEBASTIAN',
              // sehingga pengguna lain melihat nama itu setiap kali Firestore
              // lambat merespons.
              String userName = '';
              if (snapshot.connectionState == ConnectionState.active &&
                  snapshot.hasData &&
                  snapshot.data!.exists) {
                final data = snapshot.data!.data() as Map<String, dynamic>;
                userName = (data['displayName'] as String? ?? '').toUpperCase();
              }
              return Text(
                'Halo, $userName',
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Colors.white),
              );
            },
          ),
        ],
      ),
    );
  }
  
  /// Buka alur verifikasi 4 langkah.
  ///
  /// Controller di-scope PADA halaman alur, bukan di main.dart, sehingga ia
  /// dibuat saat masuk dan dibuang saat keluar - tidak ada state verifikasi yang
  /// tertinggal di memori setelah pengguna selesai.
  Future<void> _startVerification(BuildContext context) async {
    if (!ClaimVerificationFlowPage.isSupportedPlatform) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Fitur verifikasi biometrik hanya tersedia di aplikasi Android.',
          ),
        ),
      );
      return;
    }

    final authService = Provider.of<AuthService>(context, listen: false);
    final api = Provider.of<VerificationApiService>(context, listen: false);
    final noBpjs = await authService.getNoBpjs();

    if (!context.mounted) return;

    if (noBpjs == null) {
      final entered = await _askForBpjs(context);
      if (entered == null || !context.mounted) return;
      await authService.setNoBpjs(entered);
      if (!context.mounted) return;
      return _openFlow(context, api, entered);
    }
    return _openFlow(context, api, noBpjs);
  }

  Future<void> _openFlow(
    BuildContext context,
    VerificationApiService api,
    String noBpjs,
  ) async {
    final attestation = BiometricAttestationService(DeviceIdentityService());
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => MultiProvider(
          providers: [
            ChangeNotifierProvider(
              create: (_) => VerificationFlowController(api, attestation),
            ),
            Provider<BiometricAttestationService>.value(value: attestation),
          ],
          child: ClaimVerificationFlowPage(
            noBpjs: noBpjs,
            kodeFaskes: AppConfig.defaultKodeFaskes,
          ),
        ),
      ),
    );
  }

  Future<String?> _askForBpjs(BuildContext context) {
    final controller = TextEditingController();
    final formKey = GlobalKey<FormState>();
    return showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Nomor BPJS'),
        content: Form(
          key: formKey,
          child: TextFormField(
            controller: controller,
            keyboardType: TextInputType.number,
            maxLength: 13,
            autofocus: true,
            decoration: const InputDecoration(
              labelText: 'Nomor BPJS (13 digit)',
              prefixIcon: Icon(Icons.badge_outlined),
            ),
            validator: (value) =>
                (value == null || !RegExp(r'^[0-9]{13}$').hasMatch(value.trim()))
                    ? 'Nomor BPJS harus 13 digit'
                    : null,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Batal'),
          ),
          FilledButton(
            onPressed: () {
              if (formKey.currentState!.validate()) {
                Navigator.pop(context, controller.text.trim());
              }
            },
            child: const Text('Lanjutkan'),
          ),
        ],
      ),
    );
  }

  Widget _buildMainFeatureCard(BuildContext context) {
    return Card(
      elevation: 8,
      shadowColor: Colors.black.withOpacity(0.1),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => _startVerification(context),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [Theme.of(context).colorScheme.secondary.withOpacity(0.8), Theme.of(context).colorScheme.primary],
              begin: Alignment.centerLeft,
              end: Alignment.centerRight,
            ),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.2),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.verified_user_rounded, color: Colors.white, size: 32),
              ),
              const SizedBox(width: 16),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('VERIFIKASI KLAIM BPJS', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white, letterSpacing: 1.1)),
                    SizedBox(height: 4),
                    Text('Verifikasi wajah & sidik jari sebelum mengajukan klaim', style: TextStyle(color: Colors.white70)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildServicesGrid(BuildContext context) {
    final List<Map<String, dynamic>> features = [
      {'title': 'Cek Gejala (AI)', 'icon': Icons.shield_outlined, 'color': Colors.teal, 'page': const SymptomCheckerPage()},
      {'title': 'Konsultasi Langsung', 'icon': Icons.calendar_month_outlined, 'color': Colors.blue, 'page': const AppointmentPage()},
      {'title': 'Rekaman Medis', 'icon': Icons.folder_copy_outlined, 'color': Colors.green, 'page': const MedicalRecordsPage()},
      {'title': 'Konsultasi Online', 'icon': Icons.video_call_outlined, 'color': Colors.orange, 'page': const TelemedicinePage()},
      {'title': 'Info Rumah Sakit', 'icon': Icons.add_circle_outline, 'color': Colors.purple, 'page': const HospitalInfoPage()},
    ];

    return GridView.count(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: 2,
      crossAxisSpacing: 16,
      mainAxisSpacing: 16,
      childAspectRatio: 1.0,
      children: features.map((feature) {
        return ServiceCard(
          title: feature['title'],
          icon: feature['icon'],
          color: feature['color'],
          page: feature['page'],
        );
      }).toList(),
    );
  }

  Widget _buildHealthTipCard(BuildContext context) {
    return Card(
      elevation: 2,
      shadowColor: Colors.grey.withOpacity(0.1),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () {},
        child: Column(
          children: [
            Image.network(
              'https://images.unsplash.com/photo-1543362906-acfc16c67564?q=80&w=1965&auto=format&fit=crop',
              height: 150,
              width: double.infinity,
              fit: BoxFit.cover,
            ),
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Pentingnya Hidrasi untuk Tubuh',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Minum air yang cukup setiap hari adalah kunci untuk menjaga fungsi tubuh tetap optimal.',
                    style: TextStyle(color: Colors.grey.shade700),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
