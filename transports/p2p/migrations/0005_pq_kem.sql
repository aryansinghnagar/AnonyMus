-- Migration 0005: Add ML-KEM-768 public/private key columns to contacts
-- These are used when ANONYMUS_PQ_HYBRID=1 is set.
-- Columns are nullable — existing contacts without PQ keys fall back to X25519-only DR.

ALTER TABLE contacts ADD COLUMN peer_kem_public_key TEXT;    -- Base64-encoded 1184-byte ML-KEM-768 public key (from peer)
ALTER TABLE contacts ADD COLUMN my_kem_private_key  TEXT;    -- Base64-encoded 2400-byte ML-KEM-768 private key (ours)
