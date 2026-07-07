-- Add display_name and dr_state columns for E2EE Double Ratchet and Incognito Mode
ALTER TABLE contacts ADD COLUMN display_name TEXT;
ALTER TABLE contacts ADD COLUMN dr_state TEXT;
