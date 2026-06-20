package com.example.privacychat.data

import android.content.Context
import android.content.SharedPreferences

class PreferencesHelper(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("privacy_chat_prefs", Context.MODE_PRIVATE)

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

    fun clear() {
        prefs.edit().clear().apply()
    }
}
