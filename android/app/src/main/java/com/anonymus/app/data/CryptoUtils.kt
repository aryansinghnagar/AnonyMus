package com.anonymus.app.data

import android.util.Base64
import android.util.Log
import java.nio.ByteBuffer
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * Cryptographic utility layer for AnonyMus Android (Protocol v2).
 *
 * Key exchange:   X25519 (XDH)
 * Session E2EE:   Double Ratchet (DoubleRatchetSession) + NaCl box (Lazysodium)
 * Legacy support: v1 AES-256-GCM symmetric chain (for historical message replay)
 *
 * All public key export formats match the Python backend and web frontend:
 *   - Public keys: 32-byte raw, base64-encoded (NO_WRAP)
 *   - Private keys: 32-byte raw, base64-encoded (NO_WRAP)
 */
object CryptoUtils {

    /** Padded plaintext block size (matches Python/JS: 16 KB) */
    const val PADDED_SIZE = 16384
    /** Legacy v1 block size for history replay */
    const val BLOCK_SIZE_V1 = 512

    private const val TAG = "CryptoUtils"

    // -----------------------------------------------------------------------
    // Key pair generation & export (X25519)
    // -----------------------------------------------------------------------

    /**
     * Generates a fresh X25519 key pair.
     * @return Pair(publicKeyRaw32Bytes, privateKeyRaw32Bytes)
     */
    fun generateKeyPair(): Pair<ByteArray, ByteArray> {
        val kpg = KeyPairGenerator.getInstance("XDH")
        kpg.initialize(java.security.spec.NamedParameterSpec.X25519)
        val kp = kpg.generateKeyPair()
        val pubRaw = DoubleRatchetSession.exportX25519PublicRaw(kp)
        val privRaw = DoubleRatchetSession.exportX25519PrivateRaw(kp)
        return Pair(pubRaw, privRaw)
    }

    /**
     * Exports raw X25519 public key bytes as a base64 string (NO_WRAP).
     * Result is exactly 44 characters (32 bytes → base64).
     */
    fun exportPublicKey(rawPublicKeyBytes: ByteArray): String =
        Base64.encodeToString(rawPublicKeyBytes, Base64.NO_WRAP)

    /**
     * Imports a base64-encoded raw X25519 public key.
     */
    fun importPublicKeyBytes(base64String: String): ByteArray =
        Base64.decode(base64String, Base64.NO_WRAP)

    /**
     * Computes X25519 DH shared secret from raw key bytes.
     * @return 32-byte shared secret
     */
    fun computeSharedSecret(myPrivRaw: ByteArray, theirPubRaw: ByteArray): ByteArray =
        DoubleRatchetSession.x25519Dh(myPrivRaw, theirPubRaw)

    // -----------------------------------------------------------------------
    // Safety Number (v2 format: 12 groups of 5 decimal digits)
    // -----------------------------------------------------------------------

    /**
     * Produces a human-verifiable safety number: 12 groups of 5 decimal digits.
     * Matches Python [protocol.compute_safety_number] and JS [computeSafetyNumber].
     */
    fun computeSafetyNumber(myPubKeyBase64: String, theirPubKeyBase64: String): String {
        val sorted = listOf(myPubKeyBase64, theirPubKeyBase64).sorted()
        val data = (sorted[0] + sorted[1]).toByteArray(Charsets.UTF_8)
        val h = MessageDigest.getInstance("SHA-256").digest(data)

        val groups = mutableListOf<String>()
        var i = 0
        while (groups.size < 12) {
            val byteIdx = (i * 2.5).toInt()
            if (byteIdx + 1 >= h.size) break
            val v = ((h[byteIdx].toInt() and 0xFF) shl 8) or (h[byteIdx + 1].toInt() and 0xFF)
            groups.add((v % 100000).toString().padStart(5, '0'))
            i++
        }
        return groups.joinToString(" ")
    }

    // -----------------------------------------------------------------------
    // AAD construction (v2 format: role + seq + 16-byte session hash + version)
    // -----------------------------------------------------------------------

