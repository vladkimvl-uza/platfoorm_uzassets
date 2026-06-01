"""Integration tests for admin MFA endpoints.

Routes (prefix /admin/users):
  GET  /mfa-overview                 — admin.users / admin.security / owner
  POST /{user_id}/mfa-force-disable  — owner-only emergency wipe
"""
import uuid as _uuid
from datetime import UTC

import pytest

pytestmark = pytest.mark.integration


async def _enable_mfa(db, user, chat_id=12345, username="alice"):
    from datetime import datetime

    from sqlalchemy import update

    from app.core.encryption import encrypt_int
    from app.models.user import User
    from app.services.mfa_service import _hash_bcrypt, generate_recovery_codes

    codes = generate_recovery_codes()
    await db.execute(update(User).where(User.id == user.id).values(
        mfa_enabled=True,
        mfa_method="telegram",
        telegram_chat_id_encrypted=encrypt_int(chat_id),
        telegram_username=username,
        telegram_linked_at=datetime.now(UTC),
        mfa_recovery_codes_hashed=[_hash_bcrypt(c) for c in codes],
    ))
    await db.commit()


# ─── GET /admin/users/mfa-overview ─────────────────────────────────

async def test_mfa_overview_owner_sees_all(db, make_user, app_client, auth_header):
    owner = await make_user(email="owner-mfa@example.com", is_owner=True, role_codes=[])
    u_with = await make_user(email="with-mfa@example.com")
    await _enable_mfa(db, u_with)
    await make_user(email="without-mfa@example.com")

    r = await app_client.get("/admin/users/mfa-overview", headers=auth_header(owner))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "users" in body and "summary" in body
    emails = {u["email"] for u in body["users"]}
    assert "with-mfa@example.com" in emails
    assert "without-mfa@example.com" in emails

    assert body["summary"]["total"] >= 3
    assert body["summary"]["mfa_enabled_count"] >= 1
    assert body["summary"]["telegram_linked_count"] >= 1


async def test_mfa_overview_admin_users_perm_allowed(db, make_user, app_client, auth_header):
    """Non-owner with admin.users role still sees overview."""
    admin = await make_user(email="admin-mfa@example.com", role_codes=["admin"])
    r = await app_client.get("/admin/users/mfa-overview", headers=auth_header(admin))
    assert r.status_code == 200, r.text


async def test_mfa_overview_non_admin_blocked(db, make_user, app_client, auth_header):
    plain = await make_user(email="plain-mfa@example.com", role_codes=["organization"])
    r = await app_client.get("/admin/users/mfa-overview", headers=auth_header(plain))
    assert r.status_code == 403, r.text


async def test_mfa_overview_row_shape(db, make_user, app_client, auth_header):
    """Verify all expected fields are present in row shape."""
    owner = await make_user(email="owner-shape@example.com", is_owner=True)
    target = await make_user(email="row-shape@example.com")
    await _enable_mfa(db, target)

    r = await app_client.get("/admin/users/mfa-overview", headers=auth_header(owner))
    body = r.json()
    row = next((u for u in body["users"] if u["email"] == "row-shape@example.com"), None)
    assert row is not None
    expected_keys = {
        "id", "email", "full_name", "username", "is_active", "is_owner",
        "mfa_enabled", "mfa_method", "telegram_linked", "telegram_username",
        "telegram_linked_at", "recovery_codes_remaining", "last_login_at",
        "last_login_ip",
    }
    assert expected_keys.issubset(row.keys())
    assert row["mfa_enabled"] is True
    assert row["telegram_linked"] is True
    assert row["recovery_codes_remaining"] == 10  # generate_recovery_codes() default
    assert row["telegram_username"] == "alice"


