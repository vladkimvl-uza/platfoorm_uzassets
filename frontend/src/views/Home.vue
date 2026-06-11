<script setup lang="ts">
/**
 * Home.vue — entry homepage 1:1 с легасиом (index.html:5400-5540).
 *
 * Без: лого UzAssets, language switches (не реализовано в Vue).
 * Добавлено: WeatherWidget (Ташкент), TomorrowHolidayWidget (если завтра праздник).
 */
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import MeshGradient from "@/components/Home/MeshGradient.vue";
import WeatherWidget from "@/components/Home/WeatherWidget.vue";
import TomorrowHolidayWidget from "@/components/Home/TomorrowHolidayWidget.vue";
import CurrenciesWidget from "@/components/Home/CurrenciesWidget.vue";
import FlagSeparator from "@/components/Home/FlagSeparator.vue";
import WorldCupWidget from "@/components/Home/WorldCupWidget.vue";
import { getHoliday } from "@/api/holidays";

const router = useRouter();
const auth = useAuthStore();

// Виджет ЧМ-2026 — по умолчанию СКРЫТ; показывается только если пользователь
// явно его открыл (флаг «показан» в localStorage). Курсы остаются на месте.
const WC_SHOW_KEY = "home-wc-shown";
const wcHidden = ref<boolean>(
  !(typeof localStorage !== "undefined" && localStorage.getItem(WC_SHOW_KEY) === "1"),
);
const wcRevealFx = ref(false);  // одноразовый пролёт мяча со шлейфом флага
let _fxTimer: number | null = null;
function hideWc() {
  wcHidden.value = true;
  try { localStorage.removeItem(WC_SHOW_KEY); } catch { /* noop */ }
}
function showWc() {
  wcHidden.value = false;
  try { localStorage.setItem(WC_SHOW_KEY, "1"); } catch { /* noop */ }
  // запускаем эффект пролёта по области баннера
  wcRevealFx.value = false;
  if (_fxTimer) clearTimeout(_fxTimer);
  requestAnimationFrame(() => {
    wcRevealFx.value = true;
    _fxTimer = window.setTimeout(() => { wcRevealFx.value = false; }, 4200);
  });
}

// Time-of-day greeting (1:1 legacy logic — by hour)
const greeting = computed(() => {
  const h = new Date().getHours();
  if (h >= 5 && h < 12) return "Доброе утро";
  if (h >= 12 && h < 18) return "Добрый день";
  return "Добрый вечер";
});

const firstName = computed(() => {
  const u = auth.user;
  if (!u) return "";
  if (u.full_name) return u.full_name.trim().split(/\s+/)[0];
  if (u.username) return u.username;
  if (u.email) return u.email.split("@")[0];
  return "";
});

const userInitial = computed(() => {
  const u = auth.user;
  if (!u) return "?";
  const src = u.full_name || u.username || u.email || "";
  return (src[0] || "?").toUpperCase();
});

const userDisplayName = computed(() => {
  const u = auth.user;
  if (!u) return "—";
  return u.full_name || u.username || u.email || "—";
});

// True if there's a UZ holiday in next 0..3 days — drives both widget + flag separator
const hasUpcomingHoliday = computed(() => {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let offset = 0; offset <= 3; offset++) {
    const d = new Date(today);
    d.setDate(today.getDate() + offset);
    if (getHoliday(d)) return true;
  }
  return false;
});

function openProfile() {
  router.push("/settings/security");
}

function enterPortfolio() {
  router.push("/dashboard");
}
function openEsg() {
  window.open("https://moodle.uz-assets.uz/", "_blank", "noopener");
}
function openTenzorsoft() {
  window.open("https://dashboard.uz-assets.uz/auth/sign-in", "_blank", "noopener");
}
function openTenzorsoftSub(path: string, ev: Event) {
  ev.stopPropagation();
  ev.preventDefault();
  window.open(`https://dashboard.uz-assets.uz/${path}`, "_blank", "noopener");
}
function openEkengash() {
  window.open("https://ekengash.imv.uz/auth", "_blank", "noopener");
}
function doLogout() {
  auth.clear();
  router.push({ name: "login" });
}
</script>