    /**
     * Constructs Authenticated Additional Data (AAD) for AES-GCM.
     * Protocol v2 format (matches Python [construct_aad] and JS [constructAAD]).
     */
    fun constructAAD(role: String, seqNum: Int, sessionId: String, protocolVersion: Int = 2): ByteArray {
        if (protocolVersion == 1) {
            val aad = ByteArray(5)
            aad[0] = role[0].code.toByte()
            ByteBuffer.wrap(aad, 1, 4).putInt(seqNum)
            return aad
        }
        val sessionHash = MessageDigest.getInstance("SHA-256")
            .digest(sessionId.toByteArray(Charsets.UTF_8))
        val truncated = sessionHash.copyOfRange(0, 16)

        val aad = ByteArray(22) // 1 + 4 + 16 + 1
        aad[0] = role[0].code.toByte()
        ByteBuffer.wrap(aad, 1, 4).putInt(seqNum)
        System.arraycopy(truncated, 0, aad, 5, 16)
        aad[21] = protocolVersion.toByte()
        return aad
    }

    // -----------------------------------------------------------------------
    // V1 Symmetric Chain Helpers (legacy history replay only)
    // -----------------------------------------------------------------------

    /**
     * Derives a per-message key and next chain key from the current chain key.
     * Used only for replaying old v1 messages from local DB history.
     */
    fun deriveChainKeys(chainKey: ByteArray): Pair<ByteArray, ByteArray> {
        val msgKey = DoubleRatchetSession.hmacSha256(
            chainKey, "AnonyMus-MessageKey".toByteArray()
        )
        val nextKey = DoubleRatchetSession.hmacSha256(
            chainKey, "AnonyMus-ChainKey".toByteArray()
        )
        return Pair(msgKey, nextKey)
    }

    /**
     * V1 AES-256-GCM encrypt. Returns [EncryptedPayload] with base64 IV and ciphertext.
     * Used for relay mode and legacy history replay.
     */
    fun encryptMessageV1(keyBytes: ByteArray, plaintext: String, role: String, seqNum: Int, sessionId: String): EncryptedPayload {
        val iv = ByteArray(12).also { SecureRandom().nextBytes(it) }
        val textBytes = plaintext.toByteArray(Charsets.UTF_8)
        val paddedLen = maxOf(BLOCK_SIZE_V1, ((textBytes.size + 4 + BLOCK_SIZE_V1 - 1) / BLOCK_SIZE_V1) * BLOCK_SIZE_V1)

        val buffer = ByteBuffer.allocate(paddedLen)
        buffer.putInt(textBytes.size)
        buffer.put(textBytes)
        if (paddedLen > textBytes.size + 4) {
            val padding = ByteArray(paddedLen - textBytes.size - 4)
            SecureRandom().nextBytes(padding)
            buffer.put(padding)
        }

        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(keyBytes, "AES"), GCMParameterSpec(128, iv))
        cipher.updateAAD(constructAAD(role, seqNum, sessionId, 1))
        val ciphertext = cipher.doFinal(buffer.array())

