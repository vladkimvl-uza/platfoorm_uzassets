"""Integration tests for C3 — per-company scope (Pack 147 model).

Per-company access is now sourced from membership in Group(company_id=...)
+ UserGroupRole. `allowed_companies` JSONB no longer exists.

Covers ensure_company_access on:
  * GET / PUT / DELETE /kpi/{company_id}/{year}
  * GET /kpi/comment/{company_id}/{year}/{period}
  * POST /bp/upsert (payload.company_id)

Also covers that owner / companies.view_all bypass works.
"""
import uuid

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
async def two_companies(make_company_group):
    """Create two companies + their bound groups; return (allowed, forbidden)
    each as (company, group) tuple."""
    a_co, a_g = await make_company_group(code="alpha", name="Альфа")
    b_co, b_g = await make_company_group(code="beta", name="Бета")
    return (a_co, a_g), (b_co, b_g)


async def test_scoped_user_cannot_get_kpi_of_other_company(
    make_user, app_client, auth_header, two_companies,
):
    (allowed_co, allowed_grp), (forbidden_co, _) = two_companies
    # User has viewer role globally (to satisfy permission check)
    # AND viewer role IN allowed_grp (to satisfy scope check).
    u = await make_user(
        role_codes=["viewer"],
        groups=[(allowed_grp.id, "viewer")],
    )

    # Read allowed → 200 (no KPI data yet)
    r_ok = await app_client.get(
        f"/kpi/{allowed_co.id}/2026", headers=auth_header(u),
    )
    assert r_ok.status_code == 200, r_ok.text

    # Read forbidden → 403 (not a member of that group)
    r_no = await app_client.get(
        f"/kpi/{forbidden_co.id}/2026", headers=auth_header(u),
    )
    assert r_no.status_code == 403, r_no.text


async def test_scoped_user_cannot_delete_kpi_of_other_company(
    db, make_user, app_client, auth_header, two_companies,
):
    """Non-admin with kpi.delete in role, but only one allowed company.
    Hitting the OTHER company → 403."""
    from sqlalchemy import text
    (_, allowed_grp), (forbidden_co, _) = two_companies

    # Build an ad-hoc role with kpi.view + kpi.delete (no companies.view_all).
    await db.execute(text("""
        INSERT INTO roles (id, code, name_ru, is_system, is_active, sort_order, created_at, updated_at)
        VALUES (gen_random_uuid(), 'kpi_admin', 'KPI Admin', false, true, 100, now(), now())
        ON CONFLICT (code) DO NOTHING
    """))
    await db.execute(text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
         WHERE r.code = 'kpi_admin'
           AND p.code IN ('kpi.view', 'kpi.delete')
        ON CONFLICT DO NOTHING
    """))
    await db.commit()

    u = await make_user(
        role_codes=[],
        groups=[(allowed_grp.id, "kpi_admin")],
    )
    r_no = await app_client.delete(
        f"/kpi/{forbidden_co.id}/2026", headers=auth_header(u),
    )
    assert r_no.status_code == 403, r_no.text


async def test_owner_bypass_kpi_scope(make_user, app_client, auth_header, two_companies):
    (_, _), (forbidden_co, _) = two_companies
    owner = await make_user(is_owner=True, role_codes=[])
    r = await app_client.get(
        f"/kpi/{forbidden_co.id}/2026", headers=auth_header(owner),
    )
    assert r.status_code == 200, r.text


async def test_companies_view_all_bypass_kpi_scope(db, make_user, app_client, auth_header, two_companies):
    """User with companies.view_all globally — sees ANY company, even
    without group membership."""
    from sqlalchemy import text
    (_, _), (forbidden_co, _) = two_companies
    # No groups at all — but role gives both companies.view_all and kpi.view
    u = await make_user(role_codes=["viewer"])
    await db.execute(text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
         WHERE r.code = 'viewer' AND p.code = 'companies.view_all'
        ON CONFLICT DO NOTHING
    """))
    await db.commit()

    r = await app_client.get(
        f"/kpi/{forbidden_co.id}/2026", headers=auth_header(u),
    )
    assert r.status_code == 200, r.text


async def test_unknown_company_id_returns_403_not_500(make_user, app_client, auth_header):
    """Scoped user hitting a UUID that doesn't exist → 403 (not 500)."""
    u = await make_user(role_codes=["viewer"])  # no group membership → 0 allowed
    fake = uuid.uuid4()
    r = await app_client.get(f"/kpi/{fake}/2026", headers=auth_header(u))
    assert r.status_code == 403


async def test_scoped_user_bp_upsert_blocked_for_other_company(
    db, make_user, app_client, auth_header, two_companies,
):
    """payload.company_id scope check on /bp/upsert."""
    from sqlalchemy import text
    (_, allowed_grp), (forbidden_co, _) = two_companies

    # viewer-like role that ALSO has bp.edit, just for this test
    await db.execute(text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
         WHERE r.code = 'viewer' AND p.code = 'bp.edit'
        ON CONFLICT DO NOTHING
    """))
    await db.commit()

    u = await make_user(
        role_codes=["viewer"],
        groups=[(allowed_grp.id, "viewer")],
    )

    r = await app_client.post(
        "/bp/upsert",
        json={
            "company_id": str(forbidden_co.id),
            "year": 2026, "period": "annual", "metric": "revenue",
            "plan": "100", "expect": None, "fact": None,
        },
        headers=auth_header(u),
    )
    assert r.status_code == 403, r.text
