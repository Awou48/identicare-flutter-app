import 'package:flutter/material.dart';
import 'package:identicare_mobile/models/verification_history.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:identicare_mobile/widgets/verification/status_badge.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

/// Jejak audit lengkap satu sesi verifikasi, termasuk percobaan yang GAGAL.
///
/// Kegagalan sengaja ditampilkan: percobaan wajah yang gagal justru sinyal yang
/// paling berguna untuk mendeteksi fraud, dan menyembunyikannya akan membuat
/// jejak audit ini tidak ada gunanya.
class VerificationDetailPage extends StatefulWidget {
  const VerificationDetailPage({super.key, required this.sessionId});

  final String sessionId;

  @override
  State<VerificationDetailPage> createState() => _VerificationDetailPageState();
}

class _VerificationDetailPageState extends State<VerificationDetailPage> {
  Map<String, dynamic>? _data;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    final api = context.read<VerificationApiService>();
    final result = await api.fetchHistoryDetail(widget.sessionId);
    if (!mounted) return;
    result.when(
      ok: (json) => setState(() {
        _data = json;
        _loading = false;
      }),
      failure: (f) => setState(() {
        _error = f.message;
        _loading = false;
      }),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Detail Verifikasi')),
      body: _body(),
    );
  }

  Widget _body() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Text(_error!, textAlign: TextAlign.center),
        ),
      );
    }

    final data = _data!;
    final session = (data['session'] as Map?)?.cast<String, dynamic>() ?? const {};
    final result = (session['result'] as Map?)?.cast<String, dynamic>();
    final risk = (session['risk'] as Map?)?.cast<String, dynamic>() ?? const {};
    final lokasi = (data['lokasi'] as Map?)?.cast<String, dynamic>() ?? const {};
    final claim = (data['claim'] as Map?)?.cast<String, dynamic>() ?? const {};
    final events = ((data['events'] as List?) ?? const [])
        .map((e) => VerificationEvent.fromJson((e as Map).cast<String, dynamic>()))
        .toList();

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
            side: BorderSide(color: Colors.grey.shade200),
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('Hasil', style: TextStyle(fontWeight: FontWeight.bold)),
                    StatusBadge(
                      status: result?['decision'] as String? ?? session['status'] as String? ?? '',
                      compact: true,
                    ),
                  ],
                ),
                const Divider(height: 20),
                if (result?['receipt_no'] != null)
                  _kv('Nomor Bukti', '${result!['receipt_no']}', monospace: true),
                if (lokasi['label'] != null) _kv('Lokasi', '${lokasi['label']}'),
                if (claim['poli'] != null && '${claim['poli']}'.isNotEmpty)
                  _kv('Poli', '${claim['poli']}'),
                _kv('Skor Risiko', '${risk['score'] ?? 0}/100 (${risk['band'] ?? 'LOW'})'),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 4),
          child: Text('Jejak Audit', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
        ),
        const SizedBox(height: 8),
        ...events.map(_eventTile),
      ],
    );
  }

  Widget _kv(String label, String value, {bool monospace = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 110,
              child: Text(label,
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
            ),
            Expanded(
              child: Text(
                value,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  fontFamily: monospace ? 'monospace' : null,
                ),
              ),
            ),
          ],
        ),
      );

  Widget _eventTile(VerificationEvent event) {
    final color = event.isFailure ? const Color(0xFFD93025) : const Color(0xFF34A853);
    final scores = event.scores.entries
        .where((e) => e.value != null)
        .map((e) => '${e.key} ${e.value}')
        .join(' · ');

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 26,
            height: 26,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color.withValues(alpha: 0.12),
            ),
            child: Icon(
              event.isFailure ? Icons.close : Icons.check,
              size: 15,
              color: color,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(event.stepLabel,
                        style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                    Text(
                      DateFormat('HH:mm:ss').format(event.at.toLocal()),
                      style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
                    ),
                  ],
                ),
                if (event.errorCode != null)
                  Text(event.errorCode!,
                      style: const TextStyle(fontSize: 11, color: Color(0xFFD93025))),
                if (scores.isNotEmpty)
                  Text(scores, style: TextStyle(fontSize: 11, color: Colors.grey.shade700)),
                if (event.latencyMs != null)
                  Text('${event.latencyMs} ms',
                      style: TextStyle(fontSize: 10, color: Colors.grey.shade500)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
