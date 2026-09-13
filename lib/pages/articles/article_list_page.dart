import 'package:flutter/material.dart';
import 'package:identicare_mobile/models/article.dart';
import 'package:identicare_mobile/pages/articles/article_detail_page.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:identicare_mobile/theme/app_theme.dart';
import 'package:identicare_mobile/widgets/common/app_components.dart';
import 'package:provider/provider.dart';

class ArticleListPage extends StatefulWidget {
  const ArticleListPage({super.key});

  @override
  State<ArticleListPage> createState() => _ArticleListPageState();
}

class _ArticleListPageState extends State<ArticleListPage> {
  final _scrollController = ScrollController();
  final _items = <Article>[];

  List<String> _categories = const [];
  String? _category;
  bool _loading = false;
  bool _hasMore = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadCategories();
      _load(reset: true);
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >=
            _scrollController.position.maxScrollExtent - 300 &&
        _hasMore &&
        !_loading) {
      _load();
    }
  }

  Future<void> _loadCategories() async {
    final result =
        await context.read<VerificationApiService>().fetchArticleCategories();
    if (!mounted) return;
    result.when(
      ok: (categories) => setState(() => _categories = categories),
      failure: (_) {},
    );
  }

  Future<void> _load({bool reset = false}) async {
    if (_loading) return;
    setState(() {
      _loading = true;
      if (reset) _error = null;
    });

    final result = await context.read<VerificationApiService>().fetchArticles(
          skip: reset ? 0 : _items.length,
          kategori: _category,
        );
    if (!mounted) return;

    result.when(
      ok: (page) => setState(() {
        if (reset) _items.clear();
        _items.addAll(page.items);
        _hasMore = page.hasMore;
        _loading = false;
      }),
      failure: (f) => setState(() {
        _loading = false;
        _error = f.message;
      }),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Artikel Kesehatan')),
      body: Column(
        children: [
          if (_categories.isNotEmpty)
            SizedBox(
              height: 52,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.page,
                  vertical: AppSpacing.sm,
                ),
                children: [
                  _chip('Semua', null),
                  for (final category in _categories) _chip(category, category),
                ],
              ),
            ),
          Expanded(child: _body()),
        ],
      ),
    );
  }

  Widget _chip(String label, String? value) {
    return Padding(
      padding: const EdgeInsets.only(right: AppSpacing.sm),
      child: ChoiceChip(
        label: Text(label),
        selected: _category == value,
        onSelected: (_) {
          setState(() => _category = value);
          _load(reset: true);
        },
      ),
    );
  }

  Widget _body() {
    if (_items.isEmpty && _loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_items.isEmpty) {
      return AppEmptyState(
        icon: _error != null ? Icons.cloud_off_rounded : Icons.article_outlined,
        title:
            _error != null ? 'Tidak dapat memuat artikel' : 'Belum ada artikel',
        message: _error != null
            ? 'Periksa koneksi server di menu Pengaturan.'
            : 'Artikel kesehatan akan muncul di sini.',
        detail: _error,
        onRetry: () => _load(reset: true),
      );
    }

    return RefreshIndicator(
      onRefresh: () => _load(reset: true),
      child: ListView.separated(
        controller: _scrollController,
        padding: const EdgeInsets.all(AppSpacing.page),
        itemCount: _items.length + (_hasMore ? 1 : 0),
        separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.md),
        itemBuilder: (context, index) {
          if (index >= _items.length) {
            return const Padding(
              padding: EdgeInsets.all(AppSpacing.lg),
              child: Center(child: CircularProgressIndicator()),
            );
          }
          return _ArticleRow(
            article: _items[index],
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => ArticleDetailPage(slug: _items[index].slug),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _ArticleRow extends StatelessWidget {
  const _ArticleRow({required this.article, required this.onTap});

  final Article article;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.white,
      borderRadius: AppRadius.mdAll,
      child: InkWell(
        borderRadius: AppRadius.mdAll,
        onTap: onTap,
        child: Ink(
          decoration: BoxDecoration(
            borderRadius: AppRadius.mdAll,
            border: Border.all(color: AppColors.ink100),
          ),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ClipRRect(
                  borderRadius: AppRadius.smAll,
                  child: SizedBox(
                    width: 88,
                    height: 88,
                    child: article.imageUrl == null
                        ? Container(
                            color: AppColors.ink100,
                            child: const Icon(Icons.article_outlined,
                                color: AppColors.ink300),
                          )
                        : Image.network(
                            article.imageUrl!,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) => Container(
                              color: AppColors.ink100,
                              child: const Icon(
                                  Icons.image_not_supported_outlined,
                                  color: AppColors.ink300),
                            ),
                          ),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
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
                      const SizedBox(height: 6),
                      Text(
                        article.judul,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 14.5,
                          fontWeight: FontWeight.w700,
                          height: 1.3,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        article.ringkasan,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 12,
                          height: 1.4,
                          color: AppColors.ink900.withValues(alpha: 0.7),
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        '${article.readingMinutes} menit baca',
                        style: const TextStyle(
                            fontSize: 11, color: AppColors.ink500),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
