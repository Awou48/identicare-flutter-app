import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:identicare_mobile/config/app_config.dart';
import 'package:identicare_mobile/pages/verification/biometric_enrollment_page.dart';
import 'package:identicare_mobile/pages/verification/link_bpjs_page.dart';
import 'package:identicare_mobile/pages/verification/steps/step_1_face_scan_page.dart';
import 'package:identicare_mobile/pages/verification/steps/step_2_fingerprint_page.dart';
import 'package:identicare_mobile/pages/verification/steps/step_3_review_data_page.dart';
import 'package:identicare_mobile/pages/verification/steps/step_4_verify_result_page.dart';
import 'package:identicare_mobile/services/device_identity_service.dart';
import 'package:identicare_mobile/state/verification_flow_controller.dart';
import 'package:identicare_mobile/widgets/verification/step_progress_indicator.dart';
import 'package:provider/provider.dart';

/// Cangkang alur verifikasi klaim BPJS 4 langkah.
///
/// Memakai [IndexedStack], BUKAN PageView: pengguna tidak boleh bisa menggeser
/// mundur melewati langkah biometrik yang sudah lolos. Indeksnya digerakkan oleh
/// `controller.currentStep`, yang hanya diisi dari respons server.
class ClaimVerificationFlowPage extends StatefulWidget {
  const ClaimVerificationFlowPage({
    super.key,
    required this.noBpjs,
    this.kodeFaskes,
    this.poli = 'Penyakit Dalam',
    this.jenisLayanan = 'RAWAT_JALAN',
    this.estimasiBiaya = 0,
  });

  final String noBpjs;
  final String? kodeFaskes;
  final String poli;
  final String jenisLayanan;
  final int estimasiBiaya;

  /// Alur ini butuh kamera DAN sensor sidik jari asli. `local_auth` tidak punya
  /// implementasi web, dan `camera` tidak punya implementasi desktop - keduanya
  /// akan melempar MissingPluginException di tengah alur, bukan saat build.
  static bool get isSupportedPlatform {
    if (kIsWeb) return false;
    try {
      return Platform.isAndroid;
    } catch (_) {
      return false;
    }
  }

  @override
  State<ClaimVerificationFlowPage> createState() => _ClaimVerificationFlowPageState();
}

class _ClaimVerificationFlowPageState extends State<ClaimVerificationFlowPage> {
  final _deviceIdentity = DeviceIdentityService();
  bool _starting = true;
  String? _startError;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _start());
  }

  Future<void> _start() async {
    final controller = context.read<VerificationFlowController>();
    final device = await _deviceIdentity.describe();

    final ok = await controller.start(
      noBpjs: widget.noBpjs,
      kodeFaskes: widget.kodeFaskes ?? AppConfig.defaultKodeFaskes,
      device: device,
      jenisLayanan: widget.jenisLayanan,
      poli: widget.poli,
      estimasiBiaya: widget.estimasiBiaya,
    );

    if (!mounted) return;
    setState(() {
      _starting = false;
      _startError = ok ? null : controller.error;
    });
  }

  Future<bool> _confirmExit() async {
    final controller = context.read<VerificationFlowController>();
    if (controller.isCommitted) return true;

    final leave = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Batalkan verifikasi?'),
        content: const Text(
          'Proses verifikasi klaim akan dibatalkan dan Anda harus mengulang '
          'dari awal.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Lanjutkan Verifikasi'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('Batalkan'),
          ),
        ],
      ),
    );

    if (leave == true) {
      // Fire-and-forget: sesi juga akan kedaluwarsa sendiri di server.
      unawaited(controller.cancel());
      return true;
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<VerificationFlowController>();

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        if (await _confirmExit() && mounted) {
          Navigator.of(context).pop();
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Verifikasi Klaim BPJS'),
          backgroundColor: Colors.white,
          elevation: 0.5,
        ),
        body: Column(
          children: [
            StepProgressIndicator(currentStep: controller.currentStep),
            const Divider(height: 1),
            Expanded(child: _body(controller)),
          ],
        ),
      ),
    );
  }

  Widget _body(VerificationFlowController controller) {
    if (_starting) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Menyiapkan sesi verifikasi...'),
          ],
        ),
      );
    }

    if (_startError != null) {
      return _StartFailure(
        message: _startError!,
        needsEnrollment: controller.needsEnrollment,
        needsBpjsLink: controller.needsBpjsLink,
        onRetry: _retry,
        onLink: () async {
          final linked = await Navigator.push<Map<String, dynamic>>(
            context,
            MaterialPageRoute(builder: (_) => const LinkBpjsPage()),
          );
          if (linked != null && mounted) _retry();
        },
        onEnroll: () async {
          final done = await Navigator.push<bool>(
            context,
            MaterialPageRoute(builder: (_) => const BiometricEnrollmentPage()),
          );
          // Kembali dari pendaftaran yang berhasil: langsung coba mulai lagi,
          // supaya pengguna tidak perlu menekan tombol kedua untuk sesuatu yang
          // sudah jelas ingin mereka lakukan.
          if (done == true && mounted) _retry();
        },
      );
    }

    return IndexedStack(
      index: controller.currentStep.index0,
      children: const [
        Step1FaceScanPage(),
        Step2FingerprintPage(),
        Step3ReviewDataPage(),
        Step4VerifyResultPage(),
      ],
    );
  }

  void _retry() {
    setState(() {
      _starting = true;
      _startError = null;
    });
    _start();
  }
}

