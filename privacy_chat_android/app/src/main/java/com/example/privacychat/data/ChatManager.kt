package com.example.privacychat.data

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
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
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

    // App Preferences
    private lateinit var prefs: PreferencesHelper

    // Cryptographic Session Keys
    private var myKeyPair: KeyPair? = null
    private var myPublicKeyExported: String? = null
    
    // Shared secrets derived with other users: targetUsername -> AES SecretKey
    private val sharedSecrets = mutableMapOf<String, SecretKeySpec>()
    
    // Queue for messages received before their public key was retrieved: targetUsername -> list of raw messages
    private val pendingMessages = mutableMapOf<String, MutableList<PendingMessage>>()

    data class PendingMessage(val iv: String, val ciphertext: String)

    // Socket.IO instance
    private var socket: Socket? = null
    
    // OkHttpClient
    private var okHttpClient: OkHttpClient? = null

    // Compose observable state
    var currentUsername: String? = null
        private set

    private val _connectionStatus = MutableStateFlow(ConnectionStatus.DISCONNECTED)
    val connectionStatus: StateFlow<ConnectionStatus> = _connectionStatus.asStateFlow()

    private val _onlineUsers = MutableStateFlow<List<String>>(emptyList())
    val onlineUsers: StateFlow<List<String>> = _onlineUsers.asStateFlow()

    // Map of conversation messages: partnerUsername -> message list
    private val _conversations = MutableStateFlow<Map<String, List<ChatMessage>>>(emptyMap())
    val conversations: StateFlow<Map<String, List<ChatMessage>>> = _conversations.asStateFlow()

    fun initialize(context: Context) {
        prefs = PreferencesHelper(context)
    }

    private fun getOkHttpClient(): OkHttpClient {
        val host = prefs.host
        val trustSelfSigned = prefs.trustSelfSigned

        if (okHttpClient == null) {
            val builder = OkHttpClient.Builder()
            if (trustSelfSigned) {
                try {
                    val trustAllCerts = arrayOf<TrustManager>(object : X509TrustManager {
                        override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
                        override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
                        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
                    })

                    val sslContext = SSLContext.getInstance("TLS")
                    sslContext.init(null, trustAllCerts, java.security.SecureRandom())
                    builder.sslSocketFactory(sslContext.socketFactory, trustAllCerts[0] as X509TrustManager)
                    
                    // Safety check: Restrict Hostname Verification bypass strictly to the configured server IP
                    builder.hostnameVerifier(HostnameVerifier { hostname, _ ->
                        hostname == host || hostname == "localhost" || hostname == "127.0.0.1"
                    })
                    Log.d(TAG, "Unsafe OkHttpClient created (trusting self-signed certs for host $host)")
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to build unsafe SSLSocketFactory", e)
                }
            }
            okHttpClient = builder.build()
        }
        return okHttpClient!!
    }

    fun resetClient() {
        disconnect()
        okHttpClient = null
        sharedSecrets.clear()
        pendingMessages.clear()
        myKeyPair = null
        myPublicKeyExported = null
        _conversations.value = emptyMap()
        _onlineUsers.value = emptyList()
        currentUsername = null
    }

    fun performAuthRequest(
        endpoint: String, // "/login" or "/register"
        username: String,
        password: CharSequence,
        callback: (success: Boolean, message: String) -> Unit
    ) {
        val host = prefs.host
        val port = prefs.port
        if (host.isNullOrBlank()) {
            callback(false, "Server not configured")
            return
        }

        val client = getOkHttpClient()
        val mediaType = MediaType.parse("application/json; charset=utf-8")
        val jsonBody = JSONObject().apply {
            put("username", username)
            put("password", password.toString())
        }

        val url = "https://$host:$port$endpoint"
        val request = Request.Builder()
            .url(url)
            .post(RequestBody.create(mediaType, jsonBody.toString()))
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e(TAG, "Auth request failed", e)
                mainHandler.post { callback(false, "Network error: ${e.message}") }
            }

            override fun onResponse(call: Call, response: Response) {
                val responseStr = response.body()?.string() ?: ""
                try {
                    val json = JSONObject(responseStr)
                    val success = json.optBoolean("success", false)
                    val errorMsg = json.optString("error", "Unknown error")
                    mainHandler.post {
                        if (response.isSuccessful && success) {
                            if (endpoint == "/login") {
                                currentUsername = username
                            }
                            callback(true, "Success")
                        } else {
                            callback(false, errorMsg)
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to parse auth response", e)
                    mainHandler.post { callback(false, "Server error: ${response.code()}") }
                }
            }
        })
    }

    /**
     * Establishes real-time connection using Socket.IO
     */
    fun connect() {
        val host = prefs.host
        val port = prefs.port
        val username = currentUsername
        if (host.isNullOrBlank() || username.isNullOrBlank()) {
            _connectionStatus.value = ConnectionStatus.ERROR
            return
        }

        if (socket != null) {
            return
        }

        _connectionStatus.value = ConnectionStatus.CONNECTING
        Log.d(TAG, "Connecting to SocketIO https://$host:$port")

        try {
            val client = getOkHttpClient()
            val options = IO.Options().apply {
                callFactory = client
                webSocketFactory = client
                secure = true
                reconnection = true
            }

            socket = IO.socket("https://$host:$port", options)

            // Setup Socket.IO Event Handlers
            socket?.on(Socket.EVENT_CONNECT) {
                Log.d(TAG, "Socket connected. Initializing E2EE keys.")
                _connectionStatus.value = ConnectionStatus.CONNECTED

                // Generate P-256 KeyPair in RAM
                try {
                    if (myKeyPair == null) {
                        myKeyPair = CryptoUtils.generateKeyPair()
                        myPublicKeyExported = CryptoUtils.exportPublicKey(myKeyPair!!.public)
                    }

                    // Authenticate session
                    val authObj = JSONObject().apply { put("username", username) }
                    socket?.emit("authenticate", authObj)

                    // Export public key
                    val keyObj = JSONObject().apply { put("public_key", myPublicKeyExported) }
                    socket?.emit("public_key", keyObj)
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to initialize cryptographic session", e)
                    _connectionStatus.value = ConnectionStatus.ERROR
                }
            }

            socket?.on(Socket.EVENT_DISCONNECT) { args ->
                val reason = args.firstOrNull()?.toString() ?: "Unknown"
                Log.w(TAG, "Socket disconnected: $reason")
                _connectionStatus.value = ConnectionStatus.DISCONNECTED
            }

            socket?.on(Socket.EVENT_CONNECT_ERROR) { args ->
                val err = args.firstOrNull()?.toString() ?: "Unknown"
                Log.e(TAG, "Socket connection error: $err")
                _connectionStatus.value = ConnectionStatus.ERROR
            }

            socket?.on("user_list_update") { args ->
                val data = args.firstOrNull()
                Log.d(TAG, "Received user_list_update: $data")
                val usersList = mutableListOf<String>()
                
                if (data is JSONArray) {
                    for (i in 0 until data.length()) {
                        val name = data.getString(i)
                        if (name != username) {
                            usersList.add(name)
                        }
                    }
                } else if (data is JSONObject) {
                    val arr = data.optJSONArray("users")
                    if (arr != null) {
                        for (i in 0 until arr.length()) {
                            val name = arr.getString(i)
                            if (name != username) {
                                usersList.add(name)
                            }
                        }
                    }
                }
                _onlineUsers.value = usersList
            }

            socket?.on("public_key") { args ->
                val data = args.firstOrNull() as? JSONObject ?: return@on
                val sender = data.optString("username")
                val pubKeyBase64 = data.optString("public_key")
                Log.d(TAG, "Received public key from $sender")

                if (sender.isNotBlank() && pubKeyBase64.isNotBlank() && myKeyPair != null) {
                    try {
                        val importedKey = CryptoUtils.importPublicKey(pubKeyBase64)
                        val sharedSecret = CryptoUtils.deriveSharedSecret(myKeyPair!!.private, importedKey)
                        sharedSecrets[sender] = sharedSecret
                        Log.d(TAG, "Successfully derived shared secret with $sender")

                        // Flush pending messages
                        val queued = pendingMessages[sender]
                        if (!queued.isNullOrEmpty()) {
                            for (msg in queued) {
                                handleIncomingCiphertext(sender, msg.iv, msg.ciphertext)
                            }
                            queued.clear()
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "Error importing public key or deriving secret for $sender", e)
                    }
                }
            }

            socket?.on("private_message") { args ->
                val data = args.firstOrNull() as? JSONObject ?: return@on
                val from = data.optString("from")
                val iv = data.optString("iv")
                val ciphertext = data.optString("ciphertext")
                Log.d(TAG, "Received private message from $from")

                if (from.isNotBlank() && iv.isNotBlank() && ciphertext.isNotBlank()) {
                    val secret = sharedSecrets[from]
                    if (secret == null) {
                        // Request user key first, queue message
                        Log.d(TAG, "No shared secret with $from. Requesting key and queueing message.")
                        val queued = pendingMessages.getOrPut(from) { mutableListOf() }
                        queued.add(PendingMessage(iv, ciphertext))
                        
                        val reqData = JSONObject().apply { put("username", from) }
                        socket?.emit("request_key", reqData)
                    } else {
                        handleIncomingCiphertext(from, iv, ciphertext)
                    }
                }
            }

            socket?.connect()
        } catch (e: Exception) {
            Log.e(TAG, "Socket connection init exception", e)
            _connectionStatus.value = ConnectionStatus.ERROR
        }
    }

    private fun handleIncomingCiphertext(from: String, iv: String, ciphertext: String) {
        val secret = sharedSecrets[from]
        if (secret != null) {
            val decrypted = CryptoUtils.decryptMessage(secret, iv, ciphertext)
            val chatMsg = if (decrypted != null) {
                ChatMessage(sender = from, text = decrypted, isDecryptedSuccessfully = true)
            } else {
                ChatMessage(sender = from, text = "[encrypted message — could not decrypt]", isDecryptedSuccessfully = false)
            }
            appendMessage(from, chatMsg)
        }
    }

    fun requestPublicKeyIfNeeded(targetUsername: String) {
        if (!sharedSecrets.containsKey(targetUsername)) {
            val reqData = JSONObject().apply { put("username", targetUsername) }
            socket?.emit("request_key", reqData)
        }
    }

    fun sendPrivateMessage(targetUsername: String, text: String): Boolean {
        val secret = sharedSecrets[targetUsername]
        if (secret == null) {
            Log.w(TAG, "Cannot send message: no shared secret derived yet with $targetUsername")
            requestPublicKeyIfNeeded(targetUsername)
            return false
        }

        try {
            val payload = CryptoUtils.encryptMessage(secret, text)
            val msgObj = JSONObject().apply {
                put("to", targetUsername)
                put("iv", payload.iv)
                put("ciphertext", payload.ciphertext)
            }
            socket?.emit("private_message", msgObj)

            val chatMsg = ChatMessage(sender = "You", text = text)
            appendMessage(targetUsername, chatMsg)
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
        }
    }

    fun disconnect() {
        Log.d(TAG, "Disconnecting Socket.IO client")
        socket?.disconnect()
        socket?.off()
        socket = null
        _connectionStatus.value = ConnectionStatus.DISCONNECTED
    }
}
