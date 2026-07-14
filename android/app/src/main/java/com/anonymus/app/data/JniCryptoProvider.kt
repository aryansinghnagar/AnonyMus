package com.anonymus.app.data

import java.security.KeyPair
import java.security.PrivateKey
import java.security.PublicKey
import java.nio.charset.StandardCharsets
import java.util.Base64
import java.security.MessageDigest
import java.nio.ByteBuffer

class JniPublicKey(private val rawBytes: ByteArray) : PublicKey {
    override fun getAlgorithm(): String = "X25519"
    override fun getFormat(): String = "RAW"
    override fun getEncoded(): ByteArray = rawBytes
}

class JniPrivateKey(private val rawBytes: ByteArray) : PrivateKey {
    override fun getAlgorithm(): String = "X25519"
    override fun getFormat(): String = "RAW"
    override fun getEncoded(): ByteArray = rawBytes
}

class JniCryptoProvider : CryptoProvider {
    companion object {
        init {
            System.loadLibrary("anonymus_core")
        }

        @JvmStatic
        private external fun generateKeypairNative(): ByteArray

        @JvmStatic
        private external fun x25519DhNative(privateKey: ByteArray, publicKey: ByteArray): ByteArray

        @JvmStatic
        private external fun aeadEncryptNative(key: ByteArray, plaintext: ByteArray, aad: ByteArray): ByteArray

        @JvmStatic
        private external fun aeadDecryptNative(key: ByteArray, blob: ByteArray, aad: ByteArray): ByteArray

        @JvmStatic
        private external fun hkdfDeriveNative(ikm: ByteArray, info: ByteArray, salt: ByteArray, outputLen: Int): ByteArray
    }

    override fun generateKeyPair(): KeyPair {
        val raw = generateKeypairNative()
        val priv = JniPrivateKey(raw.copyOfRange(0, 32))
        val pub = JniPublicKey(raw.copyOfRange(32, 64))
        return KeyPair(pub, priv)
    }

    override fun exportPublicKey(publicKey: PublicKey): String {
        return Base64.getEncoder().encodeToString(publicKey.encoded)
    }

    override fun importPublicKey(base64String: String): PublicKey {
        return JniPublicKey(Base64.getDecoder().decode(base64String))
    }

    override fun computeSafetyNumber(myPubKeyBase64: String, theirPubKeyBase64: String): String {
        return CryptoUtils.computeSafetyNumber(myPubKeyBase64, theirPubKeyBase64)
    }

    override fun deriveSessionKeys(
        myPrivateKey: PrivateKey,
        theirPublicKey: PublicKey,
        myPubKeyBase64: String,
        theirPubKeyBase64: String
    ): SessionKeys {
        val sharedSecret = x25519DhNative(myPrivateKey.encoded, theirPublicKey.encoded)
        val salt = ByteArray(32)

        val clientKeyBytes = hkdfDeriveNative(
            sharedSecret,
            "AnonyMus-Client-To-Server-Key".toByteArray(StandardCharsets.UTF_8),
            salt,
            32
        )
        val serverKeyBytes = hkdfDeriveNative(
            sharedSecret,
            "AnonyMus-Server-To-Client-Key".toByteArray(StandardCharsets.UTF_8),
            salt,
            32
        )

        val isAlice = myPubKeyBase64 < theirPubKeyBase64
        return if (isAlice) {
            SessionKeys(writeKey = clientKeyBytes, readKey = serverKeyBytes)
        } else {
            SessionKeys(writeKey = serverKeyBytes, readKey = clientKeyBytes)
        }
    }

    override fun deriveChainKeys(rootKey: ByteArray): Pair<ByteArray, ByteArray> {
        val salt = ByteArray(32)
        val chainKey = hkdfDeriveNative(rootKey, "AnonyMus-ChainKey".toByteArray(StandardCharsets.UTF_8), salt, 32)
        val messageKey = hkdfDeriveNative(chainKey, "AnonyMus-MessageKey".toByteArray(StandardCharsets.UTF_8), salt, 32)
        val nextChainKey = hkdfDeriveNative(chainKey, "AnonyMus-NextChainKey".toByteArray(StandardCharsets.UTF_8), salt, 32)
        return Pair(messageKey, nextChainKey)
    }

    override fun encryptMessage(
        keyBytes: ByteArray,
        plaintext: String,
        role: String,
        seqNum: Int,
        sessionId: String?
    ): EncryptedPayload {
        val aad = CryptoUtils.constructAAD(role, seqNum, sessionId ?: "", 2)
        val textBytes = plaintext.toByteArray(StandardCharsets.UTF_8)
        val textLen = textBytes.size

        // Padding (matches constructAAD alignment and Signal padding rules)
        val paddedLength = Math.ceil((textLen + 4).toDouble() / CryptoUtils.BLOCK_SIZE_V1).toInt() * CryptoUtils.BLOCK_SIZE_V1
        val buffer = ByteBuffer.allocate(paddedLength)
        buffer.putInt(textLen)
        buffer.put(textBytes)
        val paddedPlaintext = buffer.array()

        val blob = aeadEncryptNative(keyBytes, paddedPlaintext, aad)
        val iv = blob.copyOfRange(0, 12)
        val ciphertext = blob.copyOfRange(12, blob.size)

        return EncryptedPayload(
            iv = Base64.getEncoder().encodeToString(iv),
            ciphertext = Base64.getEncoder().encodeToString(ciphertext)
        )
    }

    override fun decryptMessage(
        keyBytes: ByteArray,
        ivBase64: String,
        ciphertextBase64: String,
        role: String,
        seqNum: Int,
        sessionId: String?
    ): String? {
        return try {
            val iv = Base64.getDecoder().decode(ivBase64)
            val ct = Base64.getDecoder().decode(ciphertextBase64)
            val blob = ByteArray(iv.size + ct.size)
            System.arraycopy(iv, 0, blob, 0, iv.size)
            System.arraycopy(ct, 0, blob, iv.size, ct.size)

            val aad = CryptoUtils.constructAAD(role, seqNum, sessionId ?: "", 2)
            val paddedPlaintext = aeadDecryptNative(keyBytes, blob, aad)

            val buffer = ByteBuffer.wrap(paddedPlaintext)
            val textLen = buffer.getInt()
            if (textLen < 0 || textLen > paddedPlaintext.size - 4) {
                return null
            }
            val textBytes = ByteArray(textLen)
            buffer.get(textBytes)
            String(textBytes, StandardCharsets.UTF_8)
        } catch (e: Exception) {
            android.util.Log.e("JniCryptoProvider", "Cryptographic decryption operation failed", e)
            null
        }
    }
}
