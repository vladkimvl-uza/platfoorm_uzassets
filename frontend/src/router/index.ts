import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/Login.vue"),
      meta: { layout: "blank" },
    },
    {
      path: "/login-v2",
      name: "login-v2",
      component: () => import("@/views/LoginV2.vue"),
      meta: { layout: "blank" },
    },
    {
      path: "/login-mfa",
      name: "login-mfa-step",
      component: () => import("@/views/LoginMfaStep.vue"),
      meta: { layout: "blank" },
    },
    // Pack 13.3: MFA onboarding wizard — fullscreen, requires auth, runs after login
    {
      path: "/mfa-onboarding",
      name: "mfa-onboarding",
      component: () => import("@/views/MfaOnboarding.vue"),
      meta: { layout: "blank", requiresAuth: true },
    },
    // Forced/voluntary password change (also reachable from profile menu)
    {
      path: "/change-password",
      name: "change-password",
      component: () => import("@/views/ChangePasswordPage.vue"),
      meta: { layout: "blank", requiresAuth: true, title: "Смена пароля" },
    },
    {
      path: "/home",
      name: "home",
      component: () => import("@/views/Home.vue"),
      meta: { layout: "blank", requiresAuth: true, title: "UzAssets" },
    },
    {
      path: "/",
      component: () => import("@/views/AppShell.vue"),
      meta: { requiresAuth: true },
      children: [
        { path: "", redirect: "/home" },
        {
          path: "dashboard",
          name: "dashboard",
          component: () => import("@/views/Dashboard.vue"),
          meta: { title: "Проекты трансформации" },
        },
        {
          path: "executive-dashboard",
          name: "executive-dashboard",
          component: () => import("@/views/ExecutiveDashboard.vue"),
          meta: { requiresAuth: true, requiresPermission: "financials.view" },
        },
        {
          path: "companies",
          name: "companies",
          component: () => import("@/views/Companies.vue"),
          meta: { title: "Компании", requiresPermission: "companies.view" },
        },
        {
          path: "companies/:id",
          name: "company-detail",
          component: () => import("@/views/CompanyDetail.vue"),
          meta: { title: "Компания", requiresPermission: "companies.view" },
          props: true,
        },
        {
          path: "companies/:code/workspace",
          name: "company-workspace",
          component: () => import("@/views/CompanyWorkspace.vue"),
          meta: { title: "Карточка компании", requiresPermission: "companies.view" },
          props: true,
        },

        // Pack 9aJ · Company Library (MDM)
        {
          path: "library/companies",
          name: "library-companies",
          component: () => import("@/views/library/CompanyLibraryIndex.vue"),
          meta: { title: "Библиотека · Компании", requiresPermission: "companies.view" },
        },
        {
          path: "library/companies/:id",
          name: "library-company-detail",
          component: () => import("@/views/library/CompanyLibraryDetail.vue"),
          meta: { title: "Карточка · Библиотека", requiresPermission: "companies.view" },
          props: true,
        },

        // ─── Public Developer Docs (Phase 5.5) ───
        // Mounted under AppShell so user gets nav consistency, but content is
        // public — no permission check on the parent route.
        {
          path: "api-docs",
          component: () => import("@/views/devdocs/DevDocsLayout.vue"),
          meta: { title: "API · Документация", public: true },
          children: [
            { path: "",               name: "devdocs-quickstart", component: () => import("@/views/devdocs/QuickstartPage.vue") },
            { path: "authentication", name: "devdocs-auth",       component: () => import("@/views/devdocs/AuthPage.vue") },
            { path: "rate-limits",    name: "devdocs-rate",       component: () => import("@/views/devdocs/RateLimitsPage.vue") },
            { path: "webhooks",       name: "devdocs-webhooks",   component: () => import("@/views/devdocs/WebhooksPage.vue") },
            { path: "sdk",            name: "devdocs-sdk",        component: () => import("@/views/devdocs/SdkPage.vue") },
            { path: "endpoints/:module",            name: "devdocs-module",   component: () => import("@/views/devdocs/ModulePage.vue") },
            { path: "endpoints/:module/:operation", name: "devdocs-endpoint", component: () => import("@/views/devdocs/EndpointPage.vue") },
          ],
        },
        // Sidebar link "РљРѕРјРїР°РЅРёРё Рё СЃРµРєС‚РѕСЂР°" в†’ /admin/companies
        // (path renamed from "companies-admin" to "admin/companies", route name kept).
        // Pack 9.2: moved into /admin/rbac-v2 (Companies tab) — keep redirect for old bookmarks
        {
          path: "admin/companies",
          name: "companies-admin",
          redirect: "/admin/companies-legacy",
        },
        // Pack 9.2: companies admin v2 still mounted as separate page for direct deep links
        // (use this route if users have bookmarked it)
        {
          path: "admin/companies-legacy",
          name: "companies-admin-legacy",
          component: () => import("@/views/CompaniesAdmin.vue"),
          meta: { requiresPermission: "companies.edit" },
        },
        // Pack 7.35: системные константы (курсы USD, бюджет РУ)
        {
          path: "admin/system-config",
          name: "system-config",
          component: () => import("@/views/SystemConfig.vue"),
          meta: { title: "Системные константы", requiresPermission: "system.config.view" },
        },
        // Pack 149: DB-консоль (owner/admin only)
        {
          path: "admin/database",
          name: "admin-database",
          component: () => import("@/views/DatabaseAdmin.vue"),
          meta: { title: "База данных", requiresOwnerOrAdmin: true },
        },
        // Pack 150: TLS-сертификат (owner/admin only)
        {
          path: "admin/tls",
          name: "admin-tls",
          component: () => import("@/views/TlsAdmin.vue"),
          meta: { title: "TLS сертификат", requiresOwnerOrAdmin: true },
        },
        // Pack 9.2.2: audit log moved into RBAC v2 as tab — keep redirect for old links
        {
          path: "admin/audit",
          name: "admin-audit",
          redirect: "/admin/rbac-v3/audit",
        },
        // Pack 141: RBAC v3 (parallel to v2 — for testing; will replace v2 in p144)
        {
          path: "admin/rbac-v3",
          component: () => import("@/views/rbac-v3/RBACShell.vue"),
          meta: { title: "RBAC v3", requiresPermission: "admin.users" },
          children: [
            { path: "", redirect: { name: "rbac-v3-users" } },
            { path: "users", name: "rbac-v3-users", component: () => import("@/views/rbac-v3/UsersPage.vue") },
            { path: "roles", name: "rbac-v3-roles", component: () => import("@/views/rbac-v3/RolesPage.vue") },
            { path: "groups", name: "rbac-v3-groups", component: () => import("@/views/rbac-v3/GroupsPage.vue") },
            { path: "email-rules", name: "rbac-v3-email", component: () => import("@/views/rbac-v3/EmailRulesPage.vue") },
            { path: "audit", name: "rbac-v3-audit", component: () => import("@/views/rbac-v3/AuditFeedPage.vue") },
          ],
        },
        // Pack 144: RBAC v2 removed — redirect old bookmarks to v3
        {
          path: "admin/rbac-v2",
          name: "admin-rbac-v2",
          redirect: "/admin/rbac-v3",
        },
        // Pack 148-followup: ModerationTab.vue used to live as a tab inside
        // RBAC v2. When v2 was removed it became orphaned — restore as a
        // standalone admin route so the moderation workflow is reachable.
        {
          path: "admin/moderation",
          name: "admin-moderation",
          component: () => import("@/components/moderation/ModerationTab.vue"),
          meta: { title: "Модерация", requiresPermission: "moderation.review" },
        },
        {
          path: "admin/security",
          name: "admin-security",
          redirect: "/admin/rbac-v3",
        },
        // Pack 11.0: personal notifications inbox + settings
        {
          path: "notifications",
          name: "notifications",
          component: () => import("@/views/NotificationsView.vue"),
          meta: { title: "Уведомления" },
        },
        {
          path: "notifications/settings",
          name: "notifications-settings",
          component: () => import("@/views/NotificationSettings.vue"),
          meta: { title: "Настройки уведомлений" },
        },
        {
          path: "settings/security",
          name: "settings-security",
          component: () => import("@/views/SecuritySettings.vue"),
          meta: { title: "Безопасность" },
        },
        // Pack 11.2: Admin Broadcasts
        {
          path: "admin/broadcasts",
          name: "admin-broadcasts",
          component: () => import("@/views/AdminBroadcasts.vue"),
          meta: { title: "Кастомные рассылки", requiresPermission: "notifications.broadcast" },
        },
        // Pack 149: Catalogs — directions + consultants admin CRUD
        {
          path: "admin/catalogs",
          name: "admin-catalogs",
          component: () => import("@/views/admin/CatalogsPage.vue"),
          meta: { title: "Каталоги · направления и консультанты", requiresPermission: "companies.edit" },
        },
        // Pack 149: Storage backend admin (S3 / local) + smoke test
        {
          path: "admin/storage",
          name: "admin-storage",
          component: () => import("@/views/admin/StoragePage.vue"),
          meta: { title: "Хранилище файлов", requiresPermission: "companies.edit" },
        },
        // Pack 12.0: API Catalog + Service Accounts + API keys
        {
          path: "admin/api",
          name: "admin-api",
          component: () => import("@/views/ApiCatalog.vue"),
          meta: { title: "API & Интеграции", requiresPermission: "api_catalog.read" },
        },
        {
          path: "boards",
          name: "boards",
          component: () => import("@/views/Boards.vue"),
          meta: { title: "Доски", requiresPermission: "tasks.view" },
        },
        {
          path: "board/:id",
          name: "board-kanban",
          component: () => import("@/views/BoardKanban.vue"),
          meta: { title: "Доска", requiresPermission: "tasks.view" },
          props: true,
        },
        {
          path: "tasks",
          name: "tasks",
          component: () => import("@/views/Tasks.vue"),
          meta: { requiresPermission: "tasks.view" },
        },
        {
          path: "projects",
          name: "projects",
          component: () => import("@/views/Projects.vue"),
          meta: { title: "Проекты", requiresPermission: "tasks.view" },
        },
        {
          path: "project/:id",
          name: "project-detail",
          component: () => import("@/views/ProjectDetail.vue"),
          meta: { title: "Проект", requiresPermission: "tasks.view" },
          props: true,
        },
        {
          path: "ratings",
          name: "ratings",
          component: () => import("@/views/Ratings.vue"),
          meta: { requiresPermission: "ratings.view" },
        },
        {
          path: "kpi",
          name: "kpi",
          component: () => import("@/views/KPI.vue"),
          meta: { title: "KPI", requiresPermission: "kpi.view" },
        },
        {
          path: "financials",
          name: "financials",
          component: () => import("@/views/Financials.vue"),
          meta: { title: "Финансы", requiresPermission: "financials.view" },
        },
        {
          path: "financials-detailed",
          name: "financials-detailed",
          component: () => import("@/views/FinancialsDetailed.vue"),
          meta: { requiresPermission: "financials.view" },
        },
        {
          path: "financials-edit",
          name: "financials-edit",
          component: () => import("@/views/FinancialsEdit.vue"),
          meta: { title: "Финансы — редактор", requiresPermission: "financials.edit" },
        },
        {
          path: "financials-edit/nsbu",
          name: "financials-edit-nsbu",
          component: () => import("@/views/NsbuEditor.vue"),
          meta: { title: "Финансы — НСБУ редактор", requiresPermission: "financials.edit" },
        },
        {
          path: "financials-edit/ifrs",
          name: "financials-edit-ifrs",
          component: () => import("@/views/IfrsEditor.vue"),
          meta: { title: "Финансы — МСФО редактор", requiresPermission: "financials.edit" },
        },
        // FinModel — единая глобальная страница, company/year выбираются в топбаре.
        {
          path: "finmodel",
          name: "finmodel",
          component: () => import("@/views/finmodel/FinModelPage.vue"),
          meta: { title: "Финансовая модель", requiresPermission: "finmodel.view" },
        },
        {
          path: "business-plan",
          name: "business-plan",
          component: () => import("@/views/BusinessPlan.vue"),
          meta: { title: "Бизнес-план", requiresPermission: "bp.view" },
        },
        {
          path: "credit-portfolio",
          name: "credit-portfolio",
          component: () => import("@/views/CreditPortfolio.vue"),
          meta: { title: "Кредитный портфель", requiresPermission: "credit.view" },
        },
        {
          path: "invest-projects",
          name: "invest-projects",
          component: () => import("@/views/InvestProjects.vue"),
          meta: { title: "Инвест-проекты", requiresPermission: "investment.view" },
        },
        {
          path: "procurement/forensic",
          name: "procurement-forensic",
          component: () => import("@/views/ForensicAudit.vue"),
          meta: { requiresPermission: "procurement.view" },
        },
        {
          path: "consultants",
          name: "consultants",
          component: () => import("@/views/Consultants.vue"),
          // No dedicated permission — page is visible to any auth'd user.
          meta: { title: "Консультанты" },
        },
        {
          path: "procurement/analysis",
          name: "procurement-analysis",
          component: () => import("@/views/ProcurementAnalysis.vue"),
          meta: { requiresPermission: "procurement.view" },
        },
        // Added with merged bundle: ESG + Corporate Governance modules.
        {
          path: "governance",
          name: "governance",
          component: () => import("@/views/Governance.vue"),
          meta: { title: "Корпоративное управление", requiresPermission: "governance.view" },
        },
        {
          path: "esg",
          name: "esg",
          component: () => import("@/views/ESG.vue"),
          meta: { requiresPermission: "esg.view" },
        },
        {
          path: "ai-chat",
          name: "ai-chat",
          component: () => import("@/views/AiChat.vue"),
          meta: { title: "ИИ-ассистент", requiresPermission: "ai.chat" },
        },
        // Pack 144: RBAC v1/v2 removed — redirect to v3
        {
          path: "rbac",
          name: "rbac",
          redirect: "/admin/rbac-v3",
        },
      ],
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/views/NotFound.vue"),
    },
  ],
});