<template>
  <div class="home-page">
    <!-- ═══ HERO BANNER ═══ -->
    <div class="home-banner">
      <MeshGradient />

      <!-- Topbar — без логотипа, без lang-switches -->
      <div class="home-topbar">
        <div class="home-tb-left">
          <span class="home-tb-eyebrow">Единая платформа трансформации</span>
        </div>
        <div class="home-tb-right">
          <button
            class="home-profile-pill"
            type="button"
            @click="openProfile"
            title="Профиль и настройки безопасности"
          >
            <div class="home-av">
              <img v-if="auth.user?.avatar_url" :src="auth.user.avatar_url" alt="" />
              <template v-else>{{ userInitial }}</template>
            </div>
            <div class="home-user">
              <div class="home-uname">{{ userDisplayName }}</div>
              <div class="home-uemail">{{ auth.user?.email }}</div>
            </div>
            <svg
              class="home-profile-chev"
              width="12" height="12" viewBox="0 0 16 16"
              fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"
            >
              <polyline points="6 4 10 8 6 12"/>
            </svg>
          </button>
          <button class="home-logout-btn" @click="doLogout" title="Выйти из системы">
            Выйти
          </button>
        </div>
      </div>

      <!-- Hero greeting -->
      <div class="home-hero">
        <div class="home-hero-inner">
          <h1 class="home-greeting">{{ greeting }}<span v-if="firstName">, {{ firstName }}</span></h1>

          <!-- Weather + holiday + CBU rates -->
          <div class="home-extra-row">
            <WeatherWidget />
            <TomorrowHolidayWidget />
            <transition name="wc-pop">
              <div v-if="!wcHidden" class="wc-slot">
                <WorldCupWidget @hide="hideWc" />
              </div>
            </transition>
            <CurrenciesWidget />
          </div>
          <button v-if="wcHidden" class="home-wc-restore" type="button" @click="showWc">
            <img src="https://flagcdn.com/w20/uz.png" alt="UZ" width="16" height="12" />
            Чемпионат мира по футболу 2026 · Узбекистан
          </button>

          <!-- Развевающийся на ветру флаг Узбекистана на весь фон при раскрытии -->
          <div v-if="wcRevealFx" class="home-wc-fx" aria-hidden="true">
            <img class="home-wc-fx-bg" src="https://flagcdn.com/w1280/uz.png" alt="" />
          </div>
        </div>
      </div>

      <!-- UZ flag separator — appears together with holiday widget (same delay) -->
      <FlagSeparator v-if="hasUpcomingHoliday" />
    </div>

    <!-- ═══ CONTENT ═══ -->
    <div class="home-content">
      <!-- Products UzAssets -->
      <div class="home-section-head">
        <div class="home-section-stripe" style="background: #7C6FF7"></div>
        <span class="home-section-label">Продукты UzAssets</span>
      </div>

      <div class="home-panel-unified">
        <!-- Hero left: Portfolio -->
        <div
          class="hpu-hero"
          @click="enterPortfolio"
          @mouseover="(($refs.heroEnter as HTMLElement | undefined)?.style.setProperty('opacity', '1'))"
          @mouseleave="(($refs.heroEnter as HTMLElement | undefined)?.style.setProperty('opacity', '0'))"
        >
          <div class="hpu-hero-head">
            <div class="hpu-hero-icon">
              <img
                src="/favicon.svg"
                alt="UzAssets — Единая платформа трансформации"
                class="hpu-hero-logo"
              />
            </div>
            <span class="hpu-hero-badge">Портфель</span>
          </div>
          <div>
            <div class="hpu-hero-title">Портфель государственных компаний</div>
            <div class="hpu-hero-sub">Мониторинг проектов трансформаций</div>
          </div>
          <div class="hpu-hero-foot">
            <span ref="heroEnter" class="hpu-hero-enter">Перейти →</span>
          </div>
        </div>

        <div class="hpu-divider"></div>

        <!-- Right: ESG card -->
        <div class="hpu-right">
          <a href="https://moodle.uz-assets.uz/" target="_blank" rel="noopener" class="hpu-esg" @click.prevent="openEsg">
            <div class="hpu-esg-head">
              <div class="hpu-esg-icon">
                <img
                  src="/uzassets-logo.png"
                  alt="UzAssets ESG Center of Excellence"
                  class="hpu-esg-logo"
                />
              </div>
              <div class="hpu-esg-title">UzAssets ESG Center<br>of Excellence</div>
            </div>
            <div class="hpu-esg-foot">
              <span>Открыть
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                  <path d="M3.5 3.5h5v5"/>
                  <path d="M8.5 3.5L3 9"/>
                </svg>
              </span>
            </div>
          </a>
        </div>
      </div>

      <!-- External systems -->
      <div class="home-section-head">
        <div class="home-section-stripe" style="background: #94A3B8"></div>
        <span class="home-section-label" style="color: var(--t3, #94A3B8)">Внешние системы</span>
      </div>

      <div class="home-ws-grid">
        <a class="home-ws-card" href="https://dashboard.uz-assets.uz/auth/sign-in" target="_blank" rel="noopener" @click.prevent="openTenzorsoft">
          <div class="home-ws-head">
            <div class="home-ws-icon home-ws-icon-blue">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#378ADD" stroke-width="1.8" stroke-linecap="round">
                <rect x="3" y="3" width="7" height="7" rx="1.5"/>
                <rect x="14" y="3" width="7" height="7" rx="1.5"/>
                <rect x="3" y="14" width="7" height="7" rx="1.5"/>
                <rect x="14" y="14" width="7" height="7" rx="1.5"/>
              </svg>
            </div>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#94A3B8" stroke-width="1.5" stroke-linecap="round">
              <path d="M5.5 2H3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V8.5"/>
              <path d="M8 2h4v4"/>
              <path d="M12 2L6.5 7.5"/>
            </svg>
          </div>
          <div>
            <div class="home-ws-title">Финансовые показатели и инвестиционный портфель</div>
            <div class="home-ws-sub">Аналитическая панель управления</div>
          </div>
          <div class="home-ws-tag-row">
            <span class="home-ws-vendor">ООО Tenzorsoft | Разработано совместно с UzAssets</span>
          </div>
          <div class="home-ws-pills">
            <span class="home-ws-pill" @click="openTenzorsoftSub('credits', $event)">Кредитный портфель</span>
            <span class="home-ws-pill" @click="openTenzorsoftSub('investments-v2', $event)">Инвестиционные проекты</span>
            <span class="home-ws-pill" @click="openTenzorsoftSub('soe-dashboard/finmodel-old-3', $event)">Финансовая модель</span>
          </div>
        </a>

        <a class="home-ws-card" href="https://ekengash.imv.uz/auth" target="_blank" rel="noopener" @click.prevent="openEkengash">
          <div class="home-ws-head">
            <div class="home-ws-icon home-ws-icon-imv">
              <svg width="24" height="24" viewBox="0 0 32 32" fill="none">
                <circle cx="16" cy="16" r="14" fill="#0F6E56"/>
                <text x="16" y="20" font-size="10" font-weight="700" fill="white" text-anchor="middle" font-family="-apple-system, system-ui">IMV</text>
              </svg>
            </div>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#94A3B8" stroke-width="1.5" stroke-linecap="round">
              <path d="M5.5 2H3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V8.5"/>
              <path d="M8 2h4v4"/>
              <path d="M12 2L6.5 7.5"/>
            </svg>
          </div>
          <div>
            <div class="home-ws-title">E-Kengash IMV</div>
            <div class="home-ws-sub">Электронные заседания</div>
          </div>
          <div class="home-ws-tag-row">
            <span class="home-ws-vendor" style="color: #4B6A8A; background: rgba(75, 106, 138, 0.07)">
              ИВЦ Министерства Экономики и Финансов Республики Узбекистан
            </span>
          </div>
        </a>
      </div>

      <!-- uz-assets.uz link -->
      <div class="home-foot-link">
        <a href="https://uz-assets.uz/uz/" target="_blank" rel="noopener">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <circle cx="12" cy="12" r="10"/>
            <path d="M2 12h20"/>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
          </svg>
          uz-assets.uz
        </a>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════ */
