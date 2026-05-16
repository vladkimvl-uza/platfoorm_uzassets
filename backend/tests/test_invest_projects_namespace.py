"""Integration tests for invest_projects namespace contract (C3b).

Convention enforced by `_enforce_path_scope`:
  * owner / `companies.view_all` — bypass all paths
  * scoped users may read/write ONLY `companies/<company_code>/...` where
    <company_code> is in their `allowed_companies`
  * root / any other top-level branch — 403 for scoped users
"""
import pytest


pytestmark = pytest.mark.integration


async def test_owner_can_read_root(make_user, app_client, auth_header):
    owner = await make_user(is_owner=True, role_codes=[])
    r = await app_client.get(
        "/invest-projects-storage/root/",
        headers=auth_header(owner),
    )
    assert r.status_code in (200, 503), r.text  # 503 if table missing — acceptable


async def test_owner_can_read_anything(make_user, app_client, auth_header):
    owner = await make_user(is_owner=True, role_codes=[])
    r = await app_client.get(
        "/invest-projects-storage/root/companies/anything/sub.json",
        headers=auth_header(owner),
    )
    assert r.status_code in (200, 503)


async def test_scoped_user_cannot_read_root(make_user, app_client, auth_header):
    u = await make_user(role_codes=["organization"], allowed_companies=["acme"])
    r = await app_client.get(
        "/invest-projects-storage/root/",
        headers=auth_header(u),
    )
    assert r.status_code == 403, r.text
    assert "companies/" in r.text


async def test_scoped_user_cannot_read_other_company(make_user, app_client, auth_header):
    u = await make_user(role_codes=["organization"], allowed_companies=["acme"])
    r = await app_client.get(
        "/invest-projects-storage/root/companies/wayne_enterprises/foo.json",
        headers=auth_header(u),
    )
    assert r.status_code == 403


async def test_scoped_user_cannot_read_non_companies_branch(make_user, app_client, auth_header):
    u = await make_user(role_codes=["organization"], allowed_companies=["acme"])
    r = await app_client.get(
        "/invest-projects-storage/root/shared/templates.json",
        headers=auth_header(u),
    )
    assert r.status_code == 403


async def test_scoped_user_can_read_own_company(db, make_user, app_client, auth_header):
    """Scope check goes through if path = companies/<allowed_code>/..."""
    from app.models.company import Company
    acme = Company(code="acme", name_ru="ACME")
    db.add(acme)
    await db.commit()

    u = await make_user(role_codes=["organization"], allowed_companies=["acme"])
    r = await app_client.get(
        "/invest-projects-storage/root/companies/acme/projects.json",
        headers=auth_header(u),
    )
    # Either 200 (with null data) or 503 (table missing) — anything except 403
    assert r.status_code != 403, r.text


async def test_scoped_user_company_code_case_insensitive(db, make_user, app_client, auth_header):
    """allowed_companies normalized to lowercase; request path is lowercased too."""
    from app.models.company import Company
    db.add(Company(code="acme", name_ru="ACME"))
    await db.commit()

    u = await make_user(role_codes=["organization"], allowed_companies=["ACME"])
    r = await app_client.get(
        "/invest-projects-storage/root/companies/Acme/x.json",
        headers=auth_header(u),
    )
    assert r.status_code != 403


async def test_scoped_put_to_other_company_blocked(db, make_user, app_client, auth_header):
    from app.models.company import Company
    db.add_all([
        Company(code="acme", name_ru="ACME"),
        Company(code="wayne_enterprises", name_ru="Wayne"),
    ])
    await db.commit()
    u = await make_user(role_codes=["organization"], allowed_companies=["acme"])
    r = await app_client.put(
        "/invest-projects-storage/root/companies/wayne_enterprises/x.json",
        json={"a": 1},
        headers=auth_header(u),
    )
    assert r.status_code == 403
