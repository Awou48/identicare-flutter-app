import 'package:flutter/material.dart';
import 'package:identicare_mobile/auth_wrapper.dart';
import 'package:identicare_mobile/services/auth_service.dart';
import 'package:provider/provider.dart';
import 'package:firebase_core/firebase_core.dart';
import 'firebase_options.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  await AuthService().signOut();

  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (context) => AuthService(),
      child: MaterialApp(
        title: 'IdentiCare',
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF0A7E8C), // Biru Kehijauan
            primary: const Color(0xFF0A7E8C),
            secondary: const Color(0xFF34A853), // Hijau
            background: const Color(0xFFF5F8FA),
          ),
          useMaterial3: true,
          fontFamily: 'Poppins',
          scaffoldBackgroundColor: const Color(0xFFF5F8FA),
          appBarTheme: const AppBarTheme(
            backgroundColor: Colors.transparent,
            elevation: 0,
            foregroundColor: Color(0xFF1E293B),
            titleTextStyle: TextStyle(
              fontFamily: 'Poppins',
              fontSize: 20,
              fontWeight: FontWeight.w600,
              color: Color(0xFF1E293B),
            )
          ),
        ),
        home: const AuthWrapper(),
        debugShowCheckedModeBanner: false,
      ),
    );
  }
}
