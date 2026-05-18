<script setup lang="ts">
/**
 * AppShell — главный layout приложения UzAssets.
 *
 *   • UzAssets logo + bell + "ЕДИНАЯ ПЛАТФОРМА ТРАНСФОРМАЦИИ"
 *   • 10 пунктов меню в стабильном порядке
 *   • 2 collapsible groups: Финансы, Закупки
 *   • Executive Dashboard — AMBER + Review badge (первый пункт)
 *   • BETA badges на soft-launch features
 *   • RBAC только для admin
 *
 * Минимальный script setup — без auth store dependency.
 * isAdmin() читает из localStorage/sessionStorage 'uz_user' с fallback false.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch , provide } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import SidebarCompaniesSection from "@/components/SidebarCompaniesSection.vue";
import { useAuthStore } from "@/stores/auth";
import { useNotificationsStore } from "@/stores/notifications";
import NotificationBell from "@/components/notifications/NotificationBell.vue";
import NotificationToast from "@/components/notifications/NotificationToast.vue";
import EptLogo from "@/components/EptLogo.vue";
import AppTopbar from "@/components/AppTopbar.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

// ─── State ───
// Pack 7.57: persist sidebarCollapsed in localStorage.
// Default: user preference if set, else auto-collapse on narrow screens.
const LS_SIDEBAR_KEY = "uz_sidebar_collapsed_v1";
function loadSidebarPref(): boolean | null {
  try {
    const raw = localStorage.getItem(LS_SIDEBAR_KEY);
    if (raw === "true") return true;
    if (raw === "false") return false;
  } catch { /* noop */ }
  return null;
}
const _userPref = loadSidebarPref();
const sidebarCollapsed = ref(
  _userPref !== null
    ? _userPref
    : typeof window !== "undefined" && window.matchMedia
      ? window.matchMedia("(max-width: 1366px)").matches
      : false
);
if (typeof window !== "undefined" && window.matchMedia && _userPref === null) {
  // Only auto-react to viewport if user hasn't explicitly set a preference
  const mq = window.matchMedia("(max-width: 1366px)");
  const handler = (e: MediaQueryListEvent) => { sidebarCollapsed.value = e.matches; };
  mq.addEventListener("change", handler);
}
const mobileSidebarOpen = ref(false);

const LS_GROUPS_KEY = "uz_sidebar_groups_v1";

function loadGroups(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(LS_GROUPS_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      return {
        finance: p.finance !== false,
        procurement: p.procurement !== false,
      };
    }
  } catch (_) { /* noop */ }
  return { finance: true, procurement: true };
}

const openGroups = ref<Record<string, boolean>>(loadGroups());

function toggleGroup(name: string): void {
  openGroups.value[name] = !openGroups.value[name];
  try {
    localStorage.setItem(LS_GROUPS_KEY, JSON.stringify(openGroups.value));
  } catch (_) { /* noop */ }
}

// ─── Sidebar collapse ───
function toggleSidebar(): void {
  sidebarCollapsed.value = !sidebarCollapsed.value;
  // Pack 7.57: persist user preference
  try {
    localStorage.setItem(LS_SIDEBAR_KEY, String(sidebarCollapsed.value));
  } catch { /* noop */ }
}
provide('toggleSidebar', toggleSidebar);

function toggleMobileSidebar(): void {
  mobileSidebarOpen.value = !mobileSidebarOpen.value;
}

// Mobile: закрывать sidebar после navigation
watch(() => route.fullPath, () => {
  if (typeof window !== "undefined" && window.innerWidth < 1024) {
    mobileSidebarOpen.value = false;
  }
});

// ─── Auth ───
function isAdmin(): boolean {
  if (!auth.user) return false;
  const u: any = auth.user;
  if (u.is_owner === true || u.is_admin === true) return true;
  const roles: string[] = Array.isArray(u.roles) ? u.roles : [];
  return roles.includes("admin") || roles.includes("ROLE_ADMIN") || roles.includes("ROLE_OWNER");
}

