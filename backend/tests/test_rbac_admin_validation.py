"""Integration tests for RBAC admin endpoint input validation.

Smaller surface but high signal — these guards prevent admin from
shooting themselves with typos or referencing dead identifiers.
"""
import pytest
import uuid


pytestmark = pytest.mark.integration


async def test_create_user_unknown_role_400(make_user, app_client, auth_header):
    admin = await make_user(role_codes=["admin"])
    r = await app_client.post(
        "/rbac/v3/users",
        json={
            "email": "newone@example.com",
            "full_name": "New Guy",
            "password": "StrongPa$$w0rdQ7K",
            "role_codes": ["financier", "totally_made_up_role"],
        },
        headers=auth_header(admin),
    )
    assert r.status_code == 400
    assert "totally_made_up_role" in r.text


async def test_update_role_permissions_unknown_perm_400(make_user, app_client, auth_header):
    admin = await make_user(role_codes=["admin"])
    r = await app_client.patch(
        "/rbac/v3/roles/financier/permissions",
        json={"permission_codes": ["kpi.view", "made.up.perm"]},
        headers=auth_header(admin),
    )
    assert r.status_code == 400
    assert "made.up.perm" in r.text


async def test_delete_role_with_users_409(make_user, app_client, auth_header):
    """Role 'financier' has at least the created user → cannot delete."""
    admin = await make_user(role_codes=["admin"])
    await make_user(role_codes=["financier"])

    # Need 'financier' to be non-system for delete to even be considered.
    # Seed makes it non-system (is_system=False).
    r = await app_client.delete(
        "/rbac/v3/roles/financier",
        headers=auth_header(admin),
    )
    assert r.status_code == 409
    assert "user" in r.text.lower()


async def test_delete_system_role_400(make_user, app_client, auth_header):
    admin = await make_user(role_codes=["admin"])
    r = await app_client.delete(
        "/rbac/v3/roles/admin",
        headers=auth_header(admin),
    )
    assert r.status_code == 400
    assert "system" in r.text.lower()


async def test_permanent_delete_owner_400(make_user, app_client, auth_header):
    admin = await make_user(role_codes=["admin"])
    owner = await make_user(is_owner=True, role_codes=[])
    r = await app_client.delete(
        f"/rbac/v3/users/{owner.id}/permanent",
        headers=auth_header(admin),
    )
    assert r.status_code == 400
    assert "owner" in r.text.lower()


async def test_permanent_delete_self_400(make_user, app_client, auth_header):
    admin = await make_user(role_codes=["admin"])
    r = await app_client.delete(
        f"/rbac/v3/users/{admin.id}/permanent",
        headers=auth_header(admin),
    )
    assert r.status_code == 400


async def test_rbe_patch_unknown_role_400(make_user, app_client, auth_header):
    """PATCH /rbac/v3/role-by-email/{id} validates role_codes."""
    from app.models.user import RoleByEmail
    admin = await make_user(role_codes=["admin"])

    # Create a rule first
    r1 = await app_client.post(
        "/rbac/v3/role-by-email",
        json={"email": "newhire@example.com", "role_codes": ["financier"]},
        headers=auth_header(admin),
    )
    assert r1.status_code == 201
    rule_id = r1.json()["id"]

    # Try to update with unknown role
    r2 = await app_client.patch(
        f"/rbac/v3/role-by-email/{rule_id}",
        json={"role_codes": ["financier", "ghost_role"]},
        headers=auth_header(admin),
    )
    assert r2.status_code == 400
    assert "ghost_role" in r2.text


async def test_rbe_get_returns_created_rule(make_user, app_client, auth_header):
    """Sanity: list endpoint returns rules we POST."""
    admin = await make_user(role_codes=["admin"])
    await app_client.post(
        "/rbac/v3/role-by-email",
        json={"email": "list-test@example.com", "role_codes": ["organization"]},
        headers=auth_header(admin),
    )
    r = await app_client.get("/rbac/v3/role-by-email", headers=auth_header(admin))
    assert r.status_code == 200
    emails = {item["email"] for item in r.json()}
    assert "list-test@example.com" in emails


async def test_non_admin_cannot_create_user(make_user, app_client, auth_header):
    """Plain organization user can't hit /rbac/v3/users POST."""
    u = await make_user(role_codes=["organization"])
    r = await app_client.post(
        "/rbac/v3/users",
        json={
            "email": "intruder@example.com", "full_name": "X",
            "password": "StrongPa$$w0rdQ7K", "role_codes": [],
        },
        headers=auth_header(u),
    )
    assert r.status_code == 403


async def test_unknown_user_id_404(make_user, app_client, auth_header):
    admin = await make_user(role_codes=["admin"])
    fake = uuid.uuid4()
    r = await app_client.get(f"/rbac/v3/users/{fake}", headers=auth_header(admin))
    assert r.status_code == 404
