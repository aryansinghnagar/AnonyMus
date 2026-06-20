package com.example.privacychat.data

import android.util.Base64
import java.math.BigInteger
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.PrivateKey
import java.security.PublicKey
import java.security.SecureRandom
import java.security.interfaces.ECPublicKey
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECPoint
import java.security.spec.ECPublicKeySpec
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

data class EncryptedPayload(val iv: String, val ciphertext: String)

object CryptoUtils {

    // Lazy initialization of standard P-256 parameters to avoid manual equation coding
    private val ecParameterSpec: java.security.spec.ECParameterSpec by lazy {
        val kpg = KeyPairGenerator.getInstance("EC")
        kpg.initialize(ECGenParameterSpec("secp256r1"))
        val kp = kpg.generateKeyPair()
        (kp.public as ECPublicKey).params
    }

    /**
     * Generates a fresh ECDH key pair on the P-256 curve (secp256r1).
     */
    fun generateKeyPair(): KeyPair {
        val keyPairGenerator = KeyPairGenerator.getInstance("EC")
        keyPairGenerator.initialize(ECGenParameterSpec("secp256r1"))
        return keyPairGenerator.generateKeyPair()
    }

    /**
     * Exports a public key to base64 raw representation (65 bytes starting with 0x04 for uncompressed EC key).
     */
    fun exportPublicKey(publicKey: PublicKey): String {
        val ecPubKey = publicKey as ECPublicKey
        val x = bigIntegerToUnsignedByteArray(ecPubKey.w.affineX)
        val y = bigIntegerToUnsignedByteArray(ecPubKey.w.affineY)

        val raw = ByteArray(65)
        raw[0] = 0x04 // Uncompressed key marker
        System.arraycopy(x, 0, raw, 1, 32)
        System.arraycopy(y, 0, raw, 33, 32)

        return Base64.encodeToString(raw, Base64.NO_WRAP)
    }

    /**
     * Imports a base64 raw representation of an EC public key back into a PublicKey object.
     */
    fun importPublicKey(base64String: String): PublicKey {
        val rawKey = Base64.decode(base64String, Base64.NO_WRAP)
        require(rawKey.size == 65 && rawKey[0] == 0x04.toByte()) {
            "Invalid public key format: expected 65-byte uncompressed EC key starting with 0x04"
        }

        val xBytes = rawKey.copyOfRange(1, 33)
        val yBytes = rawKey.copyOfRange(33, 65)

        val x = BigInteger(1, xBytes)
        val y = BigInteger(1, yBytes)
        val ecPoint = ECPoint(x, y)

        val spec = ECPublicKeySpec(ecPoint, ecParameterSpec)
        val kf = KeyFactory.getInstance("EC")
        return kf.generatePublic(spec)
    }

    /**
     * Combines my private key and their public key using ECDH to derive a 256-bit AES secret key.
     */
    fun deriveSharedSecret(myPrivateKey: PrivateKey, theirPublicKey: PublicKey): SecretKeySpec {
        val keyAgreement = KeyAgreement.getInstance("ECDH")
        keyAgreement.init(myPrivateKey)
        keyAgreement.doPhase(theirPublicKey, true)
        val rawSecret = keyAgreement.generateSecret()
        
        // Ensure standard length is 32 bytes (256 bits). If not, we trim or pad it.
        val aesKeyBytes = padOrTrim(rawSecret, 32)
        return SecretKeySpec(aesKeyBytes, "AES")
    }

    /**
     * Encrypts a message with AES-GCM (12-byte IV, 128-bit authentication tag length) and returns base64 strings.
     */
    fun encryptMessage(sharedSecret: SecretKeySpec, plaintext: String): EncryptedPayload {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        val iv = ByteArray(12)
        SecureRandom().nextBytes(iv)
        val parameterSpec = GCMParameterSpec(128, iv)
        cipher.init(Cipher.ENCRYPT_MODE, sharedSecret, parameterSpec)

        val ciphertext = cipher.doFinal(plaintext.toByteArray(Charsets.UTF_8))
        return EncryptedPayload(
            iv = Base64.encodeToString(iv, Base64.NO_WRAP),
            ciphertext = Base64.encodeToString(ciphertext, Base64.NO_WRAP)
        )
    }

    /**
     * Decrypts a message with AES-GCM using base64 IV and ciphertext. Returns null on failure.
     */
    fun decryptMessage(sharedSecret: SecretKeySpec, ivBase64: String, ciphertextBase64: String): String? {
        return try {
            val iv = Base64.decode(ivBase64, Base64.NO_WRAP)
            val ciphertext = Base64.decode(ciphertextBase64, Base64.NO_WRAP)

            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            val parameterSpec = GCMParameterSpec(128, iv)
            cipher.init(Cipher.DECRYPT_MODE, sharedSecret, parameterSpec)

            val decrypted = cipher.doFinal(ciphertext)
            String(decrypted, Charsets.UTF_8)
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    private fun bigIntegerToUnsignedByteArray(value: BigInteger): ByteArray {
        val array = value.toByteArray()
        if (array.isEmpty()) return ByteArray(32)
        if (array[0] == 0.toByte()) {
            val stripped = ByteArray(array.size - 1)
            System.arraycopy(array, 1, stripped, 0, stripped.size)
            return padOrTrim(stripped, 32)
        }
        return padOrTrim(array, 32)
    }

    private fun padOrTrim(array: ByteArray, targetSize: Int): ByteArray {
        if (array.size == targetSize) return array
        val result = ByteArray(targetSize)
        if (array.size < targetSize) {
            System.arraycopy(array, 0, result, targetSize - array.size, array.size)
        } else {
            System.arraycopy(array, array.size - targetSize, result, 0, targetSize)
        }
        return result
    }
}
