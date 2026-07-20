"""
Capability Tiers Engine (L0–L3) — Hardware Adaptation System
============================================================
Dynamically categorizes system hardware into four distinct execution tiers:

  - L0 (Low-End / Constrained): RAM < 2GB or Cores <= 2.
  - L1 (Standard / Mid-Range): RAM 2GB–4GB or Cores 4.
  - L2 (High-Performance): RAM 4GB–16GB, Cores 8+.
  - L3 (Server / High-Throughput): RAM > 16GB, Cores 16+.

Provides runtime parameters for PBKDF2 iterations, memory pressure thresholds,
message batching sizes, and WASM memory limits.
"""

from __future__ import annotations

import os
from enum import Enum
from dataclasses import dataclass

try:
    import psutil
except ImportError:
    psutil = None


class CapabilityTierLevel(str, Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


@dataclass(frozen=True)
class CapabilityProfile:
    tier: CapabilityTierLevel
    ram_bytes: int
    cpu_cores: int
    pbkdf2_iterations: int
    max_in_memory_messages: int
    db_cache_size_kb: int
    enable_ui_animations: bool
    enable_background_prekeys: bool


# Pre-defined tier profiles according to anonymus_plan.md Section 6.C1
TIER_PROFILES: dict[CapabilityTierLevel, CapabilityProfile] = {
    CapabilityTierLevel.L0: CapabilityProfile(
        tier=CapabilityTierLevel.L0,
        ram_bytes=1 * 1024 * 1024 * 1024,
        cpu_cores=2,
        pbkdf2_iterations=100_000,
        max_in_memory_messages=50,
        db_cache_size_kb=2_000,
        enable_ui_animations=False,
        enable_background_prekeys=False,
    ),
    CapabilityTierLevel.L1: CapabilityProfile(
        tier=CapabilityTierLevel.L1,
        ram_bytes=4 * 1024 * 1024 * 1024,
        cpu_cores=4,
        pbkdf2_iterations=300_000,
        max_in_memory_messages=250,
        db_cache_size_kb=8_000,
        enable_ui_animations=True,
        enable_background_prekeys=True,
    ),
    CapabilityTierLevel.L2: CapabilityProfile(
        tier=CapabilityTierLevel.L2,
        ram_bytes=16 * 1024 * 1024 * 1024,
        cpu_cores=8,
        pbkdf2_iterations=600_000,
        max_in_memory_messages=1_000,
        db_cache_size_kb=32_000,
        enable_ui_animations=True,
        enable_background_prekeys=True,
    ),
    CapabilityTierLevel.L3: CapabilityProfile(
        tier=CapabilityTierLevel.L3,
        ram_bytes=64 * 1024 * 1024 * 1024,
        cpu_cores=16,
        pbkdf2_iterations=1_000_000,
        max_in_memory_messages=5_000,
        db_cache_size_kb=128_000,
        enable_ui_animations=True,
        enable_background_prekeys=True,
    ),
}


def detect_capability_tier() -> CapabilityProfile:
    """
    Inspects host hardware specifications (RAM, CPU core count) and returns
    the appropriate CapabilityProfile for runtime resource adaptation.
    """
    # Force override via environment variable if specified
    override = os.getenv("ANONYMUS_CAPABILITY_TIER", "").upper()
    if override in CapabilityTierLevel.__members__:
        return TIER_PROFILES[CapabilityTierLevel(override)]

    cpu_cores = os.cpu_count() or 2
    if psutil is not None:
        try:
            ram_bytes = psutil.virtual_memory().total
        except Exception:
            ram_bytes = 4 * 1024 * 1024 * 1024
    else:
        ram_bytes = 4 * 1024 * 1024 * 1024

    ram_gb = ram_bytes / (1024 * 1024 * 1024)

    if ram_gb < 2.0 or cpu_cores <= 2:
        tier = CapabilityTierLevel.L0
    elif ram_gb < 4.5 or cpu_cores <= 4:
        tier = CapabilityTierLevel.L1
    elif ram_gb < 16.5 or cpu_cores <= 8:
        tier = CapabilityTierLevel.L2
    else:
        tier = CapabilityTierLevel.L3

    return TIER_PROFILES[tier]
