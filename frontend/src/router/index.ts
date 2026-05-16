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
    {
      path: "/",
      component: () => import("@/views/AppShell.vue"),
      meta: { requiresAuth: true },
      children: [
        { path: "", redirect: "/dashboard" },
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
          meta: { requiresAuth: true },
        },
        {
          path: "companies",
          name: "companies",
          component: () => import("@/views/Companies.vue"),
          meta: { title: "Компании" },
        },
        {
          path: "companies/:id",
          name: "company-detail",
          component: () => import("@/views/CompanyDetail.vue"),
          meta: { title: "Компания" },
          props: true,
        },
        {
          path: "companies/:code/workspace",
          name: "company-workspace",
          component: () => import("@/views/CompanyWorkspace.vue"),
          meta: { title: "Карточка компании" },
          props: true,
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
        },
        // Pack 7.35: системные константы (курсы USD, бюджет РУ)
        {
          path: "admin/system-config",
          name: "system-config",
          component: () => import("@/views/SystemConfig.vue"),
          meta: { title: "Системные константы" },
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
          meta: { title: "Доски" },
        },
        {
          path: "board/:id",
          name: "board-kanban",
          component: () => import("@/views/BoardKanban.vue"),
          meta: { title: "Доска" },
          props: true,
        },
        {
          path: "tasks",
          name: "tasks",
          component: () => import("@/views/Tasks.vue"),
        },
        {
          path: "projects",
          name: "projects",
          component: () => import("@/views/Projects.vue"),
          meta: { title: "Проекты" },
        },
        {
          path: "project/:id",
          name: "project-detail",
          component: () => import("@/views/ProjectDetail.vue"),
          meta: { title: "Проект" },
          props: true,
        },
        {
          path: "ratings",
          name: "ratings",
          component: () => import("@/views/Ratings.vue"),
        },
        {
          path: "kpi",
          name: "kpi",
          component: () => import("@/views/KPI.vue"),
          meta: { title: "KPI" },
        },
        {
          path: "financials",
          name: "financials",
          component: () => import("@/views/Financials.vue"),
          meta: { title: "Финансы" },
        },
        {
          path: "financials-detailed",
          name: "financials-detailed",
          component: () => import("@/views/FinancialsDetailed.vue"),
        },
        {
          path: "financials-edit",
          name: "financials-edit",
          component: () => import("@/views/FinancialsEdit.vue"),
          meta: { title: "Финансы — редактор" },
        },
        {
          path: "financials-edit/nsbu",
          name: "financials-edit-nsbu",
          component: () => import("@/views/NsbuEditor.vue"),
          meta: { title: "Финансы — НСБУ редактор" },
        },
        {
          path: "financials-edit/ifrs",
          name: "financials-edit-ifrs",
          component: () => import("@/views/IfrsEditor.vue"),
          meta: { title: "Финансы — МСФО редактор" },
        },
        {
          path: "fin-model",
          name: "fin-model",
          component: () => import("@/views/FinModel.vue"),
          meta: { title: "Финансовая модель" },
        },
        {
          path: "business-plan",
          name: "business-plan",
          component: () => import("@/views/BusinessPlan.vue"),
          meta: { title: "Бизнес-план" },
        },
        {
          path: "credit-portfolio",
          name: "credit-portfolio",
          component: () => import("@/views/CreditPortfolio.vue"),
          meta: { title: "Кредитный портфель" },
        },
        {
          path: "invest-projects",
          name: "invest-projects",
          component: () => import("@/views/InvestProjects.vue"),
          meta: { title: "Инвест-проекты" },
        },
        {
          path: "procurement/forensic",
          name: "procurement-forensic",
          component: () => import("@/views/ForensicAudit.vue"),
        },
        {
          path: "consultants",
          name: "consultants",
          component: () => import("@/views/Consultants.vue"),
          meta: { title: "Консультанты" },
        },
        {
          path: "procurement/analysis",
          name: "procurement-analysis",
          component: () => import("@/views/ProcurementAnalysis.vue"),
        },
        // Added with merged bundle: ESG + Corporate Governance modules.
        {
          path: "governance",
          name: "governance",
          component: () => import("@/views/Governance.vue"),
          meta: { title: "Корпоративное управление" },
        },
        {
          path: "esg",
          name: "esg",
          component: () => import("@/views/ESG.vue"),
        },
        {
          path: "ai-chat",
          name: "ai-chat",
          component: () => import("@/views/AiChat.vue"),
          meta: { title: "ИИ-ассистент" },
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
});

export default router;
