package com.anonymus.app.service

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import com.anonymus.app.data.PreferencesHelper
import kotlinx.coroutines.*
import okhttp3.*
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.Base64
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

class PushService : Service() {

    private val TAG = "PushService"
    private val serviceJob = SupervisorJob()
    private val serviceScope = CoroutineScope(Dispatchers.IO + serviceJob)
    private lateinit var prefs: PreferencesHelper
    private var pollingJob: Job? = null

    companion object {
        const val ACTION_START = "com.anonymus.app.service.START"
        const val ACTION_STOP = "com.anonymus.app.service.STOP"
    }

    override fun onCreate() {
        super.onCreate()
        prefs = PreferencesHelper(this)
        NotificationHelper.createChannels(this)
        Log.d(TAG, "Service Created")
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action
        Log.d(TAG, "onStartCommand action: $action")

        if (action == ACTION_STOP) {
            stopForegroundService()
            return START_NOT_STICKY
        }

        // Start foreground immediately to comply with Android 8+ background limits
        val notification = NotificationHelper.buildServiceNotification(this)
        startForeground(NotificationHelper.SERVICE_NOTIFICATION_ID, notification)

        if (pollingJob == null || pollingJob?.isActive == false) {
            startPollingLoop()
        }

        return START_STICKY
    }

    private fun startPollingLoop() {
        pollingJob = serviceScope.launch {
            while (isActive) {
                if (!prefs.pushEnabled || !prefs.isConfigured() || prefs.sessionCookie == null) {
                    Log.d(TAG, "Push disabled or not configured/logged in. Stopping service.")
                    stopSelf()
                    break
                }

                try {
                    pollNotifications()
                } catch (e: Exception) {
                    Log.e(TAG, "Error in polling cycle: ${e.message}", e)
                }

                delay(30000) // Poll every 30 seconds
            }
        }
    }

