import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:identicare_mobile/theme/app_theme.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

/// Tautkan akun login ke data peserta BPJS.
///
/// Langkah yang hilang. Login dikelola Firebase; data BPJS, template biometrik,
/// dan riwayat verifikasi ada di MongoDB. Keduanya dijahit oleh satu field -
/// dan sebelum halaman ini, tidak ada cara bagi pengguna biasa untuk
/// mengisinya. Setiap akun baru berakhir di "Akun belum tertaut BPJS" di tiga
/// layar berbeda, dengan tombol "Coba Lagi" yang tidak pernah bisa berhasil.
///
/// Bukti kepemilikan: tiga data yang tercetak di kartu fisik. Bukan bukti
/// yang kuat, tetapi cukup untuk menghentikan penautan sembarangan, dan
/// pengaman sebenarnya ada di server: sekali tertaut tidak bisa diambil alih
/// dari sini, percobaan salah dibatasi, dan klaim tetap harus lolos gerbang
/// deduplikasi wajah.
class LinkBpjsPage extends StatefulWidget {
  const LinkBpjsPage({super.key});

  @override
  State<LinkBpjsPage> createState() => _LinkBpjsPageState();
}

class _LinkBpjsPageState extends State<LinkBpjsPage> {
  final _formKey = GlobalKey<FormState>();
  final _bpjs = TextEditingController();
  final _nik = TextEditingController();
  DateTime? _dob;
  bool _busy = false;
  String? _error;
  int? _attemptsLeft;

  @override
  void dispose() {
    _bpjs.dispose();
    _nik.dispose();
    super.dispose();
  }

  Future<void> _pickDob() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _dob ?? DateTime(now.year - 30, 1, 1),
      firstDate: DateTime(1900),
      lastDate: now,
      locale: const Locale('id', 'ID'),
      helpText: 'Tanggal lahir sesuai KTP',
    );
    if (picked != null) setState(() => _dob = picked);
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_dob == null) {
      setState(() => _error = 'Pilih tanggal lahir Anda.');
      return;
    }

    setState(() {
      _busy = true;
      _error = null;
    });

    final api = context.read<VerificationApiService>();
    final result = await api.linkBpjs(
      noBpjs: _bpjs.text.trim(),
      nik: _nik.text.trim(),
      tanggalLahir: DateFormat('yyyy-MM-dd').format(_dob!),
    );
    if (!mounted) return;

    result.when(
      ok: (body) {
        Navigator.of(context).pop(body);
      },
      failure: (f) => setState(() {
        _busy = false;
        _error = f.message;
        _attemptsLeft = (f.details['attempts_left'] as num?)?.toInt();
      }),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Tautkan Nomor BPJS')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                padding: const EdgeInsets.all(AppSpacing.lg),
                decoration: BoxDecoration(
                  color: AppColors.brandSoft,
                  borderRadius: AppRadius.mdAll,
                ),
                child: const Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.badge_outlined, color: AppColors.brandDark),
                    SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Text(
                        'Masukkan data persis seperti di kartu BPJS dan KTP Anda. '
                        'Akun hanya dapat ditautkan satu kali.',
                        style: TextStyle(fontSize: 13, height: 1.4, color: AppColors.ink900),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.xxl),

              TextFormField(
                controller: _bpjs,
                enabled: !_busy,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                maxLength: 13,
                decoration: const InputDecoration(
                  labelText: 'Nomor Kartu BPJS',
                  helperText: '13 digit',
                  prefixIcon: Icon(Icons.credit_card_outlined),
                ),
                validator: (v) => (v == null || v.trim().length != 13)
                    ? 'Nomor BPJS harus 13 digit'
                    : null,
              ),
              const SizedBox(height: AppSpacing.md),

              TextFormField(
                controller: _nik,
                enabled: !_busy,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                maxLength: 16,
                decoration: const InputDecoration(
                  labelText: 'NIK (KTP)',
                  helperText: '16 digit',
                  prefixIcon: Icon(Icons.perm_identity_outlined),
                ),
                validator: (v) =>
                    (v == null || v.trim().length != 16) ? 'NIK harus 16 digit' : null,
              ),
              const SizedBox(height: AppSpacing.md),

              InkWell(
                onTap: _busy ? null : _pickDob,
                borderRadius: AppRadius.smAll,
                child: InputDecorator(
                  decoration: const InputDecoration(
                    labelText: 'Tanggal Lahir',
                    prefixIcon: Icon(Icons.cake_outlined),
                    suffixIcon: Icon(Icons.calendar_today_outlined, size: 18),
                  ),
                  child: Text(
                    _dob == null
                        ? 'Pilih tanggal'
                        : DateFormat('dd MMMM yyyy', 'id_ID').format(_dob!),
                    style: TextStyle(
                      color: _dob == null ? AppColors.ink500 : AppColors.ink900,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.xl),

              if (_error != null) ...[
                Container(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  decoration: BoxDecoration(
                    color: AppColors.danger.withValues(alpha: 0.08),
                    borderRadius: AppRadius.smAll,
                    border: Border.all(color: AppColors.danger.withValues(alpha: 0.35)),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.error_outline_rounded, color: AppColors.danger, size: 18),
                      const SizedBox(width: AppSpacing.sm),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(_error!, style: const TextStyle(fontSize: 13, height: 1.35)),
                            if (_attemptsLeft != null && _attemptsLeft! > 0)
                              Padding(
                                padding: const EdgeInsets.only(top: 4),
                                child: Text(
                                  'Sisa percobaan: $_attemptsLeft',
                                  style: const TextStyle(fontSize: 12, color: AppColors.ink700),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
              ],

              FilledButton.icon(
                onPressed: _busy ? null : _submit,
                icon: _busy
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.link_rounded),
                label: Text(_busy ? 'Memeriksa...' : 'Tautkan Akun'),
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
              const SizedBox(height: AppSpacing.lg),
              const Text(
                'Data Anda diperiksa terhadap catatan BPJS. Kami tidak menyimpan NIK '
                'dalam bentuk terbaca.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 11.5, color: AppColors.ink500, height: 1.4),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
