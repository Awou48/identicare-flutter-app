package com.example.identicare_mobile

import io.flutter.embedding.android.FlutterFragmentActivity

// FlutterFragmentActivity, bukan FlutterActivity. BiometricPrompt (yang dipakai
// local_auth) hanya bisa ditampilkan dari FragmentActivity; dengan FlutterActivity
// biasa, authenticate() langsung melempar PlatformException(no_fragment_activity)
// tanpa prompt apa pun - dan aplikasi menampilkannya sebagai "dibatalkan".
class MainActivity : FlutterFragmentActivity()
