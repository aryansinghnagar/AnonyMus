"""
Marker for legacy tests that require the full Flask/cryptography stack.

Add `@pytest.mark.legacy` to any test that imports Flask-era modules.
Run with: pytest -m "not legacy" to skip them in a lightweight v3 environment.
"""
