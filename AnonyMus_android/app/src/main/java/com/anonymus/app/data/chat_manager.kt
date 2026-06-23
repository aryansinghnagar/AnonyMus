package com.anonymus.app.data

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import io.socket.client.IO
import io.socket.client.Socket
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext
import kotlinx.coroutines.Dispatchers
import okhttp3.MediaType
import okhttp3.RequestBody
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.security.KeyPair
import java.security.cert.X509Certificate
import javax.crypto.spec.SecretKeySpec
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager
import javax.net.ssl.HostnameVerifier

data class ChatMessage(
    val sender: String,
    val text: String,
    val timestamp: Long = System.currentTimeMillis(),
    val isDecryptedSuccessfully: Boolean = true
)

enum class ConnectionStatus {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    ERROR
}

object ChatManager {
    private const val TAG = "ChatManager"
    private val mainHandler = Handler(Looper.getMainLooper())
    private lateinit var prefs: PreferencesHelper

    // Cryptographic Session Keys
    private var myKeyPair: KeyPair? = null
    var myPublicKeyExported: String? = null
        private set
    var myQueueId: String? = null
        private set

    // Peer Information (Zero-Knowledge only supports 1:1 right now per app instance)
    var theirQueueId: String? = null
        private set
    var theirPublicKeyExported: String? = null
        private set
    var writeKey: ByteArray? = null
        private set
    var readKey: ByteArray? = null
        private set
    var myRole: String? = null
        private set
    var theirRole: String? = null
        private set
    var sendSeq = 0
        private set
    var recvSeq = 0
        private set
    
    var safetyNumber: String? = null
        private set

    private var pendingInvite: Pair<String, String>? = null

    // Socket.IO
    private var socket: Socket? = null
    private var okHttpClient: OkHttpClient? = null

    // Compose state
    private val _connectionStatus = MutableStateFlow(ConnectionStatus.DISCONNECTED)
    val connectionStatus: StateFlow<ConnectionStatus> = _connectionStatus.asStateFlow()

    private val _isSessionActive = MutableStateFlow(false)
    val isSessionActive: StateFlow<Boolean> = _isSessionActive.asStateFlow()

    // Map of conversation messages: partnerName -> message list
    private val _conversations = MutableStateFlow<Map<String, List<ChatMessage>>>(emptyMap())
    val conversations: StateFlow<Map<String, List<ChatMessage>>> = _conversations.asStateFlow()
    
    // Disappearing Messages
    var disappearTimerSeconds = 0
    
    private var appContext: android.content.Context? = null

    fun initialize(context: android.content.Context) {
        appContext = context.applicationContext
        prefs = PreferencesHelper(context)
    }