async def test_mfa_overview_excludes_inactive(db, make_user, app_client, auth_header):
    """Inactive users should not appear in overview (is_active=True filter)."""
    owner = await make_user(email="owner-inact@example.com", is_owner=True)
    await make_user(email="active-u@example.com", is_active=True)
    await make_user(email="inactive-u@example.com", is_active=False)

    r = await app_client.get("/admin/users/mfa-overview", headers=auth_header(owner))
    emails = {u["email"] for u in r.json()["users"]}
    assert "active-u@example.com" in emails
    assert "inactive-u@example.com" not in emails


# ─── POST /admin/users/{id}/mfa-force-disable ──────────────────────

async def test_force_disable_wipes_mfa(db, make_user, app_client, auth_header):
    from sqlalchemy import select

    from app.models.user import User

    owner = await make_user(email="owner-wipe@example.com", is_owner=True)
    target = await make_user(email="wipe-target@example.com")
    await _enable_mfa(db, target)

    r = await app_client.post(
        f"/admin/users/{target.id}/mfa-force-disable",
        headers=auth_header(owner),
    )
    assert r.status_code == 204, r.text

    refreshed = (await db.execute(
        select(User).where(User.id == target.id),
    )).scalar_one()
    await db.refresh(refreshed)
    assert refreshed.mfa_enabled is False
    assert refreshed.telegram_chat_id_encrypted is None
    assert refreshed.telegram_username is None
    assert refreshed.telegram_linked_at is None
    assert refreshed.mfa_recovery_codes_hashed in (None, [])


async def test_force_disable_non_owner_blocked(db, make_user, app_client, auth_header):
    admin = await make_user(email="admin-no-wipe@example.com", role_codes=["admin"])
    target = await make_user(email="t1@example.com")
    await _enable_mfa(db, target)

    r = await app_client.post(
        f"/admin/users/{target.id}/mfa-force-disable",
        headers=auth_header(admin),
    )
    assert r.status_code == 403, r.text
    assert "влад" in r.text.lower()


async def test_force_disable_self_returns_400(db, make_user, app_client, auth_header):
    owner = await make_user(email="owner-self@example.com", is_owner=True)
    r = await app_client.post(
        f"/admin/users/{owner.id}/mfa-force-disable",
        headers=auth_header(owner),
    )
    assert r.status_code == 400, r.text


async def test_force_disable_unknown_user_returns_404(make_user, app_client, auth_header):
    owner = await make_user(email="owner-404@example.com", is_owner=True)
    fake = _uuid.uuid4()
    r = await app_client.post(
        f"/admin/users/{fake}/mfa-force-disable",
        headers=auth_header(owner),
    )
    assert r.status_code == 404, r.text


async def test_force_disable_writes_audit_entry(db, make_user, app_client, auth_header):
    """Verify audit_log gets a row with our action code."""
    from sqlalchemy import text
    owner = await make_user(email="owner-audit@example.com", is_owner=True)
    target = await make_user(email="audit-target@example.com")
    await _enable_mfa(db, target)

    r = await app_client.post(
        f"/admin/users/{target.id}/mfa-force-disable",
        headers=auth_header(owner),
    )
    assert r.status_code == 204

    rows = (await db.execute(
        text("""
            SELECT action, actor_email, entity_id, notes
              FROM audit_log
             WHERE action = 'mfa.force_disabled_by_admin'
               AND entity_id = :tid
        """),
        {"tid": str(target.id)},
    )).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_email == "owner-audit@example.com"
    assert "audit-target@example.com" in (row.notes or "")
    assert "mfa_was=True" in (row.notes or "")


async def test_force_disable_on_user_without_mfa_still_204(db, make_user, app_client, auth_header):
    """Idempotent: wiping a clean user is fine, no special-case."""
    owner = await make_user(email="owner-clean@example.com", is_owner=True)
    target = await make_user(email="clean-user@example.com")  # no MFA enabled

    r = await app_client.post(
        f"/admin/users/{target.id}/mfa-force-disable",
        headers=auth_header(owner),
    )
    assert r.status_code == 204, r.text
