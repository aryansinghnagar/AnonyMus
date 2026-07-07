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
import android.net.Uri
import android.content.ContentValues
import android.provider.MediaStore
import android.os.Environment
import android.os.Build
import android.webkit.MimeTypeMap
import android.widget.Toast
import android.util.Base64
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import java.io.File
import java.io.FileOutputStream
import java.io.FileInputStream
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import javax.crypto.Cipher
import java.nio.charset.StandardCharsets

data class ChatMessage(
    val sender: String,
    var text: String,
    val timestamp: Long = System.currentTimeMillis(),
    val isDecryptedSuccessfully: Boolean = true,
    val id: String = java.util.UUID.randomUUID().toString(),
    var remainingSeconds: Int = -1,
    var reactions: List<String> = emptyList(),
    var isFile: Boolean = false,
    var fileName: String = "",
    var fileSize: Long = 0L,
    var fileMasterKey: String = "",
    var fileChunks: List<String> = emptyList(),
    var fileSenderOnion: String? = null,
    var fileProgress: Float = -1f, // -1f = idle, -2f = completed, -3f = error, otherwise 0..1 progress
    var deliveryState: String = "sent",
    var isEdited: Boolean = false,
    var editHistory: List<String> = emptyList()
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
    private var cachedOkHttpClient: OkHttpClient? = null
    private val chainKeyLock = Any()

    // Compose state
    private val _connectionStatus = MutableStateFlow(ConnectionStatus.DISCONNECTED)
    val connectionStatus: StateFlow<ConnectionStatus> = _connectionStatus.asStateFlow()

    private val _isSessionActive = MutableStateFlow(false)
    val isSessionActive: StateFlow<Boolean> = _isSessionActive.asStateFlow()

    private val _conversations = MutableStateFlow<Map<String, List<ChatMessage>>>(emptyMap())
    val conversations: StateFlow<Map<String, List<ChatMessage>>> = _conversations.asStateFlow()

    private val _typingPreview = MutableStateFlow<String?>(null)
    val typingPreview: StateFlow<String?> = _typingPreview.asStateFlow()
    
    // Disappearing Messages
    private val _disappearTimerSeconds = MutableStateFlow(0)
    val disappearTimerSeconds: StateFlow<Int> = _disappearTimerSeconds.asStateFlow()

    private fun getOkHttpClient(): OkHttpClient {
        val host = prefs.host
        val trustSelfSigned = prefs.trustSelfSigned

        cachedOkHttpClient?.let { return it }

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
        
        val client = builder.build()
        cachedOkHttpClient = client
        return client
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
        synchronized(chainKeyLock) {
            sendChainKey?.fill(0)
            recvChainKey?.fill(0)
            sendChainKey = null
            recvChainKey = null
        }
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
        synchronized(chainKeyLock) {
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
                synchronized(chainKeyLock) {
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

        if (socket != null && socket?.connected() == true) return
        socket?.disconnect()
        socket?.off()
        socket = null

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
                    appendMessage(theirQueueId ?: "Peer", ChatMessage("System", "[Message delivery failed: Peer is offline]"))
                }
            }
            
            socket?.on("queue_payload") { args ->
                val data = args.firstOrNull() as? JSONObject ?: return@on
                val payloadStr = data.optString("payload")
                
                try {
                    val initialPayload = JSONObject(payloadStr)
                    
                    fun processPayload(payload: JSONObject) {
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
                            synchronized(chainKeyLock) {
                                sendChainKey = sessionKeys.writeKey
                                recvChainKey = sessionKeys.readKey
                            }
                            
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
                            appendMessage(theirQueueId ?: "Peer", ChatMessage("Peer", "[Connected Securely]"))
                            startAdaptiveKeepAlive()
                            
                        } else if (type == "queue_update") {
                            theirQueueId = payload.optString("new_queue")
                            appendMessage(theirQueueId ?: "Peer", ChatMessage("System", "[Peer updated secure channel]"))
                            
                        } else if (type == "message") {
                            val hasRecvKey = synchronized(chainKeyLock) { recvChainKey != null }
                            if (!hasRecvKey) return
                            val iv = payload.optString("iv")
                            val ciphertext = payload.optString("ciphertext")
                            
                            // Derive message decryption key from chain
                            var decrypted: String? = null
                            synchronized(chainKeyLock) {
                                val derived = cryptoProvider.deriveChainKeys(recvChainKey!!)
                                val msgKey = derived.first
                                
                                decrypted = cryptoProvider.decryptMessage(msgKey, iv, ciphertext, theirRole!!, recvSeq, sessionId)
                                if (decrypted != null) {
                                    recvChainKey = derived.second
                                    recvSeq++
                                }
                            }
                            
                            if (decrypted != null) {
                                val msgObj = JSONObject(decrypted)
                                val msgType = msgObj.optString("type")
                                if (msgType == "control") {
                                    val action = msgObj.optString("action")
                                    if (action == "static" || action == "heartbeat") return
                                    if (action == "obliviate") {
                                        mainHandler.post { infinitySnap() }
                                        return
                                    }
                                    if (action == "timer_set") {
                                        val duration = msgObj.optInt("duration_seconds")
                                        _disappearTimerSeconds.value = duration
                                        appendMessage(theirQueueId ?: "Peer", ChatMessage("System", "[Peer set disappearing messages to ${if (duration > 0) "$duration seconds" else "Off"}]"))
                                        
                                        // Reply with timer_ack
                                        synchronized(chainKeyLock) {
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
                                        }
                                        return
                                    }
                                    if (action == "timer_ack") {
                                        val duration = msgObj.optInt("duration_seconds")
                                        _disappearTimerSeconds.value = duration
                                        appendMessage(theirQueueId ?: "Peer", ChatMessage("System", "[Peer confirmed disappearing messages timer: ${if (duration > 0) "$duration seconds" else "Off"}]"))
                                        return
                                    }
                                } else if (msgType == "text") {
                                    val content = msgObj.optString("content")
                                    val ts = msgObj.optLong("timestamp", System.currentTimeMillis())
                                    appendMessage(theirQueueId ?: "Peer", ChatMessage("Peer", content, isDecryptedSuccessfully = true, timestamp = ts, deliveryState = "sent"))
                                    sendReceipt(ts, "read")
                                } else if (msgType == "x.grp.invite") {
                                    val groupName = msgObj.optString("name")
                                    appendMessage(theirQueueId ?: "Peer", ChatMessage("System", "[Group Invitation]: You were invited to join group '$groupName' (Join via Web Client)"))
                                } else if (msgType == "x.grp.message") {
                                    val content = msgObj.optString("content")
                                    val senderName = msgObj.optString("sender_nickname")
                                    appendMessage(theirQueueId ?: "Peer", ChatMessage("System", "[Group Message from $senderName]: $content"))
                                } else if (msgType == "x.msg.edit") {
                                    val targetTimestamp = msgObj.optLong("target_timestamp")
                                    val content = msgObj.optString("content")
                                    _conversations.update { current ->
                                        val partner = theirQueueId ?: "Peer"
                                        val list = current[partner]?.map { msg ->
                                            if (msg.timestamp == targetTimestamp) {
                                                val oldText = msg.text
                                                msg.text = content
                                                msg.isEdited = true
                                                msg.editHistory = msg.editHistory + oldText
                                                msg
                                            } else {
                                                msg
                                            }
                                        } ?: return@update current
                                        current.toMutableMap().apply {
                                            put(partner, list)
                                        }
                                    }
                                } else if (msgType == "x.msg.delete") {
                                    val targetTimestamp = msgObj.optLong("target_timestamp")
                                    _conversations.update { current ->
                                        val partner = theirQueueId ?: "Peer"
                                        val list = current[partner]?.filter { it.timestamp != targetTimestamp } ?: return@update current
                                        current.toMutableMap().apply {
                                            put(partner, list)
                                        }
                                    }
                                } else if (msgType == "x.msg.receipt") {
                                    val targetTimestamp = msgObj.optLong("target_timestamp")
                                    val state = msgObj.optString("state")
                                    _conversations.update { current ->
                                        val partner = theirQueueId ?: "Peer"
                                        val list = current[partner]?.map { msg ->
                                            if (msg.timestamp == targetTimestamp && msg.sender == "You") {
                                                msg.deliveryState = state
                                                msg
                                            } else {
                                                msg
                                            }
                                        } ?: return@update current
                                        current.toMutableMap().apply {
                                            put(partner, list)
                                        }
                                    }
                                } else if (msgType == "x.msg.live") {
                                    val content = msgObj.optString("content")
                                    _typingPreview.value = if (content.isEmpty()) null else content
                                } else if (msgType == "x.msg.reaction") {
                                    val targetTimestamp = msgObj.optLong("target_msg_id")
                                    val emoji = msgObj.optString("emoji")
                                    addLocalReaction(targetTimestamp, emoji, "Peer")
                                } else if (msgType == "x.file.descr") {
                                    val fileName = msgObj.optString("file_name")
                                    val fileSize = msgObj.optLong("file_size")
                                    val masterKey = msgObj.optString("master_key")
                                    val senderOnion = msgObj.optString("sender_onion")
                                    val chunksArr = msgObj.optJSONArray("chunks")
                                    val chunks = mutableListOf<String>()
                                    if (chunksArr != null) {
                                        for (i in 0 until chunksArr.length()) {
                                            chunks.add(chunksArr.getString(i))
                                        }
                                    }
                                    val timestamp = msgObj.optLong("timestamp", System.currentTimeMillis())
                                    val msgText = if (fileName.endsWith(".webm") && fileName.startsWith("voice_note")) {
                                        "[Voice Note]"
                                    } else if (fileName.endsWith(".webm") && fileName.startsWith("video_note")) {
                                        "[Video Note]"
                                    } else {
                                        "Sent file: $fileName"
                                    }
                                    appendMessage(
                                        theirQueueId ?: "Peer",
                                        ChatMessage(
                                            sender = "Peer",
                                            text = msgText,
                                            timestamp = timestamp,
                                            isDecryptedSuccessfully = true,
                                            isFile = true,
                                            fileName = fileName,
                                            fileSize = fileSize,
                                            fileMasterKey = masterKey,
                                            fileChunks = chunks,
                                            fileSenderOnion = if (senderOnion.isEmpty()) null else senderOnion
                                        )
                                    )
                                }
                            } else {
                                appendMessage(theirQueueId ?: "Peer", ChatMessage("Peer", "[encrypted message — could not decrypt]", isDecryptedSuccessfully = false))
                            }
                        } else if (type == "batch") {
                            val eventsArr = payload.optJSONArray("events")
                            if (eventsArr != null) {
                                for (i in 0 until eventsArr.length()) {
                                    val subPayload = eventsArr.getJSONObject(i)
                                    processPayload(subPayload)
                                }
                            }
                        }
                    }

                    processPayload(initialPayload)
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
            synchronized(chainKeyLock) {
                sendChainKey = sessionKeys.writeKey
                recvChainKey = sessionKeys.readKey
            }
            
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
            
            appendMessage(theirQueueId ?: "Peer", ChatMessage("Peer", "[Sent handshake to Peer]"))
            startAdaptiveKeepAlive()
            _isSessionActive.value = true
        } catch(e: Exception) {
            Log.e(TAG, "Failed to accept invite", e)
        }
    }

    fun sendPrivateMessage(text: String): Boolean {
        synchronized(chainKeyLock) {
            if (sendChainKey == null || theirQueueId == null) {
                Log.w(TAG, "Cannot send: no write key or target queue")
                return false
            }

            try {
                val payloadObj = JSONObject().apply {
                    put("type", "text")
                    put("content", text)
                    put("timestamp", System.currentTimeMillis())
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
                appendMessage(theirQueueId ?: "Peer", chatMsg)
                return true
            } catch (e: Exception) {
                Log.e(TAG, "Encryption/Transmission failure", e)
                return false
            }
        }
    }

    fun setDisappearingTimer(seconds: Int) {
        _disappearTimerSeconds.value = seconds
        synchronized(chainKeyLock) {
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

    fun sendEphemeralPayload(payloadObj: JSONObject): Boolean {
        synchronized(chainKeyLock) {
            if (sendChainKey == null || theirQueueId == null) {
                return false
            }
            try {
                val derived = cryptoProvider.deriveChainKeys(sendChainKey!!)
                val msgKey = derived.first
                sendChainKey = derived.second

                val encrypted = cryptoProvider.encryptMessage(msgKey, payloadObj.toString(), myRole!!, sendSeq, sessionId)
                sendSeq++
                
                val payload = JSONObject().apply {
                    put("type", "message")
                    put("iv", encrypted.iv)
                    put("ciphertext", encrypted.ciphertext)
                    put("ephemeral", true)
                }
                
                socket?.emit("push_queue", JSONObject().apply {
                    put("queue_id", theirQueueId)
                    put("payload", payload.toString())
                })
                return true
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send ephemeral payload", e)
                return false
            }
        }
    }

    fun sendTypingDraft(text: String) {
        val payload = JSONObject().apply {
            put("type", "x.msg.live")
            put("content", text)
        }
        sendEphemeralPayload(payload)
    }

    fun sendReaction(targetTimestamp: Long, emoji: String) {
        val payload = JSONObject().apply {
            put("type", "x.msg.reaction")
            put("target_msg_id", targetTimestamp)
            put("emoji", emoji)
        }
        synchronized(chainKeyLock) {
            if (sendChainKey == null || theirQueueId == null) return
            try {
                val derived = cryptoProvider.deriveChainKeys(sendChainKey!!)
                val msgKey = derived.first
                sendChainKey = derived.second

                val encrypted = cryptoProvider.encryptMessage(msgKey, payload.toString(), myRole!!, sendSeq, sessionId)
                sendSeq++
                
                val outerPayload = JSONObject().apply {
                    put("type", "message")
                    put("iv", encrypted.iv)
                    put("ciphertext", encrypted.ciphertext)
                }
                
                socket?.emit("push_queue", JSONObject().apply {
                    put("queue_id", theirQueueId)
                    put("payload", outerPayload.toString())
                })
                addLocalReaction(targetTimestamp, emoji, "You")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send reaction", e)
            }
        }
    }

    private fun sendEncryptedPayload(payload: JSONObject): Boolean {
        synchronized(chainKeyLock) {
            if (sendChainKey == null || theirQueueId == null) return false
            try {
                val derived = cryptoProvider.deriveChainKeys(sendChainKey!!)
                val msgKey = derived.first
                sendChainKey = derived.second

                val encrypted = cryptoProvider.encryptMessage(msgKey, payload.toString(), myRole!!, sendSeq, sessionId)
                sendSeq++
                
                val outerPayload = JSONObject().apply {
                    put("type", "message")
                    put("iv", encrypted.iv)
                    put("ciphertext", encrypted.ciphertext)
                }
                
                socket?.emit("push_queue", JSONObject().apply {
                    put("queue_id", theirQueueId)
                    put("payload", outerPayload.toString())
                })
                return true
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send encrypted payload", e)
                return false
            }
        }
    }

    fun sendEditMessage(targetTimestamp: Long, newText: String) {
        val payload = JSONObject().apply {
            put("type", "x.msg.edit")
            put("target_timestamp", targetTimestamp)
            put("content", newText)
        }
        if (sendEncryptedPayload(payload)) {
            _conversations.update { current ->
                val partner = theirQueueId ?: "Peer"
                val list = current[partner]?.map { msg ->
                    if (msg.timestamp == targetTimestamp && msg.sender == "You") {
                        val oldText = msg.text
                        msg.text = newText
                        msg.isEdited = true
                        msg.editHistory = msg.editHistory + oldText
                        msg
                    } else {
                        msg
                    }
                } ?: return@update current
                current.toMutableMap().apply {
                    put(partner, list)
                }
            }
        }
    }

    fun sendDeleteMessage(targetTimestamp: Long) {
        val payload = JSONObject().apply {
            put("type", "x.msg.delete")
            put("target_timestamp", targetTimestamp)
        }
        if (sendEncryptedPayload(payload)) {
            _conversations.update { current ->
                val partner = theirQueueId ?: "Peer"
                val list = current[partner]?.filter { it.timestamp != targetTimestamp } ?: return@update current
                current.toMutableMap().apply {
                    put(partner, list)
                }
            }
        }
    }

    fun sendReceipt(targetTimestamp: Long, state: String) {
        val payload = JSONObject().apply {
            put("type", "x.msg.receipt")
            put("target_timestamp", targetTimestamp)
            put("state", state)
        }
        sendEncryptedPayload(payload)
    }

    fun addLocalReaction(targetTimestamp: Long, emoji: String, senderName: String) {
        val current = _conversations.value.toMutableMap()
        val queueId = theirQueueId ?: "Peer"
        val list = current[queueId]?.toMutableList() ?: return
        val idx = list.indexOfFirst { it.timestamp == targetTimestamp }
        if (idx != -1) {
            val msg = list[idx]
            val key = "$senderName-$emoji"
            if (!msg.reactions.contains(key)) {
                val updatedMsg = msg.copy(reactions = msg.reactions + key)
                list[idx] = updatedMsg
                current[queueId] = list
                _conversations.value = current
            }
        }
    }

    private fun updateMessageProgress(messageId: String, progress: Float) {
        val current = _conversations.value.toMutableMap()
        val queueId = theirQueueId ?: "Peer"
        val list = current[queueId]?.toMutableList() ?: return
        val idx = list.indexOfFirst { it.id == messageId }
        if (idx != -1) {
            val msg = list[idx]
            val updatedMsg = msg.copy(fileProgress = progress)
            list[idx] = updatedMsg
            current[queueId] = list
            _conversations.value = current
        }
    }

    fun downloadFileXFTP(
        messageId: String,
        fileName: String,
        masterKeyB64: String,
        chunks: List<String>,
        senderOnion: String?
    ) {
        val scope = CoroutineScope(Dispatchers.IO)
        scope.launch {
            try {
                updateMessageProgress(messageId, 0f)
                val masterKey = Base64.decode(masterKeyB64, Base64.DEFAULT)
                val tempFile = File(context.cacheDir, fileName)
                val outStream = FileOutputStream(tempFile)
                val client = getOkHttpClient()
                
                for (i in chunks.indices) {
                    val chunkId = chunks[i]
                    val isP2P = !senderOnion.isNullOrBlank()
                    val url = if (isP2P) {
                        "https://${prefs.host}:${prefs.port}/api/file/download/$chunkId?onion=$senderOnion"
                    } else {
                        "https://${prefs.host}:${prefs.port}/file/download/$chunkId"
                    }
                    
                    val request = Request.Builder().url(url).build()
                    val response = client.newCall(request).execute()
                    if (!response.isSuccessful) {
                        throw Exception("Failed to download chunk $chunkId: ${response.code()}")
                    }
                    
                    val encryptedBytes = response.body()?.bytes() ?: throw Exception("Empty body")
                    val info = "AnonyMus-XFTP-Chunk-$i".toByteArray(Charsets.UTF_8)
                    val chunkKey = DoubleRatchetSession.hkdfDerive256(masterKey, info)
                    val decryptedBytes = decryptGcmChunk(chunkKey, encryptedBytes)
                    outStream.write(decryptedBytes)
                    
                    val progress = (i + 1).toFloat() / chunks.size
                    updateMessageProgress(messageId, progress)
                }
                
                outStream.close()
                updateMessageProgress(messageId, 1.0f)
                saveFileToDownloads(tempFile, fileName)
                
                mainHandler.post {
                    Toast.makeText(context, "Downloaded $fileName to Downloads folder", Toast.LENGTH_LONG).show()
                }
                updateMessageProgress(messageId, -2f)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to download file", e)
                updateMessageProgress(messageId, -3f)
                mainHandler.post {
                    Toast.makeText(context, "Download failed: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun saveFileToDownloads(tempFile: File, fileName: String) {
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, fileName)
            put(MediaStore.Downloads.MIME_TYPE, getMimeType(fileName))
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
        }
        
        val resolver = context.contentResolver
        val collection = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            MediaStore.Downloads.EXTERNAL_CONTENT_URI
        } else {
            Uri.fromFile(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS))
        }
        
        val uri = resolver.insert(collection, values)
        if (uri != null) {
            resolver.openOutputStream(uri)?.use { out ->
                FileInputStream(tempFile).use { input ->
                    input.copyTo(out)
                }
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                values.clear()
                values.put(MediaStore.Downloads.IS_PENDING, 0)
                resolver.update(uri, values, null, null)
            }
        }
    }
    
    private fun getMimeType(fileName: String): String {
        val ext = MimeTypeMap.getFileExtensionFromUrl(fileName)
        return MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) ?: "*/*"
    }

    private fun decryptGcmChunk(key: ByteArray, encryptedData: ByteArray): ByteArray {
        val iv = encryptedData.copyOfRange(0, 12)
        val ciphertext = encryptedData.copyOfRange(12, encryptedData.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, iv))
        return cipher.doFinal(ciphertext)
    }

    fun disconnect() {
        socket?.disconnect()
        socket?.off()
        socket = null
        _connectionStatus.value = ConnectionStatus.DISCONNECTED
    }
}
