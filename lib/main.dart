import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:identicare_mobile/theme/app_theme.dart';
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

  await initializeDateFormatting('id_ID', null);

  await AppConfig.load();

  runApp(const MyApp());
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
          update: (_, client, previous) =>
              previous ?? VerificationApiService(client),
        ),
      ],
      child: MaterialApp(
        title: 'IdentiCare',
        theme: buildAppTheme(),
        locale: const Locale('id', 'ID'),
        supportedLocales: const [Locale('id', 'ID'), Locale('en', 'US')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: const AuthWrapper(),
        debugShowCheckedModeBanner: false,
      ),
    );
  }
}
