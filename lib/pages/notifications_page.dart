import 'package:flutter/material.dart';
import 'package:identicare_mobile/models/article.dart';
import 'package:identicare_mobile/models/verification_history.dart';
import 'package:identicare_mobile/pages/articles/article_detail_page.dart';
import 'package:identicare_mobile/pages/verification/verification_detail_page.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:identicare_mobile/theme/app_theme.dart';
import 'package:identicare_mobile/widgets/common/app_components.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

/// Notifikasi.
///
/// Lonceng di beranda sebelumnya `onPressed: () {}`. Alih-alih memasang push
/// notification (yang butuh FCM, token perangkat, dan backend pengirim), isinya
/// diturunkan dari data yang SUDAH ada: hasil verifikasi terakhir, status
/// pendaftaran biometrik, dan artikel baru.
///
/// Itu keputusan yang disengaja. Notifikasi yang mengarang isinya lebih buruk
/// daripada tidak ada notifikasi; yang di sini semuanya dapat ditelusuri ke
/// catatan nyata di server, dan setiap baris bisa dibuka ke sumbernya.
class NotificationsPage extends StatefulWidget {
  const NotificationsPage({super.key});

  @override
  State<NotificationsPage> createState() => _NotificationsPageState();
}

class _NotificationsPageState extends State<NotificationsPage> {
  bool _loading = true;
  String? _error;
  List<_Notification> _items = const [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    final api = context.read<VerificationApiService>();
    final items = <_Notification>[];

    final peserta = await api.pesertaMe();
    if (!mounted) return;
    peserta.when(
      ok: (status) {
        if (!status.biometricEnrolled) {
          items.add(_Notification(
            title: 'Biometrik belum terdaftar',
            body: 'Daftarkan wajah Anda agar dapat mengajukan klaim BPJS.',
            icon: Icons.face_retouching_natural_rounded,
            tone: _Tone.warning,
            at: DateTime.now(),
          ));
        }
        if (status.tunggakanBulan > 0) {
          items.add(_Notification(
            title: 'Iuran menunggak ${status.tunggakanBulan} bulan',
            body: 'Tunggakan menaikkan skor risiko pada verifikasi klaim.',
            icon: Icons.payments_outlined,
            tone: _Tone.warning,
            at: DateTime.now(),
          ));
        }
      },
      failure: (f) {
        if (f.errorCode != 'PESERTA_NOT_FOUND') _error = f.message;
      },
    );

    final history = await api.fetchHistory(limit: 10);
    if (!mounted) return;
    history.when(
      ok: (page) {
        for (final entry in page.items) {
          items.add(_fromVerification(entry));
        }
      },
      failure: (f) => _error ??= f.message,
    );

    final articles = await api.fetchArticles(limit: 3);
    if (!mounted) return;
    articles.when(
      ok: (page) {
        for (final article in page.items) {
          items.add(_Notification(
            title: 'Artikel: ${article.judul}',
            body: article.ringkasan,
            icon: Icons.article_outlined,
            tone: _Tone.info,
            at: article.publishedAt ?? DateTime.now(),
            article: article,
          ));
        }
      },
      failure: (_) {},
    );

    items.sort((a, b) => b.at.compareTo(a.at));
    if (!mounted) return;
    setState(() {
      _items = items;
      _loading = false;
    });
  }

  _Notification _fromVerification(VerificationHistoryEntry entry) {
    final approved = entry.status == 'APPROVED';
    final review = entry.status == 'REVIEW';
    return _Notification(
      title: switch (entry.status) {
        'APPROVED' => 'Klaim terverifikasi',
        'REVIEW' => 'Klaim menunggu tinjauan petugas',
        'REJECTED' => 'Klaim ditolak',
        _ => 'Verifikasi ${entry.statusLabel}',
      },
      body: [
        if (entry.faskes != null) entry.faskes!,
        if (entry.receiptNo != null) entry.receiptNo!,
      ].join(' · '),
      icon: approved
          ? Icons.verified_rounded
          : (review ? Icons.pending_actions_rounded : Icons.gpp_bad_rounded),
      tone: approved ? _Tone.success : (review ? _Tone.warning : _Tone.danger),
      at: entry.tanggal,
      sessionId: entry.sessionId,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Notifikasi')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _body(),
      ),
    );
  }

  Widget _body() {
    if (_loading) return const Center(child: CircularProgressIndicator());

    if (_items.isEmpty) {
      return AppEmptyState(
        icon: _error != null ? Icons.cloud_off_rounded : Icons.notifications_none_rounded,
        title: _error != null ? 'Tidak dapat memuat notifikasi' : 'Belum ada notifikasi',
        message: _error != null
            ? 'Periksa koneksi server di menu Pengaturan.'
            : 'Pemberitahuan tentang verifikasi dan kesehatan Anda akan muncul di sini.',
        detail: _error,
        onRetry: _load,
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.all(AppSpacing.page),
      itemCount: _items.length,
      separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.md),
      itemBuilder: (context, index) => _NotificationTile(
        item: _items[index],
        onTap: () => _open(_items[index]),
      ),
    );
  }

  void _open(_Notification item) {
    if (item.sessionId != null) {
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => VerificationDetailPage(sessionId: item.sessionId!),
        ),
      );
    } else if (item.article != null) {
      Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => ArticleDetailPage(slug: item.article!.slug)),
      );
    }
  }
}

enum _Tone { success, warning, danger, info }

class _Notification {
  final String title;
  final String body;
  final IconData icon;
  final _Tone tone;
  final DateTime at;
  final String? sessionId;
  final Article? article;

  const _Notification({
    required this.title,
    required this.body,
    required this.icon,
    required this.tone,
    required this.at,
    this.sessionId,
    this.article,
  });
}

class _NotificationTile extends StatelessWidget {
  const _NotificationTile({required this.item, required this.onTap});

  final _Notification item;
  final VoidCallback onTap;

  Color get _color => switch (item.tone) {
        _Tone.success => AppColors.success,
        _Tone.warning => AppColors.warning,
        _Tone.danger => AppColors.danger,
        _Tone.info => AppColors.info,
      };

  @override
  Widget build(BuildContext context) {
    final tappable = item.sessionId != null || item.article != null;

    return Material(
      color: AppColors.white,
      borderRadius: AppRadius.mdAll,
      child: InkWell(
        borderRadius: AppRadius.mdAll,
        onTap: tappable ? onTap : null,
        child: Ink(
          decoration: BoxDecoration(
            borderRadius: AppRadius.mdAll,
            border: Border.all(color: AppColors.ink100),
          ),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    color: _color.withValues(alpha: 0.12),
                    borderRadius: AppRadius.smAll,
                  ),
                  child: Icon(item.icon, size: AppIcons.md, color: _color),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.title,
                        style: const TextStyle(
                          fontSize: 14.5,
                          fontWeight: FontWeight.w600,
                          height: 1.3,
                        ),
                      ),
                      if (item.body.isNotEmpty) ...[
                        const SizedBox(height: 3),
                        Text(
                          item.body,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 12.5,
                            height: 1.4,
                            color: AppColors.ink900.withValues(alpha: 0.7),
                          ),
                        ),
                      ],
                      const SizedBox(height: 6),
                      Text(
                        DateFormat('dd MMM yyyy · HH:mm', 'id_ID').format(item.at.toLocal()),
                        style: const TextStyle(fontSize: 11, color: AppColors.ink500),
                      ),
                    ],
                  ),
                ),
                if (tappable)
                  const Icon(Icons.chevron_right_rounded,
                      color: AppColors.ink300, size: AppIcons.md),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
