"""Tests for MFA service.

Unit (no DB): code/token/recovery-code generators + their format invariants.
Integration: emit/verify login challenge, recovery-code consume, link token.
"""
import re
import pytest


# ─────────────────────────────────────────────────────────────────
# Unit
# ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_gen_login_code_is_6_digits():
    from app.services.mfa_service import _gen_login_code
    for _ in range(200):
        c = _gen_login_code()
        assert isinstance(c, str) and len(c) == 6 and c.isdigit()


@pytest.mark.unit
def test_gen_login_code_preserves_leading_zeros():
    """Across many samples some should start with '0' — proves leading-zero pad."""
    from app.services.mfa_service import _gen_login_code
    samples = [_gen_login_code() for _ in range(2000)]
    assert any(s.startswith("0") for s in samples)


@pytest.mark.unit
def test_gen_recovery_code_format():
    from app.services.mfa_service import _gen_recovery_code
    pat = re.compile(r"^[0-9A-F]{4}-[0-9A-F]{4}$")
    for _ in range(50):
        c = _gen_recovery_code()
        assert pat.match(c), c


@pytest.mark.unit
def test_generate_recovery_codes_count_and_uniqueness():
    from app.services.mfa_service import generate_recovery_codes, RECOVERY_CODES_COUNT
    codes = generate_recovery_codes()
    assert len(codes) == RECOVERY_CODES_COUNT
    assert len(set(codes)) == RECOVERY_CODES_COUNT  # all unique (very high prob)


@pytest.mark.unit
def test_gen_link_token_format():
    from app.services.mfa_service import _gen_link_token
    pat = re.compile(r"^[A-Z0-9XY]{12}$")  # 12 chars, uppercase alnum + XY substitutes
    for _ in range(50):
        t = _gen_link_token()
        assert pat.match(t), t
        # Underscore and dash specifically replaced
        assert "_" not in t and "-" not in t


@pytest.mark.unit
def test_check_bcrypt_handles_malformed_hash():
    """Same defense as core.password.verify_password — bcrypt 4.x panics."""
    from app.services.mfa_service import _check_bcrypt
    assert _check_bcrypt("anything", "not-a-bcrypt") is False
    assert _check_bcrypt("", "") is False


# ─────────────────────────────────────────────────────────────────
# Integration
# ─────────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_verify_recovery_code_consumes_one(db, make_user):
    """Recovery code is single-use: after verify, that hash is gone."""
    from app.services.mfa_service import (
        generate_recovery_codes,
        verify_recovery_code,
        _hash_bcrypt,
    )

    codes = generate_recovery_codes()
    hashes = [_hash_bcrypt(c) for c in codes]
    u = await make_user(email="recov@example.com")
    u.mfa_recovery_codes_hashed = list(hashes)
    await db.commit()
    await db.refresh(u)

    assert len(u.mfa_recovery_codes_hashed) == 10

    # Consume one
    ok = await verify_recovery_code(db, u, codes[0])
    assert ok is True
    await db.refresh(u)
    assert len(u.mfa_recovery_codes_hashed) == 9

    # Reusing the same code → False (it was removed)
    ok2 = await verify_recovery_code(db, u, codes[0])
    assert ok2 is False
    await db.refresh(u)
    assert len(u.mfa_recovery_codes_hashed) == 9


@pytest.mark.integration
async def test_verify_recovery_code_wrong_code(db, make_user):
    from app.services.mfa_service import (
        generate_recovery_codes, _hash_bcrypt, verify_recovery_code,
    )
    codes = generate_recovery_codes()
    u = await make_user(email="recov2@example.com")
    u.mfa_recovery_codes_hashed = [_hash_bcrypt(c) for c in codes]
    await db.commit()
    await db.refresh(u)

    ok = await verify_recovery_code(db, u, "FFFF-FFFF")  # not in list
    assert ok is False
    await db.refresh(u)
    assert len(u.mfa_recovery_codes_hashed) == 10  # untouched


@pytest.mark.integration
async def test_verify_recovery_code_case_insensitive(db, make_user):
    """Code is normalised .upper() on input."""
    from app.services.mfa_service import (
        generate_recovery_codes, _hash_bcrypt, verify_recovery_code,
    )
    codes = generate_recovery_codes()
    u = await make_user(email="recov3@example.com")
    u.mfa_recovery_codes_hashed = [_hash_bcrypt(c) for c in codes]
    await db.commit()
    await db.refresh(u)

    ok = await verify_recovery_code(db, u, codes[0].lower())
    assert ok is True


