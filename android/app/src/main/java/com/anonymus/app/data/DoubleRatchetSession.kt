package com.anonymus.app.data

import android.util.Log
import org.json.JSONObject
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.SecureRandom
import java.security.spec.AlgorithmParameterSpec
import javax.crypto.KeyAgreement
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Double Ratchet session state for a single P2P contact.
 *
 * Mirrors the Python [core/double_ratchet.py] and JavaScript [crypto.js]
 * implementations exactly so all three platforms interoperate.
 *
 * Key exchange: X25519
 * Root/chain KDF: HKDF-SHA256
 * Message encryption key: 32-byte output of chain KDF (used by CryptoUtils.encryptMessageV2)
 * State persistence: [serialize] / [fromJson]
 */
class DoubleRatchetSession private constructor() {

    // Current DH ratchet key pair (our side)
    var dhPrivateKeyBytes: ByteArray? = null
    var dhPublicKeyBytes: ByteArray? = null

    // Remote DH public key (their current ratchet key)
    var dhRemotePublicKeyBytes: ByteArray? = null

    // Symmetric ratchet keys
    var rootKey: ByteArray? = null
    var sendingChainKey: ByteArray? = null
    var receivingChainKey: ByteArray? = null

    var seqSend: Int = 0
    var seqRecv: Int = 0
    var prevChainLength: Int = 0

    // Skipped message keys: key = "peerPubBase64_seq", value = messageKeyHex
    val skippedMessageKeys: MutableMap<String, String> = mutableMapOf()

    // -----------------------------------------------------------------------
    // Static factory methods
    // -----------------------------------------------------------------------