/* Root + banner — 1:1 legacy */
/* ═══════════════════════════════════════════════════════════════ */
/* #app is `display:flex; width:100vw; height:100vh; overflow:hidden`.
   AppShell uses Vue 3 fragments (aside + main) so each fragment is a
   direct flex child. Home.vue has a single root, so we MUST set
   `flex:1 1 100%` or it collapses to content-width (narrow-content bug). */
.home-page {
  flex: 1 1 100%;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--bg2, #F8FAFC);
}
.home-banner {
  background: linear-gradient(180deg, #0C1230 0%, #0F163A 35%, #1E2A4A 100%);
  width: 100%;
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Topbar — no logo, no lang switches */
.home-topbar {
  height: 58px;
  display: flex;
  align-items: center;
  padding: 0 28px;
  justify-content: space-between;
  flex-shrink: 0;
  width: 100%;
  box-sizing: border-box;
  position: relative;
  z-index: 2;
}
.home-tb-eyebrow {
  font-size: 10px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.home-tb-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.home-profile-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 12px 4px 4px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  cursor: pointer;
  font-family: inherit;
  color: inherit;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}
.home-profile-pill:hover {
  background: rgba(255, 255, 255, 0.10);
  border-color: rgba(255, 255, 255, 0.20);
  transform: translateY(-1px);
}
.home-profile-pill:active {
  transform: translateY(0);
}
.home-profile-chev {
  color: rgba(255, 255, 255, 0.40);
  flex-shrink: 0;
  transition: color 0.15s, transform 0.15s;
}
.home-profile-pill:hover .home-profile-chev {
  color: rgba(255, 255, 255, 0.85);
  transform: translateX(2px);
}

.home-av {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #8B7FFF, #6C5CE7);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(108, 92, 231, 0.30);
  overflow: hidden;
}
.home-av img { width: 100%; height: 100%; object-fit: cover; }
.home-user {
  display: flex;
  flex-direction: column;
}
.home-uname {
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.88);
}
.home-uemail {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.38);
}
.home-logout-btn {
  padding: 5px 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  font-size: 11px;
  color: rgba(255, 255, 255, 0.50);
  cursor: pointer;
  margin-left: 4px;
  transition: background 0.12s, color 0.12s;
}
.home-logout-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.85);
}

