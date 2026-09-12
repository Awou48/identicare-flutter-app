import 'package:flutter/material.dart';
import 'package:identicare_mobile/models/article.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:identicare_mobile/theme/app_theme.dart';
import 'package:identicare_mobile/widgets/common/app_components.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

class ArticleDetailPage extends StatefulWidget {
  const ArticleDetailPage({super.key, required this.slug});

  final String slug;

  @override
  State<ArticleDetailPage> createState() => _ArticleDetailPageState();
}

class _ArticleDetailPageState extends State<ArticleDetailPage> {
  Article? _article;
  bool _loading = true;
  String? _error;

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
    final result = await context.read<VerificationApiService>().fetchArticle(widget.slug);
    if (!mounted) return;
    result.when(
      ok: (article) => setState(() {
        _article = article;
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
    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: const Text('Artikel')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (_article == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Artikel')),
        body: AppEmptyState(
          icon: Icons.cloud_off_rounded,
          title: 'Tidak dapat memuat artikel',
          message: 'Periksa koneksi server di menu Pengaturan.',
          detail: _error,
          onRetry: _load,
        ),
      );
    }

    final article = _article!;
    return Scaffold(
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            expandedHeight: article.imageUrl == null ? 0 : 220,
            pinned: true,
            backgroundColor: AppColors.white,
            flexibleSpace: article.imageUrl == null
                ? null
                : FlexibleSpaceBar(
                    background: Image.network(
                      article.imageUrl!,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => Container(color: AppColors.ink100),
                    ),
                  ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.page),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (article.kategori.isNotEmpty)
                    AppStatusBadge(
                      label: article.kategori,
                      icon: Icons.local_offer_rounded,
                      color: AppColors.brandDark,
                      background: AppColors.brandSoft,
                      dense: true,
                    ),
                  const SizedBox(height: AppSpacing.md),
                  Text(
                    article.judul,
                    style: const TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                      height: 1.3,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Row(
                    children: [
                      if (article.penulis != null) ...[
                        Text(
                          article.penulis!,
                          style: const TextStyle(fontSize: 12.5, color: AppColors.ink500),
                        ),
                        const Text(' · ', style: TextStyle(color: AppColors.ink300)),
                      ],
                      Text(
                        '${article.readingMinutes} menit baca',
                        style: const TextStyle(fontSize: 12.5, color: AppColors.ink500),
                      ),
                      if (article.publishedAt != null) ...[
                        const Text(' · ', style: TextStyle(color: AppColors.ink300)),
                        Text(
                          DateFormat('dd MMM yyyy', 'id_ID')
                              .format(article.publishedAt!.toLocal()),
                          style: const TextStyle(fontSize: 12.5, color: AppColors.ink500),
                        ),
                      ],
                    ],
                  ),
                  const Divider(height: AppSpacing.xxxl),
                  _ArticleBody(konten: article.konten ?? article.ringkasan),
                  if (article.sumber != null) ...[
                    const SizedBox(height: AppSpacing.xxl),
                    Text(
                      'Sumber: ${article.sumber}',
                      style: const TextStyle(fontSize: 11.5, color: AppColors.ink500),
                    ),
                  ],
                  const SizedBox(height: AppSpacing.xxxl),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Penyaji markdown minimal.
///
/// Hanya menangani paragraf dan **judul tebal** - dua hal yang benar-benar
/// dipakai artikel ini. Menambahkan paket markdown penuh untuk itu berarti satu
/// dependensi lagi demi sintaks yang tidak dipakai.
class _ArticleBody extends StatelessWidget {
  const _ArticleBody({required this.konten});

  final String konten;

  @override
  Widget build(BuildContext context) {
    final blocks = konten.split('\n\n').where((b) => b.trim().isNotEmpty);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final block in blocks) _block(block.trim()),
      ],
    );
  }

  Widget _block(String text) {
    final isHeading = text.startsWith('**') && text.endsWith('**');
    if (isHeading) {
      return Padding(
        padding: const EdgeInsets.only(top: AppSpacing.xl, bottom: AppSpacing.sm),
        child: Text(
          text.substring(2, text.length - 2),
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            height: 1.35,
          ),
        ),
      );
    }

    if (text.startsWith('- ')) {
      return Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final line in text.split('\n'))
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Padding(
                      padding: EdgeInsets.only(top: 7, right: AppSpacing.md),
                      child: SizedBox(
                        width: 5,
                        height: 5,
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            color: AppColors.brand,
                            shape: BoxShape.circle,
                          ),
                        ),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        line.replaceFirst(RegExp(r'^-\s*'), ''),
                        style: const TextStyle(
                          fontSize: 14.5,
                          height: 1.65,
                          color: AppColors.ink700,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.lg),
      child: Text(
        text,
        style: const TextStyle(fontSize: 14.5, height: 1.7, color: AppColors.ink700),
      ),
    );
  }
}
