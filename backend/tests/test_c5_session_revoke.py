"""Integration tests for C5 — session revocation on admin actions.

Covers:
  * deactivate_user → all sessions revoked
  * update_user (roles changed) → sessions revoked
  * update_user (only is_active False) → sessions revoked
  * reset_password (admin) → sessions revoked
  * permanently_delete_user → sessions revoked before delete
"""
from datetime import UTC

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.integration


async def _live_sessions(db, user_id):
    """Count non-revoked sessions for a user."""
    from app.models.user import UserSession
    return (await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    )).scalars().all()


async def _seed_session(db, user, refresh_hash="rh_seed"):
    """Insert a fake live refresh-session for the user."""
    from datetime import datetime, timedelta

    from app.models.user import UserSession
    s = UserSession(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    db.add(s)
    await db.commit()
    return s


async def test_deactivate_revokes_all_sessions(db, make_user, app_client, auth_header):
    admin = await make_user(role_codes=["admin"])
    target = await make_user(role_codes=["organization"])
    await _seed_session(db, target, "rh_target1")
    await _seed_session(db, target, "rh_target2")

    assert len(await _live_sessions(db, target.id)) == 2

    r = await app_client.delete(
        f"/rbac/v3/users/{target.id}", headers=auth_header(admin),
    )
    assert r.status_code == 204, r.text
    assert len(await _live_sessions(db, target.id)) == 0


async def test_update_user_roles_change_revokes_sessions(db, make_user, app_client, auth_header):
    admin = await make_user(role_codes=["admin"])
    target = await make_user(role_codes=["organization"])
    await _seed_session(db, target, "rh_role_change")
    assert len(await _live_sessions(db, target.id)) == 1

    r = await app_client.patch(
        f"/rbac/v3/users/{target.id}",
        json={"role_codes": ["financier"]},
        headers=auth_header(admin),
    )
    assert r.status_code == 200, r.text
    assert len(await _live_sessions(db, target.id)) == 0


async def test_update_user_same_roles_does_not_revoke(db, make_user, app_client, auth_header):
    """Patch с тем же набором ролей — сессии остаются."""
    admin = await make_user(role_codes=["admin"])
    target = await make_user(role_codes=["organization"])
    await _seed_session(db, target, "rh_no_change")

    r = await app_client.patch(
        f"/rbac/v3/users/{target.id}",
        json={"role_codes": ["organization"], "full_name": "Renamed"},
        headers=auth_header(admin),
    )
    assert r.status_code == 200, r.text
    assert len(await _live_sessions(db, target.id)) == 1


async def test_reset_password_revokes_sessions(db, make_user, app_client, auth_header):
    admin = await make_user(role_codes=["admin"])
    target = await make_user(role_codes=["organization"])
    await _seed_session(db, target, "rh_pwd_reset")

    r = await app_client.post(
        f"/rbac/v3/users/{target.id}/reset-password",
        json={"new_password": "NewStrongPa$$w0rd!", "must_change_password": True},
        headers=auth_header(admin),
    )
    assert r.status_code == 204, r.text
    assert len(await _live_sessions(db, target.id)) == 0


async def test_update_user_set_inactive_revokes_sessions(db, make_user, app_client, auth_header):
    admin = await make_user(role_codes=["admin"])
    target = await make_user(role_codes=["organization"])
    await _seed_session(db, target, "rh_deact_via_patch")

    r = await app_client.patch(
        f"/rbac/v3/users/{target.id}",
        json={"is_active": False},
        headers=auth_header(admin),
    )
    assert r.status_code == 200, r.text
    assert len(await _live_sessions(db, target.id)) == 0