/* Hero block */
.home-hero {
  padding: 28px 0 36px;
  width: 100%;
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}
.home-hero-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 32px;
  position: relative;
  z-index: 2;
}
@keyframes heroBlurIn {
  from { opacity: 0; filter: blur(10px); transform: scale(1.03); }
  to { opacity: 1; filter: blur(0); transform: scale(1); }
}
.home-greeting {
  font-size: 30px;
  font-weight: 700;
  color: #fff;
  letter-spacing: -0.04em;
  margin: 0 0 22px;
  animation: heroBlurIn 0.55s var(--ease-standard) 0.05s both;
}

.home-extra-row {
  display: flex;
  align-items: stretch;
  gap: 14px;
  flex-wrap: wrap;
}
.home-extra-row > * {
  flex: 1 1 320px;
}
.home-wc-restore {
  position: relative; overflow: hidden;
  display: inline-flex; align-items: center; gap: 8px;
  margin-top: 12px; padding: 9px 18px;
  border-radius: 999px;
  border: 1px solid rgba(110, 231, 160, 0.5);
  background: linear-gradient(135deg, #1EB53A 0%, #0F8E5A 60%, #0099FF 130%);
  color: #fff;
  font-size: 12.5px; font-weight: 600; letter-spacing: .01em; cursor: pointer;
  box-shadow: 0 6px 20px rgba(30, 181, 58, 0.34);
  transition: transform 0.16s var(--ease-standard, ease), box-shadow 0.16s;
  will-change: transform;
}
/* блик — только transform (GPU), без анимации layout-свойств */
.home-wc-restore::after {
  content: ""; position: absolute; top: 0; bottom: 0; left: 0; width: 44%;
  background: linear-gradient(100deg, transparent, rgba(255,255,255,.45), transparent);
  transform: translateX(-240%) skewX(-18deg);
  animation: home-wc-sheen 3.6s ease-in-out infinite;
  will-change: transform; pointer-events: none;
}
@keyframes home-wc-sheen {
  0%, 55% { transform: translateX(-240%) skewX(-18deg); }
  100%    { transform: translateX(420%) skewX(-18deg); }
}
.home-wc-restore:hover { transform: translateY(-2px) scale(1.03); box-shadow: 0 10px 26px rgba(30, 181, 58, 0.46); }
.home-wc-restore img { border-radius: 2px; box-shadow: 0 0 0 1px rgba(0,0,0,.18); position: relative; z-index: 1; }
@media (prefers-reduced-motion: reduce) {
  .home-wc-restore::after { display: none; }
}

/* Развевающийся на ветру флаг Узбекистана на весь фон при раскрытии */
.home-hero-inner { position: relative; }
.home-hero-inner > h1,
.home-hero-inner > .home-extra-row,
.home-hero-inner > .home-wc-restore { position: relative; z-index: 1; }
.home-wc-fx {
  position: absolute; inset: -10px -20px; pointer-events: none;
  overflow: hidden; z-index: 0; border-radius: 18px;
}
/* флаг на всю площадь, не обрезан (fill), плавно появляется + лёгкая волна на ветру */
.home-wc-fx-bg {
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: fill; transform-origin: center; will-change: transform, opacity;
  opacity: 0; animation: home-fx-bg 4.2s ease-in-out both;
}
@keyframes home-fx-bg {
  0%   { opacity: 0; transform: perspective(900px) rotateY(0deg) skewY(0deg) scale(1.04); }
  18%  { opacity: .22; }
  40%  { transform: perspective(900px) rotateY(4deg) skewY(-1deg) scale(1.01); }
  60%  { opacity: .22; transform: perspective(900px) rotateY(-3deg) skewY(.8deg) scale(1); }
  82%  { opacity: .14; transform: perspective(900px) rotateY(2deg) skewY(-.5deg) scale(1.01); }
  100% { opacity: 0; transform: perspective(900px) rotateY(0deg) skewY(0deg) scale(1.03); }
}
@media (prefers-reduced-motion: reduce) { .home-wc-fx { display: none; } }

/* Плавное раздвижение/сдвиг блоков: clip slot, контент внутри стабилен */
.wc-slot {
  flex: 0 1 auto; overflow: hidden; will-change: max-width;
  display: flex; align-items: stretch;
}

/* Плавное раздвижение: тянем только max-width (контент внутри фиксирован →
   не пересчитывается), курсы плавно сдвигаются. Мягкая ease-кривая. */
.wc-pop-enter-active, .wc-pop-leave-active {
  transition: max-width .6s cubic-bezier(.25, .8, .25, 1), opacity .45s ease;
  overflow: hidden;
}
.wc-pop-enter-from, .wc-pop-leave-to { max-width: 0; opacity: 0; }
.wc-pop-enter-to, .wc-pop-leave-from { max-width: 520px; opacity: 1; }

/* ═══════════════════════════════════════════════════════════════ */
/* Content */
/* ═══════════════════════════════════════════════════════════════ */
.home-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 36px 32px 64px;
  width: 100%;
  box-sizing: border-box;
}
.home-section-head {
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 4px;
  max-width: 1200px;
  width: 100%;
}
.home-section-head:not(:first-child) {
  margin-top: 28px;
}
.home-section-stripe {
  width: 3px;
  height: 14px;
  border-radius: 2px;
}
.home-section-label {
  font-size: 11.5px;
  font-weight: 600;
  color: rgba(30, 42, 74, 0.55);
  letter-spacing: 0.02em;
}

