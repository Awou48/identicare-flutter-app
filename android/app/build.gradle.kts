plugins {
    id("com.android.application")
    // START: FlutterFire Configuration
    id("com.google.gms.google-services")
    // END: FlutterFire Configuration
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.example.identicare_mobile"
    compileSdk = flutter.compileSdkVersion

    // 27.0.12077973 ada di SDK ini tetapi direktorinya KOSONG (unduhan rusak,
    // tidak punya source.properties), sehingga build gagal dengan CXX1101.
    // 28.2.13676358 terpasang lengkap. Ganti kembali kalau NDK 27 diunduh ulang.
    ndkVersion = "28.2.13676358"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }

    kotlinOptions {
        jvmTarget = "1.8"
    }

    defaultConfig {
        // JANGAN diubah tanpa mendaftarkan aplikasi Android kedua di Firebase
        // Console: google-services.json dan firebase.json terikat pada ID ini,
        // dan menggantinya akan merusak Firebase Auth secara diam-diam.
        applicationId = "com.example.identicare_mobile"
        // Eksplisit, bukan warisan default Flutter: androidx.biometric butuh 23+
        // dan attestation kunci Keystore butuh 24+.
        minSdk = 24
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // CATATAN: masih menandatangani rilis dengan kunci DEBUG, jadi APK
            // ini belum bisa didistribusikan. Untuk rilis sungguhan, buat
            // android/key.properties (sudah di .gitignore) lalu tambahkan
            // signingConfigs.create("release") yang membacanya.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    source = "../.."
}

dependencies {
    // Dibutuhkan local_auth untuk BiometricPrompt, dan menjadi dasar jalur
    // attestation Keystore (Tier B) berikutnya.
    implementation("androidx.biometric:biometric:1.1.0")
}