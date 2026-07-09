package com.anonymus.app.data

import com.google.crypto.tink.subtle.EllipticCurves
import com.google.crypto.tink.subtle.Hkdf
import java.security.KeyPair
import java.security.PrivateKey
import java.security.PublicKey
import java.security.interfaces.ECPrivateKey
import java.security.interfaces.ECPublicKey
import java.nio.charset.StandardCharsets
import java.util.Base64

class TinkCryptoProvider : CryptoProvider {
    override fun generateKeyPair(): KeyPair {
        return CryptoUtils.generateKeyPair()
    }

    override fun exportPublicKey(publicKey: PublicKey): String {
        return CryptoUtils.exportPublicKey(publicKey)
    }

    override fun importPublicKey(base64String: String): PublicKey {
        return CryptoUtils.importPublicKey(base64String)
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
        val sharedSecret = EllipticCurves.computeSharedSecret(
            myPrivateKey as ECPrivateKey,
            theirPublicKey as ECPublicKey
        )

        val salt = ByteArray(32) // 32 zero bytes
        val clientKeyBytes = Hkdf.computeHkdf(
            "HmacSha256",
            sharedSecret,
            salt,
            "AnonyMus-Client-To-Server-Key".toByteArray(StandardCharsets.UTF_8),
            32
        )

        val serverKeyBytes = Hkdf.computeHkdf(
            "HmacSha256",
            sharedSecret,
            salt,
            "AnonyMus-Server-To-Client-Key".toByteArray(StandardCharsets.UTF_8),
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
        val chainKey = Hkdf.computeHkdf(
            "HmacSha256",
            rootKey,
            salt,
            "AnonyMus-ChainKey".toByteArray(StandardCharsets.UTF_8),
            32
        )
        val messageKey = Hkdf.computeHkdf(
            "HmacSha256",
            chainKey,
            salt,
            "AnonyMus-MessageKey".toByteArray(StandardCharsets.UTF_8),
            32
        )
        val nextChainKey = Hkdf.computeHkdf(
            "HmacSha256",
            chainKey,
            salt,
            "AnonyMus-NextChainKey".toByteArray(StandardCharsets.UTF_8),
            32
        )
        return Pair(messageKey, nextChainKey)
    }

    override fun encryptMessage(keyBytes: ByteArray, plaintext: String, role: String, seqNum: Int, sessionId: String?): EncryptedPayload {
        val cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding")
        val iv = ByteArray(12)
        java.security.SecureRandom().nextBytes(iv)
        val parameterSpec = javax.crypto.spec.GCMParameterSpec(128, iv)
        val key = javax.crypto.spec.SecretKeySpec(keyBytes, "AES")
        cipher.init(javax.crypto.Cipher.ENCRYPT_MODE, key, parameterSpec)

        val aad = constructAAD(role, seqNum, sessionId, 2)
        cipher.updateAAD(aad)

        val textBytes = plaintext.toByteArray(StandardCharsets.UTF_8)
        val textLen = textBytes.size
        val paddedLength = Math.ceil((textLen + 4).toDouble() / CryptoUtils.BLOCK_SIZE).toInt() * CryptoUtils.BLOCK_SIZE

        val buffer = java.nio.ByteBuffer.allocate(paddedLength)
        buffer.putInt(textLen)
        buffer.put(textBytes)

        if (paddedLength > textLen + 4) {
            val paddingBytes = ByteArray(paddedLength - textLen - 4)
            java.security.SecureRandom().nextBytes(paddingBytes)
            buffer.put(paddingBytes)
        }

        val ciphertext = cipher.doFinal(buffer.array())
        return EncryptedPayload(
            iv = Base64.getEncoder().encodeToString(iv),
            ciphertext = Base64.getEncoder().encodeToString(ciphertext)
        )
    }

    override fun decryptMessage(keyBytes: ByteArray, ivBase64: String, ciphertextBase64: String, role: String, seqNum: Int, sessionId: String?): String? {
        return try {
            val iv = Base64.getDecoder().decode(ivBase64)
            val ciphertext = Base64.getDecoder().decode(ciphertextBase64)

            val cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding")
            val parameterSpec = javax.crypto.spec.GCMParameterSpec(128, iv)
            val key = javax.crypto.spec.SecretKeySpec(keyBytes, "AES")

            var decrypted: ByteArray? = null
            try {
                cipher.init(javax.crypto.Cipher.DECRYPT_MODE, key, parameterSpec)
                val aadV2 = constructAAD(role, seqNum, sessionId, 2)
                cipher.updateAAD(aadV2)
                decrypted = cipher.doFinal(ciphertext)
            } catch (e: Exception) {
                cipher.init(javax.crypto.Cipher.DECRYPT_MODE, key, parameterSpec)
                val aadV1 = constructAAD(role, seqNum, sessionId, 1)
                cipher.updateAAD(aadV1)
                decrypted = cipher.doFinal(ciphertext)
            }

            if (decrypted == null) return null

            val buffer = java.nio.ByteBuffer.wrap(decrypted)
            val textLen = buffer.getInt()

            if (textLen < 0 || textLen > decrypted.size - 4) {
                return null
            }

            val textBytes = ByteArray(textLen)
            buffer.get(textBytes)
            String(textBytes, StandardCharsets.UTF_8)
        } catch (e: Exception) {
            android.util.Log.e("TinkCryptoProvider", "Cryptographic operation failed")
            null
        }
    }

    private fun constructAAD(role: String, seqNum: Int, sessionId: String?, protocolVersion: Int): ByteArray {
        if (protocolVersion == 1) {
            val aad = ByteArray(5)
            aad[0] = role[0].code.toByte()
            val buffer = java.nio.ByteBuffer.wrap(aad)
            buffer.position(1)
            buffer.putInt(seqNum)
            return aad
        }

        val aad = ByteArray(1 + 4 + 16 + 1)
        aad[0] = role[0].code.toByte()
        val buffer = java.nio.ByteBuffer.wrap(aad)
        buffer.position(1)
        buffer.putInt(seqNum)

        val sessionBytes = (sessionId ?: "").toByteArray(StandardCharsets.UTF_8)
        val truncatedSession = ByteArray(16)
        System.arraycopy(sessionBytes, 0, truncatedSession, 0, Math.min(sessionBytes.size, 16))

        System.arraycopy(truncatedSession, 0, aad, 5, 16)
        aad[21] = protocolVersion.toByte()
        return aad
    }
}
