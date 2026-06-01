"""Integration tests for refresh-token replay defense.

Scenario: attacker steals an old refresh token. User legitimately rotates
their session (old refresh is revoked, new pair issued). Attacker tries
to use the OLD refresh.

Expected: refresh_tokens detects a revoked-token reuse and revokes ALL
sessions for that user as defense-in-depth (forced logout everywhere).
"""
import pytest
from sqlalchemy import select

pytestmark = pytest.mark.integration


async def _live_sessions(db, user_id):
    from app.models.user import UserSession
    return (await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    )).scalars().all()


async def test_normal_rotation_works(db, make_user):
    """Sanity: legitimate rotation produces new pair, old revoked, 1 live session."""
    from app.services.auth_service import authenticate, refresh_tokens

    pwd = "TestPa$$w0rdQ7K"
    await make_user(email="rotateme@example.com", password=pwd)
    user, access1, refresh1 = await authenticate(db, login_id="rotateme@example.com", password=pwd)

    assert len(await _live_sessions(db, user.id)) == 1

    user2, access2, refresh2 = await refresh_tokens(db, refresh_token=refresh1)
    assert refresh2 != refresh1
    # Old session revoked, new one live → still 1 live total
    assert len(await _live_sessions(db, user.id)) == 1


async def test_replay_revokes_all_sessions(db, make_user):
    """Use refresh1 twice — second use is replay → all sessions purged."""
    from app.services.auth_service import authenticate, refresh_tokens

    pwd = "TestPa$$w0rdQ7K"
    await make_user(email="replay@example.com", password=pwd)

    # Two separate login sessions
    user, _, refresh_a = await authenticate(db, login_id="replay@example.com", password=pwd)
    _, _, refresh_b = await authenticate(db, login_id="replay@example.com", password=pwd)

    assert len(await _live_sessions(db, user.id)) == 2

    # Rotate refresh_a → revoked
    await refresh_tokens(db, refresh_token=refresh_a)
    # Now refresh_a is revoked. Attacker replays it:
    with pytest.raises(Exception) as exc_info:
        await refresh_tokens(db, refresh_token=refresh_a)
    assert "replay" in str(exc_info.value).lower()

    # All sessions for that user should now be revoked
    assert len(await _live_sessions(db, user.id)) == 0


async def test_unknown_jti_fails_unauthorized(db, make_user):
    """A refresh token with a jti the DB never saw → 401, NO mass revoke
    (we can't even identify which user to wipe)."""
    from app.core import jwt as J
    from app.services.auth_service import authenticate, refresh_tokens

    pwd = "TestPa$$w0rdQ7K"
    user = await make_user(email="ghost@example.com", password=pwd)
    await authenticate(db, login_id="ghost@example.com", password=pwd)

    # Hand-craft a refresh token with a fresh jti never persisted
    bogus, _ = J.create_refresh_token(subject=str(user.id), jti="ghost-jti-never-stored")

    with pytest.raises(Exception):
        await refresh_tokens(db, refresh_token=bogus)

    # The legitimate session is still alive (we did NOT mass-revoke).
    assert len(await _live_sessions(db, user.id)) == 1


async def test_inactive_user_cannot_refresh(db, make_user):
    from sqlalchemy import update

    from app.models.user import User
    from app.services.auth_service import authenticate, refresh_tokens

    pwd = "TestPa$$w0rdQ7K"
    u = await make_user(email="inactive-refresh@example.com", password=pwd)
    _, _, refresh = await authenticate(db, login_id="inactive-refresh@example.com", password=pwd)

    await db.execute(update(User).where(User.id == u.id).values(is_active=False))
    await db.commit()

    with pytest.raises(Exception) as exc:
        await refresh_tokens(db, refresh_token=refresh)
    assert "not found" in str(exc.value).lower() or "inactive" in str(exc.value).lower()