// Pack 148-followup: sidebar items are now gated by the same permission
// codes the router enforces. `auth.hasPermission` already bypasses for
// owner + role admin so they keep seeing every section.
const can = (code: string) => auth.hasPermission(code);
// Group visibility: show the collapsible header iff at least one sub-link
// is visible to this user.
const showFinanceGroup = computed(() =>
  can("financials.view") || can("finmodel.view")
    || can("credit.view") || can("investment.view"),
);
const showProcurementGroup = computed(() => can("procurement.view"));
function canViewAudit(): boolean {
  if (!auth.user) return false;
  const u: any = auth.user;
  if (u.is_owner === true) return true;
  const roles: string[] = Array.isArray(u.roles) ? u.roles : [];
  if (roles.includes("admin") || roles.includes("ROLE_ADMIN") || roles.includes("ROLE_OWNER")) return true;
  const perms: string[] = Array.isArray(u.permissions) ? u.permissions : [];
  return perms.includes("audit.view");
}
function logout(): void {
  auth.clear();
  void router.push({ name: "login" });
}

// ─── Mobile detection ───
function checkMobile(): void {
  if (typeof window === "undefined") return;
  if (window.innerWidth >= 1024) {
    mobileSidebarOpen.value = false;
  }
}

const notifStore = useNotificationsStore();

onMounted(() => {
  checkMobile();
  window.addEventListener("resize", checkMobile);
  // Pack 11.0: connect notifications WS + start polling fallback
  if (auth.isAuthenticated) {
    notifStore.start();
  }
});

watch(() => auth.isAuthenticated, (isAuth) => {
  if (isAuth) notifStore.start();
  else        notifStore.stop();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", checkMobile);
  notifStore.stop();
});

// Pack 144: preview_token handler + impersonate banner
import { ref as _impRef, onMounted as _impOnMounted } from 'vue';
import ImpersonateBanner from '@/components/rbac-v3/ImpersonateBanner.vue';
const _impEmail = _impRef<string | null>(null);
const _impActive = _impRef<boolean>(false);
_impOnMounted(() => {
  // First: detect ?preview_token in URL and stash it
  const url = new URL(window.location.href);
  const tok = url.searchParams.get('preview_token');
  const targetEmail = url.searchParams.get('preview_email');
  if (tok) {
    // Save current real token for later restore
    const currentToken = localStorage.getItem('uza_access_token');
    const currentRefresh = localStorage.getItem('uza_refresh_token');
    if (currentToken && !localStorage.getItem('uza_preview_real_token')) {
      localStorage.setItem('uza_preview_real_token', currentToken);
      if (currentRefresh) localStorage.setItem('uza_preview_real_refresh', currentRefresh);
    }
    // Apply preview token
    localStorage.setItem('uza_access_token', tok);
    localStorage.removeItem('uza_refresh_token'); // preview cannot refresh
    if (targetEmail) localStorage.setItem('uza_preview_email', targetEmail);
    // Clean URL and reload to make stores pick up new identity
    url.searchParams.delete('preview_token');
    url.searchParams.delete('preview_email');
    window.history.replaceState({}, '', url.toString());
    window.location.reload();
    return;
  }
  // Restore previous state on subsequent mounts
  if (localStorage.getItem('uza_preview_real_token')) {
    _impActive.value = true;
    _impEmail.value = localStorage.getItem('uza_preview_email') || 'другой пользователь';
  }
});
function exitImpersonate() {
  const realToken = localStorage.getItem('uza_preview_real_token');
  const realRefresh = localStorage.getItem('uza_preview_real_refresh');
  if (realToken) {
    localStorage.setItem('uza_access_token', realToken);
    if (realRefresh) localStorage.setItem('uza_refresh_token', realRefresh);
    localStorage.removeItem('uza_preview_real_token');
    localStorage.removeItem('uza_preview_real_refresh');
    localStorage.removeItem('uza_preview_email');
    window.location.href = '/';
  } else {
    // No backup — just clear preview token (forces re-login)
    localStorage.removeItem('uza_access_token');
    localStorage.removeItem('uza_preview_email');
    window.location.href = '/login';
  }
}
</script>

