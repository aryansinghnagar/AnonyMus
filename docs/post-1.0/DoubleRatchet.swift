//
//  DoubleRatchet.swift
//  AnonyMus iOS Client
//
//  Swift-native implementation boilerplate for X25519 Double Ratchet E2EE
//  utilizing Apple's CryptoKit framework.
//

import Foundation
import CryptoKit

public enum RatchetError: Error {
    case invalidKeyLength
    case keyDerivationFailed
    case encryptionFailed
    case decryptionFailed
    case skippedMessageLimitExceeded
}

public class DoubleRatchetSession {
    private var dhPrivateKey: Curve25519.Signing.PrivateKey
    private var dhPublicKey: Curve25519.Signing.PublicKey
    private var dhRemotePublicKey: Curve25519.Signing.PublicKey?
    
    private var rootKey: Data
    private var sendingChainKey: Data?
    private var receivingChainKey: Data?
    
    private var seqSend = 0
    private var seqRecv = 0
    private var prevChainLength = 0
    
    // Keyed by "remoteDHPublicKeyBase64_sequenceNumber"
    private var skippedMessageKeys: [String: Data] = [:]
    
    public init(sharedSecret: Data) throws {
        self.dhPrivateKey = Curve25519.Signing.PrivateKey()
        self.dhPublicKey = self.dhPrivateKey.publicKey
        self.rootKey = sharedSecret
    }
    
    /// Initializes Alice's session with a shared DH secret and Bob's DH public key
    public static func initAlice(sharedSecret: Data, peerDhPubBytes: Data) throws -> DoubleRatchetSession {
        let session = try DoubleRatchetSession(sharedSecret: sharedSecret)
        let remoteKey = try Curve25519.Signing.PublicKey(rawRepresentation: peerDhPubBytes)
        session.dhRemotePublicKey = remoteKey
        
        // Root KDF: derive rootKey and sendingChainKey
        let dhOut = try session.computeDH(privateKey: session.dhPrivateKey, publicKey: remoteKey)
        let derived = try session.hkdfDerive512(ikm: dhOut, info: "AnonyMus-DR-RootRatchet".data(using: .utf8)!, salt: sharedSecret)
        
        session.rootKey = derived.subdata(in: 0..<32)
        session.sendingChainKey = derived.subdata(in: 32..<64)
        session.receivingChainKey = nil
        return session;
    }
    
    /// Encrypts an outgoing message, ratcheting the sending chain key
    public func encrypt(plaintext: String) throws -> (iv: Data, ciphertext: Data, dhPub: Data, seq: Int, prevChainLen: Int) {
        guard let chainKey = self.sendingChainKey else {
            throw RatchetError.keyDerivationFailed
        }
        
        // Derive message key and next chain key
        let derived = try hkdfDerive512(ikm: Data(repeating: 0, count: 32), info: "AnonyMus-DR-ChainRatchet".data(using: .utf8)!, salt: chainKey)
        let msgKey = derived.subdata(in: 0..<32)
        self.sendingChainKey = derived.subdata(in: 32..<64)
        
        // Encrypt message using AES-GCM
        let iv = SymmetricKey(data: Data(repeating: 0, count: 12)) // Note: Use secure random IV in production!
        let sealedBox = try AES.GCM.seal(plaintext.data(using: .utf8)!, using: SymmetricKey(data: msgKey), nonce: AES.GCM.Nonce(data: iv))
        
        let seq = self.seqSend
        self.seqSend += 1
        
        return (
            iv: Data(iv),
            ciphertext: sealedBox.ciphertext,
            dhPub: self.dhPublicKey.rawRepresentation,
            seq: seq,
            prevChainLen: self.prevChainLength
        )
    }
    
    // MARK: - Cryptographic Helpers
    
    private func computeDH(privateKey: Curve25519.Signing.PrivateKey, publicKey: Curve25519.Signing.PublicKey) throws -> Data {
        // Bridge representation or use native Curve25519 KeyAgreement keys
        fatalError("Implement Agreement Key casting for Curve25519")
    }
    
    private func hkdfDerive512(ikm: Data, info: Data, salt: Data) throws -> Data {
        let key = SymmetricKey(data: ikm)
        let derived = HKDF<SHA256>.deriveKey(
            inputKeyMaterial: key,
            salt: salt,
            info: info,
            outputByteCount: 64
        )
        return derived.withUnsafeBytes { Data($0) }
    }
}
