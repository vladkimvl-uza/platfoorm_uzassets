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
import GlobalEntityEditor from "@/components/GlobalEntityEditor.vue";
import { useAiActivation } from "@/composables/useAiActivation";
import { useHeartbeat } from "@/composables/usePresence";

const aiAct = useAiActivation();
const aiActive = computed(() => aiAct.state.active);
import UserProfileModal from "@/components/UserProfileModal.vue";
import WelcomeModal from "@/components/WelcomeModal.vue";
import BottomNav from "@/components/BottomNav.vue";
import EptLogo from "@/components/EptLogo.vue";
import AppTopbar from "@/components/AppTopbar.vue";
import PasswordExpiryBanner from "@/components/PasswordExpiryBanner.vue";
import AiBubble from "@/components/Ai/AiBubble.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

// Presence: фоновый heartbeat пока вкладка активна (online/away/offline).
useHeartbeat();

const showProfile = ref(false);

// Приветственное окно первого входа (показывается один раз; флаг welcome_seen).
const welcomeClosed = ref(false);
const showWelcome = computed(() =>
  !welcomeClosed.value && !!auth.user && auth.user.welcome_seen === false,
);

const profileInitials = computed(() => {
  const n = (auth.user?.full_name || auth.user?.email || "?").trim();
  const p = n.split(/\s+/);
  return ((p[0]?.[0] || "") + (p[1]?.[0] || "")).toUpperCase() || n[0]?.toUpperCase() || "?";
});

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

// Красные счётчики «новых событий» в сайдбаре — из непрочитанных уведомлений,
// сматченных по типу на пункт. Тип с точкой на конце = префикс (watch. → все
// watch.status/progress/...). Live-обновление через WS в notifStore.
function secBadge(types: string[]): number {
  const by = (notifStore.unreadByType || {}) as Record<string, number>;
  let n = 0;
  for (const k of Object.keys(by)) {
    for (const t of types) {
      if (t.endsWith(".") ? k.startsWith(t) : k === t) { n += by[k] || 0; break; }
    }
  }
  return n;
}
const SB = {
  projects: ["assignment", "task.status_changed", "comment.replied", "mention"],
  followed: ["watch."],
  calendar: ["deadline.approaching", "deadline.missed"],
  bp: ["bp."],
  kpi: ["kpi."],
  governance: ["governance."],
  esg: ["esg."],
  procurement: ["procurement.", "moderation.procurement"],
  ratings: ["ratings."],
  companies: ["owner.activity"],
};