    companion object {
        private const val TAG = "DoubleRatchetSession"
        private const val MAX_SKIP = 100

        /**
         * Alice role: we sent the original handshake.
         * @param sharedSecret 32-byte X25519 shared secret
         * @param peerDhPubBytes peer's 32-byte X25519 public key
         */
        fun initAlice(sharedSecret: ByteArray, peerDhPubBytes: ByteArray): DoubleRatchetSession {
            val session = DoubleRatchetSession()
            val kp = generateX25519KeyPair()
            session.dhPrivateKeyBytes = kp.private.encoded // raw 32 bytes via BC
            session.dhPublicKeyBytes = exportX25519PublicRaw(kp)
            session.dhRemotePublicKeyBytes = peerDhPubBytes

            val dhOut = x25519Dh(session.dhPrivateKeyBytes!!, peerDhPubBytes)
            val derived = hkdfDerive512(
                ikm = dhOut,
                info = "AnonyMus-DR-RootRatchet".toByteArray(),
                salt = sharedSecret
            )
            session.rootKey = derived.copyOfRange(0, 32)
            session.sendingChainKey = derived.copyOfRange(32, 64)
            session.receivingChainKey = null
            return session
        }

        /**
         * Bob role: we received the original handshake.
         * @param sharedSecret 32-byte X25519 shared secret
         * @param myDhPrivBytes our 32-byte raw X25519 private key
         */
        fun initBob(sharedSecret: ByteArray, myDhPrivBytes: ByteArray): DoubleRatchetSession {
            val session = DoubleRatchetSession()
            session.dhPrivateKeyBytes = myDhPrivBytes
            session.dhPublicKeyBytes = deriveX25519PublicFromPrivate(myDhPrivBytes)
            session.dhRemotePublicKeyBytes = null
            session.rootKey = sharedSecret
            session.sendingChainKey = null
            session.receivingChainKey = null
            return session
        }

        fun fromJson(json: String): DoubleRatchetSession {
            val obj = JSONObject(json)
            val session = DoubleRatchetSession()
            session.dhPrivateKeyBytes = if (obj.has("dhPriv") && !obj.isNull("dhPriv"))
                android.util.Base64.decode(obj.getString("dhPriv"), android.util.Base64.NO_WRAP) else null
            session.dhPublicKeyBytes = if (obj.has("dhPub") && !obj.isNull("dhPub"))
                android.util.Base64.decode(obj.getString("dhPub"), android.util.Base64.NO_WRAP) else null
            session.dhRemotePublicKeyBytes = if (obj.has("dhRem") && !obj.isNull("dhRem"))
                android.util.Base64.decode(obj.getString("dhRem"), android.util.Base64.NO_WRAP) else null
            session.rootKey = if (obj.has("rk") && !obj.isNull("rk"))
                fromHex(obj.getString("rk")) else null
            session.sendingChainKey = if (obj.has("sck") && !obj.isNull("sck"))
                fromHex(obj.getString("sck")) else null
            session.receivingChainKey = if (obj.has("rck") && !obj.isNull("rck"))
                fromHex(obj.getString("rck")) else null
            session.seqSend = obj.optInt("ss", 0)
            session.seqRecv = obj.optInt("sr", 0)
            session.prevChainLength = obj.optInt("pn", 0)
            val skipped = obj.optJSONObject("sk")
            if (skipped != null) {
                val keys = skipped.keys()
                while (keys.hasNext()) {
                    val k = keys.next()
                    session.skippedMessageKeys[k] = skipped.getString(k)
                }
            }
            return session
        }

        // -----------------------------------------------------------------------
        // X25519 helpers using Android's Conscrypt / BouncyCastle provider
        // -----------------------------------------------------------------------

        fun generateX25519KeyPair(): KeyPair {
            val kpg = KeyPairGenerator.getInstance("XDH")
            kpg.initialize(javax.crypto.spec.DHParameterSpec(
                java.math.BigInteger.ONE, java.math.BigInteger.ONE
            ).let {
                // Use named-curve spec for X25519
                java.security.spec.NamedParameterSpec.X25519
            })
            return kpg.generateKeyPair()
        }

        fun exportX25519PublicRaw(kp: KeyPair): ByteArray {
            // JDK 11+: XECPublicKey exposes u coordinate
            val pub = kp.public
            val encoded = pub.encoded // SubjectPublicKeyInfo DER
            // Raw X25519 public key is the last 32 bytes of the DER encoding
            return encoded.copyOfRange(encoded.size - 32, encoded.size)
        }

        fun exportX25519PrivateRaw(kp: KeyPair): ByteArray {
            val priv = kp.private
            val encoded = priv.encoded // PKCS8 DER
            // Raw X25519 private key is the last 32 bytes of the PKCS8 encoding
            return encoded.copyOfRange(encoded.size - 32, encoded.size)
        }

        fun importX25519PublicFromRaw(rawBytes: ByteArray): java.security.PublicKey {
            val kf = KeyFactory.getInstance("XDH")
            // Wrap in SubjectPublicKeyInfo: 12-byte header for X25519 + 32 bytes key
            val header = byteArrayOf(
                0x30, 0x2a,       // SEQUENCE
                0x30, 0x05,       // SEQUENCE (AlgorithmIdentifier)
                0x06, 0x03,       // OID
                0x2b, 0x65, 0x6e, // 1.3.101.110 (id-X25519)
                0x03, 0x21, 0x00  // BIT STRING, 33 bytes, 0 unused bits
            )
            val spki = header + rawBytes
            val keySpec = java.security.spec.X509EncodedKeySpec(spki)
            return kf.generatePublic(keySpec)
        }

        fun importX25519PrivateFromRaw(rawBytes: ByteArray): java.security.PrivateKey {
            val kf = KeyFactory.getInstance("XDH")
            // Wrap in PKCS8: header for X25519 + octet string wrapping
            val header = byteArrayOf(
                0x30, 0x2e,       // SEQUENCE
                0x02, 0x01, 0x00, // INTEGER version = 0
                0x30, 0x05,       // SEQUENCE AlgorithmIdentifier
                0x06, 0x03,       // OID
                0x2b, 0x65, 0x6e, // 1.3.101.110 (id-X25519)
                0x04, 0x22,       // OCTET STRING
                0x04, 0x20        // OCTET STRING (inner, 32 bytes)
            )
            val pkcs8 = header + rawBytes
            val keySpec = java.security.spec.PKCS8EncodedKeySpec(pkcs8)
            return kf.generatePrivate(keySpec)
        }

        fun deriveX25519PublicFromPrivate(rawPriv: ByteArray): ByteArray {
            val privKey = importX25519PrivateFromRaw(rawPriv)
            // Re-encode private key to PKCS8 and derive public from it
            val kf = KeyFactory.getInstance("XDH")
            val pubKeySpec = kf.getKeySpec(privKey, java.security.spec.XECPublicKeySpec::class.java)
            val pub = kf.generatePublic(pubKeySpec as java.security.spec.KeySpec)
            val encoded = pub.encoded
            return encoded.copyOfRange(encoded.size - 32, encoded.size)
        }

        fun x25519Dh(myPrivRaw: ByteArray, theirPubRaw: ByteArray): ByteArray {
            val myPriv = importX25519PrivateFromRaw(myPrivRaw)
            val theirPub = importX25519PublicFromRaw(theirPubRaw)
            val ka = KeyAgreement.getInstance("XDH")
            ka.init(myPriv)
            ka.doPhase(theirPub, true)
            return ka.generateSecret()
        }

        // -----------------------------------------------------------------------
        // HKDF-SHA256 — derive 64 bytes (512 bits)
        // -----------------------------------------------------------------------

        fun hkdfDerive256(ikm: ByteArray, info: ByteArray, salt: ByteArray = ByteArray(32)): ByteArray {
            val prk = hmacSha256(salt, ikm)
            val t1Input = info + byteArrayOf(0x01)
            return hmacSha256(prk, t1Input)
        }

        fun hkdfDerive512(ikm: ByteArray, info: ByteArray, salt: ByteArray = ByteArray(32)): ByteArray {
            // Extract: PRK = HMAC-SHA256(salt, ikm)
            val prk = hmacSha256(salt, ikm)
            // Expand T(1) = HMAC-SHA256(PRK, info || 0x01) — 32 bytes
            val t1Input = info + byteArrayOf(0x01)
            val t1 = hmacSha256(prk, t1Input)
            // Expand T(2) = HMAC-SHA256(PRK, T(1) || info || 0x02) — next 32 bytes
            val t2Input = t1 + info + byteArrayOf(0x02)
            val t2 = hmacSha256(prk, t2Input)
            return t1 + t2
        }

        fun hmacSha256(key: ByteArray, data: ByteArray): ByteArray {
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(key, "HmacSHA256"))
            return mac.doFinal(data)
        }

