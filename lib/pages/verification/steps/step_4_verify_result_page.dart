import 'package:flutter/material.dart';
import 'package:identicare_mobile/models/review_data.dart';
import 'package:identicare_mobile/state/verification_flow_controller.dart';
import 'package:identicare_mobile/widgets/verification/status_badge.dart';
import 'package:provider/provider.dart';

/// Langkah 4 - Verifikasi Data.
///
/// Keputusan dibuat sepenuhnya di server: commit menjalankan ulang seluruh
/// aturan fraud, dan skor apa pun yang dibawa klien tidak dipercaya.
class Step4VerifyResultPage extends StatefulWidget {
  const Step4VerifyResultPage({super.key});

  @override
  State<Step4VerifyResultPage> createState() => _Step4VerifyResultPageState();
}

class _Step4VerifyResultPageState extends State<Step4VerifyResultPage> {
  bool _committed = false;

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<VerificationFlowController>();

    if (!_committed && controller.commitResult == null && !controller.isBusy) {
      _committed = true;
      WidgetsBinding.instance.addPostFrameCallback((_) => controller.commit());
    }

    final result = controller.commitResult;

    if (result == null) {
      if (controller.error != null) {
        return _Failure(
          message: controller.error!,
          onRetry: () {
            controller.clearError();
            controller.commit();
          },
        );
      }
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Memverifikasi klaim...'),
          ],
        ),
      );
    }

    return _Result(result: result);
  }
}

class _Result extends StatelessWidget {
  const _Result({required this.result});

  final CommitResult result;

  Color get _color => switch (result.decision) {
        'APPROVED' => const Color(0xFF34A853),
        'REVIEW' => const Color(0xFFF9AB00),
        _ => const Color(0xFFD93025),
      };

  IconData get _icon => switch (result.decision) {
        'APPROVED' => Icons.verified_rounded,
        'REVIEW' => Icons.pending_actions_rounded,
        _ => Icons.gpp_bad_rounded,
      };

  String get _headline => switch (result.decision) {
        'APPROVED' => 'Klaim Terverifikasi',
        'REVIEW' => 'Menunggu Verifikasi Petugas',
        _ => 'Klaim Ditolak',
      };

  String get _body => switch (result.decision) {
        'APPROVED' =>
          'Identitas Anda berhasil diverifikasi. Klaim BPJS dapat diproses.',
        'REVIEW' =>
          'Sistem menemukan hal yang perlu ditinjau petugas fasilitas kesehatan '
              'sebelum klaim diproses.',
        _ => 'Klaim tidak dapat diproses. Hubungi petugas fasilitas kesehatan.',
      };

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 16),
          Center(
            child: Container(
              width: 110,
              height: 110,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _color.withValues(alpha: 0.1),
              ),
              child: Icon(_icon, size: 64, color: _color),
            ),
          ),
          const SizedBox(height: 20),
          Text(
            _headline,
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: _color),
          ),
          const SizedBox(height: 8),
          Text(
            _body,
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey.shade700),
          ),
          const SizedBox(height: 24),

          if (result.receiptNo != null)
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: Colors.grey.shade200),
              ),
              child: Column(
                children: [
                  Text('Nomor Bukti Verifikasi',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
                  const SizedBox(height: 6),
                  SelectableText(
                    result.receiptNo!,
                    style: const TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 17,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1.1,
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 16),

          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: Colors.grey.shade200),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('Penilaian Risiko',
                        style: TextStyle(fontWeight: FontWeight.bold)),
                    StatusBadge(status: result.riskBand, compact: true),
                  ],
                ),
                const SizedBox(height: 10),
                LinearProgressIndicator(
                  value: (result.riskScore / 100).clamp(0.0, 1.0),
                  minHeight: 6,
                  backgroundColor: Colors.grey.shade200,
                  color: _color,
                ),
                const SizedBox(height: 6),
                Text('Skor ${result.riskScore}/100',
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
                if (result.signals.isNotEmpty) ...[
                  const Divider(height: 24),
                  const Text('Sinyal terdeteksi',
                      style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                  const SizedBox(height: 8),
                  ...result.signals.map((s) => _SignalRow(signal: s)),
                ],
              ],
            ),
          ),
          const SizedBox(height: 16),

          if (result.summary.isNotEmpty)
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: Colors.grey.shade200),
              ),
              child: Column(
                children: [
                  if (result.summary['faskes'] != null)
                    _SummaryRow(
                      icon: Icons.location_on_outlined,
                      label: 'Lokasi',
                      value: '${result.summary['faskes']}',
                    ),
                  if (result.summary['waktu'] != null)
                    _SummaryRow(
                      icon: Icons.schedule,
                      label: 'Waktu',
                      value: '${result.summary['waktu']}',
                    ),
                  if (result.summary['wajah'] != null)
                    _SummaryRow(
                      icon: Icons.face_retouching_natural,
                      label: 'Skor wajah',
                      value: '${result.summary['wajah']}',
                    ),
                  if (result.summary['sidik_jari'] != null)
                    _SummaryRow(
                      icon: Icons.fingerprint,
                      label: 'Sidik jari',
                      value: '${result.summary['sidik_jari']}',
                    ),
                ],
              ),
            ),
          const SizedBox(height: 28),

          FilledButton(
            onPressed: () => Navigator.of(context).pop(result),
            style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
            child: const Text('Selesai'),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

class _SignalRow extends StatelessWidget {
  const _SignalRow({required this.signal});

  final FraudSignal signal;

  @override
  Widget build(BuildContext context) {
    final color = switch (signal.severity) {
      'critical' => const Color(0xFFD93025),
      'high' => const Color(0xFFE8710A),
      'medium' => const Color(0xFFF9AB00),
      'low' => const Color(0xFF7A8B99),
      _ => Colors.grey,
    };
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 4),
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(signal.title, style: const TextStyle(fontSize: 13)),
                Text(
                  '${signal.ruleId} · +${signal.weight}',
                  style: TextStyle(fontSize: 10, color: Colors.grey.shade600),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow({required this.icon, required this.label, required this.value});

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, size: 16, color: Colors.grey.shade600),
          const SizedBox(width: 10),
          SizedBox(
            width: 90,
            child: Text(label, style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
          ),
          Expanded(
            child: Text(value, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
          ),
        ],
      ),
    );
  }
}

class _Failure extends StatelessWidget {
  const _Failure({required this.message, required this.onRetry});

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
            const Text('Verifikasi gagal diselesaikan',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(message, textAlign: TextAlign.center),
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
