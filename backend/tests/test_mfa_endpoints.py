"""Integration tests for MFA-aware REST endpoints.

Covers /auth/login-mfa and /auth/verify-mfa.

Scenarios:
  * login-mfa, MFA disabled → returns TokenPair
  * login-mfa, MFA enabled + TG linked → returns challenge_id (no tokens)
  * login-mfa, MFA enabled BUT no TG → 500
  * verify-mfa via TG code happy path → TokenPair
  * verify-mfa wrong code → 401
  * verify-mfa via recovery code → TokenPair (and code is consumed)
  * verify-mfa wrong recovery → 401
  * verify-mfa empty body → 400
"""
import pytest


pytestmark = pytest.mark.integration


async def _set_mfa(db, user, *, method="telegram", chat_id=12345, username="alice"):
    """Enable MFA and link a fake TG chat for the test user."""
    from app.core.encryption import encrypt_int
    from app.models.user import User
    from sqlalchemy import update
    await db.execute(update(User).where(User.id == user.id).values(
        mfa_enabled=True,
        mfa_method=method,
        telegram_chat_id_encrypted=encrypt_int(chat_id),
        telegram_username=username,
    ))
    await db.commit()


async def test_login_mfa_without_mfa_returns_tokens(make_user, app_client):
    pwd = "Q9k!#mB7vN$wL2pR"
    await make_user(email="login-mfa-off@example.com", password=pwd)

    r = await app_client.post(
        "/auth/login-mfa",
        json={"login": "login-mfa-off@example.com", "password": pwd},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mfa_required"] is False
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_mfa_with_mfa_returns_challenge(db, make_user, app_client):
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="login-mfa-on@example.com", password=pwd)
    await _set_mfa(db, u)

    r = await app_client.post(
        "/auth/login-mfa",
        json={"login": "login-mfa-on@example.com", "password": pwd},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mfa_required"] is True
    assert body["challenge_id"]
    assert body["method"] in ("telegram", "totp", "both")
    # No tokens at challenge stage
    assert body.get("access_token") is None
    assert body.get("refresh_token") is None


async def test_login_mfa_enabled_but_no_tg_link_returns_500(db, make_user, app_client):
    """User has mfa_enabled=True but telegram_chat_id is NULL → 500."""
    from app.models.user import User
    from sqlalchemy import update
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="mfa-bad@example.com", password=pwd)
    await db.execute(update(User).where(User.id == u.id).values(
        mfa_enabled=True, mfa_method="telegram", telegram_chat_id_encrypted=None,
    ))
    await db.commit()

    r = await app_client.post(
        "/auth/login-mfa",
        json={"login": "mfa-bad@example.com", "password": pwd},
    )
    assert r.status_code == 500, r.text


async def test_verify_mfa_with_valid_code_returns_tokens(db, make_user, app_client):
    """Issue challenge manually (skip TG send), then verify."""
    from app.services.mfa_service import _hash_bcrypt, _gen_login_code
    from app.models.mfa import MfaLoginChallenge
    from datetime import datetime, timedelta, timezone

    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="verify-ok@example.com", password=pwd)
    await _set_mfa(db, u)

    code = _gen_login_code()
    now = datetime.now(timezone.utc)
    ch = MfaLoginChallenge(
        user_id=u.id, code_hashed=_hash_bcrypt(code),
        created_at=now, expires_at=now + timedelta(minutes=5),
    )
    db.add(ch)
    await db.commit()
    await db.refresh(ch)

    r = await app_client.post(
        "/auth/verify-mfa",
        json={"challenge_id": str(ch.id), "code": code},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "Bearer"


async def test_verify_mfa_wrong_code_returns_401(db, make_user, app_client):
    from app.services.mfa_service import _hash_bcrypt, _gen_login_code
    from app.models.mfa import MfaLoginChallenge
    from datetime import datetime, timedelta, timezone

    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="verify-bad@example.com", password=pwd)
    await _set_mfa(db, u)

    real_code = _gen_login_code()
    now = datetime.now(timezone.utc)
    ch = MfaLoginChallenge(
        user_id=u.id, code_hashed=_hash_bcrypt(real_code),
        created_at=now, expires_at=now + timedelta(minutes=5),
    )
    db.add(ch)
    await db.commit()
    await db.refresh(ch)

    r = await app_client.post(
        "/auth/verify-mfa",
        json={"challenge_id": str(ch.id), "code": "000000"},
    )
    assert r.status_code == 401, r.text


