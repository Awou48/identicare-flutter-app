import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:identicare_mobile/config/app_config.dart';
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
      return _StartFailure(message: _startError!, onRetry: () {
        setState(() {
          _starting = true;
          _startError = null;
        });
        _start();
      });
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
}

class _StartFailure extends StatelessWidget {
  const _StartFailure({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 56, color: Color(0xFFD93025)),
            const SizedBox(height: 16),
            const Text(
              'Tidak dapat memulai verifikasi',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 8),
            Text(
              'Server: ${AppConfig.apiBaseUrl}',
              style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
            ),
            const SizedBox(height: 24),
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
