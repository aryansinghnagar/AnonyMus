plugins {
  alias(libs.plugins.android.application)
  alias(libs.plugins.compose.compiler)
  alias(libs.plugins.kotlin.serialization)
  id("com.android.legacy-kapt") version "9.0.1"
}

android {
    namespace = "com.anonymus.app"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.anonymus.app"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"

        val appName = project.findProperty("GLOBAL_APP_NAME") as? String ?: "AnonyMus"
        val urlScheme = project.findProperty("GLOBAL_URL_SCHEME") as? String ?: "anonymus"
        val urlHostJoin = project.findProperty("GLOBAL_URL_HOST_JOIN") as? String ?: "join"
        val prefsName = project.findProperty("GLOBAL_PREFS_NAME") as? String ?: "anonymus_prefs"

        manifestPlaceholders["appScheme"] = urlScheme
        manifestPlaceholders["appHostJoin"] = urlHostJoin
        resValue("string", "app_name", appName)

        buildConfigField("String", "APP_NAME", "\"$appName\"")
        buildConfigField("String", "URL_SCHEME", "\"$urlScheme\"")
        buildConfigField("String", "URL_HOST_JOIN", "\"$urlHostJoin\"")
        buildConfigField("String", "PREFS_NAME", "\"$prefsName\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
      compose = true
      aidl = false
      buildConfig = true
      shaders = false
      resValues = true
    }

    packaging {
      resources {
        excludes += "/META-INF/{AL2.0,LGPL2.1}"
        // JNA ships duplicate native libs — pick one
        pickFirsts += "**/libjnidispatch.so"
      }
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
  val composeBom = platform(libs.androidx.compose.bom)
  implementation(composeBom)
  androidTestImplementation(composeBom)

  // Core Android dependencies
  implementation(libs.androidx.core.ktx)
  implementation(libs.androidx.lifecycle.runtime.ktx)
  implementation(libs.androidx.activity.compose)

  // Arch Components
  implementation(libs.androidx.lifecycle.runtime.compose)
  implementation(libs.androidx.lifecycle.viewmodel.compose)

  // Compose
  implementation(libs.androidx.compose.ui)
  implementation(libs.androidx.compose.ui.tooling.preview)
  implementation(libs.androidx.compose.material3)
  implementation("androidx.compose.material:material-icons-core")
  implementation("androidx.compose.material:material-icons-extended")
  // Tooling
  debugImplementation(libs.androidx.compose.ui.tooling)
  // Instrumented tests
  androidTestImplementation(libs.androidx.compose.ui.test.junit4)
  debugImplementation(libs.androidx.compose.ui.test.manifest)

  // Local tests: jUnit, coroutines, Android runner
  testImplementation(libs.junit)
  testImplementation(libs.kotlinx.coroutines.test)

  // Instrumented tests: jUnit rules and runners
  androidTestImplementation(libs.androidx.test.core)
  androidTestImplementation(libs.androidx.test.ext.junit)
  androidTestImplementation(libs.androidx.test.runner)
  androidTestImplementation(libs.androidx.test.espresso.core)

  // Navigation
  implementation("androidx.navigation:navigation-compose:2.7.7")
  implementation(libs.socketio.client)

  // QR Code generation
  implementation("com.google.zxing:core:3.5.3")
  implementation(libs.androidx.security.crypto)
  implementation(libs.tink.android)
  implementation(libs.androidx.biometric)

  // NaCl box (XSalsa20-Poly1305) — outer transport layer for Double Ratchet v2
  implementation("com.goterl:lazysodium-android:5.1.0@aar")
  implementation("net.java.dev.jna:jna:5.14.0@aar")

  // WorkManager for background polling / push service keep-alive
  implementation("androidx.work:work-runtime-ktx:2.9.0")

  // Room Database
  implementation(libs.room.runtime)
  implementation(libs.room.ktx)
  add("kapt", libs.room.compiler)

  // DataStore Preferences
  implementation(libs.datastore.preferences)

  // Koin Dependency Injection
  implementation(libs.koin.android)
  implementation(libs.koin.compose)

  // Ktor HTTP Client
  implementation(libs.ktor.client.core)
  implementation(libs.ktor.client.okhttp)
}

tasks.withType<org.jetbrains.kotlin.gradle.internal.KaptWithoutKotlincTask>().configureEach {
    kaptProcessJvmArgs.add("-Dorg.sqlite.tmpdir=C:/Users/Aryan/AppData/Local/Temp")
}