<template>
  <ImpersonateBanner v-if="_impActive" :target-email="_impEmail || ''" @exit="exitImpersonate" />
  <div class="uza-shell">
    <!-- Mobile overlay -->
    <div
      v-if="mobileSidebarOpen"
      class="uza-overlay"
      @click="mobileSidebarOpen = false"
    />

    <!-- ═══════════ SIDEBAR ═══════════ -->
    <aside
      class="uza-aside"
      :class="{
        collapsed: sidebarCollapsed,
        'mobile-open': mobileSidebarOpen,
      }"
    >
      <!-- Header: UzAssets logo -->
      <div class="sb-header">
        <RouterLink to="/" class="sb-brand" title="UzAssets">
          <EptLogo :size="40" />
          <span class="sb-brand-divider"></span>
          <span class="sb-brand-tagline">Единая платформа трансформации</span>
        </RouterLink>
      </div>


      <!-- Navigation -->
      <nav class="sb-body">

        <!-- ИИ-ассистент — premium card (Pack 7.44 — main value-prop) -->
        <RouterLink v-if="can('ai.chat')" to="/ai-chat" class="ai-pcard" active-class="ai-pcard-active" title="ИИ-ассистент">
          <span class="ai-pcard-pulse"></span>
          <div class="ai-pcard-logo">
            <EptLogo :size="22" />
          </div>
          <div class="ai-pcard-txt">
            <div class="ai-pcard-t1">
              ИИ-ассистент
              <span class="ai-pcard-beta">BETA</span>
            </div>

          </div>
        </RouterLink>

        <div v-if="can('ai.chat')" class="ai-pcard-divider"></div>
        <!-- 1. Executive Dashboard (AMBER) — same gate as the route -->
        <RouterLink
          v-if="can('financials.view')"
          to="/executive-dashboard"
          class="sb-item sb-exec-dash"
          active-class="active"
        >
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <path d="M3 3v18h18" />
            <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3" />
          </svg>
          <span class="sb-name">Executive Dashboard</span>
          <span class="sb-exec-badge">Review</span>
        </RouterLink>

        <!-- 2. Проекты трансформации (dashboard — без gate, главная страница) -->
        <RouterLink to="/dashboard" class="sb-item" active-class="active">
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
          </svg>
          <span class="sb-name">Проекты трансформации</span>
        </RouterLink>

        <!-- 3. Финансы (collapsible) — скрываем целиком если нет ни одного suб-доступа -->
        <template v-if="showFinanceGroup">
          <div
            class="sb-section sb-section-toggle"
            :aria-expanded="openGroups.finance"
            tabindex="0"
            @click="toggleGroup('finance')"
            @keydown.enter="toggleGroup('finance')"
            @keydown.space.prevent="toggleGroup('finance')"
          >
            <svg
              width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"
            >
              <line x1="6" y1="20" x2="6" y2="14" />
              <line x1="12" y1="20" x2="12" y2="8" />
              <line x1="18" y1="20" x2="18" y2="11" />
            </svg>
            <span class="sb-section-title">Финансы</span>
            <span class="sb-chevron" :class="{ open: openGroups.finance }"></span>
          </div>
          <div class="sb-section-body" :class="{ open: openGroups.finance }">
            <RouterLink v-if="can('financials.view')" to="/financials" class="sb-item sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Обзор портфеля</span>
            </RouterLink>

            <RouterLink v-if="can('finmodel.view')" to="/fin-model" class="sb-item sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Финансовая модель</span>
            </RouterLink>

            <RouterLink v-if="can('credit.view')" to="/credit-portfolio" class="sb-item sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Кредитный портфель</span>
            </RouterLink>

            <RouterLink v-if="can('investment.view')" to="/invest-projects" class="sb-item sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Инвест-проекты</span>
            </RouterLink>
          </div>
        </template>

        <!-- 4. Бизнес-план -->
        <RouterLink v-if="can('bp.view')" to="/business-plan" class="sb-item" active-class="active">
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="8" y1="13" x2="16" y2="13" />
            <line x1="8" y1="17" x2="13" y2="17" />
          </svg>
          <span class="sb-name">Бизнес-план</span>
        </RouterLink>

        <!-- 5. KPI -->
        <RouterLink v-if="can('kpi.view')" to="/kpi" class="sb-item" active-class="active">
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
          <span class="sb-name">KPI</span>
        </RouterLink>

        <!-- 6. Корпоративное управление -->
        <RouterLink v-if="can('governance.view')" to="/governance" class="sb-item" active-class="active">
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <path d="M3 21h18" />
            <path d="M5 21V8l7-5 7 5v13" />
            <path d="M9 21V12h6v9" />
          </svg>
          <span class="sb-name">Корпоративное управление</span>
        </RouterLink>

        <!-- 7. ESG -->
        <RouterLink v-if="can('esg.view')" to="/esg" class="sb-item" active-class="active">
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <path d="M12 2c4 4 7 8 7 12a7 7 0 1 1-14 0c0-4 3-8 7-12z" />
            <path d="M12 12v9" />
          </svg>
          <span class="sb-name">ESG</span>
        </RouterLink>

        <!-- 8. Закупки (collapsible) — скрываем целиком если нет procurement.view -->
        <template v-if="showProcurementGroup">
          <div
            class="sb-section sb-section-toggle"
            :aria-expanded="openGroups.procurement"
            tabindex="0"
            @click="toggleGroup('procurement')"
            @keydown.enter="toggleGroup('procurement')"
            @keydown.space.prevent="toggleGroup('procurement')"
          >
            <svg
              width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"
            >
              <circle cx="9" cy="21" r="1" />
              <circle cx="20" cy="21" r="1" />
              <path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6" />
            </svg>
            <span class="sb-section-title">Закупки</span>
            <span class="sb-chevron" :class="{ open: openGroups.procurement }"></span>
          </div>
          <div class="sb-section-body" :class="{ open: openGroups.procurement }">
            <RouterLink to="/procurement/forensic" class="sb-item sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Закупки и форензик-аудит</span>
            </RouterLink>
            <RouterLink to="/procurement/analysis" class="sb-item sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Анализ закупочной деятельности государственных компаний</span>
            </RouterLink>
          </div>
        </template>

        <!-- 9. Консультанты (no dedicated permission — visible to all auth'd users) -->
        <RouterLink to="/consultants" class="sb-item" active-class="active">
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
          <span class="sb-name">Консультанты</span>
        </RouterLink>

        <!-- 10. Рейтинги -->
        <RouterLink v-if="can('ratings.view')" to="/ratings" class="sb-item" active-class="active">
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
          <span class="sb-name">Рейтинги</span>
        </RouterLink>

        <!-- 11. Компании (раскрывающийся раздел с компаниями по секторам) -->
        <SidebarCompaniesSection />



        <!-- Admin (если isAdmin) -->
        <template v-if="isAdmin()">
          <div class="sb-admin-divider"></div>
          <!-- Pack 141: RBAC v3 (parallel new admin panel) -->
          <RouterLink to="/admin/rbac-v3" class="sb-item sb-item-admin" active-class="active">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2l7 4v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/>
            </svg>
            <span class="sb-name">RBAC v3 · доступы</span>
            <span style="margin-left:auto;padding:1px 6px;background:#1D9E75;color:#fff;border-radius:7px;font-size:8.5px;font-weight:500;letter-spacing:.05em;">NEW</span>
          </RouterLink>

          <!-- Pack 148-followup: Moderation (orphaned after RBAC v2 removal) -->
          <RouterLink
            v-if="can('moderation.review')"
            to="/admin/moderation"
            class="sb-item sb-item-admin"
            active-class="active"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 12l2 2 4-4"/>
              <path d="M21 12c0 4.97-4.03 9-9 9s-9-4.03-9-9 4.03-9 9-9c2.4 0 4.58.94 6.19 2.46"/>
            </svg>
            <span class="sb-name">Модерация</span>
          </RouterLink>

          <!-- Pack 148 D: Companies admin (создание + редактирование) -->
          <RouterLink
            v-if="can('companies.edit')"
            to="/admin/companies-legacy"
            class="sb-item sb-item-admin"
            active-class="active"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 21h18"/>
              <path d="M5 21V7l8-4v18"/>
              <path d="M19 21V11l-6-4"/>
              <path d="M9 9v.01"/>
              <path d="M9 12v.01"/>
              <path d="M9 15v.01"/>
              <path d="M9 18v.01"/>
            </svg>
            <span class="sb-name">Компании и сектора</span>
          </RouterLink>

                    <!-- Pack 7.35: системные константы -->
          <RouterLink to="/admin/system-config" class="sb-item sb-item-admin sb-item-macro" active-class="active">
            <svg
              width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"
            >
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            <span class="sb-name">Macro Indicators</span>
            <span class="sb-macro-beta">BETA</span>
          </RouterLink>
          <!-- Pack 11.2: Admin Broadcasts -->
          <RouterLink to="/admin/broadcasts" class="sb-item sb-item-admin" active-class="active">
            <svg
              width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"
            >
              <path d="M3 11l18-5v12L3 14v-3z" />
              <path d="M11.6 16.8a3 3 0 1 1-5.8-1.6" />
            </svg>
            <span class="sb-name">Кастомные рассылки</span>
          </RouterLink>
          <!-- Pack 12.0: API Catalog + Service accounts -->
          <RouterLink to="/admin/api" class="sb-item sb-item-admin" active-class="active">
            <svg
              width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"
            >
              <path d="M4 13h3v-3H4v3zm6 0h10v-3H10v3zm0-8h10V2H10v3zM4 5h3V2H4v3zm6 16h10v-3H10v3zM4 21h3v-3H4v3z" />
            </svg>
            <span class="sb-name">API &amp; Интеграции</span>
          </RouterLink>
        </template>

        <!-- Pack 9.2.2: Audit log moved into RBAC v2 (tab "Журнал активности") — sidebar item removed -->
      </nav>

      <!-- Footer: notification bell + logout -->
      <div class="sb-footer">
        <NotificationBell class="sb-notif-bell" />
        <button class="sb-logout" type="button" @click="logout" title="Выйти">
          <svg
            width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          <span>Выйти</span>
        </button>
      </div>
    </aside>

    <!-- Pack 11.0: Toast stack mounted globally -->
    <NotificationToast />

    <!-- ═══════════ Pack 7.57: GLOBAL SIDEBAR TOGGLE ═══════════ -->
    <!-- ═══════════ MAIN ═══════════ -->
    <div class="uza-main-col">
      <AppTopbar />
      <main class="uza-main">
        <RouterView v-slot="{ Component, route }">
        <Transition name="uza-page" mode="out-in">
          <component :is="Component" :key="route.fullPath" />
        </Transition>
      </RouterView>
      </main>
    </div>
  </div>
</template>

<style scoped>
/* ─────────────────────────── Layout ─────────────────────────── */
.uza-shell {
  display: grid;
  grid-template-columns: auto 1fr;
  width: 100%;
  min-height: 100vh;
  background: #F4F3F9;
  font-family: var(--font, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
}
.uza-main-col {
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
}

.uza-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.55);
  z-index: 90;
  backdrop-filter: blur(2px);
}