/* Unified panel (Portfolio + ESG) */
@keyframes homeIn {
  from { opacity: 0; transform: translateY(18px); }
  to { opacity: 1; transform: translateY(0); }
}
.home-panel-unified {
  background: var(--bg1, #fff);
  border: 1px solid var(--border-input);
  border-radius: 22px;
  max-width: 1200px;
  width: 100%;
  box-shadow: 0 1px 4px rgba(15, 23, 60, 0.05), 0 4px 16px rgba(15, 23, 60, 0.06);
  display: flex;
  align-items: stretch;
  animation: homeIn 0.35s ease both;
  overflow: hidden;
}
.hpu-hero {
  flex: 1;
  min-width: 0;
  padding: 26px 30px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 20px;
  transition: background 0.2s;
}
.hpu-hero:hover {
  background: #FAFAFF;
}
.hpu-hero-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.hpu-hero-icon {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  background: var(--bg1, #fff);
  border: 1px solid var(--border-input);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 6px;
  flex-shrink: 0;
}
.hpu-hero-logo {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.hpu-hero-badge {
  font-size: 11px;
  font-weight: 600;
  color: #2563EB;
  background: rgba(55, 138, 221, 0.10);
  padding: 3px 10px;
  border-radius: 20px;
  border: 1px solid #BFDBFE;
}
.hpu-hero-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.03em;
}
.hpu-hero-sub {
  font-size: 13px;
  color: rgba(30, 42, 74, 0.55);
  margin-top: 5px;
}
.hpu-hero-foot {
  margin-top: auto;
  display: flex;
  justify-content: flex-end;
}
.hpu-hero-enter {
  font-size: 13px;
  font-weight: 500;
  color: #7F77DD;
  opacity: 0;
  transition: opacity 0.2s;
}

.hpu-divider {
  width: 1px;
  background: #EEF0FA;
  margin: 14px 0;
  flex-shrink: 0;
}

.hpu-right {
  width: 260px;
  padding: 14px 10px;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.hpu-esg {
  flex: 1;
  padding: 18px;
  border-radius: 12px;
  text-decoration: none;
  color: inherit;
  transition: background 0.15s;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 14px;
}
.hpu-esg:hover {
  background: #FEF9F0;
}
.hpu-esg-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.hpu-esg-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  background: var(--bg1, #fff);
  border: 1px solid var(--border-input);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 5px;
  overflow: hidden;
}
.hpu-esg-logo {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.hpu-esg-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.01em;
  line-height: 1.35;
}
.hpu-esg-foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-top: 12px;
  border-top: 1px solid #F1F5F9;
}
.hpu-esg-foot span {
  font-size: 11px;
  color: #7F77DD;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

/* External systems grid */
.home-ws-grid {
  display: flex;
  justify-content: center;
  gap: 22px;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  flex-wrap: wrap;
}
.home-ws-card {
  background: var(--bg1, #fff);
  border: 1px solid var(--border-input);
  border-radius: 22px;
  padding: 32px 36px;
  cursor: pointer;
  transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.25s ease, border-color 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 20px;
  flex: 1 1 0;
  min-width: 320px;
  box-shadow: 0 1px 4px rgba(15, 23, 60, 0.05), 0 4px 16px rgba(15, 23, 60, 0.06);
  text-decoration: none;
  color: inherit;
  animation: homeIn 0.35s ease both;
}
.home-ws-card:nth-child(2) {
  animation-delay: 0.07s;
}
.home-ws-card:hover {
  transform: translateY(-6px);
  box-shadow: 0 24px 56px rgba(15, 23, 60, 0.13), 0 8px 20px rgba(15, 23, 60, 0.08);
  border-color: #CBD5E1;
}
.home-ws-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.home-ws-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.home-ws-icon-blue {
  background: #EBF4FF;
  border: 1px solid #BFDBFE;
}
.home-ws-icon-imv {
  background: var(--bg1, #fff);
  border: 1px solid var(--border-input);
  overflow: hidden;
}
.home-ws-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.02em;
}
.home-ws-sub {
  font-size: 12px;
  color: rgba(30, 42, 74, 0.55);
  margin-top: 4px;
}
.home-ws-tag-row {
  margin-top: auto;
  padding-top: 8px;
}
.home-ws-vendor {
  font-size: 10px;
  font-weight: 600;
  color: var(--blue);
  background: rgba(55, 138, 221, 0.08);
  padding: 2px 8px;
  border-radius: 4px;
}
.home-ws-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 12px;
}
.home-ws-pill {
  font-size: 10px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 4px;
  background: var(--bg2, #F8FAFC);
  color: rgba(30, 42, 74, 0.70);
  border: 1px solid var(--border-input);
  cursor: pointer;
  transition: all 0.15s;
  letter-spacing: 0.01em;
}
.home-ws-pill:hover {
  background: #F1F5F9;
  border-color: #CBD5E1;
}

.home-foot-link {
  text-align: center;
  padding: 24px 0 8px;
}
.home-foot-link a {
  font-size: 11px;
  color: var(--t3, #94A3B8);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  transition: color 0.15s;
}
.home-foot-link a:hover {
  color: #7C6FF7;
}

/* Responsive — 1:1 legacy breakpoints */
@media (max-width: 1024px) {
  .home-ws-card {
    flex: 1 1 100%;
    padding: 24px 20px;
  }
  .home-greeting {
    font-size: 24px;
  }
}
@media (max-width: 768px) {
  .home-panel-unified {
    flex-direction: column;
  }
  .hpu-divider {
    width: auto;
    height: 1px;
    margin: 0 14px;
  }
  .hpu-right {
    width: 100%;
  }
  .home-hero-inner {
    padding: 0 16px;
  }
  .home-greeting {
    font-size: 20px;
  }
  .home-ws-grid {
    flex-direction: column;
    gap: 12px;
  }
}
</style>
