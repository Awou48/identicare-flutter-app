import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

/// Default [FirebaseOptions]

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) {
      return web;
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      case TargetPlatform.macOS:
        return macos;
      case TargetPlatform.windows:
        return windows;
      case TargetPlatform.linux:
        throw UnsupportedError(
          'DefaultFirebaseOptions have not been configured for linux - '
          'you can reconfigure this by running the FlutterFire CLI again.',
        );
      default:
        throw UnsupportedError(
          'DefaultFirebaseOptions are not supported for this platform.',
        );
    }
  }

  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'AIzaSyB_-Ir4HhPNlUh5IIYBCyZvsBgM2CgZX6M',
    appId: '1:358504594305:web:8758a76f2f5da62d1e0680',
    messagingSenderId: '358504594305',
    projectId: 'identicare-591e3',
    authDomain: 'identicare-591e3.firebaseapp.com',
    storageBucket: 'identicare-591e3.firebasestorage.app',
    measurementId: 'G-MZVDH2FEHQ',
  );

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'AIzaSyBGUBbFVWFePFBy9HaEYL2mdz9sOBjAEyU',
    appId: '1:358504594305:android:1d08178b62c250a41e0680',
    messagingSenderId: '358504594305',
    projectId: 'identicare-591e3',
    storageBucket: 'identicare-591e3.firebasestorage.app',
  );

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'AIzaSyAyJ-s9VJZjbVdnbqP-fW_hmNLuzpGv9Ro',
    appId: '1:358504594305:ios:45f7d1086f664c391e0680',
    messagingSenderId: '358504594305',
    projectId: 'identicare-591e3',
    storageBucket: 'identicare-591e3.firebasestorage.app',
    iosBundleId: 'com.example.identicareMobile',
  );

  static const FirebaseOptions macos = FirebaseOptions(
    apiKey: 'AIzaSyAyJ-s9VJZjbVdnbqP-fW_hmNLuzpGv9Ro',
    appId: '1:358504594305:ios:45f7d1086f664c391e0680',
    messagingSenderId: '358504594305',
    projectId: 'identicare-591e3',
    storageBucket: 'identicare-591e3.firebasestorage.app',
    iosBundleId: 'com.example.identicareMobile',
  );

  static const FirebaseOptions windows = FirebaseOptions(
    apiKey: 'AIzaSyB_-Ir4HhPNlUh5IIYBCyZvsBgM2CgZX6M',
    appId: '1:358504594305:web:434c38ccaad32ebc1e0680',
    messagingSenderId: '358504594305',
    projectId: 'identicare-591e3',
    authDomain: 'identicare-591e3.firebaseapp.com',
    storageBucket: 'identicare-591e3.firebasestorage.app',
    measurementId: 'G-H0E672VL8J',
  );
}