.uza-aside {
  width: 248px;
  flex-shrink: 0;
  background: linear-gradient(180deg, #161A36 0%, #1B1F3D 100%);
  color: rgba(255, 255, 255, 0.86);
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: hidden; /* scroll moved to .sb-body */

  z-index: 100;
  border-right: 1px solid rgba(255, 255, 255, 0.04);
  /* Pack 7.57: smooth collapse animation */
  transition: width 0.28s cubic-bezier(0.34, 1.2, 0.64, 1);
}
/* aside scrollbar rules removed — scroll moved to .sb-body */

.uza-aside.collapsed { width: 56px; }

.uza-main {
  flex: 1;
  min-width: 0;
  position: relative;
}

.uza-mobile-toggle {
  display: none;
  position: fixed;
  top: 12px;
  left: 12px;
  width: 36px;
  height: 36px;
  background: #1E2A4A;
  color: #fff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  z-index: 60;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.18);
  align-items: center;
  justify-content: center;
}

/* ─────────────────────────── Sidebar Header ─────────────────────────── */
.sb-header {
  padding: 16px 10px 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.uza-aside.collapsed .sb-brand { display: none; }

.sb-brand {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  min-width: 0;
}

.sb-brand-logo {
  height: 24px;
  width: auto;
  display: block;
  object-fit: contain;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.25));
}

