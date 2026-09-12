import 'package:flutter/material.dart';
import 'package:identicare_mobile/theme/app_theme.dart';

/// Lencana status kecil, mis. "Terverifikasi dalam BPJS".
///
/// Auto-layout: lebarnya mengikuti isi (`MainAxisSize.min`) dan teksnya boleh
/// menyusut, sehingga padding tetap rata berapa pun panjang labelnya.
class AppStatusBadge extends StatelessWidget {
  const AppStatusBadge({
    super.key,
    required this.label,
    required this.icon,
    this.color = AppColors.white,
    this.background,
    this.dense = false,
  });

  final String label;
  final IconData icon;
  final Color color;
  final Color? background;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: dense ? AppSpacing.sm : AppSpacing.md,
        vertical: dense ? AppSpacing.xs : 6,
      ),
      decoration: BoxDecoration(
        color: background ?? color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(AppRadius.pill),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: dense ? 12 : 14, color: color),
          SizedBox(width: dense ? AppSpacing.xs : 6),
          Flexible(
            child: Text(
              label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: color,
                fontSize: dense ? 11 : 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Satu sel pada grid layanan.
///
/// Semua sel memakai radius, bobot ikon, dan padding yang sama; pembeda
/// visualnya hanya ikon dan label. Sebelumnya tiap kartu punya warnanya sendiri
/// (teal, biru, oranye, ungu), yang membuat grid terbaca sebagai empat hal tak
/// berhubungan alih-alih satu set.
class AppGridTile extends StatelessWidget {
  const AppGridTile({
    super.key,
    required this.label,
    required this.icon,
    required this.onTap,
    this.badge,
    this.enabled = true,
  });

  final String label;
  final IconData icon;
  final VoidCallback onTap;
  final String? badge;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.white,
      borderRadius: AppRadius.mdAll,
      child: InkWell(
        borderRadius: AppRadius.mdAll,
        onTap: enabled ? onTap : null,
        child: Ink(
          decoration: BoxDecoration(
            borderRadius: AppRadius.mdAll,
            border: Border.all(color: AppColors.ink100),
          ),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Container(
                      width: 42,
                      height: 42,
                      decoration: BoxDecoration(
                        color: enabled ? AppColors.brandSoft : AppColors.ink100,
                        borderRadius: AppRadius.smAll,
                      ),
                      child: Icon(
                        icon,
                        size: AppIcons.md,
                        color: enabled ? AppColors.brandDark : AppColors.ink500,
                      ),
                    ),
                    const Spacer(),
                    if (badge != null)
                      AppStatusBadge(
                        label: badge!,
                        icon: Icons.circle,
                        color: AppColors.warning,
                        dense: true,
                      ),
                  ],
                ),
                const SizedBox(height: AppSpacing.md),
                // Dua baris tetap: dengan tinggi teks yang sama, semua sel
                // sejajar apa pun panjang labelnya.
                SizedBox(
                  height: 38,
                  child: Text(
                    label,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 14,
                      height: 1.3,
                      fontWeight: FontWeight.w600,
                      color: enabled ? AppColors.ink900 : AppColors.ink500,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Baris daftar selebar layar, untuk tindakan sekunder yang tidak pantas
/// memakan satu sel grid penuh.
class AppListTileCard extends StatelessWidget {
  const AppListTileCard({
    super.key,
    required this.title,
    required this.icon,
    required this.onTap,
    this.subtitle,
    this.trailing,
  });

  final String title;
  final String? subtitle;
  final IconData icon;
  final VoidCallback onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
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
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Row(
              children: [
                Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                    color: AppColors.brandSoft,
                    borderRadius: AppRadius.smAll,
                  ),
                  child: const Icon(
                    Icons.local_hospital_rounded,
                    size: AppIcons.md,
                    color: AppColors.brandDark,
                  ),
                ),
                const SizedBox(width: AppSpacing.lg),
                // Expanded, bukan lebar tetap: judul panjang akan membungkus
                // alih-alih meluap ke kanan.
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        title,
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: AppColors.ink900,
                        ),
                      ),
                      if (subtitle != null) ...[
                        const SizedBox(height: 2),
                        Text(
                          subtitle!,
                          style: const TextStyle(fontSize: 12.5, color: AppColors.ink500),
                        ),
                      ],
                    ],
                  ),
                ),
                trailing ??
                    const Icon(
                      Icons.chevron_right_rounded,
                      color: AppColors.ink300,
                      size: AppIcons.lg,
                    ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Judul bagian.
class AppSectionHeader extends StatelessWidget {
  const AppSectionHeader({super.key, required this.title, this.action, this.onAction});

  final String title;
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
              color: AppColors.ink900,
            ),
          ),
          if (action != null)
            TextButton(
              onPressed: onAction,
              style: TextButton.styleFrom(
                foregroundColor: AppColors.brandDark,
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: Text(action!, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            ),
        ],
      ),
    );
  }
}

/// Keadaan kosong / error yang seragam.
class AppEmptyState extends StatelessWidget {
  const AppEmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.message,
    this.onRetry,
    this.retryLabel = 'Coba Lagi',
    this.detail,
  });

  final IconData icon;
  final String title;
  final String message;

  /// Detail teknis, ditampilkan kecil. Tanpa ini pengguna hanya melihat
  /// "Terjadi kesalahan" dan tidak punya apa pun untuk ditindaklanjuti.
  final String? detail;
  final VoidCallback? onRetry;
  final String retryLabel;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.xxxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: const BoxDecoration(
                color: AppColors.ink100,
                shape: BoxShape.circle,
              ),
              child: Icon(icon, size: AppIcons.xl, color: AppColors.ink500),
            ),
            const SizedBox(height: AppSpacing.lg),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 13.5, color: AppColors.ink500, height: 1.45),
            ),
            if (detail != null) ...[
              const SizedBox(height: AppSpacing.md),
              Container(
                padding: const EdgeInsets.all(AppSpacing.md),
                decoration: BoxDecoration(
                  color: AppColors.ink100,
                  borderRadius: AppRadius.smAll,
                ),
                child: SelectableText(
                  detail!,
                  style: const TextStyle(
                    fontSize: 11,
                    fontFamily: 'monospace',
                    color: AppColors.ink700,
                  ),
                ),
              ),
            ],
            if (onRetry != null) ...[
              const SizedBox(height: AppSpacing.xl),
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_rounded, size: AppIcons.sm),
                label: Text(retryLabel),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
