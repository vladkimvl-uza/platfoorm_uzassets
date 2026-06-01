"""Integration test for L5 — get_current_user via API-key path rejects inactive SA.

Pipeline:
  1) Create service account user, create API key.
  2) Hit a protected endpoint with `Bearer <token>` — should work (200/403 by perm).
  3) Deactivate the SA user.
  4) Hit again with same token — should be 401 (API key path returns this
     via verify_token raising sa_disabled, mapped to 401 by get_current_user).

Note: verify_token also enforces is_active inside the service. Our security.py
adds a defense-in-depth check post-verify. Both layers should reject.
"""
from datetime import UTC

import pytest

pytestmark = pytest.mark.integration


async def test_inactive_sa_token_rejected(db, make_user, app_client):
    """End-to-end: deactivated SA → 401 on protected endpoint."""
    import secrets as _secrets
    from datetime import datetime, timedelta

    from app.models.api_key import KEY_PREFIX_SANDBOX, ApiKey
    from app.services.api_key_service import _hmac_token

    sa = await make_user(
        email="sa@example.com", is_service_account=True, role_codes=[],
    )

    # Hand-build token so `rsplit('_', 1)` is unambiguous (avoid _ in body).
    # Production generate_token() uses token_urlsafe which can include '_' —
    # that's a separate bug, but not what L5 is testing.
    nonce = _secrets.token_hex(4)  # hex only, no underscores
    secret = _secrets.token_hex(20)
    prefix = f"{KEY_PREFIX_SANDBOX}{nonce}"
    plaintext = f"{prefix}_{secret}"
    hash_hmac = _hmac_token(plaintext)
    now = datetime.now(UTC)
    key = ApiKey(
        prefix=prefix,
        hash_hmac=hash_hmac,
        service_account_id=sa.id,
        name="test key",
        environment="sandbox",
        scopes=["kpi.view"],
        rate_limit_per_minute=100,
        created_by_id=sa.id,
        expires_at=now + timedelta(days=1),
        # ApiKey model lacks TimestampMixin / server_default; provide explicitly for tests.
        created_at=now,
        updated_at=now,
    )
    db.add(key)
    await db.commit()

    # While active — request should NOT be 401 (might be 200/403 depending on perm).
    r1 = await app_client.get(
        "/rbac/v3/users",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r1.status_code != 401, f"active SA should authenticate; got {r1.status_code}: {r1.text}"

    # Deactivate the SA
    sa.is_active = False
    await db.commit()

    r2 = await app_client.get(
        "/rbac/v3/users",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r2.status_code == 401, r2.text
    assert "disabled" in r2.text.lower() or "sa_disabled" in r2.text.lower()