.sb-brand-divider {
  width: 1px;
  align-self: stretch;
  min-height: 36px;
  max-height: 60px;
  background: rgba(255, 255, 255, 0.18);
  flex-shrink: 0;
  opacity: 0;
  animation: sb-divider-in 0.4s cubic-bezier(0.25, 0.85, 0.3, 1) 1.3s forwards;
}

.sb-brand-tagline {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.3;
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
  hyphens: none;
  animation: sb-tagline-slide 0.85s cubic-bezier(0.25, 0.85, 0.3, 1) 1.5s both;
}

@keyframes sb-icon-in {
  from { opacity: 0; transform: translateX(-6px) scale(.85); }
  to   { opacity: .85; transform: translateX(0) scale(1); }
}
@keyframes sb-icon-pulse {
  0%, 100% { filter: drop-shadow(0 0 6px rgba(127, 119, 221, .35)); }
  50%      { filter: drop-shadow(0 0 12px rgba(127, 119, 221, .65)); }
}
@keyframes sb-icon-pulse-amber {
  0%, 100% { filter: drop-shadow(0 0 6px rgba(250, 199, 117, .4)); }
  50%      { filter: drop-shadow(0 0 12px rgba(250, 199, 117, .7)); }
}
@keyframes sb-divider-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@keyframes sb-tagline-slide {
  0%   {
    opacity: 0;
    clip-path: inset(0 100% 0 0);
    transform: translateX(-8px);
  }
  60%  { opacity: 1; }
  100% {
    opacity: 1;
    clip-path: inset(0 0 0 0);
    transform: translateX(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .sb-brand-divider,
  .sb-brand-tagline {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
    clip-path: none !important;
  }
}



.sb-subtitle {
  padding: 6px 14px 12px;
  font-size: 9px;
  letter-spacing: 0.08em;
  color: rgba(255, 255, 255, 0.42);
  text-transform: uppercase;
  font-weight: 600;
}

/* ─────────────────────────── Nav body ─────────────────────────── */
.sb-body {
    flex: 1 1 0;
    display: block;  /* flex caused children to shrink instead of scroll */
    /* flex-direction removed (no longer flex) */
    padding: 4px 8px 8px;
    gap: 1px;
    overflow-y: scroll;  /* always show scrollbar */
    overflow-x: hidden;
    min-height: 0; /* критично для flex-child скролла */
    /* Тонкий кастомный скроллбар в стиле UzAssets */
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 255, 255, 0.18) transparent;
  }
  .sb-body::-webkit-scrollbar {
    width: 6px;
  }
  .sb-body::-webkit-scrollbar-track {
    background: transparent;
  }
  .sb-body::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.14);
    border-radius: 3px;
    transition: background 200ms;
  }
  .sb-body::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.28);
  }