        return EncryptedPayload(
            iv = Base64.encodeToString(iv, Base64.NO_WRAP),
            ciphertext = Base64.encodeToString(ciphertext, Base64.NO_WRAP)
        )
    }

    /**
     * V1 AES-256-GCM decrypt. Returns null on failure.
     */
    fun decryptMessageV1(keyBytes: ByteArray, ivBase64: String, ciphertextBase64: String, role: String, seqNum: Int, sessionId: String): String? {
        return try {
            val iv = Base64.decode(ivBase64, Base64.NO_WRAP)
            val ciphertext = Base64.decode(ciphertextBase64, Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(keyBytes, "AES"), GCMParameterSpec(128, iv))

            // Try v2 AAD first, then fall back to v1
            try {
                cipher.updateAAD(constructAAD(role, seqNum, sessionId, 2))
                extractPlaintext(cipher.doFinal(ciphertext))
            } catch (e: Exception) {
                val c2 = Cipher.getInstance("AES/GCM/NoPadding")
                c2.init(Cipher.DECRYPT_MODE, SecretKeySpec(keyBytes, "AES"), GCMParameterSpec(128, iv))
                c2.updateAAD(constructAAD(role, seqNum, sessionId, 1))
                extractPlaintext(c2.doFinal(ciphertext))
            }
        } catch (e: Exception) {
            Log.e(TAG, "V1 decryption failed")
            null
        }
    }

    // -----------------------------------------------------------------------
    // V2 Double Ratchet + NaCl Box Encrypt/Decrypt
    // -----------------------------------------------------------------------

    /**
     * V2 encrypt: advances the DR session, encrypts with AES-256-GCM,
     * then wraps in NaCl box using Lazysodium.
     *
     * @return [EncryptedPayloadV2] containing all fields needed for the wire format.
     */
    fun encryptMessageV2(
        drSession: DoubleRatchetSession,
        plaintext: String,
        role: String,
        sessionId: String,
        myPrivRaw: ByteArray,
        peerPubRaw: ByteArray
    ): EncryptedPayloadV2 {
        val step = drSession.encrypt()

        // Inner AES-256-GCM
        val iv = ByteArray(12).also { SecureRandom().nextBytes(it) }
        val textBytes = plaintext.toByteArray(Charsets.UTF_8)
        val paddedLen = maxOf(PADDED_SIZE, ((textBytes.size + 4 + PADDED_SIZE - 1) / PADDED_SIZE) * PADDED_SIZE)

        val buffer = ByteBuffer.allocate(paddedLen)
        buffer.putInt(textBytes.size)
        buffer.put(textBytes)
        if (paddedLen > textBytes.size + 4) {
            val padding = ByteArray(paddedLen - textBytes.size - 4)
            SecureRandom().nextBytes(padding)
            buffer.put(padding)
        }

        val innerCipher = Cipher.getInstance("AES/GCM/NoPadding")
        innerCipher.init(
            Cipher.ENCRYPT_MODE,
            SecretKeySpec(step.messageKey, "AES"),
            GCMParameterSpec(128, iv)
        )
        innerCipher.updateAAD(constructAAD(role, step.seq, sessionId, 2))
        val innerCiphertext = innerCipher.doFinal(buffer.array())

        // Assemble inner payload: IV (12) + ciphertext
        val innerPayload = iv + innerCiphertext

        // Outer NaCl box
        val (boxCiphertext, boxNonce) = naclBoxEncrypt(innerPayload, myPrivRaw, peerPubRaw)

        return EncryptedPayloadV2(
            naclNonce = Base64.encodeToString(boxNonce, Base64.NO_WRAP),
            naclCiphertext = Base64.encodeToString(boxCiphertext, Base64.NO_WRAP),
            drDhPublic = Base64.encodeToString(step.myDhPublicBytes, Base64.NO_WRAP),
            drSeq = step.seq,
            drPn = step.prevChainLen
        )
    }

    /**
     * V2 decrypt: opens NaCl box, advances DR session, decrypts AES-256-GCM.
     * Returns null on any failure.
     */
    fun decryptMessageV2(
        drSession: DoubleRatchetSession,
        payload: EncryptedPayloadV2,
        role: String,
        sessionId: String,
        myPrivRaw: ByteArray,
        peerPubRaw: ByteArray
    ): String? {
        return try {
            val boxNonce = Base64.decode(payload.naclNonce, Base64.NO_WRAP)
            val boxCiphertext = Base64.decode(payload.naclCiphertext, Base64.NO_WRAP)
            val drPubBytes = Base64.decode(payload.drDhPublic, Base64.NO_WRAP)

            // Outer NaCl box open
            val innerPayload = naclBoxDecrypt(boxCiphertext, boxNonce, peerPubRaw, myPrivRaw)
                ?: return null

            val innerIv = innerPayload.copyOfRange(0, 12)
            val innerCiphertext = innerPayload.copyOfRange(12, innerPayload.size)

            // DR ratchet step
            val messageKey = drSession.decrypt(drPubBytes, payload.drSeq, payload.drPn)

            // Inner AES-256-GCM decrypt
            val innerCipher = Cipher.getInstance("AES/GCM/NoPadding")
            innerCipher.init(
                Cipher.DECRYPT_MODE,
                SecretKeySpec(messageKey, "AES"),
                GCMParameterSpec(128, innerIv)
            )
            innerCipher.updateAAD(constructAAD(role, payload.drSeq, sessionId, 2))
            val decrypted = innerCipher.doFinal(innerCiphertext)
            extractPlaintext(decrypted)
        } catch (e: Exception) {
            Log.e(TAG, "V2 decryption failed")
            null
        }
    }

    // -----------------------------------------------------------------------
    // NaCl Box (XSalsa20-Poly1305) via Lazysodium-Android
    // -----------------------------------------------------------------------

    /**
     * Encrypts [plaintext] using NaCl authenticated box (XSalsa20-Poly1305).
     * Uses Lazysodium-Android under the hood.
     * @return Pair(ciphertext, nonce) — both raw byte arrays
     */
    private fun naclBoxEncrypt(plaintext: ByteArray, senderPrivRaw: ByteArray, recipientPubRaw: ByteArray): Pair<ByteArray, ByteArray> {
        // Lazysodium: com.goterl.lazysodium
        val sodium = com.goterl.lazysodium.LazySodiumAndroid(com.goterl.lazysodium.SodiumAndroid())
        val nonce = ByteArray(com.goterl.lazysodium.interfaces.Box.NONCEBYTES)
        java.security.SecureRandom().nextBytes(nonce)

        val recipientPub = com.goterl.lazysodium.utils.Key.fromBytes(recipientPubRaw)
        val senderPriv = com.goterl.lazysodium.utils.Key.fromBytes(senderPrivRaw)
        val keyPair = com.goterl.lazysodium.utils.KeyPair(recipientPub, senderPriv)

        val ciphertext = ByteArray(plaintext.size + com.goterl.lazysodium.interfaces.Box.MACBYTES)
        sodium.cryptoBoxEasy(ciphertext, plaintext, plaintext.size.toLong(), nonce, keyPair.publicKey.asBytes, keyPair.secretKey.asBytes)
        return Pair(ciphertext, nonce)
    }

    /**
     * Decrypts a NaCl box ciphertext.
     * @return plaintext bytes or null on failure
     */
    private fun naclBoxDecrypt(ciphertext: ByteArray, nonce: ByteArray, senderPubRaw: ByteArray, recipientPrivRaw: ByteArray): ByteArray? {
        return try {
            val sodium = com.goterl.lazysodium.LazySodiumAndroid(com.goterl.lazysodium.SodiumAndroid())
            val plaintext = ByteArray(ciphertext.size - com.goterl.lazysodium.interfaces.Box.MACBYTES)
            val ok = sodium.cryptoBoxOpenEasy(plaintext, ciphertext, ciphertext.size.toLong(), nonce, senderPubRaw, recipientPrivRaw)
            if (ok) plaintext else null
        } catch (e: Exception) {
            Log.e(TAG, "NaCl box open failed")
            null
        }
    }

    // -----------------------------------------------------------------------
    // Plaintext extraction helper
    // -----------------------------------------------------------------------

    private fun extractPlaintext(decrypted: ByteArray): String? {
        if (decrypted.size < 4) return null
        val textLen = ByteBuffer.wrap(decrypted, 0, 4).int
        if (textLen < 0 || textLen > decrypted.size - 4) return null
        return String(decrypted, 4, textLen, Charsets.UTF_8)
    }
}