    private fun getOkHttpClient(): OkHttpClient {
        val host = prefs.host
        val trustSelfSigned = prefs.trustSelfSigned

        if (okHttpClient == null) {
            val builder = OkHttpClient.Builder()
            if (trustSelfSigned) {
                try {
                    val trustManager = object : X509TrustManager {
                        override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
                        
                        override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                            if (chain.isNullOrEmpty()) {
                                throw java.security.cert.CertificateException("Server presented an empty certificate chain")
                            }
                            val cert = chain[0]
                            val spkiBytes = cert.publicKey.encoded
                            val digest = java.security.MessageDigest.getInstance("SHA-256")
                            val hash = digest.digest(spkiBytes)
                            val base64Hash = android.util.Base64.encodeToString(hash, android.util.Base64.NO_WRAP)
                            
                            val pinnedFingerprint = prefs.serverCertFingerprint
                            if (pinnedFingerprint == null) {
                                prefs.serverCertFingerprint = base64Hash
                                Log.i(TAG, "TOFU: Pinned new server public key SPKI hash: $base64Hash")
                            } else {
                                if (pinnedFingerprint != base64Hash) {
                                    throw java.security.cert.CertificateException(
                                        "Certificate public key fingerprint mismatch! Expected: $pinnedFingerprint, Got: $base64Hash. Possible Man-in-the-Middle attack!"
                                    )
                                }
                            }
                        }
                        
                        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
                    }

                    val sslContext = SSLContext.getInstance("TLS")
                    sslContext.init(null, arrayOf<TrustManager>(trustManager), java.security.SecureRandom())
                    builder.sslSocketFactory(sslContext.socketFactory, trustManager)
                    
                    builder.hostnameVerifier { hostname, _ ->
                        hostname == host || hostname == "localhost" || hostname == "127.0.0.1"
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to build TOFU SSLSocketFactory", e)
                }
            }
            
            builder.cookieJar(object : CookieJar {
                private val cookieStore = HashMap<String, MutableList<Cookie>>()
                
                init {
                    val savedCookie = prefs.sessionCookie
                    if (savedCookie != null) {
                        val cookie = Cookie.Builder()
                            .domain(host ?: "localhost")
                            .path("/")
                            .name("session")
                            .value(savedCookie)
                            .build()
                        cookieStore[host ?: "localhost"] = mutableListOf(cookie)
                    }
                }

                override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
                    cookieStore[url.host()] = cookies.toMutableList()
                    val sessionCookie = cookies.find { it.name() == "session" }
                    if (sessionCookie != null) {
                        prefs.sessionCookie = sessionCookie.value()
                    }
                }
                
                override fun loadForRequest(url: HttpUrl): List<Cookie> {
                    return cookieStore[url.host()] ?: ArrayList()
                }
            })
            
            okHttpClient = builder.build()
        }
        return okHttpClient!!
    }

    fun isLoggedIn(): Boolean {
        return prefs.sessionCookie != null
    }

    fun resetClient() {
        disconnect()
        okHttpClient = null
        myKeyPair = null
        myPublicKeyExported = null
        myQueueId = null
        theirQueueId = null
        theirPublicKeyExported = null
        
        // RAM Sterilization
        writeKey?.fill(0)
        readKey?.fill(0)
        writeKey = null
        readKey = null
        myRole = null
        theirRole = null
        sendSeq = 0
        recvSeq = 0
        
        safetyNumber = null
        _isSessionActive.value = false
        _conversations.value = emptyMap()
    }
    
    fun infinitySnap() {
        // Clear clipboard
        try {
            val clipboard = appContext?.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager
            clipboard?.setPrimaryClip(android.content.ClipData.newPlainText("", ""))
        } catch(e: Exception) {}
        
        resetClient()
        
        // Clear session config
        if (::prefs.isInitialized) {
            prefs.clearSession()
        }
        
        // Force clean restart instead of PID killing to prevent raw auto-login loop
        val context = appContext
        if (context != null) {
            val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)
            if (intent != null) {
                intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK)
                context.startActivity(intent)
            }
        }
    }
    
    fun obliviate() {
        if (writeKey != null && theirQueueId != null) {
            try {
                val payloadObj = JSONObject().apply {
                    put("type", "control")
                    put("action", "obliviate")
                }
                val encrypted = CryptoUtils.encryptMessage(writeKey!!, payloadObj.toString(), myRole!!, sendSeq)
                sendSeq++
                val payload = JSONObject().apply {
                    put("type", "message")
                    put("iv", encrypted.iv)
                    put("ciphertext", encrypted.ciphertext)
                }
                socket?.emit("push_queue", JSONObject().apply {
                    put("queue_id", theirQueueId)
                    put("payload", payload.toString())
                })
            } catch (e: Exception) {}
        }
        infinitySnap()
    }
    
    suspend fun register(username: String, pass: String): Pair<Boolean, String?> = withContext(Dispatchers.IO) {
        try {
            val client = getOkHttpClient()
            val payload = JSONObject().apply {
                put("username", username)
                put("password", pass)
                put("device_id", prefs.deviceId)
            }
            val request = Request.Builder()
                .url("https://${prefs.host}:${prefs.port}/register")
                .post(RequestBody.create(MediaType.parse("application/json"), payload.toString()))
                .build()
            val response = client.newCall(request).execute()
            val respStr = response.body()?.string() ?: ""
            val json = JSONObject(respStr)
            if (json.optBoolean("success")) {
                Pair(true, null)
            } else {
                Pair(false, json.optString("error", "Unknown error"))
            }
        } catch (e: Exception) {
            Pair(false, e.message)
        }
    }

    suspend fun login(username: String, pass: String): Pair<Boolean, String?> = withContext(Dispatchers.IO) {
        try {
            val client = getOkHttpClient()
            val payload = JSONObject().apply {
                put("username", username)
                put("password", pass)
                put("device_id", prefs.deviceId)
            }
            val request = Request.Builder()
                .url("https://${prefs.host}:${prefs.port}/login")
                .post(RequestBody.create(MediaType.parse("application/json"), payload.toString()))
                .build()
            val response = client.newCall(request).execute()
            val respStr = response.body()?.string() ?: ""
            val json = JSONObject(respStr)
            if (json.optBoolean("success")) {
                Pair(true, null)
            } else {
                Pair(false, json.optString("error", "Unknown error"))
            }
        } catch (e: Exception) {
            Pair(false, e.message)
        }
    }

    private fun startPsychoHistoricalStatic() {
        mainHandler.postDelayed(object : Runnable {
            override fun run() {
                if (writeKey != null && theirQueueId != null) {
                    try {
                        val payloadObj = JSONObject().apply {
                            put("type", "control")
                            put("action", "static")
                        }
                        val encrypted = CryptoUtils.encryptMessage(writeKey!!, payloadObj.toString(), myRole!!, sendSeq)
                        sendSeq++
                        val payload = JSONObject().apply {
                            put("type", "message")
                            put("iv", encrypted.iv)
                            put("ciphertext", encrypted.ciphertext)
                        }
                        socket?.emit("push_queue", JSONObject().apply {
                            put("queue_id", theirQueueId)
                            put("payload", payload.toString())
                        })
                    } catch (e: Exception) {}
                }
                // Random interval between 2-7 seconds
                mainHandler.postDelayed(this, (Math.random() * 5000 + 2000).toLong())
            }
        }, 2000)
    }

    fun connect() {
        val host = prefs.host
        val port = prefs.port
        if (host.isNullOrBlank()) {
            _connectionStatus.value = ConnectionStatus.ERROR
            return
        }

        if (socket != null) return

        _connectionStatus.value = ConnectionStatus.CONNECTING

        try {
            val client = getOkHttpClient()
            val options = IO.Options().apply {
                callFactory = client
                webSocketFactory = client
                secure = true
                reconnection = true
                transports = arrayOf("websocket")
            }

            socket = IO.socket("https://$host:$port", options)

            socket?.on(Socket.EVENT_CONNECT) {
                Log.d(TAG, "Socket connected.")
                _connectionStatus.value = ConnectionStatus.CONNECTED

                // Forward Secrecy: Generate new P-256 KeyPair on every connect
                try {
                    myKeyPair = CryptoUtils.generateKeyPair()
                    myPublicKeyExported = CryptoUtils.exportPublicKey(myKeyPair!!.public)
                    socket?.emit("create_queue")
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to initialize crypto", e)
                    _connectionStatus.value = ConnectionStatus.ERROR
                }
            }

            socket?.on("queue_created") { args ->
                val data = args.firstOrNull() as? JSONObject ?: return@on
                myQueueId = data.optString("queue_id")
                Log.d(TAG, "Queue created: $myQueueId")
                
                // Process pending invite if any
                pendingInvite?.let { (q, k) ->
                    pendingInvite = null
                    mainHandler.post {
                        acceptInvite(q, k)
                    }
                }
            }

            socket?.on("push_queue_error") { args ->
                val data = args.firstOrNull() as? JSONObject ?: return@on
                val error = data.optString("error")
                if (error == "recipient_offline") {
                    appendMessage("Peer", ChatMessage("System", "[Message delivery failed: Peer is offline]"))
                }
            }
            
            socket?.on("queue_payload") { args ->
                val data = args.firstOrNull() as? JSONObject ?: return@on
                val payloadStr = data.optString("payload")
                
                try {
                    val payload = JSONObject(payloadStr)
                    val type = payload.optString("type")
                    
                    if (type == "handshake") {
                        theirQueueId = payload.optString("reply_queue")
                        theirPublicKeyExported = payload.optString("public_key")
                        
                        val theirKey = CryptoUtils.importPublicKey(theirPublicKeyExported!!)
                        val sessionKeys = CryptoUtils.deriveSessionKeys(
                            myKeyPair!!.private,
                            theirKey,
                            myPublicKeyExported!!,
                            theirPublicKeyExported!!
                        )
                        writeKey = sessionKeys.writeKey
                        readKey = sessionKeys.readKey
                        
                        val isAlice = myPublicKeyExported!! < theirPublicKeyExported!!
                        myRole = if (isAlice) "A" else "B"
                        theirRole = if (isAlice) "B" else "A"
                        sendSeq = 0
                        recvSeq = 0
                        
                        safetyNumber = CryptoUtils.computeSafetyNumber(myPublicKeyExported!!, theirPublicKeyExported!!)
                        
                        Log.d(TAG, "Handshake received, secret derived. Safety Number: $safetyNumber")
                        _isSessionActive.value = true
                        appendMessage("Peer", ChatMessage("Peer", "[Connected Securely]"))
                        startPsychoHistoricalStatic()
                        
                    } else if (type == "message") {
                        if (readKey == null) return@on
                        val iv = payload.optString("iv")
                        val ciphertext = payload.optString("ciphertext")
                        
                        val decrypted = CryptoUtils.decryptMessage(readKey!!, iv, ciphertext, theirRole!!, recvSeq)
                        if (decrypted != null) {
                            recvSeq++
                            val msgObj = JSONObject(decrypted)
                            val msgType = msgObj.optString("type")
                            if (msgType == "control") {
                                val action = msgObj.optString("action")
                                if (action == "static") return@on
                                if (action == "obliviate") {
                                    mainHandler.post { infinitySnap() }
                                    return@on
                                }
                            } else if (msgType == "text") {
                                val content = msgObj.optString("content")
                                appendMessage("Peer", ChatMessage("Peer", content, isDecryptedSuccessfully = true))
                            }
                        } else {
                            appendMessage("Peer", ChatMessage("Peer", "[encrypted message — could not decrypt]", isDecryptedSuccessfully = false))
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to parse payload", e)
                }
            }

            socket?.on(Socket.EVENT_DISCONNECT) {
                _connectionStatus.value = ConnectionStatus.DISCONNECTED
            }
            socket?.on(Socket.EVENT_CONNECT_ERROR) { args ->
                val error = args.firstOrNull() as? Exception
                Log.e(TAG, "Socket connection error", error)
                if (error?.message?.contains("Connection rejected") == true ||
                    error?.cause?.message?.contains("Connection rejected") == true) {
                    mainHandler.post { infinitySnap() }
                } else {
                    _connectionStatus.value = ConnectionStatus.ERROR
                }
            }

            socket?.connect()
        } catch (e: Exception) {
            Log.e(TAG, "Socket connection init exception", e)
            _connectionStatus.value = ConnectionStatus.ERROR
        }
    }

    /**
     * Called when the user clicks an Invite Link (https://anonymus.local/#q=...&k=...)
     */
    fun acceptInvite(queueId: String, pubKeyBase64: String) {
        if (connectionStatus.value != ConnectionStatus.CONNECTED || myQueueId == null || myKeyPair == null) {
            Log.d(TAG, "Socket not ready. Deferring invite acceptance.")
            pendingInvite = Pair(queueId, pubKeyBase64)
            return
        }
        theirQueueId = queueId
        theirPublicKeyExported = pubKeyBase64
        
        try {
            val theirKey = CryptoUtils.importPublicKey(theirPublicKeyExported!!)
            val sessionKeys = CryptoUtils.deriveSessionKeys(
                myKeyPair!!.private,
                theirKey,
                myPublicKeyExported!!,
                theirPublicKeyExported!!
            )
            writeKey = sessionKeys.writeKey
            readKey = sessionKeys.readKey
            
            val isAlice = myPublicKeyExported!! < theirPublicKeyExported!!
            myRole = if (isAlice) "A" else "B"
            theirRole = if (isAlice) "B" else "A"
            sendSeq = 0
            recvSeq = 0
            
            safetyNumber = CryptoUtils.computeSafetyNumber(myPublicKeyExported!!, theirPublicKeyExported!!)
            
            // Send Handshake
            val payload = JSONObject().apply {
                put("type", "handshake")
                put("reply_queue", myQueueId)
                put("public_key", myPublicKeyExported)
            }
            
            socket?.emit("push_queue", JSONObject().apply {
                put("queue_id", theirQueueId)
                put("payload", payload.toString())
            })
            
            appendMessage("Peer", ChatMessage("Peer", "[Sent handshake to Peer]"))
            startPsychoHistoricalStatic()
            _isSessionActive.value = true
        } catch(e: Exception) {
            Log.e(TAG, "Failed to accept invite", e)
        }
    }

    fun sendPrivateMessage(text: String): Boolean {
        if (writeKey == null || theirQueueId == null) {
            Log.w(TAG, "Cannot send: no write key or target queue")
            return false
        }

        try {
            val payloadObj = JSONObject().apply {
                put("type", "text")
                put("content", text)
            }
            val encrypted = CryptoUtils.encryptMessage(writeKey!!, payloadObj.toString(), myRole!!, sendSeq)
            sendSeq++
            val payload = JSONObject().apply {
                put("type", "message")
                put("iv", encrypted.iv)
                put("ciphertext", encrypted.ciphertext)
            }
            
            socket?.emit("push_queue", JSONObject().apply {
                put("queue_id", theirQueueId)
                put("payload", payload.toString())
            })

            val chatMsg = ChatMessage(sender = "You", text = text)
            appendMessage("Peer", chatMsg)
            return true
        } catch (e: Exception) {
            Log.e(TAG, "Encryption/Transmission failure", e)
            return false
        }
    }

    private fun appendMessage(chatPartner: String, message: ChatMessage) {
        mainHandler.post {
            _conversations.update { currentConversations ->
                val list = currentConversations[chatPartner]?.toMutableList() ?: mutableListOf()
                list.add(message)
                currentConversations.toMutableMap().apply {
                    put(chatPartner, list)
                }
            }
            
            // Handle disappearing messages
            if (disappearTimerSeconds > 0) {
                mainHandler.postDelayed({
                    _conversations.update { current ->
                        val list = current[chatPartner]?.toMutableList() ?: return@update current
                        list.remove(message)
                        current.toMutableMap().apply { put(chatPartner, list) }
                    }
                }, disappearTimerSeconds * 1000L)
            }
        }
    }

    fun disconnect() {
        socket?.disconnect()
        socket?.off()
        socket = null
        _connectionStatus.value = ConnectionStatus.DISCONNECTED
    }
}
