import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:identicare_mobile/config/app_config.dart';
import 'package:identicare_mobile/models/article.dart';
import 'package:identicare_mobile/services/auth_service.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:identicare_mobile/theme/app_theme.dart';
import 'package:identicare_mobile/widgets/common/app_components.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late final TextEditingController _urlController;

  bool _testing = false;
  _ConnectionResult? _result;
  PesertaStatus? _peserta;

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController(text: AppConfig.apiBaseUrl);
    WidgetsBinding.instance.addPostFrameCallback((_) => _testConnection());
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _testConnection() async {
    setState(() {
      _testing = true;
      _result = null;
    });

    final api = context.read<VerificationApiService>();
    final stopwatch = Stopwatch()..start();
    final health = await api.health();
    stopwatch.stop();

    if (!mounted) return;

    health.when(
      ok: (json) {
        final checks =
            (json['checks'] as Map?)?.cast<String, dynamic>() ?? const {};
        setState(() {
          _testing = false;
          _result = _ConnectionResult(
            ok: true,
            latencyMs: stopwatch.elapsedMilliseconds,
            mongo: checks['mongo'] as String?,
            faceModels: checks['face_models'] as String?,
            pesertaCount: (checks['peserta_count'] as num?)?.toInt(),
            env: checks['env'] as String?,
          );
        });
      },
      failure: (f) => setState(() {
        _testing = false;
        _result = _ConnectionResult(
          ok: false,
          latencyMs: stopwatch.elapsedMilliseconds,
          errorCode: f.errorCode,
          message: f.message,
        );
      }),
    );

    final peserta = await api.pesertaMe();
    if (!mounted) return;
    peserta.when(
      ok: (status) => setState(() => _peserta = status),
      failure: (_) => setState(() => _peserta = null),
    );
  }

  Future<void> _saveUrl() async {
    await AppConfig.setOverride(_urlController.text);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text('Alamat server disimpan: ${AppConfig.apiBaseUrl}')),
    );
    _testConnection();
  }

  Future<void> _resetUrl() async {
    await AppConfig.setOverride(null);
    if (!mounted) return;
    setState(() => _urlController.text = AppConfig.apiBaseUrl);
    _testConnection();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Pengaturan')),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.page),
        children: [
          const AppSectionHeader(title: 'Koneksi Server'),
          _ConnectionCard(
              result: _result,
              testing: _testing,
              baseUrl: AppConfig.apiBaseUrl),
          const SizedBox(height: AppSpacing.md),
          FilledButton.icon(
            onPressed: _testing ? null : _testConnection,
            icon: _testing
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white),
                  )
                : const Icon(Icons.wifi_tethering_rounded, size: AppIcons.sm),
            label: Text(_testing ? 'Menguji...' : 'Uji Koneksi'),
          ),
          if (kDebugMode) ...[
            const SizedBox(height: AppSpacing.xxl),
            const AppSectionHeader(title: 'Alamat Server (mode debug)'),
            Container(
              padding: const EdgeInsets.all(AppSpacing.lg),
              decoration: BoxDecoration(
                color: AppColors.white,
                borderRadius: AppRadius.mdAll,
                border: Border.all(color: AppColors.ink100),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  TextField(
                    controller: _urlController,
                    keyboardType: TextInputType.url,
                    autocorrect: false,
                    decoration: const InputDecoration(
                      labelText: 'Base URL',
                      hintText: 'http://192.168.0.102:8000',
                      prefixIcon: Icon(Icons.dns_outlined),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  Row(
                    children: [
                      Expanded(
                        child: FilledButton(
                            onPressed: _saveUrl, child: const Text('Simpan')),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: OutlinedButton(
                          onPressed: AppConfig.hasOverride ? _resetUrl : null,
                          child: const Text('Reset'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.md),
                  const _Hint(
                    'Gunakan alamat IP LAN komputer Anda, bukan 0.0.0.0 atau '
                    'localhost. 0.0.0.0 adalah alamat untuk MENDENGARKAN di sisi '
                    'server, bukan alamat yang bisa dihubungi dari perangkat lain.',
                  ),
                  const _Hint(
                    'Ponsel harus berada di Wi-Fi yang sama dengan komputer. '
                    'Lewat jaringan seluler, alamat 192.168.x.x tidak akan pernah '
                    'terjangkau.',
                  ),
                  _Hint('Default saat kompilasi: ${AppConfig.compiledDefault}'),
                ],
              ),
            ),
          ],
          const SizedBox(height: AppSpacing.xxl),
          const AppSectionHeader(title: 'Akun'),
          _AccountCard(peserta: _peserta),
          const SizedBox(height: AppSpacing.xxl),
          const AppSectionHeader(title: 'Tentang'),
          Container(
            decoration: BoxDecoration(
              color: AppColors.white,
              borderRadius: AppRadius.mdAll,
              border: Border.all(color: AppColors.ink100),
            ),
            child: const Column(
              children: [
                _InfoRow(label: 'Aplikasi', value: 'IdentiCare'),
                Divider(height: 1),
                _InfoRow(label: 'Versi', value: '1.1.0'),
                Divider(height: 1),
                _InfoRow(
                  label: 'Mode',
                  value: kDebugMode ? 'Debug' : 'Rilis',
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.xxl),
          OutlinedButton.icon(
            onPressed: () async {
              final confirmed = await showDialog<bool>(
                context: context,
                builder: (context) => AlertDialog(
                  title: const Text('Keluar dari akun?'),
                  content: const Text(
                      'Anda perlu masuk kembali untuk mengakses verifikasi.'),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('Batal'),
                    ),
                    TextButton(
                      onPressed: () => Navigator.pop(context, true),
                      style: TextButton.styleFrom(
                          foregroundColor: AppColors.danger),
                      child: const Text('Keluar'),
                    ),
                  ],
                ),
              );
              if (confirmed == true && context.mounted) {
                await context.read<AuthService>().signOut();
              }
            },
            style: OutlinedButton.styleFrom(
              foregroundColor: AppColors.danger,
              side: const BorderSide(color: AppColors.danger),
            ),
            icon: const Icon(Icons.logout_rounded, size: AppIcons.sm),
            label: const Text('Keluar'),
          ),
        ],
      ),
    );
  }
}

class _ConnectionResult {
  final bool ok;
  final int latencyMs;
  final String? mongo;
  final String? faceModels;
  final int? pesertaCount;
  final String? env;
  final String? errorCode;
  final String? message;

  const _ConnectionResult({
    required this.ok,
    required this.latencyMs,
    this.mongo,
    this.faceModels,
    this.pesertaCount,
    this.env,
    this.errorCode,
    this.message,
  });
}

class _ConnectionCard extends StatelessWidget {
  const _ConnectionCard({
    required this.result,
    required this.testing,
    required this.baseUrl,
  });

  final _ConnectionResult? result;
  final bool testing;
  final String baseUrl;

  @override
  Widget build(BuildContext context) {
    final ok = result?.ok ?? false;
    final color = testing
        ? AppColors.ink500
        : (result == null
            ? AppColors.ink500
            : (ok ? AppColors.success : AppColors.danger));

    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.white,
        borderRadius: AppRadius.mdAll,
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                testing
                    ? Icons.sync_rounded
                    : (ok ? Icons.cloud_done_rounded : Icons.cloud_off_rounded),
                color: color,
                size: AppIcons.lg,
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text(
                  testing
                      ? 'Menguji koneksi...'
                      : (result == null
                          ? 'Belum diuji'
                          : (ok
                              ? 'Server terhubung'
                              : 'Server tidak terjangkau')),
                  style: TextStyle(
                      fontWeight: FontWeight.w700, fontSize: 15, color: color),
                ),
              ),
              if (result != null && !testing)
                Text(
                  '${result!.latencyMs} ms',
                  style: const TextStyle(fontSize: 12, color: AppColors.ink500),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          SelectableText(
            baseUrl,
            style: const TextStyle(
              fontFamily: 'monospace',
              fontSize: 12.5,
              color: AppColors.ink700,
            ),
          ),
          if (result != null && !testing) ...[
            const Divider(height: AppSpacing.xxl),
            if (ok) ...[
              _Check(
                  'Database',
                  result!.mongo == 'ok' ? 'terhubung' : '${result!.mongo}',
                  result!.mongo == 'ok'),
              _Check('Model wajah', result!.faceModels ?? '-',
                  result!.faceModels == 'loaded'),
              _Check('Peserta terdaftar', '${result!.pesertaCount ?? 0}', true),
              _Check('Lingkungan', result!.env ?? '-', true),
            ] else ...[
              Text(
                result!.message ?? 'Tidak diketahui',
                style: const TextStyle(
                    fontSize: 13, color: AppColors.ink700, height: 1.45),
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(
                'Kode: ${result!.errorCode}',
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 11,
                  color: AppColors.ink500,
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              const _Hint(
                  'Pastikan backend berjalan: uvicorn app.main:app --host 0.0.0.0 --port 8000'),
              const _Hint(
                  'Pastikan ponsel dan komputer berada di Wi-Fi yang sama.'),
              const _Hint('Windows Firewall mungkin memblokir port 8000.'),
            ],
          ],
        ],
      ),
    );
  }
}

