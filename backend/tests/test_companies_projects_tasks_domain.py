"""Domain integration tests — companies / projects / tasks happy path + 403/404.

Covers the most user-facing CRUD endpoints in three top domain modules:

  /companies        — list, get, create (owner), 403 for non-priv user
  /projects         — list, create (with scope), 403 for cross-company
  /tasks            — list, get, create (with scope), 404 for non-existent

Permission seed (from data/seed): role 'admin' has companies.create, viewer has
companies.view + tasks.view. Owner bypasses all checks.
"""
import uuid

import pytest

pytestmark = pytest.mark.integration


# ─── /companies ────────────────────────────────────────────────────

async def test_companies_list_returns_array(make_user, app_client, auth_header):
    """Owner can list — returns empty or populated array, never 401/403."""
    owner = await make_user(email="co-owner@example.com", is_owner=True)
    r = await app_client.get("/companies", headers=auth_header(owner))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body or isinstance(body, list)


async def test_companies_list_403_for_user_without_view(make_user, app_client, auth_header):
    """User with no roles → no companies.view → 403."""
    plain = await make_user(email="co-plain@example.com", role_codes=[])
    r = await app_client.get("/companies", headers=auth_header(plain))
    assert r.status_code == 403, r.text


async def test_companies_get_404_for_unknown_code(make_user, app_client, auth_header):
    """Owner querying nonexistent company code → 404."""
    owner = await make_user(email="co-get-404@example.com", is_owner=True)
    r = await app_client.get(
        "/companies/this-code-does-not-exist", headers=auth_header(owner),
    )
    assert r.status_code == 404, r.text


async def test_companies_get_happy_path(make_user, make_company_group, app_client, auth_header):
    """Existing company by code → 200 with full payload."""
    co, _ = await make_company_group(code="happy_get_co", name="Happy Get Co")
    owner = await make_user(email="co-get-ok@example.com", is_owner=True)
    r = await app_client.get(
        f"/companies/{co.code}", headers=auth_header(owner),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "happy_get_co"
    assert body["name_ru"] == "Happy Get Co"


async def test_companies_create_403_for_viewer(make_user, app_client, auth_header):
    """Viewer (no companies.create) → 403 on POST /companies."""
    viewer = await make_user(email="co-create-403@example.com", role_codes=["viewer"])
    r = await app_client.post(
        "/companies",
        headers=auth_header(viewer),
        json={"code": "blocked_co", "name_ru": "Blocked"},
    )
    assert r.status_code == 403, r.text


async def test_companies_create_happy_path_owner(make_user, app_client, auth_header):
    """Owner creates a fresh company → 201 + audit row written by handler."""
    owner = await make_user(email="co-create-ok@example.com", is_owner=True)
    unique = f"created_{uuid.uuid4().hex[:6]}"
    r = await app_client.post(
        "/companies",
        headers=auth_header(owner),
        json={"code": unique, "name_ru": "Создано в тесте", "name_short": unique[:8]},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == unique


# ─── /projects ─────────────────────────────────────────────────────

async def test_projects_list_owner_200(make_user, app_client, auth_header):
    """Owner lists projects globally → 200, never 401/403."""
    owner = await make_user(email="proj-list-ok@example.com", is_owner=True)
    r = await app_client.get("/projects", headers=auth_header(owner))
    assert r.status_code == 200, r.text


async def test_projects_list_403_no_view(make_user, app_client, auth_header):
    """Plain user (no tasks.view) → 403."""
    plain = await make_user(email="proj-403@example.com", role_codes=[])
    r = await app_client.get("/projects", headers=auth_header(plain))
    assert r.status_code == 403, r.text


async def test_projects_create_owner_happy_path(make_user, make_company_group, app_client, auth_header):
    """Owner creates a project against a real company → 201."""
    co, _ = await make_company_group(code="proj_co", name="Project Co")
    owner = await make_user(email="proj-create-ok@example.com", is_owner=True)
    r = await app_client.post(
        "/projects",
        headers=auth_header(owner),
        json={
            "title": "Test Project",
            "status": "new",
            "priority": "medium",
            "company_id": str(co.id),
            "portfolio_year": 2026,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Test Project"


async def test_projects_create_403_cross_company(
    make_user, make_company_group, app_client, auth_header,
):
    """Scoped user with access to company A tries to create in company B → 403."""
    co_a, grp_a = await make_company_group(code="proj_scope_a")
    co_b, _ = await make_company_group(code="proj_scope_b")
    u = await make_user(
        email="proj-scope-no@example.com",
        role_codes=[],
        groups=[(grp_a.id, "viewer")],
    )
    r = await app_client.post(
        "/projects",
        headers=auth_header(u),
        json={
            "title": "Trying cross-company",
            "company_id": str(co_b.id),
        },
    )
    # Either 403 (scope rejected) or 403 (missing tasks.edit). Both are valid.
    assert r.status_code == 403, r.text


# ─── /tasks ────────────────────────────────────────────────────────

async def test_tasks_list_owner_200(make_user, app_client, auth_header):
    """Owner lists tasks globally → 200."""
    owner = await make_user(email="task-list-ok@example.com", is_owner=True)
    r = await app_client.get("/tasks", headers=auth_header(owner))
    assert r.status_code == 200, r.text


async def test_tasks_list_403_no_view(make_user, app_client, auth_header):
    """User without tasks.view → 403."""
    plain = await make_user(email="task-403@example.com", role_codes=[])
    r = await app_client.get("/tasks", headers=auth_header(plain))
    assert r.status_code == 403, r.text


async def test_tasks_get_404_for_unknown_id(make_user, app_client, auth_header):
    """Owner querying a fresh random UUID → 404."""
    owner = await make_user(email="task-404@example.com", is_owner=True)
    fake_id = uuid.uuid4()
    r = await app_client.get(f"/tasks/{fake_id}", headers=auth_header(owner))
    assert r.status_code == 404, r.text


async def test_tasks_create_owner_happy_path(make_user, make_company_group, app_client, auth_header):
    """Owner creates a task for an existing company → 201 with id."""
    co, _ = await make_company_group(code="task_co", name="Task Co")
    owner = await make_user(email="task-create-ok@example.com", is_owner=True)
    r = await app_client.post(
        "/tasks",
        headers=auth_header(owner),
        json={
            "title": "Test Task",
            "status": "new",
            "priority": "high",
            "company_id": str(co.id),
            "portfolio_year": 2026,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Test Task"
    assert body["priority"] == "high"


async def test_tasks_create_403_for_viewer(make_user, make_company_group, app_client, auth_header):
    """Viewer (no tasks.edit) → 403 on POST /tasks."""
    co, _ = await make_company_group(code="task_viewer_co")
    viewer = await make_user(
        email="task-viewer-403@example.com", role_codes=["viewer"],
    )
    r = await app_client.post(
        "/tasks",
        headers=auth_header(viewer),
        json={"title": "Should be blocked", "company_id": str(co.id)},
    )
    assert r.status_code == 403, r.text


async def test_tasks_create_403_cross_company(
    make_user, make_company_group, app_client, auth_header,
):
    """Scoped user with access to company A tries to create in B → 403."""
    co_a, grp_a = await make_company_group(code="task_scope_a")
    co_b, _ = await make_company_group(code="task_scope_b")
    u = await make_user(
        email="task-scope-no@example.com",
        role_codes=[],
        groups=[(grp_a.id, "viewer")],
    )
    r = await app_client.post(
        "/tasks",
        headers=auth_header(u),
        json={"title": "Cross-company task", "company_id": str(co_b.id)},
    )
    assert r.status_code == 403, r.text
