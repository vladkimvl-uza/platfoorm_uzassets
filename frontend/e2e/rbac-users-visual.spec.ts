import { expect, test, type Page } from "@playwright/test";

const owner = {
  id: "qa-owner",
  email: "owner@example.com",
  username: "qa-owner",
  full_name: "Алина Владелец",
  is_owner: true,
  is_active: true,
  must_change_password: false,
  password_changed_at: "2026-07-01T08:00:00Z",
  organization_id: "company-alpha",
  company: "UzAssets Alpha",
  sector: "Управляющая компания",
  org_profile_set: true,
  department: "Администрация",
  job_title: "Руководитель",
  last_login_at: "2026-07-29T08:00:00Z",
  welcome_seen: true,
  ui_locale: "ru",
  roles: ["owner"],
  permissions: [],
  scope_unrestricted: true,
  scope_companies: [],
  direct_permissions: [],
};

const executiveViewer = {
  ...owner,
  id: "qa-viewer",
  email: "viewer@example.com",
  username: "qa-viewer",
  full_name: "Бахтиёр Наблюдатель",
  is_owner: false,
  organization_id: null,
  company: null,
  sector: null,
  department: "Аналитика",
  job_title: "Наблюдатель",
  roles: ["viewer"],
  permissions: ["exec_dashboard.view"],
  direct_permissions: ["exec_dashboard.view"],
  scope_unrestricted: false,
};

const overview = {
  users_total: 5,
  users_active: 4,
  users_inactive: 1,
  roles_total: 8,
  permissions_total: 42,
  users_without_roles: 1,
  most_assigned_roles: [],
};

const users = [
  {
    id: "user-owner",
    email: "owner@example.com",
    full_name: "Алина Владелец",
    department: "Администрация",
    job_title: "Руководитель",
    is_active: true,
    is_owner: true,
    must_change_password: false,
    password_changed_at: "2026-07-01T08:00:00Z",
    last_login_at: "2026-07-29T08:00:00Z",
    last_seen_at: "2026-07-29T08:30:00Z",
    locked_until: null,
    created_at: "2026-01-10T08:00:00Z",
    role_codes: ["admin"],
    role_names: ["Администратор"],
    organization_id: "company-alpha",
    company: "UzAssets Alpha",
    allowed_companies: null,
    company_memberships: [
      {
        company_id: "company-alpha",
        company_name: "UzAssets Alpha",
        group_id: "group-alpha",
        group_name: "UzAssets Alpha",
        role_code: "admin",
        role_name: "Администратор",
      },
      {
        company_id: "company-beta",
        company_name: "UzAssets Beta",
        group_id: "group-beta",
        group_name: "UzAssets Beta",
        role_code: "viewer",
        role_name: "Наблюдатель",
      },
    ],
  },
  {
    id: "user-active",
    email: "active@example.com",
    full_name: "Бахтиёр Аналитик",
    department: "Аналитика",
    job_title: "Аналитик",
    is_active: true,
    is_owner: false,
    must_change_password: true,
    password_changed_at: null,
    last_login_at: null,
    last_seen_at: null,
    locked_until: null,
    created_at: "2026-04-10T08:00:00Z",
    role_codes: [],
    role_names: [],
    organization_id: "company-alpha",
    company: "UzAssets Alpha",
    allowed_companies: null,
    company_memberships: [{
      company_id: "company-alpha",
      company_name: "UzAssets Alpha",
      group_id: "group-alpha",
      group_name: "UzAssets Alpha",
      role_code: "analyst",
      role_name: "Аналитик",
    }],
  },
  {
    id: "user-blocked",
    email: "blocked@example.com",
    full_name: "Дилноза Архив",
    department: "Финансы",
    job_title: "Специалист",
    is_active: false,
    is_owner: false,
    must_change_password: false,
    password_changed_at: "2026-03-01T08:00:00Z",
    last_login_at: "2026-05-01T08:00:00Z",
    last_seen_at: "2026-05-01T08:30:00Z",
    locked_until: null,
    created_at: "2026-03-10T08:00:00Z",
    role_codes: ["viewer"],
    role_names: ["Наблюдатель"],
    organization_id: "company-beta",
    company: "UzAssets Beta",
    allowed_companies: null,
    company_memberships: [{
      company_id: "company-beta",
      company_name: "UzAssets Beta",
      group_id: "group-beta",
      group_name: "UzAssets Beta",
      role_code: "viewer",
      role_name: "Наблюдатель",
    }],
  },
  {
    id: "user-gamma",
    email: "gamma@example.com",
    full_name: "Камола Риск",
    department: "Риск-менеджмент",
    job_title: "Эксперт",
    is_active: true,
    is_owner: false,
    must_change_password: false,
    password_changed_at: "2026-06-20T08:00:00Z",
    last_login_at: "2026-07-28T08:00:00Z",
    last_seen_at: "2026-07-28T08:30:00Z",
    locked_until: null,
    created_at: "2026-05-10T08:00:00Z",
    role_codes: ["analyst"],
    role_names: ["Аналитик"],
    organization_id: "company-gamma",
    company: "UzAssets Gamma",
    allowed_companies: null,
    company_memberships: [{
      company_id: "company-gamma",
      company_name: "UzAssets Gamma",
      group_id: "group-gamma",
      group_name: "UzAssets Gamma",
      role_code: "analyst",
      role_name: "Аналитик",
    }],
  },
  {
    id: "user-unassigned",
    email: "new@example.com",
    full_name: "Шерзод Новый",
    department: null,
    job_title: null,
    is_active: true,
    is_owner: false,
    must_change_password: true,
    password_changed_at: null,
    last_login_at: null,
    last_seen_at: null,
    locked_until: null,
    created_at: "2026-07-29T08:00:00Z",
    role_codes: [],
    role_names: [],
    organization_id: null,
    company: null,
    allowed_companies: null,
    company_memberships: [],
  },
];

