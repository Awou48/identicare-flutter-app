import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:identicare_mobile/config/app_config.dart';
import 'package:identicare_mobile/models/step_results.dart';
import 'package:identicare_mobile/pages/verification/override_request_page.dart';
import 'package:identicare_mobile/services/face_capture_service.dart';
import 'package:identicare_mobile/state/verification_flow_controller.dart';
import 'package:identicare_mobile/widgets/verification/face_camera_overlay.dart';
import 'package:provider/provider.dart';

class Step1FaceScanPage extends StatefulWidget {
  const Step1FaceScanPage({super.key});

  @override
  State<Step1FaceScanPage> createState() => _Step1FaceScanPageState();
}

class _Step1FaceScanPageState extends State<Step1FaceScanPage>
    with WidgetsBindingObserver {
  final _capture = FaceCaptureService();

  bool _preparing = true;
  String? _cameraError;
  bool _permissionDenied = false;
  FaceOverlayState _overlay = FaceOverlayState.idle;
  int _framesTaken = 0;
  _CapturePhase _phase = _CapturePhase.idle;

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
      _permissionDenied = init.permissionDenied;
    });
    if (init.ok) {
      await context.read<VerificationFlowController>().loadChallenge();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!_capture.isReady) return;
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
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

  Future<void> _scan() async {
    final controller = context.read<VerificationFlowController>();
    controller.clearError();
    setState(() {
      _overlay = FaceOverlayState.capturing;
      _framesTaken = 0;
      _phase = _CapturePhase.neutral;
    });

    try {
      await Future<void>.delayed(AppConfig.faceNeutralHold);
      if (!mounted) return;
      final frames = await _capture.captureBurst(
        frames: 1,
        onFrame: (index, total) {
          if (mounted) setState(() => _framesTaken = index);
        },
      );

      setState(() => _phase = _CapturePhase.challenge);
      await Future<void>.delayed(AppConfig.faceChallengeHold);
      if (!mounted) return;
      frames.addAll(await _capture.captureBurst(
        frames: AppConfig.faceBurstFrames - 1,
        onFrame: (index, total) {
          if (mounted) setState(() => _framesTaken = 1 + index);
        },
      ));

      setState(() => _phase = _CapturePhase.idle);
      final passed = await controller.submitFace(frames);
      if (!mounted) return;
      setState(() {
        _overlay = passed ? FaceOverlayState.success : FaceOverlayState.failure;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _overlay = FaceOverlayState.failure;
        _cameraError = 'Pengambilan gambar gagal: $e';
      });
    }
  }

  String _instructionFor(
      VerificationFlowController controller, LivenessChallenge? challenge) {
    switch (_phase) {
      case _CapturePhase.neutral:
        return 'Hadapkan wajah lurus ke kamera';
      case _CapturePhase.challenge:
        return '${challenge?.instruction ?? 'Gerakkan kepala'} - sekarang! '
            '($_framesTaken/${AppConfig.faceBurstFrames})';
      case _CapturePhase.idle:
        if (controller.isBusy) return 'Memproses...';

        return challenge == null
            ? 'Posisikan wajah di dalam oval'
            : 'Siap? Nanti Anda diminta: ${challenge.instruction.toLowerCase()}';
    }
  }

  Future<void> _openOverride(VerificationFlowController controller) async {
    final body = await Navigator.push<Map<String, dynamic>>(
      context,
      MaterialPageRoute(
        builder: (_) => OverrideRequestPage(
          sessionId: controller.sessionId!,
          sessionToken: controller.sessionToken!,
        ),
      ),
    );
    if (body != null && mounted) {
      controller.applyOverrideResult(body);
    }
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<VerificationFlowController>();

    if (_preparing) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_cameraError != null && !_capture.isReady) {
      return _CameraError(
        message: _cameraError!,
        permissionDenied: _permissionDenied,
        onRetry: () {
          setState(() => _preparing = true);
          _prepare();
        },
      );
    }

    final face = controller.faceResult;
    final challenge = controller.challenge;

    return Column(
      children: [
        Expanded(
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (_capture.isReady)
                FittedBox(
                  fit: BoxFit.cover,
                  clipBehavior: Clip.hardEdge,
                  child: SizedBox(
                    width:
                        _capture.controller!.value.previewSize?.height ?? 480,
                    height:
                        _capture.controller!.value.previewSize?.width ?? 640,
                    child: CameraPreview(_capture.controller!),
                  ),
                ),
              FaceCameraOverlay(
                state: _overlay,
                instruction: _instructionFor(controller, challenge),
              ),
            ],
          ),
        ),
        _Footer(
          controller: controller,
          face: face,
          onScan: _scan,
          onRequestOverride: () => _openOverride(controller),
        ),
      ],
    );
  }
}

enum _CapturePhase { idle, neutral, challenge }

class _Footer extends StatelessWidget {
  const _Footer({
    required this.controller,
    required this.face,
    required this.onScan,
    required this.onRequestOverride,
  });

  final VerificationFlowController controller;
  final FaceStepResult? face;
  final VoidCallback onScan;
  final VoidCallback onRequestOverride;

  @override
  Widget build(BuildContext context) {
    final error = controller.error;
    final exhausted = face?.isExhausted ?? false;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      color: Colors.white,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (error != null) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFD93025).withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                children: [
                  const Icon(Icons.error_outline,
                      color: Color(0xFFD93025), size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(error, style: const TextStyle(fontSize: 13)),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
          ] else ...[
            Text(
              'Pastikan wajah terlihat jelas, pencahayaan cukup, '
              'dan hanya Anda yang berada di depan kamera.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
            ),
            const SizedBox(height: 12),
          ],
          if (exhausted) ...[
            const Text(
              'Batas percobaan tercapai.',
              textAlign: TextAlign.center,
              style: TextStyle(
                  color: Color(0xFFD93025), fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 6),
            Text(
              'Jika wajah tidak dapat dipindai karena cedera, keterbatasan '
              'fisik, atau masalah perangkat, petugas dapat mengajukan '
              'verifikasi manual.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: controller.isBusy ? null : onRequestOverride,
              icon: const Icon(Icons.medical_information_outlined),
              label: const Text('Ajukan Verifikasi Manual (Petugas)'),
            ),
          ] else
            FilledButton.icon(
              onPressed: controller.isBusy ? null : onScan,
              icon: controller.isBusy
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.face_retouching_natural),
              label: Text(controller.isBusy
                  ? 'Memverifikasi...'
                  : (face != null ? 'Coba Lagi' : 'Mulai Scan Wajah')),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
            ),
        ],
      ),
    );
  }
}

class _CameraError extends StatelessWidget {
  const _CameraError({
    required this.message,
    required this.permissionDenied,
    required this.onRetry,
  });

  final String message;
  final bool permissionDenied;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              permissionDenied
                  ? Icons.no_photography_outlined
                  : Icons.videocam_off_outlined,
              size: 56,
              color: Colors.grey.shade500,
            ),
            const SizedBox(height: 16),
            const Text('Kamera tidak tersedia',
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