/* ─────────── ИИ-ассистент premium card (Pack 7.44, Вариант A) ─────────── */
.ai-pcard {
  position: relative;
  display: flex; align-items: center; gap: 9px;
  margin: 3px 4px 5px;
  padding: 8px 10px 8px 10px;
  border-radius: 10px;
  background: linear-gradient(135deg, #7F77DD 0%, #534AB7 50%, #4F8AE0 100%);
  text-decoration: none;
  cursor: pointer;
  overflow: hidden;
  box-shadow: 0 3px 12px rgba(127, 119, 221, .32);
  transition: transform .2s, box-shadow .2s;
}
.ai-pcard:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 22px rgba(127, 119, 221, .50);
}
.ai-pcard::before {
  content: ""; position: absolute; inset: 0;
  background: radial-gradient(circle at 80% 20%, rgba(255, 255, 255, .18), transparent 50%);
  pointer-events: none;
}
.ai-pcard::after {
  content: ""; position: absolute; top: 0; left: -100%; right: 0; bottom: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .18), transparent);
  animation: ai-pcard-shine 3.5s ease-in-out infinite;
  pointer-events: none;
}
@keyframes ai-pcard-shine {
  0%, 100% { left: -100%; }
  50%      { left: 100%; }
}
.ai-pcard-logo {
  width: 28px; height: 28px;
  border-radius: 7px;
  background: rgba(255, 255, 255, .18);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  position: relative; z-index: 1;
  animation: ai-pcard-breathe 3s ease-in-out infinite;
}
@keyframes ai-pcard-breathe {
  0%, 100% { transform: scale(1); }
  50%      { transform: scale(1.08); }
}
.ai-pcard-txt {
  flex: 1; min-width: 0;
  position: relative; z-index: 1;
}
.ai-pcard-t1 {
  color: #fff;
  font-size: 12px; font-weight: 500;
  line-height: 1.15;
  letter-spacing: -0.005em;
  display: flex; align-items: center; gap: 5px; flex-wrap: nowrap;
}
.ai-pcard-beta {
  display: inline-block;
  font-size: 7.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #fff;
  background: rgba(255, 255, 255, .22);
  -webkit-backdrop-filter: blur(4px);
  backdrop-filter: blur(4px);
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid rgba(255, 255, 255, .35);
  text-transform: uppercase;
  line-height: 1.3;
  flex-shrink: 0;
}
.ai-pcard-t2 {
  color: rgba(255, 255, 255, .82);
  font-size: 10px;
  margin-top: 3px;
  letter-spacing: 0.04em;
  text-transform: lowercase;
}
.ai-pcard-pulse {
  position: absolute; top: 6px; right: 7px;
  width: 6px; height: 6px; border-radius: 50%;
  background: #5DCAA5; z-index: 2;
  box-shadow: 0 0 0 0 rgba(93, 202, 165, .6);
  animation: ai-pcard-dot 1.8s ease-out infinite;
}
@keyframes ai-pcard-dot {
  0%   { box-shadow: 0 0 0 0 rgba(93, 202, 165, .6); }
  70%  { box-shadow: 0 0 0 8px rgba(93, 202, 165, 0); }
  100% { box-shadow: 0 0 0 0 rgba(93, 202, 165, 0); }
}
.ai-pcard.ai-pcard-active {
  box-shadow: 0 4px 22px rgba(127, 119, 221, .65),
              inset 0 0 0 1.5px rgba(255, 255, 255, .35);
}
.ai-pcard-divider {
  height: 1px;
  background: rgba(255, 255, 255, .08);
  margin: 4px 12px 8px;
}
.uza-aside.collapsed .ai-pcard-txt,
.uza-aside.collapsed .ai-pcard-pulse,
.uza-aside.collapsed .ai-pcard-divider { display: none; }
.uza-aside.collapsed .ai-pcard { padding: 10px; justify-content: center; }
/* Generic sb-item */
.sb-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.72);
  text-decoration: none;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: -0.005em;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  position: relative;
  user-select: none;
}
.sb-item svg {
  flex-shrink: 0;
  opacity: 0.85;
  color: rgba(255, 255, 255, 0.60);
}
.sb-item .sb-name {
  flex: 1;
  min-width: 0;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sb-item:hover {
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.95);
}
.sb-item:hover svg {
  color: rgba(255, 255, 255, 0.95);
  transform: scale(1.12) rotate(-3deg);
  opacity: 1;
}
.sb-item.active {
  background: rgba(127, 119, 221, 0.14);
  color: #fff;
}
.sb-item.active svg {
  color: #B5AEEC;
  opacity: 1;
  transform: scale(1.06);
  animation: sb-icon-pulse 2.6s ease-in-out infinite, sb-icon-in .55s cubic-bezier(.34, 1.2, .64, 1) both;
}

