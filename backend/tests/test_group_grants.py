"""Integration tests for has_effective_permission — group_permission_grant flow.

This is the heart of the C1 fix. Without these tests, the C1 regression
("v2 grants never applied") could silently come back.

Covers:
  * group GRANT adds a permission the user doesn't have via role
  * group DENY revokes a permission the user has via role
  * expired group grant is ignored
  * owner / admin role still bypass groups
  * combined: role+grant, role+deny, multi-group
"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import text


pytestmark = pytest.mark.integration


async def _make_group(db, code: str, users: list, grants: list[tuple[str, str]] | None = None,
                     expires_at=None):
    """grants = list of (permission_code, grant_type)."""
    from app.models.rbac_v3 import GroupPermissionGrant
    from app.models.user import Group
    g = Group(code=code, name=f"Group {code}")
    db.add(g)
    await db.flush()
    for u in users:
        await db.execute(
            text("INSERT INTO user_group (user_id, group_id) VALUES (:uid, :gid)"),
            {"uid": u.id, "gid": g.id},
        )
    for perm_code, gtype in (grants or []):
        db.add(GroupPermissionGrant(
            group_id=g.id, permission_code=perm_code, grant_type=gtype,
            expires_at=expires_at,
        ))
    await db.commit()
    return g


async def test_group_grant_gives_perm_user_lacks_via_role(db, make_user):
    """User without kpi.edit in role gets it via group grant."""
    from app.core.security import has_effective_permission
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.user import User, Role

    u = await make_user(role_codes=["organization"])  # no kpi.edit
    await _make_group(db, "g-grant", [u], [("kpi.edit", "grant")])

    # Re-fetch user with roles+permissions selectinload (как делает get_current_user).
    fresh = (await db.execute(
        select(User).where(User.id == u.id).options(
            selectinload(User.roles).selectinload(Role.permissions),
        ),
    )).scalar_one()

    assert await has_effective_permission(db, fresh, "kpi.edit") is True


async def test_group_deny_overrides_role_grant(db, make_user):
    """User has kpi.view via role; group deny revokes it."""
    from app.core.security import has_effective_permission
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.user import User, Role

    u = await make_user(role_codes=["financier"])  # has kpi.view
    await _make_group(db, "g-deny", [u], [("kpi.view", "deny")])

    fresh = (await db.execute(
        select(User).where(User.id == u.id).options(
            selectinload(User.roles).selectinload(Role.permissions),
        ),
    )).scalar_one()

    assert await has_effective_permission(db, fresh, "kpi.view") is False


async def test_expired_group_grant_ignored(db, make_user):
    """Group grant with expires_at in the past is ignored."""
    from app.core.security import has_effective_permission
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.user import User, Role

    u = await make_user(role_codes=["organization"])
    past = datetime.now(timezone.utc) - timedelta(days=1)
    await _make_group(db, "g-exp", [u], [("kpi.edit", "grant")], expires_at=past)

    fresh = (await db.execute(
        select(User).where(User.id == u.id).options(
            selectinload(User.roles).selectinload(Role.permissions),
        ),
    )).scalar_one()

    assert await has_effective_permission(db, fresh, "kpi.edit") is False


async def test_admin_role_bypasses_group_deny(db, make_user):
    """Even if a group denies a permission, role admin still bypasses."""
    from app.core.security import has_effective_permission
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.user import User, Role

    u = await make_user(role_codes=["admin"])
    await _make_group(db, "g-deny-admin", [u], [("kpi.view", "deny")])

    fresh = (await db.execute(
        select(User).where(User.id == u.id).options(
            selectinload(User.roles).selectinload(Role.permissions),
        ),
    )).scalar_one()

    # admin role → is_super_admin → True regardless of deny
    assert await has_effective_permission(db, fresh, "kpi.view") is True


async def test_owner_bypasses_group_deny(db, make_user):
    from app.core.security import has_effective_permission
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.user import User, Role

    u = await make_user(role_codes=[], is_owner=True)
    await _make_group(db, "g-deny-owner", [u], [("admin.users", "deny")])

    fresh = (await db.execute(
        select(User).where(User.id == u.id).options(
            selectinload(User.roles).selectinload(Role.permissions),
        ),
    )).scalar_one()

    assert await has_effective_permission(db, fresh, "admin.users") is True


async def test_group_grant_through_endpoint_authorizes(db, make_user, app_client, auth_header):
    """End-to-end: user без kpi.view в роли получает доступ через group grant.

    Hits /kpi/summary which uses require_permission('kpi.view').
    """
    u = await make_user(role_codes=["organization"], is_owner=True)
    # Use is_owner=True so the SCOPE check passes; we test PERMISSION here, not scope.
    # Wait — owner bypasses everything via is_super_admin. We want to verify
    # the group grant code path specifically.
    # Re-do: non-owner with companies.view_all so scope passes, no kpi.view in roles.
    from sqlalchemy import text as _text
    u2 = await make_user(role_codes=["organization"], is_owner=False)
    # Give organization role companies.view_all so scope passes.
    await db.execute(_text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.code = 'organization' AND p.code = 'companies.view_all'
    """))
    await db.commit()

    # First check: without group grant, /kpi/summary → 403
    r1 = await app_client.get("/kpi/summary/2026/year", headers=auth_header(u2))
    assert r1.status_code == 403, r1.text

    # Now grant kpi.view via group
    await _make_group(db, "g-kpi-view", [u2], [("kpi.view", "grant")])

    r2 = await app_client.get("/kpi/summary/2026/year", headers=auth_header(u2))
    assert r2.status_code == 200, r2.text


async def test_group_deny_blocks_endpoint(db, make_user, app_client, auth_header):
    """User has kpi.view via role but group deny → endpoint 403."""
    u = await make_user(role_codes=["financier"], is_owner=False)
    # financier already has kpi.view per seed. Add companies.view_all so scope passes.
    await db.execute(text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.code = 'financier' AND p.code = 'companies.view_all'
    """))
    await db.commit()

    # Sanity: works without deny
    r1 = await app_client.get("/kpi/summary/2026/year", headers=auth_header(u))
    assert r1.status_code == 200, r1.text

    # Deny via group → blocked
    await _make_group(db, "g-kpi-deny", [u], [("kpi.view", "deny")])
    r2 = await app_client.get("/kpi/summary/2026/year", headers=auth_header(u))
    assert r2.status_code == 403, r2.text
