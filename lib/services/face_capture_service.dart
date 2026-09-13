import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:identicare_mobile/config/app_config.dart';
import 'package:image/image.dart' as img;

class FaceCaptureService {
  CameraController? _controller;
  List<CameraDescription> _cameras = const [];
  bool _initializing = false;

  CameraController? get controller => _controller;
  bool get isReady => _controller?.value.isInitialized ?? false;

  Future<CaptureInit> initialize() async {
    if (_initializing) {
      return const CaptureInit(ok: false, reason: 'Sedang menyiapkan kamera.');
    }
    _initializing = true;
    try {
      _cameras = await availableCameras();
      if (_cameras.isEmpty) {
        return const CaptureInit(
          ok: false,
          reason: 'Tidak ada kamera yang terdeteksi pada perangkat ini.',
        );
      }

      final front = _cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.front,
        orElse: () => _cameras.first,
      );

      final controller = CameraController(
        front,
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await controller.initialize();
      _controller = controller;
      return const CaptureInit(ok: true);
    } on CameraException catch (e) {
      final denied = e.code == 'CameraAccessDenied' ||
          e.code == 'CameraAccessDeniedWithoutPrompt';
      return CaptureInit(
        ok: false,
        permissionDenied: denied,
        reason: denied
            ? 'Izin kamera ditolak. Aktifkan lewat Pengaturan aplikasi.'
            : 'Kamera tidak dapat dijalankan (${e.code}).',
      );
    } on Exception catch (e) {
      return CaptureInit(ok: false, reason: 'Kamera gagal disiapkan: $e');
    } finally {
      _initializing = false;
    }
  }

  Future<List<List<int>>> captureBurst({
    int frames = AppConfig.faceBurstFrames,
    Duration interval = AppConfig.faceBurstInterval,
    void Function(int index, int total)? onFrame,
  }) async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      throw StateError('Kamera belum siap.');
    }

    final captured = <List<int>>[];
    for (var i = 0; i < frames; i++) {
      final file = await controller.takePicture();
      final bytes = await file.readAsBytes();
      captured.add(await compute(_downscale, bytes));
      onFrame?.call(i + 1, frames);

      try {
        await File(file.path).delete();
      } catch (_) {}

      if (i < frames - 1) await Future<void>.delayed(interval);
    }
    return captured;
  }

  Future<void> pause() async {
    try {
      await _controller?.pausePreview();
    } catch (_) {}
  }

  Future<void> resume() async {
    try {
      await _controller?.resumePreview();
    } catch (_) {}
  }

  Future<void> dispose() async {
    final controller = _controller;
    _controller = null;
    try {
      await controller?.dispose();
    } catch (_) {}
  }
}

List<int> _downscale(List<int> bytes) {
  try {
    final decoded = img.decodeImage(Uint8List.fromList(bytes));
    if (decoded == null) return bytes;

    final oriented = img.bakeOrientation(decoded);

    final longest =
        oriented.width > oriented.height ? oriented.width : oriented.height;
    final resized = longest > AppConfig.uploadMaxDimension
        ? img.copyResize(
            oriented,
            width: oriented.width >= oriented.height
                ? AppConfig.uploadMaxDimension
                : null,
            height: oriented.height > oriented.width
                ? AppConfig.uploadMaxDimension
                : null,
            interpolation: img.Interpolation.average,
          )
        : oriented;

    return img.encodeJpg(resized, quality: AppConfig.uploadJpegQuality);
  } catch (_) {
    return bytes;
  }
}

class CaptureInit {
  final bool ok;
  final bool permissionDenied;
  final String? reason;

  const CaptureInit({
    required this.ok,
    this.permissionDenied = false,
    this.reason,
  });
}
