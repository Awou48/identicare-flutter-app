package com.example.identicare_mobile

import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

// FlutterFragmentActivity, bukan FlutterActivity. BiometricPrompt (yang dipakai
// local_auth maupun KeystoreSigner) hanya bisa ditampilkan dari FragmentActivity;
// dengan FlutterActivity biasa, authenticate() langsung melempar
// PlatformException(no_fragment_activity) tanpa prompt apa pun.
class MainActivity : FlutterFragmentActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, KeystoreSigner.CHANNEL)
            .setMethodCallHandler(KeystoreSigner(this))
    }
}