// в”Ђв”Ђв”Ђ Auth guard в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
// Synchronous вЂ” auth store reads tokens from localStorage at creation,
// no bootstrap step is needed.
// Pack 13.3: onboarding check — async guard, runs after standard auth check
let onboardingChecked = false;
async function checkOnboardingNeeded(): Promise<boolean> {
  const { mfaApi } = await import("@/api/mfa");
  try {
    const st = await mfaApi.onboardingStatus();
    return st.needed;
  } catch {
    return false;
  }
}

router.beforeEach(async (to) => {
  const auth = useAuthStore();

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }

  if (to.name === "login" && auth.isAuthenticated) {
    return { name: "dashboard" };
  }

  // Force password change: if must_change_password=true, allow only the
  // change-password page itself + auth endpoints. Any other navigation is
  // bounced here. Matches backend's get_current_user enforcement.
  if (
    auth.isAuthenticated &&
    auth.user?.must_change_password === true &&
    to.name !== "change-password" &&
    to.name !== "login" &&
    to.name !== "login-v2" &&
    to.name !== "login-mfa-step" &&
    to.name !== "mfa-onboarding"
  ) {
    return { name: "change-password" };
  }

  // Pack 13.3: redirect to onboarding wizard on first authenticated nav.
  // Runs once per session to avoid hitting backend on every route change.
  if (
    auth.isAuthenticated &&
    !onboardingChecked &&
    to.name !== "mfa-onboarding" &&
    to.name !== "login" &&
    to.name !== "login-v2" &&
    to.name !== "login-mfa-step"
  ) {
    onboardingChecked = true;
    const needed = await checkOnboardingNeeded();
    if (needed) {
      return { name: "mfa-onboarding" };
    }
  }

  // Enforce requiresPermission meta. Walks matched route chain (parent +
  // child) so nested admin routes inherit the gate from their parent.
  // Owner / admin role bypass is handled inside auth.hasPermission().
  if (auth.isAuthenticated) {
    for (const match of to.matched) {
      const req = match.meta?.requiresPermission as string | undefined;
      if (req && !auth.hasPermission(req)) {
        // Soft-deny: send them home rather than throwing a hard 403 in UI.
        // Dashboard isn't permission-gated, so it's a safe fallback.
        return { name: "dashboard", query: { denied: req } };
      }
      // Pack 149: harder gate — DB-консоль для owner/admin
      if (match.meta?.requiresOwnerOrAdmin) {
        const u: any = auth.user;
        const allowed = !!(u && (u.is_owner === true || u.is_admin === true || auth.hasRole("admin")));
        if (!allowed) {
          return { name: "dashboard", query: { denied: "owner_or_admin" } };
        }
      }
    }
  }
});

export default router;