    private suspend fun pollNotifications() = withContext(Dispatchers.IO) {
        val host = prefs.host ?: return@withContext
        val port = prefs.port
        val client = getOkHttpClient(host)

        // 1. Fetch contacts list
        val contactsUrl = "https://$host:$port/api/contacts"
        val contactsRequest = Request.Builder()
            .url(contactsUrl)
            .addHeader("Cookie", "session=${prefs.sessionCookie}")
            .get()
            .build()

        var contactsList: JSONArray? = null
        try {
            client.newCall(contactsRequest).execute().use { response ->
                if (response.isSuccessful) {
                    val bodyStr = response.body()?.string()
                    if (!bodyStr.isNullOrBlank()) {
                        contactsList = JSONArray(bodyStr)
                    }
                } else {
                    Log.w(TAG, "Failed to fetch contacts: ${response.code()}")
                }
            }
        } catch (e: IOException) {
            Log.e(TAG, "Network error fetching contacts: ${e.message}")
            return@withContext
        }

        val list = contactsList ?: return@withContext
        val tokensToPoll = ArrayList<String>()
        val tokenToContactMap = HashMap<String, ContactInfo>()

        // 2. Register tokens for any contact missing one
        for (i in 0 until list.length()) {
            val contact = list.getJSONObject(i)
            val onion = contact.optString("onion_address")
            val nickname = contact.optString("nickname")
            val displayName = contact.optString("display_name", "")
            val resolvedName = if (displayName.isNotBlank()) displayName else nickname
            var token = contact.optString("notify_queue_token", "")

            if (onion.isBlank()) continue

            if (token.isBlank()) {
                // Register a new token
                val registerUrl = "https://$host:$port/api/notifications/register"
                val regPayload = JSONObject().apply { put("onion_address", onion) }
                val regRequest = Request.Builder()
                    .url(registerUrl)
                    .addHeader("Cookie", "session=${prefs.sessionCookie}")
                    .post(RequestBody.create(MediaType.parse("application/json"), regPayload.toString()))
                    .build()

                try {
                    client.newCall(regRequest).execute().use { response ->
                        if (response.isSuccessful) {
                            val respBody = response.body()?.string()
                            if (!respBody.isNullOrBlank()) {
                                token = JSONObject(respBody).optString("token")
                                Log.i(TAG, "Successfully registered new notification token for contact $onion")
                            }
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error registering token for $onion: ${e.message}")
                }
            }

            if (!token.isBlank()) {
                tokensToPoll.add(token)
                tokenToContactMap[token] = ContactInfo(onion, resolvedName)
            }
        }

        if (tokensToPoll.isEmpty()) return@withContext

        // 3. Poll notification flags
        val tokensCsv = tokensToPoll.joinToString(",")
        val pollUrl = "https://$host:$port/api/notifications/poll?tokens=$tokensCsv"
        val pollRequest = Request.Builder()
            .url(pollUrl)
            .addHeader("Cookie", "session=${prefs.sessionCookie}")
            .get()
            .build()

        val tokensToClear = ArrayList<String>()

        try {
            client.newCall(pollRequest).execute().use { response ->
                if (response.isSuccessful) {
                    val respStr = response.body()?.string()
                    if (!respStr.isNullOrBlank()) {
                        val pollObj = JSONObject(respStr)
                        val hasNewMap = pollObj.optJSONObject("has_new")
                        if (hasNewMap != null) {
                            val keys = hasNewMap.keys()
                            while (keys.hasNext()) {
                                val token = keys.next()
                                val hasNew = hasNewMap.optBoolean(token, false)
                                if (hasNew) {
                                    val contactInfo = tokenToContactMap[token]
                                    if (contactInfo != null) {
                                        NotificationHelper.postMessageNotification(
                                            this@PushService,
                                            contactInfo.name,
                                            "Secure message arrived",
                                            prefs.pushPrivateMode
                                        )
                                    }
                                    tokensToClear.add(token)
                                }
                            }
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error polling notifications: ${e.message}")
        }

        // 4. Clear pending notification flags
        if (tokensToClear.isNotEmpty()) {
            val clearUrl = "https://$host:$port/api/notifications/clear"
            val clearPayload = JSONObject().apply {
                val array = JSONArray()
                tokensToClear.forEach { array.put(it) }
                put("tokens", array)
            }
            val clearRequest = Request.Builder()
                .url(clearUrl)
                .addHeader("Cookie", "session=${prefs.sessionCookie}")
                .post(RequestBody.create(MediaType.parse("application/json"), clearPayload.toString()))
                .build()

            try {
                client.newCall(clearRequest).execute().use { response ->
                    if (response.isSuccessful) {
                        Log.d(TAG, "Successfully cleared notification flags for ${tokensToClear.size} tokens")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error clearing tokens: ${e.message}")
            }
        }
    }

    private fun getOkHttpClient(host: String): OkHttpClient {
        val builder = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .writeTimeout(15, TimeUnit.SECONDS)

        if (prefs.trustSelfSigned) {
            try {
                val trustManager = object : X509TrustManager {
                    override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}

                    override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                        if (chain.isNullOrEmpty()) {
                            throw CertificateException("Server presented an empty certificate chain")
                        }
                        val cert = chain[0]
                        val spkiBytes = cert.publicKey.encoded
                        val digest = MessageDigest.getInstance("SHA-256")
                        val hash = digest.digest(spkiBytes)
                        val base64Hash = Base64.getEncoder().encodeToString(hash)

                        val pinnedFingerprint = prefs.serverCertFingerprint
                        if (pinnedFingerprint == null) {
                            prefs.serverCertFingerprint = base64Hash
                            Log.i(TAG, "TOFU: Pinned certificate SPKI: $base64Hash")
                        } else if (pinnedFingerprint != base64Hash) {
                            throw CertificateException("Certificate mismatch! Expected: $pinnedFingerprint, Got: $base64Hash")
                        }
                    }

                    override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
                }

                val sslContext = SSLContext.getInstance("TLS")
                sslContext.init(null, arrayOf<TrustManager>(trustManager), SecureRandom())
                builder.sslSocketFactory(sslContext.socketFactory, trustManager)
                builder.hostnameVerifier { hostname, _ ->
                    hostname == host || hostname == "localhost" || hostname == "127.0.0.1"
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to configure trust self-signed manager", e)
            }
        }

        return builder.build()
    }

    private fun stopForegroundService() {
        Log.d(TAG, "Stopping service")
        pollingJob?.cancel()
        stopForeground(true)
        stopSelf()
    }

    override fun onDestroy() {
        super.onDestroy()
        serviceJob.cancel()
        Log.d(TAG, "Service Destroyed")
    }

    private data class ContactInfo(val onion: String, val name: String)
}
