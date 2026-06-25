# ProGuard Rules for AnonyMus

# Kotlin Serialization Keep Rules
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod

# Keep serializable classes and their companion objects
-keepclassmembers class * {
    @kotlinx.serialization.Serializable *;
}
-keep class * {
    @kotlinx.serialization.Serializable *;
}
-keepclassmembers class * {
    *** Companion;
}

# Socket.IO client keep rules
-keep class io.socket.client.** { *; }
-keep class io.socket.engineio.client.** { *; }
-keep class io.socket.parser.** { *; }
-keep class io.socket.thread.** { *; }
-dontwarn io.socket.client.**
-dontwarn io.socket.engineio.client.**

# OkHttp3 keep rules (used by Socket.IO)
-keepattributes Signature, *Annotation*, InnerClasses
-keepclassmembers class * {
    javax.net.ssl.SSLSocketFactory getSocketFactory();
    javax.net.ssl.X509TrustManager getTrustManager();
}
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn javax.annotation.**
-dontwarn org.conscrypt.**

# Android Jetpack Security
-keep class androidx.security.crypto.** { *; }

# Strip debug and verbose logs in release build
-assumenosideeffects class android.util.Log {
    public static boolean isLoggable(java.lang.String, int);
    public static int v(...);
    public static int d(...);
}
