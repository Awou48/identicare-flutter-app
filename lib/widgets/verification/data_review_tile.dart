import 'package:flutter/material.dart';

class DataReviewTile extends StatelessWidget {
  const DataReviewTile({
    super.key,
    required this.label,
    required this.value,
    this.icon,
    this.highlight = false,
    this.monospace = false,
  });

  final String label;
  final String value;
  final IconData? icon;
  final bool highlight;

  final bool monospace;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 18, color: Colors.grey.shade600),
            const SizedBox(width: 12),
          ],
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: TextStyle(color: Colors.grey.shade700, fontSize: 13),
            ),
          ),
          Expanded(
            child: Text(
              value.isEmpty ? '-' : value,
              style: TextStyle(
                fontWeight: highlight ? FontWeight.bold : FontWeight.w500,
                fontSize: 14,
                fontFamily: monospace ? 'monospace' : null,
                letterSpacing: monospace ? 0.5 : null,
                color: highlight
                    ? theme.colorScheme.primary
                    : const Color(0xFF1E293B),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class BiometricResultCard extends StatelessWidget {
  const BiometricResultCard({
    super.key,
    required this.title,
    required this.passed,
    this.icon,
    this.detail,
    this.warning,
  });

  final String title;
  final bool passed;
  final IconData? icon;
  final String? detail;

  final String? warning;

  @override
  Widget build(BuildContext context) {
    final color = passed ? const Color(0xFF34A853) : const Color(0xFFD93025);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Icon(icon ?? (passed ? Icons.check_circle : Icons.cancel),
              color: color, size: 22),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 14)),
                if (detail != null)
                  Text(detail!,
                      style:
                          TextStyle(fontSize: 12, color: Colors.grey.shade700)),
                if (warning != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Row(
                      children: [
                        const Icon(Icons.info_outline,
                            size: 12, color: Color(0xFFF9AB00)),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            warning!,
                            style: const TextStyle(
                                fontSize: 11, color: Color(0xFFB06000)),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