onMounted(() => {
  checkMobile();
  window.addEventListener("resize", checkMobile);
  // Pack 11.0: connect notifications WS + start polling fallback
  if (auth.isAuthenticated) {
    notifStore.start();
    aiAct.load();
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
      <!-- Header: logo + tagline (3 строки колонкой справа от лого) + bell -->
      <div class="sb-header">
        <RouterLink to="/home" class="sb-brand" title="UzAssets · Единая платформа трансформации">
          <EptLogo :size="40" />
          <span class="sb-brand-tagline-stack">
            <span>Единая</span>
            <span>платформа</span>
            <span>трансформации</span>
          </span>
        </RouterLink>
        <NotificationBell class="sb-header-bell" />
      </div>


      <!-- Navigation -->
      <nav class="sb-body">

        <!-- ИИ-ассистент — premium card (Pack 7.44 — main value-prop) -->
        <RouterLink v-if="can('ai.chat')" to="/ai-chat" class="ai-pcard" :class="{ 'ai-pcard-off': !aiActive }" active-class="ai-pcard-active" :title="aiActive ? 'ИИ-ассистент' : 'ИИ-ассистент выключен'">
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

        <!-- 1b. Execution Summary — единый мониторинг всех прогрессов (только Admin/Owner) -->
        <RouterLink
          v-if="isAdmin()"
          to="/execution-summary"
          class="sb-item sb-exec-summary"
          active-class="active"
        >
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" />
            <circle cx="12" cy="12" r="3" />
          </svg>
          <span class="sb-name">Execution Summary</span>
          <span class="sb-summary-badge">Live</span>
        </RouterLink>

        <!-- 2. Проекты трансформации — показывает портфель проектов / задач;
             скрываем если у юзера нет ни projects.view, ни tasks.view (либо
             admin/owner — auth.hasPermission уже bypass'ит). -->
        <RouterLink v-if="can('projects.view') || can('tasks.view')"
                    to="/dashboard" class="sb-item" active-class="active">
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
          <span v-if="secBadge(SB.projects)" class="sb-badge">{{ secBadge(SB.projects) }}</span>
        </RouterLink>

        <!-- 2b. Отслеживаемое — проекты/задачи, на изменения которых подписан юзер -->
        <RouterLink v-if="can('projects.view') || can('tasks.view')"
                    to="/followed" class="sb-item" active-class="active">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/>
          </svg>
          <span class="sb-name">Отслеживаемое</span>
          <span v-if="secBadge(SB.followed)" class="sb-badge">{{ secBadge(SB.followed) }}</span>
        </RouterLink>

        <!-- 2c. Календарь дедлайнов (глобальный, все доступные компании) -->
        <RouterLink v-if="can('projects.view') || can('tasks.view')"
                    to="/calendar" class="sb-item" active-class="active">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
          <span class="sb-name">Календарь</span>
          <span v-if="secBadge(SB.calendar)" class="sb-badge">{{ secBadge(SB.calendar) }}</span>
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

            <!-- FinModel: единая страница с company picker в топбаре -->
            <RouterLink v-if="can('finmodel.view')" to="/finmodel" class="sb-item sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Финансовая модель</span>
              <span class="sb-ext-badge" title="Открывается на dashboard.uz-assets.uz">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                  <polyline points="15 3 21 3 21 9"/>
                  <line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
              </span>
            </RouterLink>

            <!-- Hidden per user request 2026-05-23 — оставлено
                 `false && …` чтобы быстро вернуть, сняв флаг. -->
            <RouterLink
              v-if="false && can('finmodel.view')"
              to="/finmodel/uap/v1"
              class="sb-item sb-sub"
              active-class="active"
            >
              <span class="sb-sub-dot" style="background: #534AB7"></span>
              <span class="sb-name">UAP · airport-style</span>
              <span
                style="
                  margin-left: 6px;
                  padding: 1px 5px;
                  background: rgba(127, 119, 221, 0.18);
                  color: #534AB7;
                  border-radius: 4px;
                  font-size: 9px;
                  font-weight: 700;
                  letter-spacing: 0.04em;
                "
              >v1</span>
            </RouterLink>

            <RouterLink v-if="can('credit.view')" to="/credit-portfolio" class="sb-item sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Кредитный портфель</span>
              <span class="sb-ext-badge" title="Открывается на dashboard.uz-assets.uz">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                  <polyline points="15 3 21 3 21 9"/>
                  <line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
              </span>
            </RouterLink>

            <RouterLink v-if="can('investment.view')" to="/invest-projects" class="sb-item sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Инвест-проекты</span>
              <span class="sb-ext-badge" title="Открывается на dashboard.uz-assets.uz">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                  <polyline points="15 3 21 3 21 9"/>
                  <line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
              </span>
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
          <span v-if="secBadge(SB.bp)" class="sb-badge">{{ secBadge(SB.bp) }}</span>
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
          <span v-if="secBadge(SB.kpi)" class="sb-badge">{{ secBadge(SB.kpi) }}</span>
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
          <span v-if="secBadge(SB.governance)" class="sb-badge">{{ secBadge(SB.governance) }}</span>
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
          <span v-if="secBadge(SB.esg)" class="sb-badge">{{ secBadge(SB.esg) }}</span>
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
            <RouterLink v-if="can('procurement.view') || can('forensic.view')"
                        to="/procurement/forensic" class="sb-item sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Закупки и форензик-аудит</span>
              <span v-if="secBadge(SB.procurement)" class="sb-badge">{{ secBadge(SB.procurement) }}</span>
            </RouterLink>
            <RouterLink v-if="can('procurement_analysis.view') || can('procurement.view')"
                        to="/procurement/analysis" class="sb-item sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Анализ закупочной деятельности государственных компаний</span>
            </RouterLink>
          </div>
        </template>

        <!-- 9. Консультанты — gate'им по consultants.view (admin/owner bypass) -->
        <RouterLink v-if="can('consultants.view')" to="/consultants" class="sb-item" active-class="active">
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
          <span v-if="secBadge(SB.ratings)" class="sb-badge">{{ secBadge(SB.ratings) }}</span>
        </RouterLink>

        <!-- 11. Компании (раскрывающийся раздел с компаниями по секторам) -->
        <SidebarCompaniesSection />

        <!-- Admin (если isAdmin) -->
        <template v-if="isAdmin()">
          <div class="sb-admin-divider"></div>

          <!-- Pack 141 + сборка: RBAC v3 = collapsible-группа со всеми admin-разделами -->
          <div
            class="sb-section sb-section-toggle sb-section-admin"
            :aria-expanded="openGroups.rbac"
            tabindex="0"
            @click="toggleGroup('rbac')"
            @keydown.enter="toggleGroup('rbac')"
            @keydown.space.prevent="toggleGroup('rbac')"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2l7 4v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/>
            </svg>
            <span class="sb-section-title">Настройки</span>
            <span class="sb-chevron" :class="{ open: openGroups.rbac }"></span>
          </div>
          <div class="sb-section-body" :class="{ open: openGroups.rbac }">
            <!-- Pack 141: основная страница доступов -->
            <RouterLink to="/admin/rbac-v3" class="sb-item sb-item-admin sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Доступы</span>
              <span style="margin-left:auto;padding:1px 6px;background:#1D9E75;color:#fff;border-radius:7px;font-size:8.5px;font-weight:500;letter-spacing:.05em;">NEW</span>
            </RouterLink>

            <!-- Pack 148-followup: Moderation -->
            <RouterLink
              v-if="can('moderation.review')"
              to="/admin/moderation"
              class="sb-item sb-item-admin sb-sub"
              active-class="active"
            >
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Модерация</span>
            </RouterLink>

            <!-- Pack 148 D: Companies admin -->
            <RouterLink
              v-if="can('companies.edit')"
              to="/admin/companies-legacy"
              class="sb-item sb-item-admin sb-sub"
              active-class="active"
            >
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Компании и сектора</span>
            </RouterLink>

            <!-- Pack 7.35: системные константы -->
            <RouterLink to="/admin/system-config" class="sb-item sb-item-admin sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Macro Indicators</span>
              <span class="sb-macro-beta">BETA</span>
            </RouterLink>

            <!-- Pack 11.2: Admin Broadcasts -->
            <RouterLink to="/admin/broadcasts" class="sb-item sb-item-admin sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Кастомные рассылки</span>
            </RouterLink>

            <!-- Pack 149: Catalogs (directions + consultants) -->
            <RouterLink
              v-if="can('companies.edit') || can('tasks.manage')"
              to="/admin/catalogs"
              class="sb-item sb-item-admin sb-sub"
              active-class="active"
            >
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Каталоги · направления и консультанты</span>
            </RouterLink>

            <!-- Конструктор задач — массовое заведение проектов/задач -->
            <RouterLink
              v-if="can('tasks.edit')"
              to="/project-builder"
              class="sb-item sb-item-admin sb-sub"
              active-class="active"
            >
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Конструктор задач и проектов</span>
            </RouterLink>

            <!-- Pack 149: Storage backend admin -->
            <RouterLink
              v-if="can('companies.edit') || can('tasks.manage')"
              to="/admin/storage"
              class="sb-item sb-item-admin sb-sub"
              active-class="active"
            >
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Хранилище файлов (S3)</span>
            </RouterLink>

            <!-- Pack 149: DB-консоль (только owner/admin) -->
            <RouterLink
              v-if="isAdmin()"
              to="/admin/database"
              class="sb-item sb-item-admin sb-sub"
              active-class="active"
            >
              <span class="sb-sub-dot"></span>
              <span class="sb-name">База данных</span>
              <span class="sb-macro-beta" style="background: rgba(226,75,74,.15); color: #C36868;">RAW</span>
            </RouterLink>

            <!-- Pack 150: TLS-сертификат (только owner/admin) -->
            <RouterLink
              v-if="isAdmin()"
              to="/admin/tls"
              class="sb-item sb-item-admin sb-sub"
              active-class="active"
            >
              <span class="sb-sub-dot"></span>
              <span class="sb-name">TLS сертификат</span>
            </RouterLink>

            <!-- Настройка SMTP / email-уведомлений (owner/admin) -->
            <RouterLink
              v-if="isAdmin()"
              to="/admin/email-settings"
              class="sb-item sb-item-admin sb-sub"
              active-class="active"
            >
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Почта и уведомления (SMTP)</span>
            </RouterLink>

            <!-- API & Интеграции (слиты в «Настройки») -->
            <RouterLink to="/admin/api" class="sb-item sb-item-admin sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Каталог API</span>
            </RouterLink>
            <RouterLink to="/api-docs" class="sb-item sb-item-admin sb-sub" active-class="active">
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Документация API</span>
            </RouterLink>

            <!-- Библиотека компаний (MDM) — слита в «Настройки» -->
            <RouterLink
              v-if="can('companies.view')"
              to="/library/companies"
              class="sb-item sb-item-admin sb-sub"
              active-class="active"
            >
              <span class="sb-sub-dot"></span>
              <span class="sb-name">Библиотека · Компании</span>
            </RouterLink>
          </div>
        </template>

        <!-- Pack 9.2.2: Audit log moved into RBAC v2 (tab "Журнал активности") — sidebar item removed -->
      </nav>

      <!-- Footer: профиль-чип + logout -->
      <div class="sb-footer">
        <button class="sb-profile" type="button" @click="showProfile = true" title="Профиль и настройки">
          <span class="sb-profile-av">
            <img v-if="auth.user?.avatar_url" :src="auth.user.avatar_url" alt="" />
            <template v-else>{{ profileInitials }}</template>
          </span>
          <span class="sb-profile-txt">
            <span class="sb-profile-name">{{ auth.user?.full_name || auth.user?.email || 'Профиль' }}</span>
            <span class="sb-profile-sub">{{ auth.user?.job_title || 'настройки профиля' }}</span>
          </span>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-left:auto;opacity:.6"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </button>
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

    <!-- Глобальная модалка задачи/проекта (открывается из уведомлений поверх
         текущей страницы, без навигации на /tasks) -->
    <GlobalEntityEditor />

    <!-- Личный кабинет (профиль/пароль/безопасность) -->
    <UserProfileModal v-if="showProfile" @close="showProfile = false" />

    <!-- Приветствие при первом входе -->
    <WelcomeModal v-if="showWelcome" @close="welcomeClosed = true" />

    <!-- Мобильная нижняя навигация (показывается только ≤768px) -->
    <BottomNav @menu="mobileSidebarOpen = true" />

    <!-- Pack 7.9e: Floating AI Bubble — отключено по запросу пользователя -->
    <!-- <AiBubble /> -->

    <!-- ═══════════ Pack 7.57: GLOBAL SIDEBAR TOGGLE ═══════════ -->
    <!-- ═══════════ MAIN ═══════════ -->
    <div class="uza-main-col">
      <AppTopbar />
      <PasswordExpiryBanner />
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
  background: var(--bg);
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
  background: linear-gradient(180deg, #0C1230 0%, #111A3E 100%);
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
  transition: width 0.28s var(--ease-standard);
}
/* aside scrollbar rules removed — scroll moved to .sb-body */

.uza-aside.collapsed { width: 56px; }

/* Премиум: амбиентное фиолетовое свечение вверху сайдбара (дышит) */
.uza-aside::before {
  content: "";
  position: absolute;
  top: -60px; left: -30px; right: -30px;
  height: 220px;
  background: radial-gradient(70% 100% at 25% 0%, rgba(127,119,221,.20), transparent 72%);
  pointer-events: none;
  z-index: 0;
  animation: sbAurora 10s ease-in-out infinite;
}
@keyframes sbAurora {
  0%, 100% { opacity: .6;  transform: translate3d(0, 0, 0); }
  50%      { opacity: 1;   transform: translate3d(14px, 6px, 0); }
}
.sb-header, .sb-body { position: relative; z-index: 1; }

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
  padding: 14px 10px 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  min-width: 0;
}
.uza-aside.collapsed .sb-brand-tagline-stack { display: none; }
.uza-aside.collapsed .sb-header {
  flex-direction: column;
  gap: 6px;
  padding: 12px 6px 8px;
}

/* Bell sits at the right of header — always visible, prominent */
.sb-header-bell {
  flex-shrink: 0;
  margin-left: auto;
}

/* Tagline — справа от логотипа, 3 строки колонкой (по слову) */
.sb-brand-tagline-stack {
  display: flex;
  flex-direction: column;
  gap: 1px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.55);
  line-height: 1.2;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
.sb-brand-tagline-stack > span {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  opacity: 0;
  transform: translateX(-12px);
  animation: sb-tagline-word-slide 0.55s cubic-bezier(0.25, 0.85, 0.3, 1) both;
}
.sb-brand-tagline-stack > span:nth-child(1) { animation-delay: 0.50s; }
.sb-brand-tagline-stack > span:nth-child(2) { animation-delay: 0.65s; }
.sb-brand-tagline-stack > span:nth-child(3) { animation-delay: 0.80s; }

@keyframes sb-tagline-word-slide {
  from { opacity: 0; transform: translateX(-12px); }
  to   { opacity: 1; transform: translateX(0);     }
}

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
  background: linear-gradient(135deg, #8B7FF0 0%, #6C5CE7 52%, #534AB7 100%);
  border: 1px solid rgba(173, 161, 255, .60);
  text-decoration: none;
  cursor: pointer;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(108, 92, 231, .45);
  transition: transform .2s, box-shadow .2s;
  animation: ai-pcard-glow 2.6s ease-in-out infinite;
}
@keyframes ai-pcard-glow {
  0%, 100% { box-shadow: 0 4px 14px rgba(108, 92, 231, .40); }
  50%      { box-shadow: 0 6px 28px rgba(139, 127, 240, .78); }
}
.ai-pcard:hover {
  transform: translateY(-1px);
  animation: none;
  box-shadow: 0 8px 26px rgba(139, 127, 240, .85);
}
.ai-pcard::before {
  content: ""; position: absolute; inset: 0;
  background: radial-gradient(circle at 80% 20%, rgba(255, 255, 255, .18), transparent 50%);
  pointer-events: none;
}
.ai-pcard::after {
  content: ""; position: absolute; top: 0; left: -100%; right: 0; bottom: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .30), transparent);
  animation: ai-pcard-shine 3s ease-in-out infinite;
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
.ai-pcard-off { opacity: .55; }
.ai-pcard-off .ai-pcard-pulse { background: #B4B2A9; box-shadow: none; animation: none; }
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
/* Красный счётчик «новых событий» (непрочитанные уведомления секции) */
.sb-badge {
  margin-left: auto;
  min-width: 17px;
  height: 17px;
  padding: 0 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #E24B4A;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;
  box-shadow: 0 0 0 2px rgba(226, 75, 74, 0.22);
  animation: sb-badge-pop 0.32s var(--ease-standard, cubic-bezier(0.34, 1.2, 0.64, 1));
}
@keyframes sb-badge-pop { from { transform: scale(0); } to { transform: scale(1); } }

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
  transition: background 0.16s, color 0.16s, transform 0.16s var(--ease-standard);
  position: relative;
  user-select: none;
}
/* Премиум: тонкий левый акцент при наведении (для неактивных пунктов) */
.sb-item:not(.active)::before {
  content: "";
  position: absolute;
  left: 0; top: 50%;
  width: 3px; height: 0;
  transform: translateY(-50%);
  background: linear-gradient(180deg, rgba(127,119,221,.9), rgba(181,174,236,.55));
  border-radius: 0 3px 3px 0;
  box-shadow: 0 0 10px rgba(127,119,221,.4);
  transition: height 0.18s var(--ease-standard);
}
.sb-item:not(.active):hover::before { height: 15px; }
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
  transform: translateX(3px);
}
.sb-item:hover svg {
  color: rgba(255, 255, 255, 0.95);
  transform: scale(1.12) rotate(-3deg);
  opacity: 1;
}
.sb-item.active {
  background: linear-gradient(135deg, rgba(127,119,221,.28) 0%, rgba(127,119,221,.14) 100%);
  border: 1px solid rgba(127,119,221,.38);
  box-shadow: 0 1px 6px rgba(127,119,221,.20), inset 0 0 0 1px rgba(255,255,255,.03);
  color: #fff;
}
/* 2026-05-26: left active indicator — fluid 3px vertical bar that grows
   on activation. Used in modern dashboards (Linear, Vercel) — premium feel. */
.sb-item.active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  width: 3px;
  height: 0;
  background: linear-gradient(180deg, #7F77DD, #B5AEEC);
  border-radius: 0 3px 3px 0;
  transform: translateY(-50%);
  animation: sbActiveBarDrop .35s var(--ease-standard) forwards;
  box-shadow: 0 0 12px rgba(127, 119, 221, .35);
}
@keyframes sbActiveBarDrop {
  0%   { height: 0; opacity: 0; }
  50%  { height: 24px; opacity: 1; }
  100% { height: 18px; opacity: 1; }
}
/* Премиум: медленное «сияние», проходящее по активному пункту */
.sb-item.active::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 6px;
  background: linear-gradient(100deg, transparent 25%, rgba(255,255,255,.12) 50%, transparent 75%);
  background-size: 220% 100%;
  animation: sbActiveSheen 4.5s ease-in-out infinite;
  pointer-events: none;
}
@keyframes sbActiveSheen {
  0%   { background-position: 200% 0; }
  60%  { background-position: -120% 0; }
  100% { background-position: -120% 0; }
}
.sb-item.active svg {
  color: #B5AEEC;
  opacity: 1;
  transform: scale(1.06);
  animation: sb-icon-pulse 2.6s ease-in-out infinite, sb-icon-in .55s var(--ease-standard) both;
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

/* Executive Dashboard уже имеет amber-акцент (inset-полоса) — убираем
   фиолетовую active-полоску ::before, чтобы цвета не накладывались. */
.sb-item.sb-exec-dash.active::before { display: none; }

/* Execution Summary — TEAL/EMERALD акцент (по аналогии с Executive Dashboard) */
.sb-item.sb-exec-summary {
  color: rgba(93, 202, 165, 0.92) !important;
  font-weight: 700;
}
.sb-item.sb-exec-summary svg { color: rgba(93, 202, 165, 0.80); opacity: 1; }
.sb-item.sb-exec-summary:hover {
  background: rgba(93, 202, 165, 0.06) !important;
  color: #5DCAA5 !important;
}
.sb-item.sb-exec-summary.active {
  background: rgba(93, 202, 165, 0.12) !important;
  color: #fff !important;
  box-shadow: inset 2px 0 0 0 #5DCAA5;
}
.sb-item.sb-exec-summary.active::before { display: none; }
.sb-item.sb-exec-summary.active svg { color: #5DCAA5; transform: scale(1.06); }
.sb-summary-badge {
  margin-left: auto;
  font-size: 9px; font-weight: 600;
  color: rgba(93, 202, 165, 0.70);
  letter-spacing: 0.04em;
  background: rgba(93, 202, 165, 0.10);
  padding: 1px 7px; border-radius: 4px;
  border: 1px solid rgba(93, 202, 165, 0.20);
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
  transition: transform 0.2s var(--ease-standard);
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
  transition: max-height 0.32s var(--ease-standard);
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

/* External-link badge — marks sidebar items that redirect to dashboard.uz-assets.uz */
.sb-ext-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: auto;
  margin-right: 2px;
  padding: 2px;
  color: rgba(255, 255, 255, 0.42);
  transition: color .12s var(--ease-standard);
}
.sb-item:hover .sb-ext-badge { color: rgba(255, 255, 255, 0.72); }
.sb-item.active .sb-ext-badge { color: rgba(255, 255, 255, 0.85); }

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
.sb-item.sb-new.active .sb-new-badge { background: var(--bg1, #fff); color: #7F77DD; }

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
  flex-wrap: wrap;
}
.sb-profile {
  display: flex; align-items: center; gap: 9px; width: 100%;
  padding: 8px 10px; border-radius: 10px;
  background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.92); cursor: pointer; font-family: inherit;
  transition: background .15s, border-color .15s;
}
.sb-profile:hover { background: rgba(127, 119, 221, 0.14); border-color: rgba(127, 119, 221, 0.32); }
.sb-profile-av {
  width: 30px; height: 30px; flex-shrink: 0; border-radius: 9px;
  background: linear-gradient(135deg, #8B7FFF 0%, #534AB7 100%);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600; color: #fff; overflow: hidden;
}
.sb-profile-av img { width: 100%; height: 100%; object-fit: cover; }
.sb-profile-txt { display: flex; flex-direction: column; min-width: 0; text-align: left; }
.sb-profile-name { font-size: 12px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sb-profile-sub { font-size: 10px; color: rgba(255, 255, 255, 0.5); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.uza-aside.collapsed .sb-profile-txt { display: none; }

.sb-pwd {
  text-decoration: none;
}
.sb-pwd:hover {
  border-color: rgba(127, 119, 221, 0.32) !important;
  color: #B5AFE8 !important;
  background: rgba(127, 119, 221, 0.06) !important;
}
.sb-notif-bell { flex-shrink: 0; }

/* Locale switcher button in sidebar footer */
.sb-locale {
  display: inline-flex; align-items: center; gap: 5px;
  background: rgba(127, 119, 221, 0.08);
  color: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 10.5px; font-weight: 600;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: background 120ms, border-color 120ms;
  flex-shrink: 0;
}
.sb-locale:hover {
  background: rgba(127, 119, 221, 0.18);
  border-color: rgba(127, 119, 221, 0.35);
}
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
    transition: transform 0.25s var(--ease-standard);
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
/* Отступ под фиксированную нижнюю навигацию (показывается ≤768px) */
@media (max-width: 768px) {
  .uza-main {
    padding-bottom: calc(58px + env(safe-area-inset-bottom));
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
