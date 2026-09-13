import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/material.dart';
import 'package:identicare_mobile/config/app_config.dart';
import 'package:identicare_mobile/models/article.dart';
import 'package:identicare_mobile/pages/articles/article_detail_page.dart';
import 'package:identicare_mobile/pages/articles/article_list_page.dart';
import 'package:identicare_mobile/pages/hospital_info_page.dart';
import 'package:identicare_mobile/pages/medical_records_page.dart';
import 'package:identicare_mobile/pages/notifications_page.dart';
import 'package:identicare_mobile/pages/settings_page.dart';
import 'package:identicare_mobile/pages/telemedicine_page.dart';
import 'package:identicare_mobile/pages/verification/claim_verification_flow_page.dart';
import 'package:identicare_mobile/pages/verification/link_bpjs_page.dart';
import 'package:identicare_mobile/pages/verification/verification_history_page.dart';
import 'package:identicare_mobile/services/auth_service.dart';
import 'package:identicare_mobile/services/biometric_attestation_service.dart';
import 'package:identicare_mobile/services/device_identity_service.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:identicare_mobile/state/verification_flow_controller.dart';
import 'package:identicare_mobile/theme/app_theme.dart';
import 'package:identicare_mobile/widgets/common/app_components.dart';
import 'package:provider/provider.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

enum _PesertaState { unknown, notLinked, notEnrolled, enrolled }

class _HomePageState extends State<HomePage> {
  final _deviceIdentity = DeviceIdentityService();

