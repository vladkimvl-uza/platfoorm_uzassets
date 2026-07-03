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
      path: "/login-mfa",
      name: "login-mfa-step",
      component: () => import("@/views/LoginMfaStep.vue"),
      meta: { layout: "blank" },
    },
    // MFA onboarding wizard — fullscreen, requires auth, runs after login
    {
      path: "/mfa-onboarding",
      name: "mfa-onboarding",
      component: () => import("@/views/MfaOnboarding.vue"),
      meta: { layout: "blank", requiresAuth: true },
    },
    // forgot-password via Telegram code
    {
      path: "/forgot-password",
      name: "forgot-password",
      component: () => import("@/views/ForgotPasswordPage.vue"),
      meta: { layout: "blank" },
    },
    // Forced/voluntary password change (also reachable from profile menu)
    {
      path: "/change-password",
      name: "change-password",
      component: () => import("@/views/ChangePasswordPage.vue"),
      meta: { layout: "blank", requiresAuth: true, title: "Смена пароля" },
    },
    // Homepage — full-screen entry page (no AppShell sidebar), 1:1 with legacy
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
        // Per user request 2026-05-23: у тех у кого есть доступ к
        // executive-dashboard — открываем его по умолчанию; остальные
        // идут на Home (исходное поведение).
        {
          path: "",
          redirect: () => {
            try {
              const a = useAuthStore();
              return a.hasPermission("financials.view") ? "/executive-dashboard" : "/home";
            } catch {
              // Если Pinia ещё не готова — fallback на исходный /home.
              return "/home";
            }
          },
        },
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
          path: "executive-overview",
          name: "executive-overview",
          component: () => import("@/views/ExecOverview.vue"),
          meta: { title: "Сводный обзор портфеля", requiresAuth: true, requiresPermission: "projects.view" },
        },
        {
          path: "execution-summary",
          name: "execution-summary",
          component: () => import("@/views/ControlTower.vue"),
          meta: { title: "Execution Summary", requiresPermission: "monitoring.view" },
        },
        // старый путь → новый (сохранённые ссылки/закладки)
        { path: "control-tower", redirect: { name: "execution-summary" } },
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

        // J · Company Library (MDM)
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
        // moved into /admin/rbac-v2 (Companies tab) — keep redirect for old bookmarks
        {
          path: "admin/companies",
          name: "companies-admin",
          redirect: "/admin/companies-legacy",
        },
        // companies admin v2 still mounted as separate page for direct deep links
        // (use this route if users have bookmarked it)
        {
          path: "admin/companies-legacy",
          name: "companies-admin-legacy",
          component: () => import("@/views/CompaniesAdmin.vue"),
          meta: { requiresPermission: "companies.edit" },
        },
        // системные константы (курсы USD, бюджет РУ)
        {
          path: "admin/system-config",
          name: "system-config",
          component: () => import("@/views/SystemConfig.vue"),
          meta: { title: "Системные константы", requiresPermission: "system.config.view" },
        },
        // Настройка SMTP / email-уведомлений (owner/admin)
        {
          path: "admin/email-settings",
          name: "email-settings",
          component: () => import("@/views/EmailSettings.vue"),
          meta: { title: "Настройка почты (SMTP)" },
        },
        // DB-консоль (owner/admin only)
        {
          path: "admin/database",
          name: "admin-database",
          component: () => import("@/views/DatabaseAdmin.vue"),
          meta: { title: "База данных", requiresOwnerOrAdmin: true },
        },
        // TLS-сертификат (owner/admin only)
        {
          path: "admin/tls",
          name: "admin-tls",
          component: () => import("@/views/TlsAdmin.vue"),
          meta: { title: "TLS сертификат", requiresOwnerOrAdmin: true },
        },
        // .2: audit log moved into RBAC v2 as tab — keep redirect for old links
        {
          path: "admin/audit",
          name: "admin-audit",
          redirect: "/admin/rbac/audit",
        },
        // RBAC v3 (parallel to v2 — for testing; will replace v2 in p144)
        {
          path: "admin/rbac",
          component: () => import("@/views/rbac-v3/RBACShell.vue"),
          meta: { title: "Управление доступом", requiresPermission: "admin.users" },
          children: [
            { path: "", redirect: { name: "rbac-v3-users" } },
            { path: "users", name: "rbac-v3-users", component: () => import("@/views/rbac-v3/UsersPage.vue") },
            { path: "roles", name: "rbac-v3-roles", component: () => import("@/views/rbac-v3/RolesPage.vue") },
            { path: "groups", name: "rbac-v3-groups", component: () => import("@/views/rbac-v3/GroupsPage.vue") },
            { path: "audit", name: "rbac-v3-audit", component: () => import("@/views/rbac-v3/AuditFeedPage.vue") },
          ],
        },
        // Старый путь /admin/rbac-v3 → /admin/rbac (сохраняем закладки/deep-links)
        { path: "admin/rbac-v3", redirect: "/admin/rbac" },
        { path: "admin/rbac-v3/:tab", redirect: (to) => `/admin/rbac/${to.params.tab}` },
        // RBAC v2 removed — redirect old bookmarks to v3
        {
          path: "admin/rbac-v2",
          name: "admin-rbac-v2",
          redirect: "/admin/rbac",
        },
        // followup: ModerationTab.vue used to live as a tab inside
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
          redirect: "/admin/rbac",
        },
        // personal notifications inbox + settings
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
        // Admin Broadcasts
        {
          path: "admin/broadcasts",
          name: "admin-broadcasts",
          component: () => import("@/views/AdminBroadcasts.vue"),
          meta: { title: "Кастомные рассылки", requiresPermission: "notifications.broadcast" },
        },
        // Catalogs — directions + consultants admin CRUD
        {
          path: "admin/catalogs",
          name: "admin-catalogs",
          component: () => import("@/views/admin/CatalogsPage.vue"),
          meta: { title: "Каталоги · направления и консультанты", requiresPermission: "companies.edit" },
        },
        // Storage backend admin (S3 / local) + smoke test
        {
          path: "admin/storage",
          name: "admin-storage",
          component: () => import("@/views/admin/StoragePage.vue"),
          meta: { title: "Хранилище файлов", requiresPermission: "companies.edit" },
        },
        // API Catalog + Service Accounts + API keys
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
          path: "projects",
          name: "projects",
          component: () => import("@/views/Projects.vue"),
          meta: { title: "Проекты", requiresPermission: "tasks.view" },
        },
        {
          path: "followed",
          name: "followed",
          component: () => import("@/views/FollowedView.vue"),
          meta: { title: "Отслеживаемое", requiresPermission: "tasks.view" },
        },
        {
          path: "calendar",
          name: "calendar",
          component: () => import("@/views/CalendarView.vue"),
          meta: { title: "Календарь", requiresPermission: "tasks.view" },
        },
        {
          path: "project-builder",
          name: "project-builder",
          component: () => import("@/views/ProjectBuilder.vue"),
          meta: { title: "Конструктор задач", requiresPermission: "tasks.edit" },
        },
        // Deep-link: уведомления/боты шлют /tasks/{id} и /projects/{id}. Отдельной
        // страницы /tasks больше нет — задачи открываются глобальной модалкой
        // (useEntityEditor перехватывает клик по уведомлению). Прямой URL
        // /tasks/{id} в браузере редиректим на /projects?open= не имеет смысла,
        // поэтому редирект /tasks/:id удалён вместе со страницей. Проекты — как есть.
        {
          path: "projects/:projectId",
          redirect: (to) => ({ name: "projects", query: { open: String(to.params.projectId) } }),
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
          path: "soe-health",
          name: "soe-health",
          component: () => import("@/views/SoeHealthDashboard.vue"),
          meta: { title: "SOE Health Check Tool", requiresPermission: "financials.view" },
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
          // Temp external redirect per user request 2026-05-23.
          // Чтобы вернуть локальный модуль — удалить `beforeEnter`.
          path: "finmodel",
          name: "finmodel",
          component: () => import("@/views/finmodel/FinModelPage.vue"),
          meta: { title: "Финансовая модель", requiresPermission: "finmodel.view" },
          beforeEnter: (_to, _from, next) => {
            window.location.assign(
              "https://dashboard.uz-assets.uz/soe-dashboard/finmodel-3?currency=UZS&unit=B&modelId=50&sector=mining&company=org-33",
            );
            next(false);
          },
        },
        // UAP-specific airport-style FinModel v1 (миграция 1:1 из легасиа)
        {
          path: "finmodel/uap/v1",
          name: "finmodel-uap-v1",
          component: () => import("@/views/finmodel/FinModelUapV1.vue"),
          meta: { title: "FinModel · Uzbekistan Airports v1", requiresPermission: "finmodel.view" },
        },
        {
          path: "business-plan",
          name: "business-plan",
          component: () => import("@/views/BusinessPlan.vue"),
          meta: { title: "Бизнес-план", requiresPermission: "bp.view" },
        },
        {
          // Temp external redirect per user request 2026-05-23.
          // Чтобы вернуть локальный модуль — удалить `beforeEnter`.
          path: "credit-portfolio",
          name: "credit-portfolio",
          component: () => import("@/views/CreditPortfolio.vue"),
          meta: { title: "Кредитный портфель", requiresPermission: "credit.view" },
          beforeEnter: (_to, _from, next) => {
            // assign() (push), не replace() — так current history entry
            // (тот dashboard с которого пришли) сохраняется, и Back в
            // браузере возвращает на него вместо infinite-loop через
            // этот же guard.
            window.location.assign(
              "https://dashboard.uz-assets.uz/soe-dashboard/credits?tab=overview",
            );
            // `next(false)` отменяет Vue-навигацию, чтобы локальный
            // компонент не успел смонтироваться и моргнуть.
            next(false);
          },
        },
        {
          // Temp external redirect per user request 2026-05-23.
          // Чтобы вернуть локальный модуль — удалить `beforeEnter`.
          path: "invest-projects",
          name: "invest-projects",
          component: () => import("@/views/InvestProjects.vue"),
          meta: { title: "Инвест-проекты", requiresPermission: "investment.view" },
          beforeEnter: (_to, _from, next) => {
            // assign() (push) — оставляет current entry в history,
            // чтобы Back в браузере возвращал на dashboard.
            window.location.assign(
              "https://dashboard.uz-assets.uz/soe-dashboard/investments?view=portfolio",
            );
            next(false);
          },
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
          // 2026-05-26: добавлен requiresPermission — раньше sidebar гейтил
          // через `v-if="can('consultants.view')"`, а роут — нет → юзер мог
          // зайти по прямой ссылке /consultants и увидеть пустой UI shell.
          meta: { title: "Консультанты", requiresPermission: "consultants.view" },
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
          meta: { title: "ИИ-ассистент", requiresPermission: "ai.view" },
        },
        // RBAC v1/v2 removed — redirect to v3
        {
          path: "rbac",
          name: "rbac",
          redirect: "/admin/rbac",
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
// onboarding check — async guard, runs after standard auth check
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

// refresh user from /auth/me once per session, чтобы stale
// must_change_password из localStorage не пропускал change-password шаг
// после admin-сброса флагов на бэке.
let userRefreshed = false;
async function refreshUserFromBackend(auth: ReturnType<typeof useAuthStore>): Promise<void> {
  if (userRefreshed) return;
  userRefreshed = true;
  try {
    const { authApi } = await import("@/api/auth");
    const me = await authApi.me();
    auth.setUser(me);
  } catch {
    // если /me падает (token rotted), оставляем local state — guard позже отбракует
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

  // refresh user from backend on first nav after auth — иначе stale
  // localStorage may bypass must_change_password / mfa flags.
  // Сбрасываем флаги при logout чтобы следующий login снова refresh'нул.
  if (!auth.isAuthenticated) {
    userRefreshed = false;
    onboardingChecked = false;
  } else if (!userRefreshed) {
    await refreshUserFromBackend(auth);
  }

  // Force password change: must run FIRST and win.
  // Раньше mfa-onboarding был в исключениях → wizard MFA мог запуститься
  // до смены пароля. Это нарушает сценарий "change-password → mfa-onboarding".
  // Теперь mfa-onboarding убран из exceptions — wizard MFA не покажется
  // пока пароль не сменён.
  if (
    auth.isAuthenticated &&
    auth.user?.must_change_password === true &&
    to.name !== "change-password" &&
    to.name !== "login" &&
    to.name !== "login-mfa-step"
  ) {
    return { name: "change-password" };
  }

  // Обязательная MFA для привилегированных (owner/admin): бэкенд выставляет
  // mfa_setup_required в /auth/me. Пока 2FA не настроена — держим на онбординге
  // (149 п.6.14, 841 5.3.3.1). Идёт ПОСЛЕ смены пароля, ДО обычного онбординга.
  if (
    auth.isAuthenticated &&
    auth.user?.must_change_password !== true &&
    (auth.user as any)?.mfa_setup_required === true &&
    to.name !== "mfa-onboarding" &&
    to.name !== "change-password" &&
    to.name !== "login" &&
    to.name !== "login-mfa-step"
  ) {
    return { name: "mfa-onboarding" };
  }

  // redirect to onboarding wizard on first authenticated nav.
  // Runs once per session to avoid hitting backend on every route change.
  // НЕ запускаем onboarding-check если still need password change
  // (password-check выше уже должен был перенаправить).
  if (
    auth.isAuthenticated &&
    auth.user?.must_change_password !== true &&
    !onboardingChecked &&
    to.name !== "mfa-onboarding" &&
    to.name !== "login" &&
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
      // harder gate — DB-консоль для owner/admin
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
