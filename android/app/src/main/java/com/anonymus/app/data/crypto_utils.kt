package com.anonymus.app.data

import java.util.Base64
import java.math.BigInteger
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.MessageDigest
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
data class SessionKeys(val writeKey: ByteArray, val readKey: ByteArray)

object CryptoUtils {
    const val BLOCK_SIZE = 512

    // Lazy initialization of standard P-256 parameters
    private val ecParameterSpec: java.security.spec.ECParameterSpec by lazy {
        val kpg = KeyPairGenerator.getInstance("EC")
        kpg.initialize(ECGenParameterSpec("secp256r1"))
        val kp = kpg.generateKeyPair()
        (kp.public as ECPublicKey).params
    }

    fun generateKeyPair(): KeyPair {
        val keyPairGenerator = KeyPairGenerator.getInstance("EC")
        keyPairGenerator.initialize(ECGenParameterSpec("secp256r1"))
        return keyPairGenerator.generateKeyPair()
    }

    fun exportPublicKey(publicKey: PublicKey): String {
        val ecPubKey = publicKey as ECPublicKey
        val x = bigIntegerToUnsignedByteArray(ecPubKey.w.affineX)
        val y = bigIntegerToUnsignedByteArray(ecPubKey.w.affineY)

        val raw = ByteArray(65)
        raw[0] = 0x04 // Uncompressed key marker
        System.arraycopy(x, 0, raw, 1, 32)
        System.arraycopy(y, 0, raw, 33, 32)

        return Base64.getEncoder().encodeToString(raw)
    }

    fun importPublicKey(base64String: String): PublicKey {
        val rawKey = Base64.getDecoder().decode(base64String)
        require(rawKey.size == 65 && rawKey[0] == 0x04.toByte()) {
            "Invalid public key format: expected 65-byte uncompressed EC key"
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

    fun constructAAD(role: String, seqNum: Int): ByteArray {
        val aad = ByteArray(5)
        aad[0] = role[0].code.toByte()
        val buffer = java.nio.ByteBuffer.wrap(aad)
        buffer.position(1)
        buffer.putInt(seqNum)
        return aad
    }

    private fun hmacSha256(key: ByteArray, data: ByteArray): ByteArray {
        val mac = javax.crypto.Mac.getInstance("HmacSHA256")
        val keySpec = SecretKeySpec(key, "HmacSHA256")
        mac.init(keySpec)
        return mac.doFinal(data)
    }

    private fun hkdfDerive(ikm: ByteArray, info: ByteArray, salt: ByteArray): ByteArray {
        val prk = hmacSha256(salt, ikm)
        val infoWithCounter = ByteArray(info.size + 1)
        System.arraycopy(info, 0, infoWithCounter, 0, info.size)
        infoWithCounter[info.size] = 0x01.toByte()
        return hmacSha256(prk, infoWithCounter)
    }

    fun deriveSessionKeys(
        myPrivateKey: PrivateKey,
        theirPublicKey: PublicKey,
        myPubKeyBase64: String,
        theirPubKeyBase64: String
    ): SessionKeys {
        val keyAgreement = KeyAgreement.getInstance("ECDH")
        keyAgreement.init(myPrivateKey)
        keyAgreement.doPhase(theirPublicKey, true)
        val rawSecret = keyAgreement.generateSecret()
        
        val ikm = padOrTrim(rawSecret, 32)
        val salt = ByteArray(32) // 32 zero bytes
        
        val labelClient = "AnonyMus-Client-To-Server-Key".toByteArray(Charsets.UTF_8)
        val labelServer = "AnonyMus-Server-To-Client-Key".toByteArray(Charsets.UTF_8)
        
        val clientKeyBytes = hkdfDerive(ikm, labelClient, salt)
        val serverKeyBytes = hkdfDerive(ikm, labelServer, salt)
        
        val isAlice = myPubKeyBase64 < theirPubKeyBase64
        
        return if (isAlice) {
            SessionKeys(writeKey = clientKeyBytes, readKey = serverKeyBytes)
        } else {
            SessionKeys(writeKey = serverKeyBytes, readKey = clientKeyBytes)
        }
    }

    fun computeSafetyNumber(myPubKeyBase64: String, theirPubKeyBase64: String): String {
        val list = listOf(myPubKeyBase64, theirPubKeyBase64).sorted()
        val data = (list[0] + list[1]).toByteArray(Charsets.UTF_8)
        
        val digest = MessageDigest.getInstance("SHA-256")
        val hash = digest.digest(data)
        
        val hexString = hash.joinToString("") { byte -> 
            String.format("%02x", byte) 
        }
        
        return hexString.chunked(8).joinToString("-")
    }

    fun encryptMessage(keyBytes: ByteArray, plaintext: String, role: String, seqNum: Int): EncryptedPayload {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        val iv = ByteArray(12)
        SecureRandom().nextBytes(iv)
        val parameterSpec = GCMParameterSpec(128, iv)
        val key = SecretKeySpec(keyBytes, "AES")
        cipher.init(Cipher.ENCRYPT_MODE, key, parameterSpec)

        val aad = constructAAD(role, seqNum)
        cipher.updateAAD(aad)

        val textBytes = plaintext.toByteArray(Charsets.UTF_8)
        val textLen = textBytes.size
        val paddedLength = Math.ceil((textLen + 4).toDouble() / BLOCK_SIZE).toInt() * BLOCK_SIZE
        
        val buffer = java.nio.ByteBuffer.allocate(paddedLength)
        buffer.putInt(textLen)
        buffer.put(textBytes)
        
        if (paddedLength > textLen + 4) {
            val paddingBytes = ByteArray(paddedLength - textLen - 4)
            SecureRandom().nextBytes(paddingBytes)
            buffer.put(paddingBytes)
        }

        val ciphertext = cipher.doFinal(buffer.array())
        return EncryptedPayload(
            iv = Base64.getEncoder().encodeToString(iv),
            ciphertext = Base64.getEncoder().encodeToString(ciphertext)
        )
    }

    fun decryptMessage(keyBytes: ByteArray, ivBase64: String, ciphertextBase64: String, role: String, seqNum: Int): String? {
        return try {
            val iv = Base64.getDecoder().decode(ivBase64)
            val ciphertext = Base64.getDecoder().decode(ciphertextBase64)

            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            val parameterSpec = GCMParameterSpec(128, iv)
            val key = SecretKeySpec(keyBytes, "AES")
            cipher.init(Cipher.DECRYPT_MODE, key, parameterSpec)

            val aad = constructAAD(role, seqNum)
            cipher.updateAAD(aad)

            val decrypted = cipher.doFinal(ciphertext)
            val buffer = java.nio.ByteBuffer.wrap(decrypted)
            val textLen = buffer.getInt()
            
            if (textLen < 0 || textLen > decrypted.size - 4) {
                return null
            }
            
            val textBytes = ByteArray(textLen)
            buffer.get(textBytes)
            String(textBytes, Charsets.UTF_8)
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
