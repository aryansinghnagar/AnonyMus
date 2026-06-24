package com.anonymus.app

import com.anonymus.app.data.JceCryptoProvider
import com.anonymus.app.data.TinkCryptoProvider
import org.junit.Assert.*
import org.junit.Test

class CryptoProviderTest {

    @Test
    fun testJceCryptoParity() {
        val provider = JceCryptoProvider()
        
        // Key Generation
        val keyPairA = provider.generateKeyPair()
        val keyPairB = provider.generateKeyPair()
        
        val pubA = provider.exportPublicKey(keyPairA.public)
        val pubB = provider.exportPublicKey(keyPairB.public)
        
        // Safety numbers match
        val sn1 = provider.computeSafetyNumber(pubA, pubB)
        val sn2 = provider.computeSafetyNumber(pubB, pubA)
        assertEquals(sn1, sn2)
        
        // Session Key Derivation
        val sessionKeysA = provider.deriveSessionKeys(
            keyPairA.private,
            provider.importPublicKey(pubB),
            pubA,
            pubB
        )
        val sessionKeysB = provider.deriveSessionKeys(
            keyPairB.private,
            provider.importPublicKey(pubA),
            pubB,
            pubA
        )
        
        // Chain key derivation
        val chainA = provider.deriveChainKeys(sessionKeysA.writeKey)
        val chainB = provider.deriveChainKeys(sessionKeysB.readKey)
        
        // Encryption / Decryption
        val plaintext = "Hello World!"
        val enc = provider.encryptMessage(chainA.first, plaintext, "A", 0, sn1)
        val dec = provider.decryptMessage(chainB.first, enc.iv, enc.ciphertext, "A", 0, sn1)
        
        assertEquals(plaintext, dec)
    }

    @Test
    fun testTinkCryptoParity() {
        val provider = TinkCryptoProvider()
        
        // Key Generation
        val keyPairA = provider.generateKeyPair()
        val keyPairB = provider.generateKeyPair()
        
        val pubA = provider.exportPublicKey(keyPairA.public)
        val pubB = provider.exportPublicKey(keyPairB.public)
        
        // Safety numbers match
        val sn1 = provider.computeSafetyNumber(pubA, pubB)
        val sn2 = provider.computeSafetyNumber(pubB, pubA)
        assertEquals(sn1, sn2)
        
        // Session Key Derivation
        val sessionKeysA = provider.deriveSessionKeys(
            keyPairA.private,
            provider.importPublicKey(pubB),
            pubA,
            pubB
        )
        val sessionKeysB = provider.deriveSessionKeys(
            keyPairB.private,
            provider.importPublicKey(pubA),
            pubB,
            pubA
        )
        
        // Chain key derivation
        val chainA = provider.deriveChainKeys(sessionKeysA.writeKey)
        val chainB = provider.deriveChainKeys(sessionKeysB.readKey)
        
        // Encryption / Decryption
        val plaintext = "Hello World!"
        val enc = provider.encryptMessage(chainA.first, plaintext, "A", 0, sn1)
        val dec = provider.decryptMessage(chainB.first, enc.iv, enc.ciphertext, "A", 0, sn1)
        
        assertEquals(plaintext, dec)
    }
}
