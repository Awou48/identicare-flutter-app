import 'package:flutter/material.dart';

class FaceCameraOverlay extends StatelessWidget {
  const FaceCameraOverlay({
    super.key,
    this.state = FaceOverlayState.idle,
    this.instruction,
  });

  final FaceOverlayState state;
  final String? instruction;

  Color get _color => switch (state) {
        FaceOverlayState.idle => Colors.white70,
        FaceOverlayState.capturing => const Color(0xFF0A7E8C),
        FaceOverlayState.success => const Color(0xFF34A853),
        FaceOverlayState.failure => const Color(0xFFD93025),
      };

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        CustomPaint(painter: _OvalCutoutPainter(color: _color)),
        if (instruction != null)
          Align(
            alignment: Alignment.topCenter,
            child: Container(
              margin: const EdgeInsets.only(top: 24, left: 24, right: 24),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.65),
                borderRadius: BorderRadius.circular(24),
              ),
              child: Text(
                instruction!,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

enum FaceOverlayState { idle, capturing, success, failure }

class _OvalCutoutPainter extends CustomPainter {
  _OvalCutoutPainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final oval = Rect.fromCenter(
      center: Offset(size.width / 2, size.height * 0.46),
      width: size.width * 0.72,
      height: size.height * 0.56,
    );

    final scrim = Path()
      ..addRect(Rect.fromLTWH(0, 0, size.width, size.height))
      ..addOval(oval)
      ..fillType = PathFillType.evenOdd;
    canvas.drawPath(
        scrim, Paint()..color = Colors.black.withValues(alpha: 0.55));

    canvas.drawOval(
      oval,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3,
    );
  }

  @override
  bool shouldRepaint(covariant _OvalCutoutPainter oldDelegate) =>
      oldDelegate.color != color;
}