  _PesertaState _peserta = _PesertaState.unknown;
  Article? _featuredArticle;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadBiometricStatus();
      _loadFeaturedArticle();
    });
  }

  Future<void> _loadBiometricStatus() async {
    final api = context.read<VerificationApiService>();
    final result = await api.pesertaMe();
    if (!mounted) return;
    result.when(
      ok: (status) => setState(() {
        _peserta = status.biometricEnrolled
            ? _PesertaState.enrolled
            : _PesertaState.notEnrolled;
      }),
      failure: (f) => setState(() {
        _peserta = f.errorCode == 'PESERTA_NOT_FOUND'
            ? _PesertaState.notLinked
            : _PesertaState.unknown;
      }),
    );
  }

  Future<void> _loadFeaturedArticle() async {
    final api = context.read<VerificationApiService>();
    final result = await api.fetchArticles(limit: 1, featuredOnly: true);
    if (!mounted) return;
    result.when(
      ok: (page) => setState(() {
        _featuredArticle = page.items.isEmpty ? null : page.items.first;
      }),
      failure: (_) {},
    );
  }

  @override
  Widget build(BuildContext context) {
    final authService = context.read<AuthService>();

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          await Future.wait([_loadBiometricStatus(), _loadFeaturedArticle()]);
        },
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            _Header(
              authService: authService,
              state: _peserta,
              onLink: () => _linkBpjs(context),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.page,
                AppSpacing.xxl,
                AppSpacing.page,
                AppSpacing.xxxl,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _PrimaryAction(onTap: () => _startVerification(context)),
                  const SizedBox(height: AppSpacing.xxl),
                  const AppSectionHeader(title: 'Layanan'),
                  _ServiceGrid(
                    onRiwayat: () => _push(const VerificationHistoryScreen()),
                    onPembaruan: () =>
                        _startVerification(context, enrolment: true),
                    onRekamMedis: () => _push(const MedicalRecordsPage()),
                    onKonsultasi: () => _push(const TelemedicinePage()),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  AppListTileCard(
                    title: 'Info Rumah Sakit',
                    subtitle: 'Fasilitas, poli, dan jam layanan',
                    icon: Icons.local_hospital_rounded,
                    onTap: () => _push(const HospitalInfoPage()),
                  ),
                  const SizedBox(height: AppSpacing.xxl),
                  AppSectionHeader(
                    title: 'Artikel Kesehatan',
                    action: 'Lihat semua',
                    onAction: () => _push(const ArticleListPage()),
                  ),
                  _ArticleCard(
                    article: _featuredArticle,
                    onTap: _featuredArticle == null
                        ? null
                        : () => _push(
                            ArticleDetailPage(slug: _featuredArticle!.slug)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _push(Widget page) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => page));
  }

  Future<void> _startVerification(BuildContext context,
      {bool enrolment = false}) async {
    if (!ClaimVerificationFlowPage.isSupportedPlatform) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
              'Fitur verifikasi biometrik hanya tersedia di aplikasi Android.'),
        ),
      );
      return;
    }

    final api = context.read<VerificationApiService>();

    final me = await api.pesertaMe();
    if (!context.mounted) return;

    final status = await me.when<Future<PesertaStatus?>>(
      ok: (status) async => status,
      failure: (f) async {
        if (f.errorCode != 'PESERTA_NOT_FOUND') {
          ScaffoldMessenger.of(context)
              .showSnackBar(SnackBar(content: Text(f.message)));
          return null;
        }
        final linked = await _linkBpjs(context);
        if (!linked || !context.mounted) return null;
        final again = await api.pesertaMe();
        return again.valueOrNull;
      },
    );
    if (status == null || !context.mounted) return;

    return _openFlow(context, api, status.noBpjs);
  }

  Future<bool> _linkBpjs(BuildContext context) async {
    final result = await Navigator.push<Map<String, dynamic>>(
      context,
      MaterialPageRoute(builder: (_) => const LinkBpjsPage()),
    );
    if (mounted) _loadBiometricStatus();
    return result != null;
  }

  Future<void> _openFlow(
    BuildContext context,
    VerificationApiService api,
    String noBpjs,
  ) async {
    final attestation = BiometricAttestationService(_deviceIdentity);
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
    if (mounted) _loadBiometricStatus();
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.authService,
    required this.state,
    required this.onLink,
  });

  final AuthService authService;
  final _PesertaState state;
  final VoidCallback onLink;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: const BoxDecoration(
        gradient: AppColors.headerGradient,
        borderRadius: BorderRadius.only(
          bottomLeft: Radius.circular(AppRadius.lg),
          bottomRight: Radius.circular(AppRadius.lg),
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.page,
            AppSpacing.lg,
            AppSpacing.sm,
            AppSpacing.xxl,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      color: AppColors.white,
                      borderRadius: AppRadius.smAll,
                    ),
                    child: Image.asset('assets/images/logo.png'),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          'IDENTICARE',
                          style: TextStyle(
                            color: AppColors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.2,
                          ),
                        ),
                        Text(
                          'Verifikasi Klaim BPJS',
                          style:
                              TextStyle(color: Colors.white70, fontSize: 11.5),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.notifications_none_rounded,
                        color: AppColors.white),
                    tooltip: 'Notifikasi',
                    onPressed: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const NotificationsPage()),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.settings_outlined,
                        color: AppColors.white),
                    tooltip: 'Pengaturan',
                    onPressed: () => Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const SettingsPage()),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.xl),
              StreamBuilder<DocumentSnapshot>(
                stream: authService.userProfileStream,
                builder: (context, snapshot) {
                  String? name;
                  if (snapshot.hasData && snapshot.data!.exists) {
                    final data = snapshot.data!.data() as Map<String, dynamic>?;
                    final raw = (data?['displayName'] as String? ?? '').trim();
                    if (raw.isNotEmpty) name = raw;
                  }

                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name == null
                            ? 'Halo'
                            : 'Halo, ${name.split(' ').first}',
                        style: const TextStyle(
                          color: AppColors.white,
                          fontSize: 26,
                          fontWeight: FontWeight.w700,
                          height: 1.15,
                        ),
                      ),
                      const SizedBox(height: AppSpacing.md),
                      _StatusBadge(state: state, onLink: onLink),
                    ],
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.state, required this.onLink});

  final _PesertaState state;
  final VoidCallback onLink;

  @override
  Widget build(BuildContext context) {
    switch (state) {
      case _PesertaState.unknown:
        return const AppStatusBadge(
          label: 'Status biometrik belum dimuat',
          icon: Icons.cloud_off_rounded,
          color: Colors.white70,
        );
      case _PesertaState.notLinked:
        return InkWell(
          onTap: onLink,
          borderRadius: BorderRadius.circular(AppRadius.pill),
          child: const AppStatusBadge(
            label: 'Tautkan nomor BPJS Anda',
            icon: Icons.link_rounded,
            color: Color(0xFFFFE08A),
          ),
        );
      case _PesertaState.notEnrolled:
        return const AppStatusBadge(
          label: 'Biometrik belum terdaftar',
          icon: Icons.error_outline_rounded,
          color: Color(0xFFFFE08A),
        );
      case _PesertaState.enrolled:
        return const AppStatusBadge(
          label: 'Terverifikasi dalam BPJS',
          icon: Icons.check_circle_rounded,
          color: AppColors.white,
        );
    }
  }
}

