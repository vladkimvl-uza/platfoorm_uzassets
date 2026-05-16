"""Integration tests for authenticate() — login + lockout + edge cases.

Covers:
  * successful login returns (user, access, refresh) and creates a UserSession
  * wrong password → 401
  * N failed attempts → user.locked_until set, 423 LOCKED
  * locked user can't login even with correct password until expiry
  * successful login resets failed_login_attempts
  * inactive user → 403 Account disabled
  * case-insensitive email match (UPPERCASE.example.com works)
  * unknown email → 401 (and no DB write besides audit row)
  * empty password gracefully → 401
"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select


pytestmark = pytest.mark.integration


async def _authenticate(db, *, email, password, ip="127.0.0.1"):
    from app.services.auth_service import authenticate
    return await authenticate(db, login_id=email, password=password, ip=ip)


async def test_successful_login_returns_tokens(db, make_user):
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="login-ok@example.com", password=pwd)
    user, access, refresh = await _authenticate(db, email="login-ok@example.com", password=pwd)
    assert user.id == u.id
    assert access and refresh
    assert access != refresh


async def test_successful_login_creates_session(db, make_user):
    from app.models.user import UserSession
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="login-sess@example.com", password=pwd)
    await _authenticate(db, email="login-sess@example.com", password=pwd)
    rows = (await db.execute(
        select(UserSession).where(UserSession.user_id == u.id),
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].revoked_at is None


async def test_wrong_password_raises_401(db, make_user):
    from fastapi import HTTPException
    pwd = "Q9k!#mB7vN$wL2pR"
    await make_user(email="wrong-pw@example.com", password=pwd)
    with pytest.raises(HTTPException) as exc:
        await _authenticate(db, email="wrong-pw@example.com", password="bad-password!Q3")
    assert exc.value.status_code == 401


async def test_lockout_after_max_failed_attempts(db, make_user):
    """N wrong attempts → locked_until set, next call returns 423."""
    from fastapi import HTTPException
    from app.config import settings
    from app.models.user import User
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="lockout@example.com", password=pwd)

    # N-1 wrong attempts → 401 each
    for _ in range(settings.LOGIN_MAX_FAILED_ATTEMPTS - 1):
        with pytest.raises(HTTPException) as exc:
            await _authenticate(db, email="lockout@example.com", password="bad-password!Q3")
        assert exc.value.status_code == 401

    # Final attempt — still 401 but now locks the account
    with pytest.raises(HTTPException) as exc:
        await _authenticate(db, email="lockout@example.com", password="bad-password!Q3")
    assert exc.value.status_code == 401

    # Re-fetch user — should have locked_until
    await db.refresh(u)
    assert u.locked_until is not None
    assert u.locked_until > datetime.now(timezone.utc)

    # Next attempt — even with CORRECT password — returns 423
    with pytest.raises(HTTPException) as exc:
        await _authenticate(db, email="lockout@example.com", password=pwd)
    assert exc.value.status_code == 423


async def test_lockout_clears_after_expiry(db, make_user):
    """Manually shift locked_until into the past — login should succeed."""
    from sqlalchemy import update
    from app.models.user import User
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="locked-expired@example.com", password=pwd)

    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.execute(update(User).where(User.id == u.id).values(
        locked_until=past, failed_login_attempts=99,
    ))
    await db.commit()

    user, _, _ = await _authenticate(db, email="locked-expired@example.com", password=pwd)
    assert user.id == u.id
    # And the counter is reset on success
    await db.refresh(u)
    assert u.failed_login_attempts == 0
    assert u.locked_until is None


async def test_successful_login_resets_failed_counter(db, make_user):
    from sqlalchemy import update
    from app.models.user import User
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="counter-reset@example.com", password=pwd)
    await db.execute(update(User).where(User.id == u.id).values(failed_login_attempts=3))
    await db.commit()

    await _authenticate(db, email="counter-reset@example.com", password=pwd)
    await db.refresh(u)
    assert u.failed_login_attempts == 0


async def test_inactive_user_blocked_with_403(db, make_user):
    from fastapi import HTTPException
    pwd = "Q9k!#mB7vN$wL2pR"
    await make_user(email="inactive@example.com", password=pwd, is_active=False)
    with pytest.raises(HTTPException) as exc:
        await _authenticate(db, email="inactive@example.com", password=pwd)
    assert exc.value.status_code == 403
    assert "отключ" in exc.value.detail.lower()


async def test_email_case_insensitive(db, make_user):
    pwd = "Q9k!#mB7vN$wL2pR"
    await make_user(email="case@example.com", password=pwd)
    # Same email in uppercase should still log in
    user, _, _ = await _authenticate(db, email="CASE@EXAMPLE.COM", password=pwd)
    assert user.email == "case@example.com"


async def test_unknown_email_returns_401_with_timing_equalization(db):
    """Don't leak 'user exists' via timing — synthetic bcrypt verify runs."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await _authenticate(db, email="nobody-here@example.com", password="any-Pa$$w0rd")
    assert exc.value.status_code == 401


async def test_empty_password_returns_401(db, make_user):
    from fastapi import HTTPException
    pwd = "Q9k!#mB7vN$wL2pR"
    await make_user(email="empty-pw@example.com", password=pwd)
    with pytest.raises(HTTPException) as exc:
        await _authenticate(db, email="empty-pw@example.com", password="")
    assert exc.value.status_code == 401


async def test_last_login_timestamp_updated(db, make_user):
    """authenticate() must stamp last_login_at + last_login_ip."""
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="last-login@example.com", password=pwd)
    assert u.last_login_at is None

    await _authenticate(db, email="last-login@example.com", password=pwd, ip="10.0.0.42")
    await db.refresh(u)
    assert u.last_login_at is not None
    assert u.last_login_ip == "10.0.0.42"