/* Executive Dashboard — AMBER (1:1 #exec-dash-nav-btn) */
.sb-item.sb-exec-dash {
  color: rgba(250, 199, 117, 0.92) !important;
  font-weight: 700;
}
.sb-item.sb-exec-dash svg {
  color: rgba(250, 199, 117, 0.78);
  opacity: 1;
}
.sb-item.sb-exec-dash:hover {
  background: rgba(250, 199, 117, 0.06) !important;
  color: #FAC775 !important;
}
.sb-item.sb-exec-dash.active {
  background: rgba(250, 199, 117, 0.12) !important;
  color: #fff !important;
  box-shadow: inset 2px 0 0 0 #FAC775;
}
.sb-item.sb-exec-dash.active svg {
  color: #FAC775;
  transform: scale(1.06);
  animation: sb-icon-pulse-amber 2.6s ease-in-out infinite;
}

.sb-exec-badge {
  margin-left: auto;
  font-size: 9px;
  font-weight: 600;
  color: rgba(250, 199, 117, 0.65);
  letter-spacing: 0.04em;
  background: rgba(250, 199, 117, 0.10);
  padding: 1px 7px;
  border-radius: 4px;
  border: 1px solid rgba(250, 199, 117, 0.18);
  text-transform: capitalize;
  flex-shrink: 0;
}

/* BETA badges removed Pack 7.44 */

/* Section toggle (Финансы / Закупки) */
.sb-section.sb-section-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.78);
  font-size: 12px;
  font-weight: 500;
  border-radius: 6px;
  transition: background 0.12s, color 0.12s;
  user-select: none;
}
.sb-section.sb-section-toggle:hover {
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.95);
}
.sb-section.sb-section-toggle svg {
  flex-shrink: 0;
  opacity: 0.85;
  color: rgba(255, 255, 255, 0.60);
}
.sb-section-title {
  flex: 1;
  font-weight: 500;
  font-size: 12px;
  color: inherit;
}

.sb-chevron {
  width: 16px;
  height: 16px;
  position: relative;
  flex-shrink: 0;
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.sb-chevron::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  width: 7px;
  height: 7px;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  transform: translate(-50%, -65%) rotate(45deg);
  opacity: 0.7;
}
.sb-chevron.open { transform: rotate(180deg); }

/* Group body */
/* Group body — CSS Grid 0fr↔1fr pattern (no magic max-height) */
/* Group body — max-height pattern with generous limit (10000px) */
/* Group body — simple max-height transition with large limit */
.sb-section-body {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.32s cubic-bezier(0.4, 0, 0.2, 1);
}
.sb-section-body.open {
  max-height: 2000px;
}