class _Check extends StatelessWidget {
  const _Check(this.label, this.value, this.good);

  final String label;
  final String value;
  final bool good;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Icon(
            good ? Icons.check_circle_rounded : Icons.error_outline_rounded,
            size: AppIcons.sm,
            color: good ? AppColors.success : AppColors.warning,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(label,
                style: const TextStyle(fontSize: 13, color: AppColors.ink700)),
          ),
          Text(
            value,
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

class _AccountCard extends StatelessWidget {
  const _AccountCard({required this.peserta});

  final PesertaStatus? peserta;

  @override
  Widget build(BuildContext context) {
    if (peserta == null) {
      return Container(
        padding: const EdgeInsets.all(AppSpacing.lg),
        decoration: BoxDecoration(
          color: AppColors.white,
          borderRadius: AppRadius.mdAll,
          border: Border.all(color: AppColors.ink100),
        ),
        child: const Row(
          children: [
            Icon(Icons.link_off_rounded,
                color: AppColors.ink300, size: AppIcons.lg),
            SizedBox(width: AppSpacing.lg),
            Expanded(
              child: Text(
                'Akun belum tertaut dengan data peserta BPJS, atau server tidak terjangkau.',
                style: TextStyle(
                    fontSize: 13, color: AppColors.ink500, height: 1.4),
              ),
            ),
          ],
        ),
      );
    }

    final p = peserta!;
    return Container(
      decoration: BoxDecoration(
        color: AppColors.white,
        borderRadius: AppRadius.mdAll,
        border: Border.all(color: AppColors.ink100),
      ),
      child: Column(
        children: [
          _InfoRow(label: 'Nama', value: p.namaLengkap),
          const Divider(height: 1),
          _InfoRow(label: 'Nomor BPJS', value: p.noBpjsMasked, monospace: true),
          const Divider(height: 1),
          _InfoRow(label: 'Status', value: p.statusKepesertaan ?? '-'),
          const Divider(height: 1),
          _InfoRow(
            label: 'Biometrik',
            value: p.biometricEnrolled ? 'Terdaftar' : 'Belum terdaftar',
          ),
          if (p.biometricEnrolled) ...[
            const Divider(height: 1),
            _InfoRow(label: 'Tingkat', value: p.assuranceLabel),
            if (p.biometricEnrolledAt != null) ...[
              const Divider(height: 1),
              _InfoRow(
                label: 'Terdaftar sejak',
                value: DateFormat('dd MMM yyyy', 'id_ID')
                    .format(p.biometricEnrolledAt!.toLocal()),
              ),
            ],
          ],
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow(
      {required this.label, required this.value, this.monospace = false});

  final String label;
  final String value;
  final bool monospace;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.lg,
        vertical: AppSpacing.md,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(label,
                style: const TextStyle(fontSize: 13, color: AppColors.ink500)),
          ),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: TextStyle(
                fontSize: 13.5,
                fontWeight: FontWeight.w600,
                fontFamily: monospace ? 'monospace' : null,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Hint extends StatelessWidget {
  const _Hint(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 2),
            child: Icon(Icons.info_outline_rounded,
                size: 13, color: AppColors.ink500),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                  fontSize: 11.5, color: AppColors.ink500, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}
