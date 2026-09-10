import 'package:flutter/material.dart';
import 'package:identicare_mobile/models/verification_session.dart';

/// Indikator 4 langkah untuk alur verifikasi klaim BPJS.
class StepProgressIndicator extends StatelessWidget {
  const StepProgressIndicator({super.key, required this.currentStep});

  final SessionStep currentStep;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final steps = SessionStep.values;
    final activeIndex = currentStep.index0;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      color: Colors.white,
      child: Row(
        children: List.generate(steps.length * 2 - 1, (i) {
          if (i.isOdd) {
            final beforeIndex = i ~/ 2;
            return Expanded(
              child: Container(
                height: 2,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                color: beforeIndex < activeIndex
                    ? theme.colorScheme.primary
                    : Colors.grey.shade300,
              ),
            );
          }

          final index = i ~/ 2;
          final done = index < activeIndex;
          final active = index == activeIndex;
          final color = done || active ? theme.colorScheme.primary : Colors.grey.shade300;

          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 30,
                height: 30,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: done ? color : (active ? color : Colors.transparent),
                  border: Border.all(color: color, width: 2),
                ),
                child: Center(
                  child: done
                      ? const Icon(Icons.check, size: 16, color: Colors.white)
                      : Text(
                          '${index + 1}',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            fontSize: 13,
                            color: active ? Colors.white : Colors.grey.shade600,
                          ),
                        ),
                ),
              ),
              const SizedBox(height: 6),
              SizedBox(
                width: 62,
                child: Text(
                  steps[index].label,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 9.5,
                    height: 1.15,
                    fontWeight: active ? FontWeight.bold : FontWeight.normal,
                    color: done || active ? theme.colorScheme.primary : Colors.grey.shade600,
                  ),
                ),
              ),
            ],
          );
        }),
      ),
    );
  }
}
