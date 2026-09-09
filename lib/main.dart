import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:identicare_mobile/auth_wrapper.dart';
import 'package:identicare_mobile/config/app_config.dart';
import 'package:identicare_mobile/services/auth_service.dart';
import 'package:identicare_mobile/services/identicare_api_client.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:provider/provider.dart';

import 'firebase_options.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  // history_page.dart dan profile_page.dart memanggil DateFormat(..., 'id_ID').
  // Tanpa inisialisasi locale ini, keduanya melempar LocaleDataException.
  await initializeDateFormatting('id_ID', null);

  // Base URL API: --dart-define, atau override debug dari SharedPreferences.
  await AppConfig.load();

  // CATATAN: di sini dulu ada `await AuthService().signOut();` yang memaksa
  // logout setiap cold start. Itu sisa kode development dan akan terlihat
  // seperti bug saat demo.

  runApp(const MyApp());
}

/// Tema aplikasi.
///
/// Sebelumnya `fontFamily: 'Poppins'` diset di sini tanpa satu pun aset font
/// terdaftar di pubspec.yaml, sehingga Flutter diam-diam mundur ke Roboto dan
/// tampilannya tidak pernah sesuai desain. `google_fonts` menyediakan Poppins
/// sungguhan.
///
/// CATATAN offline: secara default google_fonts mengunduh font saat pertama
/// dipakai lalu menyimpannya di cache perangkat. Jadi peluncuran PERTAMA di
/// perangkat baru tanpa internet akan tetap memakai Roboto sampai fontnya
/// berhasil diambil. Kalau demo harus dijamin tampil benar dalam keadaan
/// offline total, unduh berkas TTF Poppins ke `assets/fonts/`, daftarkan di
/// blok `fonts:` pubspec.yaml, dan setel
/// `GoogleFonts.config.allowRuntimeFetching = false;` - google_fonts akan
/// memakai aset paketan itu tanpa jaringan sama sekali.
ThemeData _buildTheme() {
  const primary = Color(0xFF0A7E8C); // Biru kehijauan
  const secondary = Color(0xFF34A853); // Hijau
  const surface = Color(0xFFF5F8FA);
  const ink = Color(0xFF1E293B);

  final base = ThemeData(
    colorScheme: ColorScheme.fromSeed(
      seedColor: primary,
      primary: primary,
      secondary: secondary,
      // `background` sudah deprecated sejak Flutter 3.18; `surface` penggantinya.
      surface: surface,
    ),
    useMaterial3: true,
    scaffoldBackgroundColor: surface,
  );

  return base.copyWith(
    textTheme: GoogleFonts.poppinsTextTheme(base.textTheme),
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      elevation: 0,
      foregroundColor: ink,
      titleTextStyle: GoogleFonts.poppins(
        fontSize: 20,
        fontWeight: FontWeight.w600,
        color: ink,
      ),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthService()),
        ProxyProvider<AuthService, IdenticareApiClient>(
          update: (_, auth, previous) => previous ?? IdenticareApiClient(auth),
          dispose: (_, client) => client.dispose(),
        ),
        ProxyProvider<IdenticareApiClient, VerificationApiService>(
          update: (_, client, previous) => previous ?? VerificationApiService(client),
        ),
      ],
      child: MaterialApp(
        title: 'IdentiCare',
        theme: _buildTheme(),
        home: const AuthWrapper(),
        debugShowCheckedModeBanner: false,
      ),
    );
  }
}