async function installApiMocks(page: Page, currentUser = owner) {
  page.on("pageerror", error => console.error(`[pageerror] ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") console.error(`[console] ${message.text()}`);
  });
  await page.addInitScript((user) => {
    localStorage.setItem("uza_access_token", "qa-token");
    localStorage.setItem("uza_refresh_token", "qa-refresh");
    localStorage.setItem("uza_user", JSON.stringify(user));
    localStorage.setItem("uza-locale-v1", "ru");
    localStorage.setItem("uz_sidebar_collapsed_v1", "false");
  }, currentUser);

  await page.route("**/*", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) {
      await route.continue();
      return;
    }
    let body: unknown = {};
    if (path.endsWith("/api/auth/me")) body = currentUser;
    else if (path.endsWith("/api/mfa/onboarding/status")) body = { needed: false };
    else if (path.endsWith("/api/rbac/v3/overview")) body = overview;
    else if (path.endsWith("/api/rbac/v3/users")) body = { items: users, total: users.length };
    else if (path.endsWith("/api/broadcasts/sticky")) body = [];
    else if (path.endsWith("/api/notifications/unread-count")) body = { count: 0, by_priority: {}, by_type: {}, by_module: {}, by_company: {} };
    else if (path.endsWith("/api/notifications/feed")) body = { items: [], total: 0, unread_count: 0, page: 1, per_page: 30 };
    else if (path.includes("/api/notifications")) body = {};
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

test.describe("RBAC users visual QA", () => {
  test("desktop groups users, renders flags and translates animated branding", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await installApiMocks(page);
    await page.goto("/admin/rbac/users");

    await expect(page.locator(".rv3-shell")).toBeVisible();
    await expect(page.locator(".company-group-header")).toHaveCount(4);
    await expect(page.getByText("UzAssets Alpha", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Создать пользователя" })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    const flag = page.locator(".lsw-btn .lsw-flag");
    await expect(flag).toBeVisible();
    const flagInfo = await flag.evaluate((img: HTMLImageElement) => ({ src: img.src, width: img.naturalWidth }));
    expect(flagInfo.src).toContain("/flags/ru.svg");
    expect(flagInfo.width).toBeGreaterThan(0);

    const animationNames = await page.locator(".sb-brand .ept-pixel").evaluateAll((nodes) =>
      nodes.map((node) => getComputedStyle(node).animationName),
    );
    expect(animationNames.some(name => name.startsWith("ept-assemble"))).toBe(true);

    await page.waitForTimeout(1600);
    await page.screenshot({ path: "test-results/users-desktop-ru.png", fullPage: true });

    await page.locator(".lsw-btn").click();
    await page.locator(".lsw-menu button").filter({ hasText: "English" }).click();
    await expect(page.getByRole("button", { name: "Create user" })).toBeVisible();
    await expect(page.locator(".sb-brand-tagline-stack span")).toHaveText([
      "Unified",
      "platform",
      "for transformation",
    ]);
    await expect(page.getByText("Бахтиёр Аналитик", { exact: true }).first()).toBeVisible();
  });

  test("mobile registry stays readable without horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installApiMocks(page);
    await page.goto("/admin/rbac/users");

    await expect(page.locator(".rv3-shell")).toBeVisible();
    await expect(page.locator(".company-group-header")).toHaveCount(4);
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: "test-results/users-mobile-ru.png", fullPage: true });

    await page.locator(".rv3-sb-toggle").click();
    await expect(page.locator(".uza-aside.mobile-open")).toBeVisible();
    await expect(page.locator(".uza-aside.mobile-open .lsw-flag")).toBeVisible();
    await page.screenshot({ path: "test-results/users-mobile-sidebar-ru.png" });
  });

  test("direct Executive Dashboard permission exposes the module", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await installApiMocks(page, executiveViewer);
    await page.goto("/notifications");

    await expect(page.locator(".sb-exec-dash")).toBeVisible();
    await expect(page.locator(".sb-exec-dash")).toHaveAttribute("href", "/executive-dashboard");
  });
});
