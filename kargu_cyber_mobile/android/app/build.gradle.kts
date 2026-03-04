plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
    id("com.google.gms.google-services") // <--- İŞTE BU SATIRI EKLEDİK
}

android {
    namespace = "com.example.kargu_cyber_mobile"

    // --- BURAYI DEĞİŞTİRDİK VE EKLEDİK ---
    compileSdk = 36
    buildToolsVersion = "34.0.0"
    // ------------------------------------

    ndkVersion = flutter.ndkVersion

    compileOptions {
        isCoreLibraryDesugaringEnabled = true // <--- YENİ EKLENEN SATIR: Hata çözümünün kalbi
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.example.kargu_cyber_mobile"

        // --- BURAYI GÜVENCEYE ALDIK ---
        minSdk = flutter.minSdkVersion
        // ------------------------------

        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    source = "../.."
}

// <--- SADECE SÜRÜMÜ 2.1.4 YAPTIK --->
dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}