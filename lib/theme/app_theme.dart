import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Token desain tunggal untuk seluruh aplikasi.
///
/// Sebelumnya warna ditentukan ad-hoc di tiap halaman - teal untuk satu kartu,
/// biru untuk kartu berikutnya, oranye dan ungu untuk sisanya - sehingga tidak
/// ada satu pun nilai yang bisa diubah di satu tempat. Semua nilai visual
/// sekarang berasal dari sini.
///
/// Identitasnya hijau: IdentiCare adalah produk verifikasi, dan hijau berarti
/// "terverifikasi". Warna lain hanya dipakai untuk makna semantik (peringatan,
/// bahaya), bukan untuk membedakan kartu satu dengan lainnya.
class AppColors {
  AppColors._();

  // --- Merek --- //
  static const brand = Color(0xFF34A853);
  static const brandDark = Color(0xFF1E7E38);
  static const brandDeep = Color(0xFF12602A);

  /// Latar bertint untuk ikon dan chip di atas permukaan terang.
  static const brandSoft = Color(0xFFE8F5EC);

  // --- Netral --- //
  static const ink900 = Color(0xFF0F172A);
  static const ink700 = Color(0xFF334155);
  static const ink500 = Color(0xFF64748B);
  static const ink300 = Color(0xFFCBD5E1);
  static const ink100 = Color(0xFFF1F5F9);
  static const surface = Color(0xFFF6F8FA);
  static const white = Color(0xFFFFFFFF);

  // --- Semantik: dipakai HANYA untuk makna, bukan variasi visual --- //
  static const success = brand;
  static const warning = Color(0xFFF9AB00);
  static const danger = Color(0xFFD93025);

  /// Aksen informasi. Teal dipertahankan hanya di sini, bukan sebagai warna
  /// kartu sembarangan.
  static const info = Color(0xFF0A7E8C);

  static const headerGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [brandDark, brand],
  );
}

/// Radius sudut. Tiga nilai saja - lebih dari itu dan konsistensinya hilang.
class AppRadius {
  AppRadius._();

  static const double sm = 12;
  static const double md = 16;
  static const double lg = 24;
  static const double pill = 999;

  static final BorderRadius smAll = BorderRadius.circular(sm);
  static final BorderRadius mdAll = BorderRadius.circular(md);
  static final BorderRadius lgAll = BorderRadius.circular(lg);
}

/// Skala jarak kelipatan 4.
class AppSpacing {
  AppSpacing._();

  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double xxxl = 32;

  /// Padding horizontal halaman. Dipakai setiap layar supaya tepi kiri semua
  /// konten lurus dari atas ke bawah.
  static const double page = 20;
}

/// Ukuran ikon. Bobot ikon dijaga konsisten dengan hanya memakai varian
/// `_rounded` di seluruh aplikasi - mencampur outlined dan filled membuat
/// grid terlihat tidak rata meskipun ukurannya sama.
class AppIcons {
  AppIcons._();

  static const double sm = 18;
  static const double md = 22;
  static const double lg = 26;
  static const double xl = 32;
}

ThemeData buildAppTheme() {
  final base = ThemeData(
    colorScheme: ColorScheme.fromSeed(
      seedColor: AppColors.brand,
      primary: AppColors.brand,
      secondary: AppColors.brandDark,
      surface: AppColors.surface,
      error: AppColors.danger,
    ),
    useMaterial3: true,
    scaffoldBackgroundColor: AppColors.surface,
  );

  final text = GoogleFonts.poppinsTextTheme(base.textTheme).apply(
    bodyColor: AppColors.ink900,
    displayColor: AppColors.ink900,
  );

  return base.copyWith(
    textTheme: text,
    appBarTheme: AppBarTheme(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      foregroundColor: AppColors.ink900,
      titleTextStyle: GoogleFonts.poppins(
        fontSize: 18,
        fontWeight: FontWeight.w600,
        color: AppColors.ink900,
      ),
    ),
    cardTheme: CardThemeData(
      color: AppColors.white,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadius.mdAll,
        side: const BorderSide(color: AppColors.ink100),
      ),
    ),
    // Padding horizontal wajib ada. Tombol yang direntang selebar layar tidak
    // peduli, tetapi tombol yang mengikuti lebar labelnya ("Login Petugas",
    // "Ajukan Override") tampak sesak tanpa itu - teks menempel ke tepi.
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.brand,
        foregroundColor: AppColors.white,
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg, horizontal: AppSpacing.xxl),
        shape: RoundedRectangleBorder(borderRadius: AppRadius.smAll),
        textStyle: GoogleFonts.poppins(fontSize: 15, fontWeight: FontWeight.w600),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.brand,
        foregroundColor: AppColors.white,
        elevation: 0,
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg, horizontal: AppSpacing.xxl),
        shape: RoundedRectangleBorder(borderRadius: AppRadius.smAll),
        textStyle: GoogleFonts.poppins(fontSize: 15, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.brand,
        side: const BorderSide(color: AppColors.ink300),
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg, horizontal: AppSpacing.xxl),
        shape: RoundedRectangleBorder(borderRadius: AppRadius.smAll),
        textStyle: GoogleFonts.poppins(fontSize: 15, fontWeight: FontWeight.w600),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.white,
      contentPadding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.lg,
        vertical: AppSpacing.lg,
      ),
      border: OutlineInputBorder(
        borderRadius: AppRadius.smAll,
        borderSide: const BorderSide(color: AppColors.ink300),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: AppRadius.smAll,
        borderSide: const BorderSide(color: AppColors.ink300),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: AppRadius.smAll,
        borderSide: const BorderSide(color: AppColors.brand, width: 1.6),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: AppColors.white,
      selectedColor: AppColors.brandSoft,
      side: const BorderSide(color: AppColors.ink300),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.pill)),
      // Warna WAJIB disebut di sini. Tanpa itu chip kehilangan resolusi warna
      // bawaan Material dan labelnya dirender putih - di atas latar putih dan
      // hijau muda hasilnya tidak terbaca sama sekali, yang persis terjadi pada
      // filter riwayat verifikasi.
      labelStyle: GoogleFonts.poppins(
        fontSize: 13,
        fontWeight: FontWeight.w500,
        color: AppColors.ink700,
      ),
      // ChoiceChip adalah chip "secondary": saat terpilih ia memakai gaya ini,
      // bukan labelStyle.
      secondaryLabelStyle: GoogleFonts.poppins(
        fontSize: 13,
        fontWeight: FontWeight.w600,
        color: AppColors.brandDark,
      ),
      secondarySelectedColor: AppColors.brandSoft,
      checkmarkColor: AppColors.brandDark,
      showCheckmark: true,
    ),
    bottomNavigationBarTheme: BottomNavigationBarThemeData(
      backgroundColor: AppColors.white,
      selectedItemColor: AppColors.brand,
      unselectedItemColor: AppColors.ink500,
      selectedLabelStyle: GoogleFonts.poppins(fontSize: 11, fontWeight: FontWeight.w600),
      unselectedLabelStyle: GoogleFonts.poppins(fontSize: 11),
      type: BottomNavigationBarType.fixed,
      elevation: 8,
    ),
    dividerTheme: const DividerThemeData(color: AppColors.ink100, thickness: 1),
  );
}
