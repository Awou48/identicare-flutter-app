import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:identicare_mobile/services/face_capture_service.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:identicare_mobile/theme/app_theme.dart';
import 'package:identicare_mobile/widgets/verification/face_camera_overlay.dart';
import 'package:provider/provider.dart';

/// Pendaftaran biometrik mandiri.
///
/// Ini yang menutup jalan buntu pada fitur utama: sebelumnya menekan
/// "Verifikasi Klaim BPJS" tanpa punya template wajah hanya menghasilkan pesan
/// error tanpa tindak lanjut, dan tidak ada satu pun cara di dalam aplikasi
/// untuk mendaftar.
///
/// Hasilnya dicatat sebagai SELF_ASSERTED - lebih lemah daripada pendaftaran
/// yang diverifikasi petugas dengan KTP, dan membawa batas nilai klaim.
/// Halaman ini mengatakannya terus terang, bukan menyembunyikannya.
class BiometricEnrollmentPage extends StatefulWidget {
  const BiometricEnrollmentPage({super.key});

  @override
  State<BiometricEnrollmentPage> createState() => _BiometricEnrollmentPageState();
}

class _BiometricEnrollmentPageState extends State<BiometricEnrollmentPage>
    with WidgetsBindingObserver {
  final _capture = FaceCaptureService();

  bool _preparing = true;
  bool _submitting = false;
  bool _consented = false;
  String? _cameraError;
  String? _error;
  String? _errorCode;
  Map<String, dynamic>? _result;
  int _framesTaken = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _prepare();
  }

  Future<void> _prepare() async {
    final init = await _capture.initialize();
    if (!mounted) return;
    setState(() {
      _preparing = false;
      _cameraError = init.ok ? null : init.reason;
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!_capture.isReady) return;
    if (state == AppLifecycleState.inactive || state == AppLifecycleState.paused) {
      _capture.pause();
    } else if (state == AppLifecycleState.resumed) {
      _capture.resume();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _capture.dispose();
    super.dispose();
  }

  Future<void> _enroll() async {
    final api = context.read<VerificationApiService>();
    setState(() {
      _submitting = true;
      _error = null;
      _errorCode = null;
      _framesTaken = 0;
    });

    try {
      final frames = await _capture.captureBurst(
        onFrame: (index, _) {
          if (mounted) setState(() => _framesTaken = index);
        },
      );
      final result = await api.enrollSelf(frames);
      if (!mounted) return;
      result.when(
        ok: (body) => setState(() {
          _result = body;
          _submitting = false;
        }),
        failure: (f) => setState(() {
          _error = f.message;
          _errorCode = f.errorCode;
          _submitting = false;
        }),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Pengambilan gambar gagal: $e';
        _submitting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Pendaftaran Biometrik')),
      body: _result != null ? _success() : _form(),
    );
  }

  Widget _form() {
    if (_preparing) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_cameraError != null && !_capture.isReady) {
      return _message(
        icon: Icons.videocam_off_outlined,
        title: 'Kamera tidak tersedia',
        body: _cameraError!,
        actionLabel: 'Coba Lagi',
        onAction: () {
          setState(() => _preparing = true);
          _prepare();
        },
      );
    }

    return Column(
      children: [
        Expanded(
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (_capture.isReady)
                FittedBox(
                  fit: BoxFit.cover,
                  child: SizedBox(
                    width: _capture.controller!.value.previewSize?.height ?? 480,
                    height: _capture.controller!.value.previewSize?.width ?? 640,
                    child: CameraPreview(_capture.controller!),
                  ),
                ),
              FaceCameraOverlay(
                state: _submitting
                    ? FaceOverlayState.capturing
                    : (_error != null
                        ? FaceOverlayState.failure
                        : FaceOverlayState.idle),
                instruction: _submitting
                    ? (_framesTaken > 0
                        ? 'Mengambil gambar $_framesTaken/3...'
                        : 'Mendaftarkan wajah...')
                    : 'Posisikan wajah di dalam oval',
              ),
            ],
          ),
        ),
        _footer(),
      ],
    );
  }

  Widget _footer() {
    return Container(
      width: double.infinity,
      color: AppColors.white,
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.xl,
        AppSpacing.lg,
        AppSpacing.xl,
        AppSpacing.xxl,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_error != null) ...[
            _errorBox(),
            const SizedBox(height: AppSpacing.md),
          ],
          // UU PDP 27/2022 menggolongkan data biometrik sebagai data pribadi
          // spesifik: persetujuannya harus eksplisit dan untuk tujuan tertentu,
          // bukan tersirat dari menekan tombol.
          CheckboxListTile(
            value: _consented,
            onChanged: _submitting
                ? null
                : (v) => setState(() => _consented = v ?? false),
            dense: true,
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            title: const Text(
              'Saya menyetujui data wajah saya diproses untuk verifikasi klaim '
              'BPJS. Gambar tidak disimpan; hanya ciri terenkripsi.',
              style: TextStyle(fontSize: 12, height: 1.35),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          FilledButton.icon(
            onPressed: (_submitting || !_consented) ? null : _enroll,
            icon: _submitting
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Icon(Icons.how_to_reg_rounded),
            label: Text(_submitting ? 'Mendaftarkan...' : 'Daftarkan Wajah Saya'),
            style: FilledButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
          ),
        ],
      ),
    );
  }

  Widget _errorBox() {
    // DUPLICATE_FACE tidak boleh dibingkai sebagai kesalahan pengguna: artinya
    // wajah ini sudah terdaftar atas peserta lain, dan itu sudah dilaporkan.
    final duplicate = _errorCode == 'DUPLICATE_FACE';
    final color = duplicate ? AppColors.warning : AppColors.danger;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: AppRadius.smAll,
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            duplicate ? Icons.gpp_maybe_rounded : Icons.error_outline_rounded,
            color: color,
            size: 18,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              _error!,
              style: const TextStyle(fontSize: 12.5, height: 1.35),
            ),
          ),
        ],
      ),
    );
  }

  Widget _success() {
    final quality = (_result!['quality'] as Map?)?.cast<String, dynamic>() ?? const {};
    final dedup = (_result!['dedup'] as Map?)?.cast<String, dynamic>() ?? const {};
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: AppSpacing.xl),
          const Center(
            child: CircleAvatar(
              radius: 52,
              backgroundColor: AppColors.brandSoft,
              child: Icon(Icons.verified_user_rounded, size: 58, color: AppColors.brand),
            ),
          ),
          const SizedBox(height: AppSpacing.xl),
          const Text(
            'Biometrik Terdaftar',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            'Anda sekarang dapat melakukan verifikasi klaim BPJS.',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.ink700),
          ),
          const SizedBox(height: AppSpacing.xl),
          _row('Frame digunakan', '${_result!['frames_used'] ?? '-'}'),
          if (quality['det_score'] != null)
            _row('Kualitas deteksi', '${quality['det_score']}'),
          if (quality['face_px'] != null) _row('Ukuran wajah', '${quality['face_px']} px'),
          _row('Dicek terhadap', '${dedup['candidates_checked'] ?? 0} template lain'),
          _row('Tingkat jaminan', '${_result!['assurance'] ?? '-'}'),
          const SizedBox(height: AppSpacing.lg),
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: AppColors.warning.withValues(alpha: 0.08),
              borderRadius: AppRadius.smAll,
            ),
            child: const Text(
              'Pendaftaran mandiri berlaku untuk klaim bernilai terbatas. Untuk '
              'batas penuh, lakukan pendaftaran di faskes dengan verifikasi KTP '
              'oleh petugas.',
              style: TextStyle(fontSize: 12, height: 1.4),
            ),
          ),
          const SizedBox(height: AppSpacing.xxl),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: FilledButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
            child: const Text('Selesai'),
          ),
        ],
      ),
    );
  }

  Widget _row(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          children: [
            Expanded(
              child: Text(label, style: TextStyle(color: AppColors.ink700, fontSize: 13)),
            ),
            Text(value, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
          ],
        ),
      );

  Widget _message({
    required IconData icon,
    required String title,
    required String body,
    String? actionLabel,
    VoidCallback? onAction,
  }) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xxxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 56, color: AppColors.ink500),
            const SizedBox(height: AppSpacing.lg),
            Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: AppSpacing.sm),
            Text(body, textAlign: TextAlign.center),
            if (actionLabel != null) ...[
              const SizedBox(height: AppSpacing.xl),
              FilledButton.icon(
                onPressed: onAction,
                icon: const Icon(Icons.refresh),
                label: Text(actionLabel),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
