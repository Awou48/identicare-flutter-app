import 'package:flutter/material.dart';
import 'package:identicare_mobile/services/biometric_attestation_service.dart';
import 'package:identicare_mobile/state/verification_flow_controller.dart';
import 'package:provider/provider.dart';

/// Langkah 2 - Scan Sidik Jari.
///
/// Sidik jarinya tidak pernah meninggalkan perangkat. Sensor hanya membuka
/// akses ke kunci penandatangan; yang dikirim ke server adalah tanda tangan atas
/// nonce sekali pakai.
class Step2FingerprintPage extends StatefulWidget {
  const Step2FingerprintPage({super.key});

  @override
  State<Step2FingerprintPage> createState() => _Step2FingerprintPageState();
}

class _Step2FingerprintPageState extends State<Step2FingerprintPage> {
  BiometricAvailability? _availability;
  bool _checking = true;

  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    final service = context.read<BiometricAttestationService>();
    final availability = await service.availability();
    if (!mounted) return;
    setState(() {
      _availability = availability;
      _checking = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<VerificationFlowController>();
    final result = controller.fingerprintResult;

    if (_checking) {
      return const Center(child: CircularProgressIndicator());
    }

    final availability = _availability!;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 16),
          Center(
            child: Container(
              width: 120,
              height: 120,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.08),
              ),
              child: Icon(
                Icons.fingerprint,
                size: 72,
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
          ),
          const SizedBox(height: 24),
          const Text(
            'Verifikasi Sidik Jari',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text(
            'Faktor kedua untuk memastikan klaim benar-benar diajukan oleh '
            'pemilik kartu BPJS.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey.shade700),
          ),
          const SizedBox(height: 24),

          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFF0A7E8C).withValues(alpha: 0.06),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.lock_outline, size: 18, color: Color(0xFF0A7E8C)),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Sidik jari Anda tidak dikirim ke server dan tidak disimpan '
                    'di mana pun. Sensor hanya membuka kunci penandatangan di '
                    'dalam perangkat Anda.',
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade800),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),

          if (!availability.available)
            _Unavailable(reason: availability.reason ?? 'Sensor tidak tersedia.')
          else ...[
            if (controller.error != null) ...[
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFD93025).withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.error_outline, color: Color(0xFFD93025), size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(controller.error!, style: const TextStyle(fontSize: 13)),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
            ],
            if (result != null && result.isExhausted)
              const Text(
                'Batas percobaan tercapai. Sesi verifikasi ditolak.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Color(0xFFD93025), fontWeight: FontWeight.bold),
              )
            else
              FilledButton.icon(
                onPressed: controller.isBusy
                    ? null
                    : () {
                        controller.clearError();
                        controller.submitFingerprint();
                      },
                icon: controller.isBusy
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.fingerprint),
                label: Text(controller.isBusy
                    ? 'Memverifikasi...'
                    : (result != null ? 'Coba Lagi' : 'Pindai Sidik Jari')),
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _Unavailable extends StatelessWidget {
  const _Unavailable({required this.reason});

  final String reason;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFF9AB00).withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFF9AB00).withValues(alpha: 0.4)),
      ),
      child: Column(
        children: [
          const Icon(Icons.warning_amber_rounded, color: Color(0xFFF9AB00), size: 32),
          const SizedBox(height: 8),
          const Text(
            'Sensor sidik jari tidak tersedia',
            style: TextStyle(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 6),
          Text(reason, textAlign: TextAlign.center, style: const TextStyle(fontSize: 13)),
          const SizedBox(height: 10),
          Text(
            'Emulator tidak memiliki sensor sidik jari sungguhan. '
            'Gunakan perangkat Android fisik.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
          ),
        ],
      ),
    );
  }
}
