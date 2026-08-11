plugins {
    kotlin("multiplatform") version "2.0.0"
    id("com.android.library") version "8.5.0"
}

kotlin {
    androidTarget()
    iosX64()
    iosArm64()
    iosSimulatorArm64()

    sourceSets {
        val commonMain by getting {
            dependencies {
                implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.1")
            }
        }
        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
            }
        }
    }
}

android {
    namespace = "com.anonymus.core.kmp"
    compileSdk = 34
    defaultConfig {
        minSdk = 24
    }
}
