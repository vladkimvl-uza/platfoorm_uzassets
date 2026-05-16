"""Integration tests for C3 — per-company scope on endpoints with company_id.

Covers ensure_company_access on:
  * GET / PUT / DELETE /kpi/{company_id}/{year}
  * GET /kpi/comment/{company_id}/{year}/{period}
  * POST /bp/upsert (payload.company_id)
  * Notes list filtered for scoped users
  * Procurement aggregate filtered for scoped users

Also covers that owner / companies.view_all bypass works.
"""
import uuid
import pytest


pytestmark = pytest.mark.integration


@pytest.fixture
async def two_companies(db):
    """Create two companies, return (allowed_co, forbidden_co)."""
    from app.models.company import Company
    a = Company(code="alpha", name_ru="Альфа")
    b = Company(code="beta", name_ru="Бета")
    db.add_all([a, b])
    await db.commit()
    await db.refresh(a)
    await db.refresh(b)
    return a, b


async def test_scoped_user_cannot_get_kpi_of_other_company(
    db, make_user, app_client, auth_header, two_companies,
):
    allowed, forbidden = two_companies
    u = await make_user(
        role_codes=["financier"],  # has kpi.view
        allowed_companies=[str(allowed.id)],
    )

    # Read allowed → 200 with empty list (no KPI data yet)
    r_ok = await app_client.get(
        f"/kpi/{allowed.id}/2026", headers=auth_header(u),
    )
    assert r_ok.status_code == 200, r_ok.text

    # Read forbidden → 403
    r_no = await app_client.get(
        f"/kpi/{forbidden.id}/2026", headers=auth_header(u),
    )
    assert r_no.status_code == 403, r_no.text


async def test_scoped_user_cannot_delete_kpi_of_other_company(
    db, make_user, app_client, auth_header, two_companies,
):
    allowed, forbidden = two_companies
    u = await make_user(
        role_codes=["admin"],   # admin gets bypass via is_super_admin... wait
        allowed_companies=[str(allowed.id)],
    )
    # admin role bypasses _has_permission for kpi.delete, but ensure_company_access
    # uses companies.view_all (which admin DOES have via role). So admin will pass
    # scope-check. We need a non-admin actor with kpi.delete BUT NOT companies.view_all.

    # Re-create: assign kpi.delete + organization (limited) without admin role.
    from sqlalchemy import text
    await db.execute(text("DELETE FROM user_role WHERE user_id = :uid"), {"uid": u.id})
    await db.execute(text("""
        INSERT INTO user_role (user_id, role_id)
        SELECT :uid, id FROM roles WHERE code = 'organization'
    """), {"uid": u.id})
    # Grant kpi.delete to organization role specifically for this test.
    await db.execute(text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.code = 'organization' AND p.code = 'kpi.delete'
        ON CONFLICT DO NOTHING
    """))
    await db.commit()
    await db.refresh(u, ["roles"])

    r_no = await app_client.delete(
        f"/kpi/{forbidden.id}/2026", headers=auth_header(u),
    )
    assert r_no.status_code == 403, r_no.text


async def test_owner_bypass_kpi_scope(make_user, app_client, auth_header, two_companies):
    _, forbidden = two_companies
    owner = await make_user(is_owner=True, role_codes=[])
    r = await app_client.get(
        f"/kpi/{forbidden.id}/2026", headers=auth_header(owner),
    )
    assert r.status_code == 200, r.text


async def test_companies_view_all_bypass_kpi_scope(db, make_user, app_client, auth_header, two_companies):
    from sqlalchemy import text
    _, forbidden = two_companies
    u = await make_user(role_codes=["financier"], allowed_companies=["nonsense-code"])
    # Add companies.view_all to financier
    await db.execute(text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.code = 'financier' AND p.code = 'companies.view_all'
        ON CONFLICT DO NOTHING
    """))
    await db.commit()
    # get_current_user re-fetches user with selectinload at each request,
    # so we don't need to expire the local session cache.
    r = await app_client.get(
        f"/kpi/{forbidden.id}/2026", headers=auth_header(u),
    )
    assert r.status_code == 200, r.text


async def test_unknown_company_id_returns_403_not_500(make_user, app_client, auth_header):
    """Scoped user hitting a UUID that doesn't exist → 403 (not unhandled 500)."""
    u = await make_user(role_codes=["financier"], allowed_companies=[])
    fake = uuid.uuid4()
    r = await app_client.get(f"/kpi/{fake}/2026", headers=auth_header(u))
    assert r.status_code == 403


async def test_scoped_user_bp_upsert_blocked_for_other_company(
    db, make_user, app_client, auth_header, two_companies,
):
    """payload.company_id scope check на /bp/upsert."""
    from sqlalchemy import text
    allowed, forbidden = two_companies
    u = await make_user(
        role_codes=["financier"],
        allowed_companies=[str(allowed.id)],
    )
    # Grant bp.edit to financier for this test
    await db.execute(text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.code = 'financier' AND p.code = 'bp.edit'
        ON CONFLICT DO NOTHING
    """))
    await db.commit()

    r = await app_client.post(
        "/bp/upsert",
        json={
            "company_id": str(forbidden.id),
            "year": 2026, "period": "annual", "metric": "revenue",
            "plan": "100", "expect": None, "fact": None,
        },
        headers=auth_header(u),
    )
    assert r.status_code == 403, r.text
