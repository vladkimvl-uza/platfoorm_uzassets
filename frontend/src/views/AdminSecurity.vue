<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useAuthStore } from "@/stores/auth";
import { adminMfaApi, type UserMfaRow, type MfaOverviewSummary } from "@/api/admin_mfa";
import { AxiosError } from "axios";

const auth = useAuthStore();

const loading = ref(true);
const users = ref<UserMfaRow[]>([]);
const summary = ref<MfaOverviewSummary | null>(null);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

// filters
const search = ref("");
const filterMode = ref<"all" | "enabled" | "disabled" | "tg-only">("all");

// force-disable modal
const targetUser = ref<UserMfaRow | null>(null);
const acting = ref(false);

onMounted(async () => { await refresh(); });

async function refresh() {
  loading.value = true;
  error.value = null;
  try {
    const r = await adminMfaApi.overview();
    users.value = r.users;
    summary.value = r.summary;
  } catch (e) {
    error.value = formatError(e);
  } finally {
    loading.value = false;
  }
}

function formatError(e: unknown): string {
  if (e instanceof AxiosError) return e.response?.data?.detail ?? e.message;
  return String(e);
}

function flash(msg: string) {
  notice.value = msg;
  setTimeout(() => { if (notice.value === msg) notice.value = null; }, 3500);
}

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  return users.value.filter((u) => {
    if (q) {
      const hay = `${u.email} ${u.full_name ?? ""} ${u.username ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (filterMode.value === "enabled" && !u.mfa_enabled) return false;
    if (filterMode.value === "disabled" && u.mfa_enabled) return false;
    if (filterMode.value === "tg-only" && !(u.telegram_linked && !u.mfa_enabled)) return false;
    return true;
  });
});

const filterCounts = computed(() => ({
  all: users.value.length,
  enabled: users.value.filter((u) => u.mfa_enabled).length,
  disabled: users.value.filter((u) => !u.mfa_enabled).length,
  tg_only: users.value.filter((u) => u.telegram_linked && !u.mfa_enabled).length,
}));

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

async function confirmForceDisable() {
  if (!targetUser.value) return;
  acting.value = true;
  try {
    await adminMfaApi.forceDisable(targetUser.value.id);
    flash(`2FA для ${targetUser.value.email} сброшена.`);
    targetUser.value = null;
    await refresh();
  } catch (e) {
    error.value = formatError(e);
  } finally {
    acting.value = false;
  }
}
</script>

<template>
  <div class="as-page">
    <div class="as-topbar">
      <div class="as-eyebrow">UzAssets · администрирование</div>
      <div class="as-title-row">
        <div>
          <div class="as-title">Безопасность пользователей</div>
          <div class="as-sub">2FA и привязка Telegram у каждого активного пользователя</div>
        </div>
        <button class="as-btn-ghost" :disabled="loading" @click="refresh">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
            <path d="M21 3v5h-5"/>
            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
            <path d="M8 16H3v5"/>
          </svg>
          {{ loading ? "Загрузка…" : "Обновить" }}
        </button>
      </div>
    </div>

    <!-- ─── Summary cards ─── -->
    <div v-if="summary" class="as-summary">
      <div class="as-stat">
        <div class="as-stat-val">{{ summary.total }}</div>
        <div class="as-stat-lab">всего активных</div>
      </div>
      <div class="as-stat as-stat-green">
        <div class="as-stat-val">{{ summary.mfa_enabled_count }}</div>
        <div class="as-stat-lab">2FA включена</div>
      </div>
      <div class="as-stat as-stat-blue">
        <div class="as-stat-val">{{ summary.telegram_linked_count }}</div>
        <div class="as-stat-lab">Telegram привязан</div>
      </div>
      <div class="as-stat as-stat-grey">
        <div class="as-stat-val">{{ summary.no_2fa_count }}</div>
        <div class="as-stat-lab">без 2FA</div>
      </div>
    </div>

    <transition name="uza-fade">
      <div v-if="notice" class="as-notice">{{ notice }}</div>
    </transition>
    <transition name="uza-fade">
      <div v-if="error" class="as-error">
        {{ error }}
        <button class="as-error-close" @click="error = null">×</button>
      </div>
    </transition>

    <!-- ─── Filter bar ─── -->
    <div class="as-filters">
      <input
        v-model="search"
        type="text"
        placeholder="Поиск по email, имени, username…"
        class="as-search"
      />
      <div class="as-segmented">
        <button
          class="as-seg-btn" :class="{ active: filterMode === 'all' }"
          @click="filterMode = 'all'"
        >
          Все · <span class="as-seg-count">{{ filterCounts.all }}</span>
        </button>
        <button
          class="as-seg-btn" :class="{ active: filterMode === 'enabled' }"
          @click="filterMode = 'enabled'"
        >
          С 2FA · <span class="as-seg-count">{{ filterCounts.enabled }}</span>
        </button>
        <button
          class="as-seg-btn" :class="{ active: filterMode === 'disabled' }"
          @click="filterMode = 'disabled'"
        >
          Без 2FA · <span class="as-seg-count">{{ filterCounts.disabled }}</span>
        </button>
        <button
          class="as-seg-btn" :class="{ active: filterMode === 'tg-only' }"
          @click="filterMode = 'tg-only'"
        >
          TG, но без 2FA · <span class="as-seg-count">{{ filterCounts.tg_only }}</span>
        </button>
      </div>
    </div>

    <!-- ─── Table ─── -->
    <div class="as-table-wrap">
      <table class="as-table">
        <thead>
          <tr>
            <th>Пользователь</th>
            <th class="as-th-center">2FA</th>
            <th class="as-th-center">Telegram</th>
            <th class="as-th-center">Recovery</th>
            <th>Последний вход</th>
            <th class="as-th-right" v-if="auth.isOwner">Действия</th>
          </tr>
        </thead>
        <tbody v-if="!loading">
          <tr v-for="u in filtered" :key="u.id">
            <td class="as-cell-user">
              <div class="as-user-name">
                {{ u.full_name || u.email }}
                <span v-if="u.is_owner" class="as-owner-tag">владелец</span>
              </div>
              <div class="as-user-email">{{ u.email }}</div>
            </td>
            <td class="as-th-center">
              <span v-if="u.mfa_enabled" class="as-chip as-chip-green" :title="`Метод: ${u.mfa_method}`">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M20 6 9 17l-5-5"/>
                </svg>
                включена
              </span>
              <span v-else class="as-chip as-chip-grey">отключена</span>
            </td>
            <td class="as-th-center">
              <span v-if="u.telegram_linked" class="as-chip as-chip-blue">
                @{{ u.telegram_username || '—' }}
              </span>
              <span v-else class="as-chip as-chip-grey">—</span>
            </td>
            <td class="as-th-center">
              <span v-if="u.mfa_enabled" class="as-recovery">
                {{ u.recovery_codes_remaining }}<span class="as-recovery-sep">/</span>10
              </span>
              <span v-else class="as-dim">—</span>
            </td>
            <td>
              <div class="as-cell-login">{{ fmtDate(u.last_login_at) }}</div>
              <div class="as-cell-login-ip" v-if="u.last_login_ip">{{ u.last_login_ip }}</div>
            </td>
            <td class="as-th-right" v-if="auth.isOwner">
              <button
                v-if="u.mfa_enabled || u.telegram_linked"
                :disabled="u.id === auth.user?.id"
                class="as-btn-danger-mini"
                :title="u.id === auth.user?.id ? 'Нельзя сбросить собственную 2FA здесь' : 'Принудительно отключить 2FA и отвязать Telegram'"
                @click="targetUser = u"
              >
                Сбросить
              </button>
            </td>
          </tr>
          <tr v-if="filtered.length === 0">
            <td :colspan="auth.isOwner ? 6 : 5" class="as-empty">
              Нет пользователей, удовлетворяющих фильтру.
            </td>
          </tr>
        </tbody>
        <tbody v-else>
          <tr>
            <td :colspan="auth.isOwner ? 6 : 5" class="as-loading-row">Загрузка…</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ─── Force-disable modal ─── -->
    <div v-if="targetUser" class="as-modal-backdrop" @click.self="targetUser = null">
      <div class="as-modal">
        <div class="as-modal-head">
          <h3>Сбросить 2FA</h3>
          <button class="as-modal-x" @click="targetUser = null">×</button>
        </div>
        <div class="as-modal-body">
          <p>Будет выполнено для пользователя:</p>
          <div class="as-target-block">
            <div class="as-target-name">{{ targetUser.full_name || targetUser.email }}</div>
            <div class="as-target-email">{{ targetUser.email }}</div>
          </div>
          <ul class="as-modal-list">
            <li v-if="targetUser.mfa_enabled">2FA будет отключена</li>
            <li v-if="targetUser.telegram_linked">Telegram будет отвязан</li>
            <li v-if="targetUser.recovery_codes_remaining > 0">
              Все {{ targetUser.recovery_codes_remaining }} recovery-кодов будут аннулированы
            </li>
            <li>Действие записывается в audit_log</li>
          </ul>
          <p class="as-warn-strong">
            Пользователь сможет войти с одним паролем. Сообщите ему, чтобы он привязал Telegram
            и снова включил 2FA в настройках безопасности.
          </p>
          <div class="as-modal-actions">
            <button class="as-btn-ghost" :disabled="acting" @click="targetUser = null">
              Отмена
            </button>
            <button class="as-btn-danger" :disabled="acting" @click="confirmForceDisable">
              {{ acting ? "Сброс…" : "Сбросить 2FA" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.as-page { max-width: 1100px; margin: 0 auto; padding: 24px 28px 80px; }

.as-topbar { margin-bottom: 22px; padding-bottom: 18px; border-bottom: 1px solid rgba(15,23,60,.08); }
.as-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: var(--t3, var(--t3)); }
.as-title-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-top: 4px; }
.as-title { font-size: 22px; font-weight: 500; letter-spacing: -.025em; color: var(--t1, #0F172A); }
.as-sub { font-size: 13px; color: var(--t3, var(--t3)); margin-top: 4px; }

/* ─── Summary cards ─── */
.as-summary {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px;
}
.as-stat {
  padding: 18px 20px; background: var(--bg1, #fff); border: 1px solid rgba(15,23,60,.08); border-radius: 14px;
  display: flex; flex-direction: column; gap: 4px;
  position: relative; overflow: hidden;
  --as-accent: transparent;
}
.as-stat::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--as-accent);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}
.as-stat-val { font-size: 22px; font-weight: 400; letter-spacing: -.025em; color: var(--t1, #0F172A); }
.as-stat-lab { font-size: 10px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; color: var(--t3, var(--t3)); }
.as-stat-green { --as-accent: var(--green); }
.as-stat-blue  { --as-accent: var(--blue); }
.as-stat-grey  { --as-accent: #94A3B8; }

/* ─── Notice / error ─── */
.as-notice, .as-error {
  padding: 12px 16px; border-radius: 11px; font-size: 13px;
  margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center;
}
.as-notice { background: rgba(29,158,117,.10); border: 1px solid rgba(29,158,117,.25); color: #14724E; }
.as-error  { background: rgba(239,68,68,.10); border: 1px solid rgba(239,68,68,.25); color: #B91C1C; }
.as-error-close { background: none; border: none; color: inherit; font-size: 18px; cursor: pointer; padding: 0 4px; }

/* ─── Filters ─── */
.as-filters {
  display: flex; gap: 12px; align-items: center;
  margin-bottom: 14px;
}
.as-search {
  flex: 1; height: 38px; padding: 0 14px;
  border-radius: 11px; border: 1px solid rgba(15,23,60,.12);
  background: var(--bg1, #fff); font-size: 13px; transition: all .15s;
}
.as-search:focus { outline: none; border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127,119,221,.18); }
.as-segmented {
  display: flex; background: rgba(15,23,60,.04); padding: 3px;
  border-radius: 11px; gap: 2px;
}
.as-seg-btn {
  height: 32px; padding: 0 12px; border: none; background: transparent;
  font-size: 12px; font-weight: 500; cursor: pointer;
  border-radius: 9px; color: var(--t2, #475569); transition: all .15s;
  display: flex; align-items: center; gap: 6px;
}
.as-seg-btn:hover { color: var(--t1, #0F172A); }
.as-seg-btn.active { background: var(--bg1, #fff); color: var(--t1, #0F172A); box-shadow: 0 1px 3px rgba(15,23,60,.08); }
.as-seg-count { color: var(--t3, #94A3B8); font-size: 11px; }
.as-seg-btn.active .as-seg-count { color: var(--t3, var(--t3)); }

/* ─── Table ─── */
.as-table-wrap {
  background: var(--bg1, #fff); border: 1px solid rgba(15,23,60,.08); border-radius: 14px;
  overflow: hidden; box-shadow: 0 2px 6px rgba(15,23,60,.04);
}
.as-table { width: 100%; border-collapse: collapse; }
.as-table th {
  font-size: 10px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase;
  color: var(--t3, var(--t3)); text-align: left; padding: 12px 16px;
  border-bottom: 1px solid rgba(15,23,60,.08);
  background: rgba(15,23,60,.02);
}
.as-th-center { text-align: center; }
.as-th-right { text-align: right; }
.as-table td {
  padding: 14px 16px; font-size: 13px; color: var(--t1, #0F172A);
  border-bottom: 1px solid rgba(15,23,60,.04);
}
.as-table tbody tr:hover { background: rgba(127,119,221,.03); }
.as-table tbody tr:last-child td { border-bottom: none; }

.as-cell-user { min-width: 220px; }
.as-user-name { font-weight: 500; color: var(--t1, #0F172A); display: flex; gap: 8px; align-items: center; }
.as-user-email { font-size: 11px; color: var(--t3, var(--t3)); margin-top: 2px; }
.as-owner-tag {
  font-size: 9px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase;
  padding: 2px 6px; border-radius: 6px;
  background: rgba(127,119,221,.12); color: #5B53C2;
}

.as-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: 11px;
  font-size: 11px; font-weight: 500; letter-spacing: .02em;
}
.as-chip-green { background: rgba(29,158,117,.12); color: #14724E; }
.as-chip-blue  { background: rgba(55,138,221,.12); color: #2865A7; }
.as-chip-grey  { background: rgba(100,116,139,.10); color: var(--t3, var(--t3)); }

.as-recovery { font-variant-numeric: tabular-nums; font-size: 13px; color: var(--t1, #0F172A); }
.as-recovery-sep { color: #CBD5E1; margin: 0 1px; }
.as-dim { color: #CBD5E1; }

.as-cell-login { font-size: 12px; color: var(--t2, #475569); }
.as-cell-login-ip { font-size: 10px; color: var(--t3, #94A3B8); margin-top: 2px; font-family: ui-monospace,"SF Mono",Menlo,monospace; }

.as-btn-ghost {
  height: 32px; padding: 0 14px; border-radius: 9px; border: none;
  background: rgba(127,119,221,.08); color: #5B53C2;
  font-size: 12px; font-weight: 500; cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px; transition: all .15s;
}
.as-btn-ghost:hover:not(:disabled) { background: rgba(127,119,221,.14); }
.as-btn-ghost:disabled { opacity: .5; cursor: not-allowed; }

.as-btn-danger-mini {
  height: 26px; padding: 0 10px; border-radius: 7px; border: none;
  background: rgba(239,68,68,.08); color: #B91C1C;
  font-size: 11px; font-weight: 500; cursor: pointer; transition: all .15s;
}
.as-btn-danger-mini:hover:not(:disabled) { background: rgba(239,68,68,.16); }
.as-btn-danger-mini:disabled { opacity: .35; cursor: not-allowed; }

.as-empty, .as-loading-row { text-align: center; padding: 40px; color: var(--t3, #94A3B8); font-size: 13px; }

/* ─── Modal ─── */
.as-modal-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
  animation: bgIn .25s;
}
@keyframes bgIn { from { opacity: 0; } to { opacity: 1; } }
.as-modal {
  background: var(--bg1, #fff); border-radius: 14px; max-width: 480px; width: 100%;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  animation: modalIn .45s var(--ease-standard);
}
@keyframes modalIn {
  from { opacity: 0; transform: translateY(20px) scale(.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
.as-modal-head { padding: 18px 22px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(15,23,60,.06); }
.as-modal-head h3 { font-size: 15px; font-weight: 500; letter-spacing: -.01em; color: var(--t1, #0F172A); margin: 0; }
.as-modal-x { background: none; border: none; font-size: 22px; cursor: pointer; color: var(--t3, #94A3B8); padding: 0 4px; }
.as-modal-x:hover { color: var(--t1, #0F172A); }
.as-modal-body { padding: 20px 22px; display: flex; flex-direction: column; gap: 12px; font-size: 13px; color: var(--t2, #334155); line-height: 1.55; }

.as-target-block {
  padding: 12px 14px; background: rgba(127,119,221,.06);
  border: 1px solid rgba(127,119,221,.18); border-radius: 10px;
}
.as-target-name { font-weight: 500; color: var(--t1, #0F172A); }
.as-target-email { font-size: 11px; color: var(--t3, var(--t3)); margin-top: 2px; }
.as-modal-list { margin: 0; padding-left: 18px; }
.as-modal-list li { padding: 3px 0; }
.as-warn-strong {
  background: rgba(239,159,39,.10); border: 1px solid rgba(239,159,39,.25);
  color: #B45309; padding: 10px 14px; border-radius: 10px; margin: 0;
}
.as-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }
.as-btn-danger {
  height: 38px; padding: 0 16px; border-radius: 11px; border: none;
  background: rgba(239,68,68,.10); color: #B91C1C;
  font-size: 13px; font-weight: 500; cursor: pointer; transition: all .15s;
}
.as-btn-danger:hover:not(:disabled) { background: rgba(239,68,68,.18); }
.as-btn-danger:disabled { opacity: .45; cursor: not-allowed; }

</style>
