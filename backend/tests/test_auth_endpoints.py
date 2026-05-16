"""HTTP-level integration tests for /auth/* endpoints.

Routes:
  POST /auth/login            — credentials → TokenPair
  POST /auth/refresh          — rotate refresh, issue new pair
  POST /auth/logout           — revoke refresh session
  GET  /auth/me               — current user public profile
  POST /auth/change-password  — change own password (revokes sessions)
"""
import uuid as _uuid
import pytest
from sqlalchemy import select


pytestmark = pytest.mark.integration


# ─── /auth/login ───────────────────────────────────────────────────

async def test_login_returns_token_pair(make_user, app_client):
    pwd = "Q9k!#mB7vN$wL2pR"
    await make_user(email="auth-login@example.com", password=pwd)
    r = await app_client.post(
        "/auth/login",
        json={"login": "auth-login@example.com", "password": pwd},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] > 0


async def test_login_wrong_password_401(make_user, app_client):
    pwd = "Q9k!#mB7vN$wL2pR"
    await make_user(email="auth-bad@example.com", password=pwd)
    r = await app_client.post(
        "/auth/login",
        json={"login": "auth-bad@example.com", "password": "wrong-Pa$$w0rd"},
    )
    assert r.status_code == 401, r.text


async def test_login_unknown_email_401(app_client):
    r = await app_client.post(
        "/auth/login",
        json={"login": "ghost@example.com", "password": "any-Pa$$w0rd"},
    )
    assert r.status_code == 401, r.text


async def test_login_inactive_user_403(make_user, app_client):
    pwd = "Q9k!#mB7vN$wL2pR"
    await make_user(email="auth-inactive@example.com", password=pwd, is_active=False)
    r = await app_client.post(
        "/auth/login",
        json={"login": "auth-inactive@example.com", "password": pwd},
    )
    assert r.status_code == 403, r.text


# ─── /auth/refresh ─────────────────────────────────────────────────

async def test_refresh_rotates_pair(db, make_user, app_client):
    """Rotation: old refresh revoked, new pair issued."""
    from app.models.user import UserSession
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="refresh-ok@example.com", password=pwd)
    r0 = await app_client.post(
        "/auth/login",
        json={"login": "refresh-ok@example.com", "password": pwd},
        headers={"User-Agent": "rotate-1"},
    )
    tokens = r0.json()

    r1 = await app_client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"User-Agent": "rotate-2"},
    )
    assert r1.status_code == 200, r1.text
    new_tokens = r1.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]
    assert new_tokens["access_token"] != tokens["access_token"]

    # Live sessions should still be 1 (old revoked, new live)
    live = (await db.execute(
        select(UserSession).where(
            UserSession.user_id == u.id,
            UserSession.revoked_at.is_(None),
        ),
    )).scalars().all()
    assert len(live) == 1


async def test_refresh_with_invalid_token_401(app_client):
    r = await app_client.post(
        "/auth/refresh",
        json={"refresh_token": "not.a.token"},
    )
    assert r.status_code == 401, r.text


async def test_refresh_replay_revokes_all_sessions(db, make_user, app_client):
    """Use the same refresh twice — second use = replay, all sessions purged."""
    from app.models.user import UserSession
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="replay-http@example.com", password=pwd)
    # Two login sessions
    r0 = await app_client.post(
        "/auth/login",
        json={"login": "replay-http@example.com", "password": pwd},
        headers={"User-Agent": "rep-1"},
    )
    r1 = await app_client.post(
        "/auth/login",
        json={"login": "replay-http@example.com", "password": pwd},
        headers={"User-Agent": "rep-2"},
    )
    refresh_a = r0.json()["refresh_token"]

    # First rotation — OK
    await app_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_a},
        headers={"User-Agent": "rep-3"},
    )
    # Same refresh again — replay → 401 + mass revoke
    r_replay = await app_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_a},
        headers={"User-Agent": "rep-4"},
    )
    assert r_replay.status_code == 401, r_replay.text

    live = (await db.execute(
        select(UserSession).where(
            UserSession.user_id == u.id,
            UserSession.revoked_at.is_(None),
        ),
    )).scalars().all()
    assert len(live) == 0


