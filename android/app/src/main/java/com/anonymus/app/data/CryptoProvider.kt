package com.anonymus.app.data

import java.security.KeyPair
import java.security.PrivateKey
import java.security.PublicKey

interface CryptoProvider {
    fun generateKeyPair(): KeyPair
    fun exportPublicKey(publicKey: PublicKey): String
    fun importPublicKey(base64String: String): PublicKey
    fun deriveSessionKeys(
        myPrivateKey: PrivateKey,
        theirPublicKey: PublicKey,
        myPubKeyBase64: String,
        theirPubKeyBase64: String
    ): SessionKeys
    fun computeSafetyNumber(myPubKeyBase64: String, theirPubKeyBase64: String): String
    fun encryptMessage(keyBytes: ByteArray, plaintext: String, role: String, seqNum: Int, sessionId: String?): EncryptedPayload
    fun decryptMessage(keyBytes: ByteArray, ivBase64: String, ciphertextBase64: String, role: String, seqNum: Int, sessionId: String?): String?
    fun deriveChainKeys(rootKey: ByteArray): Pair<ByteArray, ByteArray>
}
