"""
Unit Tests for MLS RFC 9420 Group Engine (core/mls_groups.py)
"""

import pytest
import base64
from core.mls_groups import MLSGroupContext, MLSKeyPackage


def test_mls_group_creation_and_membership():
    group = MLSGroupContext(group_id="test-group-1", creator_id="alice.onion")
    assert group.epoch == 0
    assert group.members == ["alice.onion"]
    assert len(group.app_secret) == 32


def test_mls_add_member_epoch_advance():
    group = MLSGroupContext(group_id="test-group-2", creator_id="alice.onion")
    bob_pkg = MLSKeyPackage(
        client_id="bob.onion",
        public_key_b64=base64.b64encode(b"bob_pub_key_32bytes").decode("utf-8"),
    )

    commit = group.add_member(bob_pkg)
    assert group.epoch == 1
    assert "bob.onion" in group.members
    assert commit["epoch"] == 1
    assert commit["added_client_id"] == "bob.onion"


def test_mls_group_message_encryption_roundtrip():
    group = MLSGroupContext(group_id="test-group-3", creator_id="alice.onion")
    plaintext = "Confidential Group Announcement"

    encrypted_payload = group.encrypt_group_message(plaintext)
    assert encrypted_payload != plaintext

    decrypted = group.decrypt_group_message(encrypted_payload)
    assert decrypted == plaintext


def test_mls_epoch_mismatch_rejection():
    group = MLSGroupContext(group_id="test-group-4", creator_id="alice.onion")
    payload = group.encrypt_group_message("Epoch 0 Message")

    # Advance epoch manually
    bob_pkg = MLSKeyPackage(
        client_id="bob.onion",
        public_key_b64=base64.b64encode(b"bob_pub_key_32bytes").decode("utf-8"),
    )
    group.add_member(bob_pkg)

    with pytest.raises(ValueError, match="Epoch mismatch"):
        group.decrypt_group_message(payload)
