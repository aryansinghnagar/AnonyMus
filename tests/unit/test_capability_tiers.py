"""
Unit Tests for Capability Tiers Engine (L0–L3)
"""

from core.capability_tiers import detect_capability_tier, CapabilityTierLevel


def test_detect_capability_tier_default():
    """Verifies that capability tier detection runs without error and returns a valid profile."""
    profile = detect_capability_tier()
    assert profile.tier in (
        CapabilityTierLevel.L0,
        CapabilityTierLevel.L1,
        CapabilityTierLevel.L2,
        CapabilityTierLevel.L3,
    )
    assert profile.pbkdf2_iterations >= 100_000
    assert profile.db_cache_size_kb > 0


def test_detect_capability_tier_env_override(monkeypatch):
    """Verifies environment variable ANONYMUS_CAPABILITY_TIER override."""
    monkeypatch.setenv("ANONYMUS_CAPABILITY_TIER", "L0")
    profile_l0 = detect_capability_tier()
    assert profile_l0.tier == CapabilityTierLevel.L0
    assert profile_l0.pbkdf2_iterations == 100_000

    monkeypatch.setenv("ANONYMUS_CAPABILITY_TIER", "L3")
    profile_l3 = detect_capability_tier()
    assert profile_l3.tier == CapabilityTierLevel.L3
    assert profile_l3.pbkdf2_iterations == 1_000_000
