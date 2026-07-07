import os
import base64
import nacl.public

class QueueCryptobox:
    @staticmethod
    def encrypt(plaintext: bytes, sender_private_key_bytes: bytes, recipient_public_key_bytes: bytes) -> tuple:
        """
        Encrypts plaintext bytes using NaCl public key Box.
        
        Returns:
            (ciphertext: bytes, nonce: bytes)
        """
        priv_key = nacl.public.PrivateKey(sender_private_key_bytes)
        pub_key = nacl.public.PublicKey(recipient_public_key_bytes)
        box = nacl.public.Box(priv_key, pub_key)
        
        nonce = os.urandom(24)
        # PyNaCl box.encrypt prepends the 24-byte nonce to the ciphertext.
        combined = box.encrypt(plaintext, nonce)
        ciphertext = combined[24:]
        return ciphertext, nonce

    @staticmethod
    def decrypt(ciphertext: bytes, nonce: bytes, sender_public_key_bytes: bytes, recipient_private_key_bytes: bytes) -> bytes:
        """
        Decrypts ciphertext bytes using NaCl public key Box.
        """
        priv_key = nacl.public.PrivateKey(recipient_private_key_bytes)
        pub_key = nacl.public.PublicKey(sender_public_key_bytes)
        box = nacl.public.Box(priv_key, pub_key)
        
        combined = nonce + ciphertext
        return box.decrypt(combined)