class _PrimaryAction extends StatelessWidget {
  const _PrimaryAction({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.brand,
      borderRadius: AppRadius.mdAll,
      child: InkWell(
        borderRadius: AppRadius.mdAll,
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: AppColors.white.withValues(alpha: 0.2),
                  borderRadius: AppRadius.smAll,
                ),
                child: const Icon(
                  Icons.document_scanner_rounded,
                  color: AppColors.white,
                  size: AppIcons.lg,
                ),
              ),
              const SizedBox(width: AppSpacing.lg),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'Verifikasi Klaim BPJS',
                      style: TextStyle(
                        color: AppColors.white,
                        fontSize: 16.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    SizedBox(height: 3),
                    Text(
                      'Wajah dan sidik jari sebelum mengajukan klaim',
                      style: TextStyle(
                          color: Colors.white70, fontSize: 12.5, height: 1.35),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              const Icon(Icons.arrow_forward_rounded,
                  color: AppColors.white, size: AppIcons.md),
            ],
          ),
        ),
      ),
    );
  }
}

class _ServiceGrid extends StatelessWidget {
  const _ServiceGrid({
    required this.onRiwayat,
    required this.onPembaruan,
    required this.onRekamMedis,
    required this.onKonsultasi,
  });

  final VoidCallback onRiwayat;
  final VoidCallback onPembaruan;
  final VoidCallback onRekamMedis;
  final VoidCallback onKonsultasi;

  @override
  Widget build(BuildContext context) {
    return GridView(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      padding: EdgeInsets.zero,
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: AppSpacing.md,
        mainAxisSpacing: AppSpacing.md,
        mainAxisExtent: AppGridTile.extentFor(context),
      ),
      children: [
        AppGridTile(
          label: 'Riwayat Verifikasi',
          icon: Icons.history_rounded,
          onTap: onRiwayat,
        ),
        AppGridTile(
          label: 'Pembaruan Biometrik',
          icon: Icons.face_retouching_natural_rounded,
          onTap: onPembaruan,
        ),
        AppGridTile(
          label: 'Rekam Medis',
          icon: Icons.folder_shared_rounded,
          onTap: onRekamMedis,
        ),
        AppGridTile(
          label: 'Konsultasi Online',
          icon: Icons.forum_rounded,
          onTap: onKonsultasi,
        ),
      ],
    );
  }
}

class _ArticleCard extends StatelessWidget {
  const _ArticleCard({required this.article, this.onTap});

  final Article? article;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    if (article == null) {
      return Container(
        padding: const EdgeInsets.all(AppSpacing.xl),
        decoration: BoxDecoration(
          color: AppColors.white,
          borderRadius: AppRadius.mdAll,
          border: Border.all(color: AppColors.ink100),
        ),
        child: const Row(
          children: [
            Icon(Icons.article_outlined,
                color: AppColors.ink300, size: AppIcons.lg),
            SizedBox(width: AppSpacing.lg),
            Expanded(
              child: Text(
                'Artikel belum tersedia.',
                style: TextStyle(color: AppColors.ink500, fontSize: 13.5),
              ),
            ),
          ],
        ),
      );
    }

    final item = article!;
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
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (item.imageUrl != null)
                ClipRRect(
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(AppRadius.md),
                    topRight: Radius.circular(AppRadius.md),
                  ),
                  child: Image.network(
                    item.imageUrl!,
                    height: 150,
                    width: double.infinity,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => Container(
                      height: 150,
                      color: AppColors.ink100,
                      child: const Icon(Icons.image_not_supported_outlined,
                          color: AppColors.ink300),
                    ),
                    loadingBuilder: (context, child, progress) =>
                        progress == null
                            ? child
                            : Container(height: 150, color: AppColors.ink100),
                  ),
                ),
              Padding(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (item.kategori.isNotEmpty) ...[
                      AppStatusBadge(
                        label: item.kategori,
                        icon: Icons.local_offer_rounded,
                        color: AppColors.brandDark,
                        background: AppColors.brandSoft,
                        dense: true,
                      ),
                      const SizedBox(height: AppSpacing.md),
                    ],
                    Text(
                      item.judul,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 15.5,
                        fontWeight: FontWeight.w700,
                        height: 1.3,
                        color: AppColors.ink900,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      item.ringkasan,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 13,
                        height: 1.45,
                        color: AppColors.ink900.withValues(alpha: 0.7),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class VerificationHistoryScreen extends StatelessWidget {
  const VerificationHistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Riwayat Verifikasi')),
      body: const VerificationHistoryPage(),
    );
  }
}
