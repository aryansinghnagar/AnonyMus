package com.anonymus.app.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first

val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "anonymus_prefs")

class PreferencesHelper(private val context: Context) {
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val cache = java.util.concurrent.ConcurrentHashMap<String, Any>()

    init {
        runBlocking {
            try {
                val prefs = context.dataStore.data.first()
                prefs.asMap().forEach { (key, value) ->
                    cache[key.name] = value
                }
            } catch (e: Exception) {
                android.util.Log.e("PreferencesHelper", "Failed to load preferences on startup", e)
            }
        }
    }

    private fun <T : Any> get(key: Preferences.Key<T>, default: T): T {
        @Suppress("UNCHECKED_CAST")
        return cache[key.name] as? T ?: default
    }

    private fun <T : Any> getNullable(key: Preferences.Key<T>): T? {
        @Suppress("UNCHECKED_CAST")
        return cache[key.name] as? T
    }

    private fun <T : Any> set(key: Preferences.Key<T>, value: T?) {
        if (value == null) {
            cache.remove(key.name)
            scope.launch {
                context.dataStore.edit { preferences ->
                    preferences.remove(key)
                }
            }
        } else {
            cache[key.name] = value
            scope.launch {
                context.dataStore.edit { preferences ->
                    preferences[key] = value
                }
            }
        }
    }

    companion object {
        private val KEY_HOST = stringPreferencesKey("server_host")
        private val KEY_PORT = intPreferencesKey("server_port")
        private val KEY_TRUST_SELF_SIGNED = booleanPreferencesKey("trust_self_signed")
        private val KEY_BIOMETRIC_LOCK = booleanPreferencesKey("biometric_lock")
        private val KEY_PUSH_ENABLED = booleanPreferencesKey("push_enabled")
        private val KEY_PUSH_PRIVATE_MODE = booleanPreferencesKey("push_private_mode")
        private val KEY_PUSH_TOKEN = stringPreferencesKey("push_token")
        private val KEY_SESSION_COOKIE = stringPreferencesKey("session_cookie")
        private val KEY_USERNAME = stringPreferencesKey("username")
    }

    var host: String?
        get() = getNullable(KEY_HOST)
        set(value) = set(KEY_HOST, value)

    var port: Int
        get() = get(KEY_PORT, 5000)
        set(value) = set(KEY_PORT, value)

    var trustSelfSigned: Boolean
        get() = get(KEY_TRUST_SELF_SIGNED, false)
        set(value) = set(KEY_TRUST_SELF_SIGNED, value)

    var biometricLock: Boolean
        get() = get(KEY_BIOMETRIC_LOCK, false)
        set(value) = set(KEY_BIOMETRIC_LOCK, value)

    var pushEnabled: Boolean
        get() = get(KEY_PUSH_ENABLED, false)
        set(value) = set(KEY_PUSH_ENABLED, value)

    var pushPrivateMode: Boolean
        get() = get(KEY_PUSH_PRIVATE_MODE, false)
        set(value) = set(KEY_PUSH_PRIVATE_MODE, value)

    var pushToken: String?
        get() = getNullable(KEY_PUSH_TOKEN)
        set(value) = set(KEY_PUSH_TOKEN, value)

    fun isConfigured(): Boolean {
        return !host.isNullOrBlank()
    }

    var sessionCookie: String?
        get() = getNullable(KEY_SESSION_COOKIE)
        set(value) = set(KEY_SESSION_COOKIE, value)

    var username: String?
        get() = getNullable(KEY_USERNAME)
        set(value) = set(KEY_USERNAME, value)

    var serverCertFingerprint: String?
        get() = host?.let { getNullable(stringPreferencesKey("server_cert_fingerprint_$it")) }
        set(value) {
            host?.let { set(stringPreferencesKey("server_cert_fingerprint_$it"), value) }
        }

    fun hasFingerprint(host: String): Boolean {
        return cache.containsKey("server_cert_fingerprint_$host")
    }

    fun clearFingerprint(host: String) {
        set(stringPreferencesKey("server_cert_fingerprint_$host"), null)
    }

    fun clearSession() {
        sessionCookie = null
        username = null
    }

    fun clear() {
        cache.clear()
        scope.launch {
            context.dataStore.edit { preferences ->
                preferences.clear()
            }
        }
    }
}