/// Layar kegagalan pembuka alur.
///
/// Dulu ini selalu menampilkan pesan yang sama plus "Coba Lagi", termasuk untuk
/// BIOMETRIC_NOT_ENROLLED - padahal mencoba lagi tidak akan pernah berhasil
/// sampai penggunanya mendaftar, dan tidak ada satu pun cara di aplikasi untuk
/// melakukannya. Tombolnya kini mengikuti penyebabnya.
class _StartFailure extends StatelessWidget {
  const _StartFailure({
    required this.message,
    required this.onRetry,
    required this.onEnroll,
    required this.onLink,
    this.needsEnrollment = false,
    this.needsBpjsLink = false,
  });

  final String message;
  final VoidCallback onRetry;
  final Future<void> Function() onEnroll;
  final Future<void> Function() onLink;
  final bool needsEnrollment;
  final bool needsBpjsLink;

  @override
  Widget build(BuildContext context) {
    final icon = needsEnrollment
        ? Icons.face_retouching_natural_rounded
        : (needsBpjsLink ? Icons.badge_outlined : Icons.error_outline);
    final color = (needsEnrollment || needsBpjsLink)
        ? Theme.of(context).colorScheme.primary
        : const Color(0xFFD93025);
    final title = needsEnrollment
        ? 'Biometrik belum terdaftar'
        : (needsBpjsLink
            ? 'Akun belum tertaut BPJS'
            : 'Tidak dapat memulai verifikasi');

    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 56, color: color),
            const SizedBox(height: 16),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(message, textAlign: TextAlign.center),
            if (needsEnrollment) ...[
              const SizedBox(height: 12),
              Text(
                'Daftarkan wajah Anda sekali, lalu verifikasi klaim dapat '
                'dilakukan kapan saja.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700),
              ),
            ],
            const SizedBox(height: 8),
            Text(
              'Server: ${AppConfig.apiBaseUrl}',
              style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
            ),
            const SizedBox(height: 24),
            // Tombolnya mengikuti penyebabnya. "Coba Lagi" untuk akun yang belum
            // tertaut tidak pernah bisa berhasil - yang dibutuhkan adalah
            // tindakan, bukan pengulangan.
            if (needsBpjsLink)
              FilledButton.icon(
                onPressed: onLink,
                icon: const Icon(Icons.link_rounded),
                label: const Text('Tautkan Nomor BPJS'),
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                ),
              )
            else if (needsEnrollment)
              FilledButton.icon(
                onPressed: onEnroll,
                icon: const Icon(Icons.how_to_reg_rounded),
                label: const Text('Daftarkan Biometrik Sekarang'),
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                ),
              )
            else
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('Coba Lagi'),
              ),
          ],
        ),
      ),
    );
  }
}