/* Sub-items inside groups */
.sb-item.sb-sub {
  padding-left: 38px !important;
  font-size: 11.5px !important;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.62);
  display: flex;
  align-items: center;
  gap: 8px;
}
.sb-item.sb-sub:hover { color: rgba(255, 255, 255, 0.92); }
.sb-item.sb-sub.active {
  color: #fff !important;
  background: rgba(127, 119, 221, 0.10);
}

.sb-sub-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.55;
  flex-shrink: 0;
}
.sb-item.sb-sub.active .sb-sub-dot {
  background: #FAC775;
  opacity: 1;
}

/* Disabled item (Финансовая модель — не реализован) */
.sb-item.sb-disabled {
  opacity: 0.4;
  cursor: not-allowed !important;
  pointer-events: none;
}
.sb-item.sb-disabled .sb-name { color: rgba(255, 255, 255, 0.50); }

/* NEW badge for newly-added sidebar items (Pack 8.0 — Инвест-проекты) */
.sb-new-badge {
  font-size: 8.5px;
  background: #7F77DD;
  color: #fff;
  padding: 1px 5px;
  border-radius: 8px;
  font-weight: 500;
  letter-spacing: 0.04em;
  margin-left: auto;
  flex-shrink: 0;
  animation: sbNewBadgePulse 2.8s ease-in-out infinite;
}
@keyframes sbNewBadgePulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(127, 119, 221, 0.55); }
  50% { box-shadow: 0 0 0 4px rgba(127, 119, 221, 0); }
}
.sb-item.sb-new.active .sb-new-badge { background: #fff; color: #7F77DD; }

/* Admin */
.sb-admin-divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.06);
  margin: 12px 6px 6px;
}
.sb-item-admin {
  font-size: 11px !important;
  color: rgba(255, 255, 255, 0.45) !important;
}

/* ─────────────────────────── Footer: logout ─────────────────────────── */
.sb-footer {
  padding: 10px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
  display: flex;
  align-items: center;
  gap: 8px;
}
.sb-notif-bell { flex-shrink: 0; }
.sb-logout {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  padding: 7px 10px;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.50);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.sb-logout:hover {
  border-color: rgba(226, 75, 74, 0.30);
  color: #E2807F;
  background: rgba(226, 75, 74, 0.05);
}

/* ─────────────────────────── Responsive ─────────────────────────── */
@media (max-width: 1023px) {
  .uza-aside {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    transform: translateX(-100%);
    transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  }
  .uza-aside.mobile-open {
    transform: translateX(0);
  }
  .uza-overlay { display: block; }
  .uza-mobile-toggle { display: inline-flex; }
}

@media (max-width: 1023px) {
  .uza-main {
    padding-top: 56px;
  }
}

/* Sidebar collapsed state */
aside.sb-collapsed {
  width: 0 !important;
  min-width: 0 !important;
  overflow: hidden !important;
  border-right: none !important;
}
/* ─────────── Macro Indicators — pastel red accent (Pack 7.44) ─────────── */
.sb-item.sb-item-macro {
  color: rgba(240, 149, 149, 0.92) !important;
}
.sb-item.sb-item-macro svg {
  color: rgba(240, 149, 149, 0.78);
  opacity: 1;
}
.sb-item.sb-item-macro:hover {
  background: rgba(240, 149, 149, 0.06) !important;
  color: #F4B5B5 !important;
}
.sb-item.sb-item-macro:hover svg {
  color: #F4B5B5;
  transform: scale(1.12) rotate(-3deg);
}
.sb-item.sb-item-macro.active {
  background: rgba(240, 149, 149, 0.12) !important;
  color: #fff !important;
  box-shadow: inset 2px 0 0 0 #F09595;
}
.sb-item.sb-item-macro.active svg {
  color: #F09595;
  transform: scale(1.06);
  animation: sb-icon-pulse-red 2.6s ease-in-out infinite;
}
@keyframes sb-icon-pulse-red {
  0%, 100% { filter: drop-shadow(0 0 6px rgba(240, 149, 149, .4)); }
  50%      { filter: drop-shadow(0 0 12px rgba(240, 149, 149, .7)); }
}

.sb-macro-beta {
  margin-left: auto;
  font-size: 8.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #F09595;
  background: rgba(240, 149, 149, 0.10);
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid rgba(240, 149, 149, 0.30);
  text-transform: uppercase;
  line-height: 1.3;
  flex-shrink: 0;
}
</style>
