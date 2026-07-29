"""Pack 147 / Stage 5 — group membership endpoint with per-(user,group) roles.

Covers:
  PUT /rbac/v3/groups/{id}/members
    - New shape: {"members": [{"user_id": ..., "role_code": ...}, ...]}
    - Legacy shape: {"user_ids": [...]} — each user gets viewer role
    - Unknown user_id → 400
    - Unknown role_code → 400
    - Empty body (no members, no user_ids) → 400
    - Atomic replace (drops old memberships, inserts new)

  GET /rbac/v3/groups/{id}
    - Returns members with role_code/role_name
    - GroupBrief includes company_id

  GET /rbac/v3/users/{id}
    - Returns group_memberships: [{group, role}, ...]

  POST /companies
    - Auto-creates Group with company_id binding
"""
import pytest
from sqlalchemy import select

pytestmark = pytest.mark.integration


async def test_set_members_new_shape_with_roles(
    db, make_user, app_client, auth_header, make_company_group,
):
    admin = await make_user(role_codes=["admin"], is_owner=True)
    _, grp = await make_company_group(code="alpha")

    alice = await make_user(email="alice-mem@example.com")
    bob   = await make_user(email="bob-mem@example.com")

    r = await app_client.put(
        f"/rbac/v3/groups/{grp.id}/members",
        json={"members": [
            {"user_id": str(alice.id), "role_code": "viewer"},
            {"user_id": str(bob.id),   "role_code": "financier"},
        ]},
        headers=auth_header(admin),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    by_email = {m["email"]: m for m in body["members"]}
    assert by_email["alice-mem@example.com"]["role_code"] == "viewer"
    assert by_email["bob-mem@example.com"]["role_code"]   == "financier"


async def test_set_members_legacy_user_ids_grants_viewer(
    db, make_user, app_client, auth_header, make_company_group,
):
    admin = await make_user(role_codes=["admin"], is_owner=True)
    _, grp = await make_company_group(code="legacy")
    u = await make_user(email="legacy-mem@example.com")

    r = await app_client.put(
        f"/rbac/v3/groups/{grp.id}/members",
        json={"user_ids": [str(u.id)]},
        headers=auth_header(admin),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["members"][0]["email"] == "legacy-mem@example.com"
    assert body["members"][0]["role_code"] == "viewer"


async def test_set_members_unknown_user_400(
    make_user, app_client, auth_header, make_company_group,
):
    import uuid as _uuid
    admin = await make_user(role_codes=["admin"], is_owner=True)
    _, grp = await make_company_group(code="unk-user")
    fake = _uuid.uuid4()
    r = await app_client.put(
        f"/rbac/v3/groups/{grp.id}/members",
        json={"members": [{"user_id": str(fake), "role_code": "viewer"}]},
        headers=auth_header(admin),
    )
    assert r.status_code == 400, r.text
    assert "Unknown user_ids" in r.text


async def test_set_members_unknown_role_400(
    make_user, app_client, auth_header, make_company_group,
):
    admin = await make_user(role_codes=["admin"], is_owner=True)
    _, grp = await make_company_group(code="unk-role")
    u = await make_user(email="ur-target@example.com")
    r = await app_client.put(
        f"/rbac/v3/groups/{grp.id}/members",
        json={"members": [{"user_id": str(u.id), "role_code": "made_up_role"}]},
        headers=auth_header(admin),
    )
    assert r.status_code == 400, r.text
    assert "made_up_role" in r.text


async def test_set_members_empty_payload_400(
    make_user, app_client, auth_header, make_company_group,
):
    admin = await make_user(role_codes=["admin"], is_owner=True)
    _, grp = await make_company_group(code="empty")
    r = await app_client.put(
        f"/rbac/v3/groups/{grp.id}/members",
        json={},
        headers=auth_header(admin),
    )
    assert r.status_code == 400, r.text


async def test_set_members_atomic_replace(
    db, make_user, app_client, auth_header, make_company_group,
):
    """Sending a new list completely replaces the old one (atomic)."""
    from app.models.user import UserGroupRole
    admin = await make_user(role_codes=["admin"], is_owner=True)
    _, grp = await make_company_group(code="replace")
    alice = await make_user(email="ar-alice@example.com")
    bob   = await make_user(email="ar-bob@example.com")
    carol = await make_user(email="ar-carol@example.com")

    # Initial: alice, bob
    await app_client.put(
        f"/rbac/v3/groups/{grp.id}/members",
        json={"members": [
            {"user_id": str(alice.id), "role_code": "viewer"},
            {"user_id": str(bob.id),   "role_code": "viewer"},
        ]},
        headers=auth_header(admin),
    )

    # Replace: bob, carol
    await app_client.put(
        f"/rbac/v3/groups/{grp.id}/members",
        json={"members": [
            {"user_id": str(bob.id),   "role_code": "viewer"},
            {"user_id": str(carol.id), "role_code": "viewer"},
        ]},
        headers=auth_header(admin),
    )

    members = (await db.execute(
        select(UserGroupRole.user_id).where(UserGroupRole.group_id == grp.id)
    )).scalars().all()
    assert set(members) == {bob.id, carol.id}


async def test_group_detail_includes_company_id(
    make_user, app_client, auth_header, make_company_group,
):
    admin = await make_user(role_codes=["admin"], is_owner=True)
    co, grp = await make_company_group(code="with-co")
    r = await app_client.get(
        f"/rbac/v3/groups/{grp.id}", headers=auth_header(admin),
    )
    assert r.status_code == 200, r.text
    assert r.json()["company_id"] == str(co.id)


async def test_user_detail_returns_group_memberships(
    db, make_user, app_client, auth_header, make_company_group,
):
    admin = await make_user(role_codes=["admin"], is_owner=True)
    co_a, grp_a = await make_company_group(code="m-a")
    co_b, grp_b = await make_company_group(code="m-b")
    u = await make_user(
        email="multi-mem@example.com",
        role_codes=[],
        groups=[(grp_a.id, "viewer"), (grp_b.id, "financier")],
    )

    r = await app_client.get(
        f"/rbac/v3/users/{u.id}", headers=auth_header(admin),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "group_memberships" in body
    by_group_code = {m["group_code"]: m for m in body["group_memberships"]}
    assert by_group_code["m-a"]["role_code"] == "viewer"
    assert by_group_code["m-a"]["company_id"] == str(co_a.id)
    assert by_group_code["m-b"]["role_code"] == "financier"
    assert by_group_code["m-b"]["company_id"] == str(co_b.id)


async def test_create_user_with_group_membership_is_atomic(
    db, make_user, app_client, auth_header, make_company_group,
):
    from types import SimpleNamespace
    from uuid import UUID

    from app.models.user import UserGroupRole

    owner = await make_user(role_codes=["admin"], is_owner=True)
    co, grp = await make_company_group(code="create-membership")

    r = await app_client.post(
        "/rbac/v3/users",
        json={
            "email": "create-membership@example.com",
            "full_name": "Create Membership",
            "password": "CreatePa$$word!12345",
            "must_change_password": True,
            "role_codes": [],
            "group_memberships": [
                {"group_id": str(grp.id), "role_code": "financier"},
            ],
        },
        headers=auth_header(owner),
    )
    assert r.status_code == 201, r.text
    body = r.json()

    by_group_code = {m["group_code"]: m for m in body["group_memberships"]}
    assert by_group_code[co.code]["role_code"] == "financier"
    assert "kpi.view" in body["effective_permissions"]

    membership = (await db.execute(
        select(UserGroupRole).where(
            UserGroupRole.user_id == UUID(body["id"]),
            UserGroupRole.group_id == grp.id,
        )
    )).scalar_one_or_none()
    assert membership is not None

    token_user = SimpleNamespace(
        id=UUID(body["id"]),
        email=body["email"],
        is_owner=False,
        roles=[],
    )
    me = await app_client.get("/auth/me", headers=auth_header(token_user))
    assert me.status_code == 200, me.text
    assert "kpi.view" in me.json()["permissions"]


async def test_create_user_unknown_group_role_does_not_create_user(
    db, make_user, app_client, auth_header, make_company_group,
):
    from app.models.user import User

    owner = await make_user(role_codes=["admin"], is_owner=True)
    _, grp = await make_company_group(code="create-bad-role")

    r = await app_client.post(
        "/rbac/v3/users",
        json={
            "email": "bad-group-role@example.com",
            "full_name": "Bad Group Role",
            "password": "CreatePa$$word!12345",
            "must_change_password": True,
            "role_codes": [],
            "group_memberships": [
                {"group_id": str(grp.id), "role_code": "made_up_role"},
            ],
        },
        headers=auth_header(owner),
    )
    assert r.status_code == 400, r.text
    assert "made_up_role" in r.text

    existing = (await db.execute(
        select(User).where(User.email == "bad-group-role@example.com")
    )).scalar_one_or_none()
    assert existing is None


async def test_post_companies_auto_creates_group(
    db, make_user, app_client, auth_header,
):
    """POST /companies creates a 1:1 Group bound to the new company."""
    from app.models.user import Group
    owner = await make_user(role_codes=["admin"], is_owner=True)

    # Need to ensure 'companies.view_all' and 'companies.create' are reachable.
    # owner bypass takes care of both. Sector lookup may fail without seed —
    # skip sector_code if endpoint accepts None.
    r = await app_client.post(
        "/companies",
        json={
            "code": "autoco",
            "name_ru": "Auto Co",
            "name_short": "Auto",
        },
        headers=auth_header(owner),
    )
    assert r.status_code == 201, r.text

    grp = (await db.execute(
        select(Group).where(Group.code == "autoco")
    )).scalar_one_or_none()
    assert grp is not None
    assert grp.name == "Auto Co"
    assert grp.company_id is not None


async def test_post_companies_with_existing_group_code_suffixes(
    db, make_user, app_client, auth_header,
):
    """If a Group with the desired code already exists (e.g. free-form
    'audit'), creating a Company 'audit' should still succeed; the new
    group gets '_co' suffix."""
    from app.models.user import Group
    owner = await make_user(role_codes=["admin"], is_owner=True)

    # Pre-create a free-form group with the desired code
    pre = Group(code="conflict", name="Pre-existing", company_id=None)
    db.add(pre)
    await db.commit()

    r = await app_client.post(
        "/companies",
        json={"code": "conflict", "name_ru": "Conflict Co"},
        headers=auth_header(owner),
    )
    assert r.status_code == 201, r.text

    # New group with _co suffix exists
    new_grp = (await db.execute(
        select(Group).where(Group.code == "conflict_co")
    )).scalar_one_or_none()
    assert new_grp is not None
    assert new_grp.company_id is not None