async def test_verify_mfa_via_recovery_code(db, make_user, app_client):
    """Path B: login + recovery_code."""
    from app.services.mfa_service import generate_recovery_codes, _hash_bcrypt
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="recov-endpoint@example.com", password=pwd)
    await _set_mfa(db, u)

    codes = generate_recovery_codes()
    u.mfa_recovery_codes_hashed = [_hash_bcrypt(c) for c in codes]
    await db.commit()
    await db.refresh(u)

    r = await app_client.post(
        "/auth/verify-mfa",
        json={"login": "recov-endpoint@example.com", "recovery_code": codes[0]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


async def test_verify_mfa_wrong_recovery_returns_401(db, make_user, app_client):
    from app.services.mfa_service import generate_recovery_codes, _hash_bcrypt
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="recov-bad@example.com", password=pwd)
    await _set_mfa(db, u)
    codes = generate_recovery_codes()
    u.mfa_recovery_codes_hashed = [_hash_bcrypt(c) for c in codes]
    await db.commit()

    r = await app_client.post(
        "/auth/verify-mfa",
        json={"login": "recov-bad@example.com", "recovery_code": "FFFF-FFFF"},
    )
    assert r.status_code == 401, r.text


async def test_verify_mfa_recovery_for_user_without_mfa_returns_401(make_user, app_client):
    """Plain user (no MFA enabled) trying recovery path → 401, not bypass."""
    pwd = "Q9k!#mB7vN$wL2pR"
    await make_user(email="no-mfa@example.com", password=pwd)
    r = await app_client.post(
        "/auth/verify-mfa",
        json={"login": "no-mfa@example.com", "recovery_code": "1234-5678"},
    )
    assert r.status_code == 401, r.text


async def test_verify_mfa_empty_body_returns_400(app_client):
    r = await app_client.post("/auth/verify-mfa", json={})
    assert r.status_code == 400, r.text


async def test_verify_mfa_unknown_challenge_id_returns_401(app_client):
    import uuid as _uuid
    r = await app_client.post(
        "/auth/verify-mfa",
        json={"challenge_id": str(_uuid.uuid4()), "code": "123456"},
    )
    assert r.status_code == 401, r.text


async def test_verify_mfa_recovery_consumes_the_code(db, make_user, app_client):
    """After successful recovery login, the same code can't be reused."""
    from app.services.mfa_service import generate_recovery_codes, _hash_bcrypt
    from app.models.user import User
    from sqlalchemy import select
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="recov-once@example.com", password=pwd)
    await _set_mfa(db, u)
    codes = generate_recovery_codes()
    u.mfa_recovery_codes_hashed = [_hash_bcrypt(c) for c in codes]
    await db.commit()

    # First use — success
    r1 = await app_client.post(
        "/auth/verify-mfa",
        json={"login": "recov-once@example.com", "recovery_code": codes[0]},
    )
    assert r1.status_code == 200

    # Re-fetch user from DB to confirm one hash is gone
    refreshed = (await db.execute(
        select(User).where(User.id == u.id)
    )).scalar_one()
    await db.refresh(refreshed)
    assert len(refreshed.mfa_recovery_codes_hashed) == 9

    # Second use of the same code — 401
    r2 = await app_client.post(
        "/auth/verify-mfa",
        json={"login": "recov-once@example.com", "recovery_code": codes[0]},
    )
    assert r2.status_code == 401, r2.text