// -----------------------------------------------------------------------
// Data classes (Package Level)
// -----------------------------------------------------------------------

data class EncryptedPayload(val iv: String, val ciphertext: String)

data class EncryptedPayloadV2(
    val naclNonce: String,     // "nacl_nonce"
    val naclCiphertext: String, // "nacl_ciphertext"
    val drDhPublic: String,    // "dr_dh_public"
    val drSeq: Int,            // "dr_seq"
    val drPn: Int              // "dr_pn"
) {
    fun toJsonString(): String = """{"nacl_nonce":"$naclNonce","nacl_ciphertext":"$naclCiphertext","dr_dh_public":"$drDhPublic","dr_seq":$drSeq,"dr_pn":$drPn}"""

    companion object {
        fun fromJsonString(json: String): EncryptedPayloadV2 {
            val obj = org.json.JSONObject(json)
            return EncryptedPayloadV2(
                naclNonce = obj.getString("nacl_nonce"),
                naclCiphertext = obj.getString("nacl_ciphertext"),
                drDhPublic = obj.getString("dr_dh_public"),
                drSeq = obj.getInt("dr_seq"),
                drPn = obj.getInt("dr_pn")
            )
        }
    }
}

data class SessionKeys(val writeKey: ByteArray, val readKey: ByteArray)
