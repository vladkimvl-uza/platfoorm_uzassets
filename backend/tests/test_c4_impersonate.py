"""Integration tests for C4 — impersonate (preview-token) escalation guard.

The endpoint must reject:
  * impersonating yourself
  * impersonating an inactive user
  * impersonating the platform owner
  * impersonating ANY target that has `admin.users` (via role or group)
"""
import pytest


pytestmark = pytest.mark.integration


async def test_cannot_impersonate_self(make_user, app_client, auth_header):
    admin = await make_user(role_codes=["admin"])
    r = await app_client.post(
        f"/rbac/v3/users/{admin.id}/preview-token",
        headers=auth_header(admin),
    )
    assert r.status_code == 400
    assert "yourself" in r.text.lower()


async def test_cannot_impersonate_owner(make_user, app_client, auth_header):
    actor = await make_user(role_codes=["admin"], is_owner=False)
    owner = await make_user(role_codes=["organization"], is_owner=True)
    r = await app_client.post(
        f"/rbac/v3/users/{owner.id}/preview-token",
        headers=auth_header(actor),
    )
    assert r.status_code == 403
    assert "owner" in r.text.lower()


async def test_cannot_impersonate_inactive(make_user, app_client, auth_header):
    actor = await make_user(role_codes=["admin"])
    target = await make_user(role_codes=["organization"], is_active=False)
    r = await app_client.post(
        f"/rbac/v3/users/{target.id}/preview-token",
        headers=auth_header(actor),
    )
    assert r.status_code == 400
    assert "inactive" in r.text.lower()


async def test_cannot_impersonate_target_with_admin_users_via_role(make_user, app_client, auth_header):
    """Two non-owner users with admin role — one cannot impersonate the other."""
    actor = await make_user(role_codes=["admin"], is_owner=False)
    target = await make_user(role_codes=["admin"], is_owner=False)
    r = await app_client.post(
        f"/rbac/v3/users/{target.id}/preview-token",
        headers=auth_header(actor),
    )
    assert r.status_code == 403
    assert "admin.users" in r.text


async def test_cannot_impersonate_target_with_admin_users_via_group(db, make_user, app_client, auth_header):
    """target has no admin role but has admin.users via group_permission_grant."""
    from sqlalchemy import text
    actor = await make_user(role_codes=["admin"], is_owner=False)
    target = await make_user(role_codes=["organization"], is_owner=False)

    # Create a group, add target to it, grant admin.users to the group.
    from app.models.rbac_v3 import GroupPermissionGrant
    from app.models.user import Group

    g = Group(code="grp_test", name="Test group")
    db.add(g)
    await db.flush()
    await db.execute(text(
        "INSERT INTO user_group (user_id, group_id) VALUES (:uid, :gid)"
    ), {"uid": target.id, "gid": g.id})
    db.add(GroupPermissionGrant(
        group_id=g.id, permission_code="admin.users", grant_type="grant",
    ))
    await db.commit()

    r = await app_client.post(
        f"/rbac/v3/users/{target.id}/preview-token",
        headers=auth_header(actor),
    )
    assert r.status_code == 403
    assert "admin.users" in r.text


async def test_impersonate_regular_user_works(make_user, app_client, auth_header):
    """Sanity: импертоните обычного юзера всё-таки можно."""
    actor = await make_user(role_codes=["admin"])
    target = await make_user(role_codes=["organization"])
    r = await app_client.post(
        f"/rbac/v3/users/{target.id}/preview-token",
        headers=auth_header(actor),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_user_id"] == str(target.id)
    assert body["access_token"]