@pytest.mark.integration
async def test_verify_login_challenge_happy_path(db, make_user):
    """Issue + verify a TG challenge. Use the plaintext returned by emit."""
    from app.services.mfa_service import verify_login_challenge
    from app.services.mfa_service import _hash_bcrypt, _gen_login_code
    from app.models.mfa import MfaLoginChallenge
    from datetime import datetime, timedelta, timezone

    u = await make_user(email="tg-ch@example.com")
    # Hand-construct a challenge so we don't need a real telegram_chat_id
    code = _gen_login_code()
    now = datetime.now(timezone.utc)
    ch = MfaLoginChallenge(
        user_id=u.id,
        code_hashed=_hash_bcrypt(code),
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    db.add(ch)
    await db.commit()
    await db.refresh(ch)

    # Wrong code first
    bad = await verify_login_challenge(db, str(ch.id), "000000")
    assert bad is False

    # Correct code
    ok = await verify_login_challenge(db, str(ch.id), code)
    assert ok is True

    # Replay — same code, but used_at is now set → False
    replay = await verify_login_challenge(db, str(ch.id), code)
    assert replay is False


@pytest.mark.integration
async def test_verify_login_challenge_after_max_attempts(db, make_user):
    """5 wrong attempts → 6th returns False even if code is correct."""
    from app.services.mfa_service import (
        verify_login_challenge, _hash_bcrypt, _gen_login_code,
        LOGIN_CODE_MAX_ATTEMPTS,
    )
    from app.models.mfa import MfaLoginChallenge
    from datetime import datetime, timedelta, timezone

    u = await make_user(email="tg-max@example.com")
    code = _gen_login_code()
    now = datetime.now(timezone.utc)
    ch = MfaLoginChallenge(
        user_id=u.id, code_hashed=_hash_bcrypt(code),
        created_at=now, expires_at=now + timedelta(minutes=5),
    )
    db.add(ch)
    await db.commit()

    # Exhaust attempts with wrong codes
    for _ in range(LOGIN_CODE_MAX_ATTEMPTS):
        await verify_login_challenge(db, str(ch.id), "999999")

    # Even correct code now → False
    blocked = await verify_login_challenge(db, str(ch.id), code)
    assert blocked is False


@pytest.mark.integration
async def test_verify_login_challenge_expired_code(db, make_user):
    """Challenge with expires_at in the past → False."""
    from app.services.mfa_service import (
        verify_login_challenge, _hash_bcrypt, _gen_login_code,
    )
    from app.models.mfa import MfaLoginChallenge
    from datetime import datetime, timedelta, timezone

    u = await make_user(email="tg-exp@example.com")
    code = _gen_login_code()
    now = datetime.now(timezone.utc)
    ch = MfaLoginChallenge(
        user_id=u.id, code_hashed=_hash_bcrypt(code),
        created_at=now - timedelta(minutes=10),
        expires_at=now - timedelta(minutes=5),  # expired
    )
    db.add(ch)
    await db.commit()

    res = await verify_login_challenge(db, str(ch.id), code)
    assert res is False


@pytest.mark.integration
async def test_link_telegram_token_lifecycle(db, make_user):
    """init_link_telegram → confirm_link_telegram → user is linked."""
    from app.services.mfa_service import (
        init_link_telegram, confirm_link_telegram, _hash_sha256,
    )

    u = await make_user(email="link-tg@example.com")
    token, expires = await init_link_telegram(db, u)
    await db.commit()

    assert token and len(token) == 12
    await db.refresh(u)
    assert u.telegram_link_token_hashed == _hash_sha256(token)
    assert u.telegram_link_token_expires_at == expires

    linked = await confirm_link_telegram(db, token, chat_id=12345, username="alice")
    await db.commit()
    assert linked is not None
    assert linked.id == u.id

    await db.refresh(u)
    # Token cleared, chat encrypted, username set
    assert u.telegram_link_token_hashed is None
    assert u.telegram_chat_id_encrypted is not None
    assert u.telegram_username == "alice"


@pytest.mark.integration
async def test_confirm_link_with_wrong_token_returns_none(db, make_user):
    from app.services.mfa_service import confirm_link_telegram
    u = await make_user(email="bad-token@example.com")
    res = await confirm_link_telegram(db, "WRONG-TOKEN", chat_id=99, username="x")
    assert res is None
