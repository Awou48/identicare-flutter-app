import 'package:flutter/material.dart';
import 'package:identicare_mobile/models/verification_history.dart';
import 'package:identicare_mobile/pages/verification/verification_detail_page.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:identicare_mobile/widgets/verification/status_badge.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

/// Riwayat verifikasi dari MongoDB (bukan Firestore).
///
/// Ini sisi lain dari keputusan database hibrida: tab "Konsultasi" tetap membaca
/// `riwayat_konsultasi` di Firestore, sedangkan tab ini membaca log verifikasi
/// dari API Python.
class VerificationHistoryPage extends StatefulWidget {
  const VerificationHistoryPage({super.key});

  @override
  State<VerificationHistoryPage> createState() => _VerificationHistoryPageState();
}

class _VerificationHistoryPageState extends State<VerificationHistoryPage> {
  final _scrollController = ScrollController();
  final _items = <VerificationHistoryEntry>[];

  String? _cursor;
  bool _hasMore = false;
  bool _loading = false;
  String? _error;
  String? _filter;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) => _load(reset: true));
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >=
            _scrollController.position.maxScrollExtent - 240 &&
        _hasMore &&
        !_loading) {
      _load();
    }
  }

  Future<void> _load({bool reset = false}) async {
    if (_loading) return;
    setState(() {
      _loading = true;
      if (reset) _error = null;
    });

    final api = context.read<VerificationApiService>();
    final result = await api.fetchHistory(
      cursor: reset ? null : _cursor,
      status: _filter,
    );

    if (!mounted) return;
    result.when(
      ok: (page) {
        setState(() {
          if (reset) _items.clear();
          _items.addAll(page.items);
          _cursor = page.nextCursor;
          _hasMore = page.hasMore;
          _loading = false;
          _error = null;
        });
      },
      failure: (f) {
        setState(() {
          _loading = false;
          // PESERTA_NOT_FOUND berarti akun ini belum ditautkan ke nomor BPJS -
          // bukan error, hanya keadaan yang perlu dijelaskan.
          _error = f.errorCode == 'PESERTA_NOT_FOUND'
              ? 'Akun ini belum tertaut dengan data peserta BPJS.'
              : f.message;
        });
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _filters(),
        Expanded(child: _body()),
      ],
    );
  }

  Widget _filters() {
    const options = <String, String?>{
      'Semua': null,
      'Disetujui': 'APPROVED',
      'Ditinjau': 'REVIEW',
      'Ditolak': 'REJECTED',
    };
    return SizedBox(
      height: 48,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        children: options.entries.map((entry) {
          final selected = _filter == entry.value;
          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: ChoiceChip(
              label: Text(entry.key),
              selected: selected,
              onSelected: (_) {
                setState(() => _filter = entry.value);
                _load(reset: true);
              },
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _body() {
    if (_error != null && _items.isEmpty) {
      return _Empty(
        icon: Icons.cloud_off_outlined,
        title: 'Tidak dapat memuat riwayat',
        message: _error!,
        onRetry: () => _load(reset: true),
      );
    }
    if (_items.isEmpty && _loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_items.isEmpty) {
      return const _Empty(
        icon: Icons.fact_check_outlined,
        title: 'Belum ada riwayat verifikasi',
        message: 'Riwayat verifikasi klaim BPJS Anda akan muncul di sini.',
      );
    }

    return RefreshIndicator(
      onRefresh: () => _load(reset: true),
      child: ListView.builder(
        controller: _scrollController,
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
        itemCount: _items.length + (_hasMore ? 1 : 0),
        itemBuilder: (context, index) {
          if (index >= _items.length) {
            return const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()),
            );
          }
          return _HistoryCard(entry: _items[index]);
        },
      ),
    );
  }
}

class _HistoryCard extends StatelessWidget {
  const _HistoryCard({required this.entry});

  final VerificationHistoryEntry entry;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => VerificationDetailPage(sessionId: entry.sessionId),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text(
                      DateFormat('EEEE, dd MMM yyyy · HH:mm', 'id_ID')
                          .format(entry.tanggal.toLocal()),
                      style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                    ),
                  ),
                  StatusBadge(status: entry.status, compact: true),
                ],
              ),
              const SizedBox(height: 10),
              if (entry.faskes != null)
                _row(Icons.location_on_outlined, entry.faskes!),
              _row(Icons.security_outlined, entry.metodeLabel),
              if (entry.receiptNo != null)
                _row(Icons.receipt_long_outlined, entry.receiptNo!),
              if (entry.skorWajah != null)
                _row(
                  Icons.face_retouching_natural,
                  'Skor wajah ${entry.skorWajah!.toStringAsFixed(3)}'
                  '${entry.skorLiveness != null ? ' · liveness ${entry.skorLiveness!.toStringAsFixed(2)}' : ''}',
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _row(IconData icon, String text) => Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Row(
          children: [
            Icon(icon, size: 14, color: Colors.grey.shade600),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                text,
                style: TextStyle(fontSize: 12, color: Colors.grey.shade800),
              ),
            ),
          ],
        ),
      );
}

class _Empty extends StatelessWidget {
  const _Empty({
    required this.icon,
    required this.title,
    required this.message,
    this.onRetry,
  });

  final IconData icon;
  final String title;
  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 56, color: Colors.grey.shade400),
            const SizedBox(height: 16),
            Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
            ),
            if (onRetry != null) ...[
              const SizedBox(height: 20),
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('Coba Lagi'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
