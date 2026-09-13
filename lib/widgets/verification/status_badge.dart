import 'package:flutter/material.dart';

class StatusBadge extends StatelessWidget {
  const StatusBadge({super.key, required this.status, this.compact = false});

  final String status;
  final bool compact;

  static const _approved = Color(0xFF34A853);
  static const _review = Color(0xFFF9AB00);
  static const _rejected = Color(0xFFD93025);

  Color get _color => switch (status.toUpperCase()) {
        'APPROVED' => _approved,
        'REVIEW' => _review,
        'REJECTED' => _rejected,
        'LOW' => _approved,
        'MEDIUM' => _review,
        'HIGH' => _rejected,
        _ => Colors.grey,
      };

  IconData get _icon => switch (status.toUpperCase()) {
        'APPROVED' => Icons.verified_rounded,
        'REVIEW' => Icons.pending_actions_rounded,
        'REJECTED' => Icons.gpp_bad_rounded,
        _ => Icons.info_outline,
      };

  String get _label => switch (status.toUpperCase()) {
        'APPROVED' => 'Disetujui',
        'REVIEW' => 'Menunggu Tinjauan',
        'REJECTED' => 'Ditolak',
        'LOW' => 'Risiko Rendah',
        'MEDIUM' => 'Risiko Sedang',
        'HIGH' => 'Risiko Tinggi',
        _ => status,
      };

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 8 : 12,
        vertical: compact ? 4 : 6,
      ),
      decoration: BoxDecoration(
        color: _color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _color.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(_icon, size: compact ? 13 : 16, color: _color),
          SizedBox(width: compact ? 4 : 6),
          Text(
            _label,
            style: TextStyle(
              color: _color,
              fontWeight: FontWeight.w600,
              fontSize: compact ? 11 : 13,
            ),
          ),
        ],
      ),
    );
  }
}