        fun toHex(bytes: ByteArray): String =
            bytes.joinToString("") { "%02x".format(it) }

        fun fromHex(hex: String): ByteArray {
            val len = hex.length
            val data = ByteArray(len / 2)
            for (i in 0 until len step 2) {
                data[i / 2] = ((Character.digit(hex[i], 16) shl 4) +
                        Character.digit(hex[i + 1], 16)).toByte()
            }
            return data
        }
    }

    // -----------------------------------------------------------------------
    // Encrypt step
    // -----------------------------------------------------------------------

    /**
     * Advances the sending chain one step.
     * @return Triple(messageKey, myDhPublicBytes, seqNum, prevChainLength)
     */
    fun encrypt(): EncryptStep {
        val derived = hkdfDerive512(
            ikm = ByteArray(32),
            info = "AnonyMus-DR-ChainRatchet".toByteArray(),
            salt = sendingChainKey!!
        )
        val messageKey = derived.copyOfRange(0, 32)
        sendingChainKey = derived.copyOfRange(32, 64)
        val seq = seqSend
        seqSend++
        return EncryptStep(messageKey, dhPublicKeyBytes!!, seq, prevChainLength)
    }

    data class EncryptStep(
        val messageKey: ByteArray,
        val myDhPublicBytes: ByteArray,
        val seq: Int,
        val prevChainLen: Int
    )

    // -----------------------------------------------------------------------
    // Decrypt step
    // -----------------------------------------------------------------------

    /**
     * Advances the receiving chain one step, performing a DH ratchet step
     * if the peer's DH key has changed.
     */
    fun decrypt(peerDhPubBytes: ByteArray, seq: Int, prevChainLen: Int): ByteArray {
        val peerB64 = android.util.Base64.encodeToString(peerDhPubBytes, android.util.Base64.NO_WRAP)
        val skipKey = "${peerB64}_$seq"

        // Check skipped message keys first
        skippedMessageKeys[skipKey]?.let {
            skippedMessageKeys.remove(skipKey)
            return fromHex(it)
        }

        val currentRemote = dhRemotePublicKeyBytes
        val dhChanged = currentRemote == null || !currentRemote.contentEquals(peerDhPubBytes)

        if (dhChanged) {
            skipMessages(prevChainLen)

            dhRemotePublicKeyBytes = peerDhPubBytes
            val dhOut1 = x25519Dh(dhPrivateKeyBytes!!, peerDhPubBytes)
            val derived1 = hkdfDerive512(
                ikm = dhOut1,
                info = "AnonyMus-DR-RootRatchet".toByteArray(),
                salt = rootKey!!
            )
            rootKey = derived1.copyOfRange(0, 32)
            receivingChainKey = derived1.copyOfRange(32, 64)

            // Generate new DH ratchet key pair
            val kp = generateX25519KeyPair()
            dhPrivateKeyBytes = exportX25519PrivateRaw(kp)
            dhPublicKeyBytes = exportX25519PublicRaw(kp)

            val dhOut2 = x25519Dh(dhPrivateKeyBytes!!, peerDhPubBytes)
            val derived2 = hkdfDerive512(
                ikm = dhOut2,
                info = "AnonyMus-DR-RootRatchet".toByteArray(),
                salt = rootKey!!
            )
            rootKey = derived2.copyOfRange(0, 32)
            sendingChainKey = derived2.copyOfRange(32, 64)

            prevChainLength = seqSend
            seqSend = 0
            seqRecv = 0
        }

        skipMessages(seq)

        val derived = hkdfDerive512(
            ikm = ByteArray(32),
            info = "AnonyMus-DR-ChainRatchet".toByteArray(),
            salt = receivingChainKey!!
        )
        val messageKey = derived.copyOfRange(0, 32)
        receivingChainKey = derived.copyOfRange(32, 64)
        seqRecv++
        return messageKey
    }

    private fun skipMessages(untilSeq: Int) {
        val rck = receivingChainKey ?: return
        if (seqRecv + MAX_SKIP < untilSeq) {
            throw IllegalStateException("Too many skipped messages ($untilSeq - $seqRecv > $MAX_SKIP)")
        }
        var currentChain = rck
        while (seqRecv < untilSeq) {
            val derived = hkdfDerive512(
                ikm = ByteArray(32),
                info = "AnonyMus-DR-ChainRatchet".toByteArray(),
                salt = currentChain
            )
            val msgKey = derived.copyOfRange(0, 32)
            currentChain = derived.copyOfRange(32, 64)
            val peerB64 = android.util.Base64.encodeToString(dhRemotePublicKeyBytes!!, android.util.Base64.NO_WRAP)
            skippedMessageKeys["${peerB64}_$seqRecv"] = toHex(msgKey)
            seqRecv++
        }
        receivingChainKey = currentChain
    }

    // -----------------------------------------------------------------------
    // Serialization
    // -----------------------------------------------------------------------

    fun serialize(): String {
        val obj = JSONObject()
        obj.put("dhPriv", dhPrivateKeyBytes?.let {
            android.util.Base64.encodeToString(it, android.util.Base64.NO_WRAP)
        })
        obj.put("dhPub", dhPublicKeyBytes?.let {
            android.util.Base64.encodeToString(it, android.util.Base64.NO_WRAP)
        })
        obj.put("dhRem", dhRemotePublicKeyBytes?.let {
            android.util.Base64.encodeToString(it, android.util.Base64.NO_WRAP)
        })
        obj.put("rk", rootKey?.let { toHex(it) })
        obj.put("sck", sendingChainKey?.let { toHex(it) })
        obj.put("rck", receivingChainKey?.let { toHex(it) })
        obj.put("ss", seqSend)
        obj.put("sr", seqRecv)
        obj.put("pn", prevChainLength)
        val skipped = JSONObject()
        skippedMessageKeys.forEach { (k, v) -> skipped.put(k, v) }
        obj.put("sk", skipped)
        return obj.toString()
    }
}
