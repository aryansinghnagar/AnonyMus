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
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager
import com.anonymus.app.BuildConfig

data class ChatMessage(
    val sender: String,
    val text: String,
    val timestamp: Long = System.currentTimeMillis(),
    val isDecryptedSuccessfully: Boolean = true,
    val id: String = java.util.UUID.randomUUID().toString(),
    var remainingSeconds: Int = -1
)

enum class ConnectionStatus {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    ERROR
}

class ChatManager(
    private val context: Context,
    private val prefs: PreferencesHelper,
    private val cryptoProvider: CryptoProvider
) {
    private val TAG = "ChatManager"
    private val mainHandler = Handler(Looper.getMainLooper())

    // Cryptographic Session Keys (Ratchet Chain Keys)
    private var myKeyPair: KeyPair? = null
    var myPublicKeyExported: String? = null
        private set
    var myQueueId: String? = null
        private set

    // Peer Information
    var theirQueueId: String? = null
        private set
    var theirPublicKeyExported: String? = null
        private set
    var sendChainKey: ByteArray? = null
        private set
    var recvChainKey: ByteArray? = null
        private set
    var myRole: String? = null
        private set
    var theirRole: String? = null
        private set
    var sendSeq = 0
        private set
    var recvSeq = 0
        private set
    
    var sessionId: String? = null
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

    private val _conversations = MutableStateFlow<Map<String, List<ChatMessage>>>(emptyMap())
    val conversations: StateFlow<Map<String, List<ChatMessage>>> = _conversations.asStateFlow()
    
    // Disappearing Messages
    private val _disappearTimerSeconds = MutableStateFlow(0)
    val disappearTimerSeconds: StateFlow<Int> = _disappearTimerSeconds.asStateFlow()

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
                            val base64Hash = java.util.Base64.getEncoder().encodeToString(hash)
                            
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
        sendChainKey?.fill(0)
        recvChainKey?.fill(0)
        sendChainKey = null
        recvChainKey = null
        myRole = null
        theirRole = null
        sendSeq = 0
        recvSeq = 0
        
        sessionId = null
        safetyNumber = null
        _isSessionActive.value = false
        _conversations.value = emptyMap()
    }
    
    fun infinitySnap() {
        // Clear clipboard
        try {
            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager
            clipboard?.setPrimaryClip(android.content.ClipData.newPlainText("", ""))
        } catch(e: Exception) {}
        
        resetClient()
        
        prefs.clearSession()
        
        // Force clean restart
        val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)
        if (intent != null) {
            intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK)
            context.startActivity(intent)
        }
    }
    
    fun obliviate() {
        if (sendChainKey != null && theirQueueId != null) {
            try {
                val payloadObj = JSONObject().apply {
                    put("type", "control")
                    put("action", "obliviate")
                }
                val derived = cryptoProvider.deriveChainKeys(sendChainKey!!)
                val msgKey = derived.first
                sendChainKey = derived.second

                val encrypted = cryptoProvider.encryptMessage(msgKey, payloadObj.toString(), myRole!!, sendSeq, sessionId)
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

    private fun startAdaptiveKeepAlive() {
        mainHandler.post(object : Runnable {
            override fun run() {
                if (sendChainKey != null && theirQueueId != null) {
                    try {
                        val payloadObj = JSONObject().apply {
                            put("type", "control")
                            put("action", "heartbeat")
                        }
                        val derived = cryptoProvider.deriveChainKeys(sendChainKey!!)
                        val msgKey = derived.first
                        sendChainKey = derived.second
                        
                        val encrypted = cryptoProvider.encryptMessage(msgKey, payloadObj.toString(), myRole!!, sendSeq, sessionId)
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
                    } catch (e: Exception) {
                        Log.e(TAG, "Keep-alive error", e)
                    }
                }
                
                // Adaptive keep-alive interval: 15-45s random with power-saving scaling
                val powerManager = context.getSystemService(Context.POWER_SERVICE) as? android.os.PowerManager
                val isPowerSave = powerManager?.isPowerSaveMode == true
                val baseInterval = if (isPowerSave) 60000L else 15000L
                val jitter = (Math.random() * 30000).toLong()
                
                mainHandler.postDelayed(this, baseInterval + jitter)
            }
        })
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
                    myKeyPair = cryptoProvider.generateKeyPair()
                    myPublicKeyExported = cryptoProvider.exportPublicKey(myKeyPair!!.public)
                    socket?.emit("create_queue")
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to initialize crypto", e)
                    _connectionStatus.value = ConnectionStatus.ERROR
                }
            }

            socket?.on("queue_created") { args ->
                val data = args.firstOrNull() as? JSONObject ?: return@on
                val newQueueId = data.optString("queue_id")
                Log.d(TAG, "Queue created: $newQueueId")
                
                if (theirQueueId != null && sendChainKey != null) {
                    // Host queue rotated for invite link single-use (burn-after-reading)
                    myQueueId = newQueueId
                    try {
                        val payload = JSONObject().apply {
                            put("type", "queue_update")
                            put("new_queue", myQueueId)
                        }
                        socket?.emit("push_queue", JSONObject().apply {
                            put("queue_id", theirQueueId)
                            put("payload", payload.toString())
                        })
                        
                        socket?.emit("register_peer", JSONObject().apply {
                            put("my_queue", myQueueId)
                            put("peer_queue", theirQueueId)
                        })
                    } catch (e: Exception) {}
                    return@on
                }
                
                myQueueId = newQueueId
                
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
                        
                        val theirKey = cryptoProvider.importPublicKey(theirPublicKeyExported!!)
                        val sessionKeys = cryptoProvider.deriveSessionKeys(
                            myKeyPair!!.private,
                            theirKey,
                            myPublicKeyExported!!,
                            theirPublicKeyExported!!
                        )
                        sendChainKey = sessionKeys.writeKey
                        recvChainKey = sessionKeys.readKey
                        
                        val isAlice = myPublicKeyExported!! < theirPublicKeyExported!!
                        myRole = if (isAlice) "A" else "B"
                        theirRole = if (isAlice) "B" else "A"
                        sendSeq = 0
                        recvSeq = 0
                        
                        sessionId = cryptoProvider.computeSafetyNumber(myPublicKeyExported!!, theirPublicKeyExported!!)
                        safetyNumber = sessionId
                        
                        Log.d(TAG, "Handshake received, secret derived. Safety Number: $safetyNumber")
                        
                        // Register peer queue ownership for backend verification
                        socket?.emit("register_peer", JSONObject().apply {
                            put("my_queue", myQueueId)
                            put("peer_queue", theirQueueId)
                        })

                        // Rotate host queue to burn invite link
                        socket?.emit("create_queue")

                        _isSessionActive.value = true
                        appendMessage("Peer", ChatMessage("Peer", "[Connected Securely]"))
                        startAdaptiveKeepAlive()
                        
                    } else if (type == "queue_update") {
                        theirQueueId = payload.optString("new_queue")
                        appendMessage("Peer", ChatMessage("System", "[Peer updated secure channel]"))
                        
                    } else if (type == "message") {
                        if (recvChainKey == null) return@on
                        val iv = payload.optString("iv")
                        val ciphertext = payload.optString("ciphertext")
                        
                        // Derive message decryption key from chain
                        val derived = cryptoProvider.deriveChainKeys(recvChainKey!!)
                        val msgKey = derived.first
                        
                        val decrypted = cryptoProvider.decryptMessage(msgKey, iv, ciphertext, theirRole!!, recvSeq, sessionId)
                        if (decrypted != null) {
                            recvChainKey = derived.second
                            recvSeq++
                            
                            val msgObj = JSONObject(decrypted)
                            val msgType = msgObj.optString("type")
                            if (msgType == "control") {
                                val action = msgObj.optString("action")
                                if (action == "static" || action == "heartbeat") return@on
                                if (action == "obliviate") {
                                    mainHandler.post { infinitySnap() }
                                    return@on
                                }
                                if (action == "timer_set") {
                                    val duration = msgObj.optInt("duration_seconds")
                                    _disappearTimerSeconds.value = duration
                                    appendMessage("Peer", ChatMessage("System", "[Peer set disappearing messages to ${if (duration > 0) "$duration seconds" else "Off"}]"))
                                    
                                    // Reply with timer_ack
                                    if (sendChainKey != null && theirQueueId != null) {
                                        try {
                                            val payloadObj = JSONObject().apply {
                                                put("type", "control")
                                                put("action", "timer_ack")
                                                put("duration_seconds", duration)
                                                put("mode", "session")
                                            }
                                            val derivedSend = cryptoProvider.deriveChainKeys(sendChainKey!!)
                                            val sendMsgKey = derivedSend.first
                                            sendChainKey = derivedSend.second
                                            
                                            val encrypted = cryptoProvider.encryptMessage(sendMsgKey, payloadObj.toString(), myRole!!, sendSeq, sessionId)
                                            sendSeq++
                                            
                                            val payloadAck = JSONObject().apply {
                                                put("type", "message")
                                                put("iv", encrypted.iv)
                                                put("ciphertext", encrypted.ciphertext)
                                            }
                                            socket?.emit("push_queue", JSONObject().apply {
                                                put("queue_id", theirQueueId)
                                                put("payload", payloadAck.toString())
                                            })
                                        } catch (e: Exception) {}
                                    }
                                    return@on
                                }
                                if (action == "timer_ack") {
                                    val duration = msgObj.optInt("duration_seconds")
                                    _disappearTimerSeconds.value = duration
                                    appendMessage("Peer", ChatMessage("System", "[Peer confirmed disappearing messages timer: ${if (duration > 0) "$duration seconds" else "Off"}]"))
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

    fun acceptInvite(queueId: String, pubKeyBase64: String) {
        if (connectionStatus.value != ConnectionStatus.CONNECTED || myQueueId == null || myKeyPair == null) {
            Log.d(TAG, "Socket not ready. Deferring invite acceptance.")
            pendingInvite = Pair(queueId, pubKeyBase64)
            return
        }
        theirQueueId = queueId
        theirPublicKeyExported = pubKeyBase64
        
        try {
            val theirKey = cryptoProvider.importPublicKey(theirPublicKeyExported!!)
            val sessionKeys = cryptoProvider.deriveSessionKeys(
                myKeyPair!!.private,
                theirKey,
                myPublicKeyExported!!,
                theirPublicKeyExported!!
            )
            sendChainKey = sessionKeys.writeKey
            recvChainKey = sessionKeys.readKey
            
            val isAlice = myPublicKeyExported!! < theirPublicKeyExported!!
            myRole = if (isAlice) "A" else "B"
            theirRole = if (isAlice) "B" else "A"
            sendSeq = 0
            recvSeq = 0
            
            sessionId = cryptoProvider.computeSafetyNumber(myPublicKeyExported!!, theirPublicKeyExported!!)
            safetyNumber = sessionId
            
            // Send Handshake (unencrypted)
            val payload = JSONObject().apply {
                put("type", "handshake")
                put("reply_queue", myQueueId)
                put("public_key", myPublicKeyExported)
            }
            
            socket?.emit("push_queue", JSONObject().apply {
                put("queue_id", theirQueueId)
                put("payload", payload.toString())
            })
            
            // Register peer queue ownership for backend verification
            socket?.emit("register_peer", JSONObject().apply {
                put("my_queue", myQueueId)
                put("peer_queue", theirQueueId)
            })
            
            appendMessage("Peer", ChatMessage("Peer", "[Sent handshake to Peer]"))
            startAdaptiveKeepAlive()
            _isSessionActive.value = true
        } catch(e: Exception) {
            Log.e(TAG, "Failed to accept invite", e)
        }
    }

    fun sendPrivateMessage(text: String): Boolean {
        if (sendChainKey == null || theirQueueId == null) {
            Log.w(TAG, "Cannot send: no write key or target queue")
            return false
        }

        try {
            val payloadObj = JSONObject().apply {
                put("type", "text")
                put("content", text)
            }
            val derived = cryptoProvider.deriveChainKeys(sendChainKey!!)
            val msgKey = derived.first
            sendChainKey = derived.second

            val encrypted = cryptoProvider.encryptMessage(msgKey, payloadObj.toString(), myRole!!, sendSeq, sessionId)
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

    fun setDisappearingTimer(seconds: Int) {
        _disappearTimerSeconds.value = seconds
        if (sendChainKey != null && theirQueueId != null) {
            try {
                val payloadObj = JSONObject().apply {
                    put("type", "control")
                    put("action", "timer_set")
                    put("duration_seconds", seconds)
                    put("mode", "session")
                }
                val derived = cryptoProvider.deriveChainKeys(sendChainKey!!)
                val msgKey = derived.first
                sendChainKey = derived.second
                
                val encrypted = cryptoProvider.encryptMessage(msgKey, payloadObj.toString(), myRole!!, sendSeq, sessionId)
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
            } catch (e: Exception) {
                Log.e(TAG, "Failed to negotiate timer", e)
            }
        }
    }

    private fun appendMessage(chatPartner: String, message: ChatMessage) {
        val msgWithTimer = if (_disappearTimerSeconds.value > 0 && message.sender != "System") {
            message.copy(remainingSeconds = _disappearTimerSeconds.value)
        } else {
            message
        }

        mainHandler.post {
            _conversations.update { currentConversations ->
                val list = currentConversations[chatPartner]?.toMutableList() ?: mutableListOf()
                list.add(msgWithTimer)
                currentConversations.toMutableMap().apply {
                    put(chatPartner, list)
                }
            }
            
            if (msgWithTimer.remainingSeconds > 0) {
                startCountdown(chatPartner, msgWithTimer.id)
            }
        }
    }

    private fun startCountdown(chatPartner: String, messageId: String) {
        val runnable = object : Runnable {
            override fun run() {
                var deleteMessage = false
                _conversations.update { current ->
                    val list = current[chatPartner]?.map { msg ->
                        if (msg.id == messageId) {
                            val nextSec = msg.remainingSeconds - 1
                            if (nextSec <= 0) {
                                deleteMessage = true
                            }
                            msg.copy(remainingSeconds = nextSec)
                        } else {
                            msg
                        }
                    } ?: return@update current
                    
                    val filteredList = if (deleteMessage) {
                        list.filter { it.id != messageId }
                    } else {
                        list
                    }
                    
                    current.toMutableMap().apply { put(chatPartner, filteredList) }
                }
                
                if (!deleteMessage) {
                    mainHandler.postDelayed(this, 1000)
                }
            }
        }
        mainHandler.postDelayed(runnable, 1000)
    }

    fun disconnect() {
        socket?.disconnect()
        socket?.off()
        socket = null
        _connectionStatus.value = ConnectionStatus.DISCONNECTED
    }
}