# ─── /auth/logout ──────────────────────────────────────────────────

async def test_logout_revokes_session(db, make_user, app_client):
    """POST /auth/logout with refresh token → that session is revoked."""
    from app.models.user import UserSession
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="logout@example.com", password=pwd)
    login = await app_client.post(
        "/auth/login",
        json={"login": "logout@example.com", "password": pwd},
    )
    tokens = login.json()

    r = await app_client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 204, r.text

    live = (await db.execute(
        select(UserSession).where(
            UserSession.user_id == u.id,
            UserSession.revoked_at.is_(None),
        ),
    )).scalars().all()
    assert len(live) == 0


async def test_logout_without_auth_401(app_client):
    r = await app_client.post("/auth/logout", json={})
    assert r.status_code == 401


# ─── /auth/me ──────────────────────────────────────────────────────

async def test_me_returns_user_profile(make_user, app_client, auth_header):
    u = await make_user(email="me@example.com", role_codes=["financier"])
    r = await app_client.get("/auth/me", headers=auth_header(u))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "me@example.com"
    assert "financier" in body["roles"]
    assert isinstance(body["permissions"], list)


async def test_me_without_auth_401(app_client):
    r = await app_client.get("/auth/me")
    assert r.status_code == 401


async def test_me_with_bad_token_401(app_client):
    r = await app_client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


# ─── /auth/change-password ─────────────────────────────────────────

async def test_change_password_success(db, make_user, app_client, auth_header):
    """Change own password; subsequent login with new password works,
    and all live sessions are revoked."""
    from app.models.user import UserSession
    pwd_old = "Q9k!#mB7vN$wL2pR"
    pwd_new = "X8b#!yT4zQwM2nKp"
    u = await make_user(email="chpw@example.com", password=pwd_old)
    # Make a live session via login
    await app_client.post("/auth/login", json={"login": "chpw@example.com", "password": pwd_old})

    r = await app_client.post(
        "/auth/change-password",
        json={"current_password": pwd_old, "new_password": pwd_new},
        headers=auth_header(u),
    )
    assert r.status_code == 204, r.text

    # Old password no longer works
    r_old = await app_client.post(
        "/auth/login",
        json={"login": "chpw@example.com", "password": pwd_old},
    )
    assert r_old.status_code == 401

    # New password works
    r_new = await app_client.post(
        "/auth/login",
        json={"login": "chpw@example.com", "password": pwd_new},
        headers={"User-Agent": "new-pw-login"},
    )
    assert r_new.status_code == 200

    # Pre-change live sessions were revoked
    refreshed = (await db.execute(
        select(UserSession).where(UserSession.user_id == u.id),
    )).scalars().all()
    # At least one session pre-change must be revoked
    assert any(s.revoked_at is not None for s in refreshed)


async def test_change_password_wrong_current_400(make_user, app_client, auth_header):
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="chpw-bad@example.com", password=pwd)
    r = await app_client.post(
        "/auth/change-password",
        json={"current_password": "wrong-Pa$$w0rd", "new_password": "X8b#!yT4zQwM2nKp"},
        headers=auth_header(u),
    )
    assert r.status_code == 400, r.text


async def test_change_password_weak_new_400(make_user, app_client, auth_header):
    pwd = "Q9k!#mB7vN$wL2pR"
    u = await make_user(email="chpw-weak@example.com", password=pwd)
    r = await app_client.post(
        "/auth/change-password",
        json={"current_password": pwd, "new_password": "short"},
        headers=auth_header(u),
    )
    # Pydantic min_length validation or policy validator — both acceptable
    assert r.status_code in (400, 422), r.text


async def test_change_password_without_auth_401(app_client):
    r = await app_client.post(
        "/auth/change-password",
        json={"current_password": "x", "new_password": "y"},
    )
    assert r.status_code == 401
