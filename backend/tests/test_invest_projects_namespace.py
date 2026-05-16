"""Integration tests for invest_projects namespace contract (C3b, Pack 147).

Convention enforced by `_enforce_path_scope`:
  * owner / `companies.view_all` — bypass all paths
  * scoped users may read/write ONLY `companies/<company_code>/...` where
    <company_code> is bound to a group the user belongs to (via UserGroupRole)
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


async def test_scoped_user_cannot_read_root(make_user, app_client, auth_header, make_company_group):
    _, acme_grp = await make_company_group(code="acme", name="ACME")
    u = await make_user(role_codes=["viewer"], groups=[(acme_grp.id, "viewer")])
    r = await app_client.get(
        "/invest-projects-storage/root/",
        headers=auth_header(u),
    )
    assert r.status_code == 403, r.text
    assert "companies/" in r.text


async def test_scoped_user_cannot_read_other_company(
    make_user, app_client, auth_header, make_company_group,
):
    _, acme_grp = await make_company_group(code="acme", name="ACME")
    u = await make_user(role_codes=["viewer"], groups=[(acme_grp.id, "viewer")])
    r = await app_client.get(
        "/invest-projects-storage/root/companies/wayne_enterprises/foo.json",
        headers=auth_header(u),
    )
    assert r.status_code == 403


async def test_scoped_user_cannot_read_non_companies_branch(
    make_user, app_client, auth_header, make_company_group,
):
    _, acme_grp = await make_company_group(code="acme", name="ACME")
    u = await make_user(role_codes=["viewer"], groups=[(acme_grp.id, "viewer")])
    r = await app_client.get(
        "/invest-projects-storage/root/shared/templates.json",
        headers=auth_header(u),
    )
    assert r.status_code == 403


async def test_scoped_user_can_read_own_company(
    make_user, app_client, auth_header, make_company_group,
):
    """Scope check goes through if path = companies/<allowed_code>/..."""
    _, acme_grp = await make_company_group(code="acme", name="ACME")
    u = await make_user(role_codes=["viewer"], groups=[(acme_grp.id, "viewer")])
    r = await app_client.get(
        "/invest-projects-storage/root/companies/acme/projects.json",
        headers=auth_header(u),
    )
    # Either 200 (with null data) or 503 (table missing) — anything except 403
    assert r.status_code != 403, r.text


async def test_scoped_user_company_code_case_insensitive(
    make_user, app_client, auth_header, make_company_group,
):
    """Allowed-company codes are lowercased on both sides of the comparison."""
    _, acme_grp = await make_company_group(code="acme", name="ACME")
    u = await make_user(role_codes=["viewer"], groups=[(acme_grp.id, "viewer")])
    r = await app_client.get(
        "/invest-projects-storage/root/companies/Acme/x.json",
        headers=auth_header(u),
    )
    assert r.status_code != 403


async def test_scoped_put_to_other_company_blocked(
    make_user, app_client, auth_header, make_company_group,
):
    _, acme_grp = await make_company_group(code="acme", name="ACME")
    # wayne_enterprises has no group bound to user
    await make_company_group(code="wayne_enterprises", name="Wayne")
    u = await make_user(role_codes=["viewer"], groups=[(acme_grp.id, "viewer")])
    r = await app_client.put(
        "/invest-projects-storage/root/companies/wayne_enterprises/x.json",
        json={"a": 1},
        headers=auth_header(u),
    )
    assert r.status_code == 403
