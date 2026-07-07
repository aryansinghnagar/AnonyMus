-- Migration: Add my_onion_address to contacts for pairwise pseudonyms
ALTER TABLE contacts ADD COLUMN my_onion_address TEXT;
