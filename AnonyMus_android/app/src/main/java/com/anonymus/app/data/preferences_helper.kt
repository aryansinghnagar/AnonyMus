package com.anonymus.app.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys

class PreferencesHelper(context: Context) {
    private val masterKeyAlias = MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC)
    private val prefs: SharedPreferences = EncryptedSharedPreferences.create(
        com.anonymus.app.BuildConfig.PREFS_NAME,
        masterKeyAlias,
        context.applicationContext,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    companion object {
        private const val KEY_HOST = "server_host"
        private const val KEY_PORT = "server_port"
        private const val KEY_TRUST_SELF_SIGNED = "trust_self_signed"
    }

    var host: String?
        get() = prefs.getString(KEY_HOST, null)
        set(value) = prefs.edit().putString(KEY_HOST, value).apply()

    var port: Int
        get() = prefs.getInt(KEY_PORT, 5000)
        set(value) = prefs.edit().putInt(KEY_PORT, value).apply()

    var trustSelfSigned: Boolean
        get() = prefs.getBoolean(KEY_TRUST_SELF_SIGNED, false)
        set(value) = prefs.edit().putBoolean(KEY_TRUST_SELF_SIGNED, value).apply()

    fun isConfigured(): Boolean {
        return !host.isNullOrBlank()
    }
    
    val deviceId: String
        get() {
            var id = prefs.getString("device_id", null)
            if (id == null) {
                id = java.util.UUID.randomUUID().toString()
                prefs.edit().putString("device_id", id).apply()
            }
            return id
        }

    var sessionCookie: String?
        get() = prefs.getString("session_cookie", null)
        set(value) = prefs.edit().putString("session_cookie", value).apply()

    var username: String?
        get() = prefs.getString("username", null)
        set(value) = prefs.edit().putString("username", value).apply()

    var serverCertFingerprint: String?
        get() = prefs.getString("server_cert_fingerprint_${host ?: ""}", null)
        set(value) = prefs.edit().putString("server_cert_fingerprint_${host ?: ""}", value).apply()

    fun hasFingerprint(host: String): Boolean {
        return prefs.contains("server_cert_fingerprint_$host")
    }

    fun clearFingerprint(host: String) {
        prefs.edit().remove("server_cert_fingerprint_$host").apply()
    }

    fun clearSession() {
        prefs.edit()
            .remove("session_cookie")
            .remove("username")
            .apply()
    }

    fun clear() {
        prefs.edit().clear().apply()
    }
}
