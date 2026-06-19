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

const search = ref("");
const filterMode = ref<"all" | "enabled" | "disabled" | "tg-only">("all");

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
  <div class="sa-wrap">
    <!-- ─── Summary stat cards ─── -->
    <div v-if="summary" class="sa-summary kpi-rail">
      <div class="sa-stat">
        <div class="sa-stat-val">{{ summary.total }}</div>
        <div class="sa-stat-lab">всего активных</div>
      </div>
      <div class="sa-stat sa-stat-green">
        <div class="sa-stat-val">{{ summary.mfa_enabled_count }}</div>
        <div class="sa-stat-lab">2FA включена</div>
      </div>
      <div class="sa-stat sa-stat-blue">
        <div class="sa-stat-val">{{ summary.telegram_linked_count }}</div>
        <div class="sa-stat-lab">Telegram привязан</div>
      </div>
      <div class="sa-stat sa-stat-grey">
        <div class="sa-stat-val">{{ summary.no_2fa_count }}</div>
        <div class="sa-stat-lab">без 2FA</div>
      </div>
    </div>

    <transition name="uza-fade">
      <div v-if="notice" class="sa-notice">{{ notice }}</div>
    </transition>
    <transition name="uza-fade">
      <div v-if="error" class="sa-error">
        {{ error }}
        <button class="sa-error-close" @click="error = null">×</button>
      </div>
    </transition>

    <!-- ─── Filters ─── -->
    <div class="sa-filters">
      <input
        v-model="search"
        type="text"
        placeholder="Поиск по email, имени, username…"
        class="sa-search"
      />
      <div class="sa-segmented">
        <button class="sa-seg-btn" :class="{ active: filterMode === 'all' }" @click="filterMode = 'all'">
          Все · <span class="sa-seg-count">{{ filterCounts.all }}</span>
        </button>
        <button class="sa-seg-btn" :class="{ active: filterMode === 'enabled' }" @click="filterMode = 'enabled'">
          С 2FA · <span class="sa-seg-count">{{ filterCounts.enabled }}</span>
        </button>
        <button class="sa-seg-btn" :class="{ active: filterMode === 'disabled' }" @click="filterMode = 'disabled'">
          Без 2FA · <span class="sa-seg-count">{{ filterCounts.disabled }}</span>
        </button>
        <button class="sa-seg-btn" :class="{ active: filterMode === 'tg-only' }" @click="filterMode = 'tg-only'">
          TG, но без 2FA · <span class="sa-seg-count">{{ filterCounts.tg_only }}</span>
        </button>
      </div>
      <button class="sa-btn-ghost" :disabled="loading" @click="refresh">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
          <path d="M21 3v5h-5"/>
          <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
          <path d="M8 16H3v5"/>
        </svg>
        {{ loading ? "…" : "Обновить" }}
      </button>
    </div>

    <!-- ─── Table ─── -->
    <div class="sa-table-wrap">
      <table class="sa-table">
        <thead>
          <tr>
            <th>Пользователь</th>
            <th class="sa-th-center">2FA</th>
            <th class="sa-th-center">Telegram</th>
            <th class="sa-th-center">Recovery</th>
            <th>Последний вход</th>
            <th class="sa-th-right" v-if="auth.isOwner">Действия</th>
          </tr>
        </thead>
        <tbody v-if="!loading">
          <tr v-for="u in filtered" :key="u.id">
            <td class="sa-cell-user">
              <div class="sa-user-name">
                {{ u.full_name || u.email }}
                <span v-if="u.is_owner" class="sa-owner-tag">владелец</span>
              </div>
              <div class="sa-user-email">{{ u.email }}</div>
            </td>
            <td class="sa-th-center">
              <span v-if="u.mfa_enabled" class="sa-chip sa-chip-green" :title="`Метод: ${u.mfa_method}`">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M20 6 9 17l-5-5"/>
                </svg>
                включена
              </span>
              <span v-else class="sa-chip sa-chip-grey">отключена</span>
            </td>
            <td class="sa-th-center">
              <span v-if="u.telegram_linked" class="sa-chip sa-chip-blue">
                @{{ u.telegram_username || '—' }}
              </span>
              <span v-else class="sa-chip sa-chip-grey">—</span>
            </td>
            <td class="sa-th-center">
              <span v-if="u.mfa_enabled" class="sa-recovery">
                {{ u.recovery_codes_remaining }}<span class="sa-recovery-sep">/</span>10
              </span>
              <span v-else class="sa-dim">—</span>
            </td>
            <td>
              <div class="sa-cell-login">{{ fmtDate(u.last_login_at) }}</div>
              <div class="sa-cell-login-ip" v-if="u.last_login_ip">{{ u.last_login_ip }}</div>
            </td>
            <td class="sa-th-right" v-if="auth.isOwner">
              <button
                v-if="u.mfa_enabled || u.telegram_linked"
                :disabled="u.id === auth.user?.id"
                class="sa-btn-danger-mini"
                :title="u.id === auth.user?.id ? 'Нельзя сбросить собственную 2FA здесь' : 'Принудительно отключить 2FA и отвязать Telegram'"
                @click="targetUser = u"
              >
                Сбросить
              </button>
            </td>
          </tr>
          <tr v-if="filtered.length === 0">
            <td :colspan="auth.isOwner ? 6 : 5" class="sa-empty">
              Нет пользователей, удовлетворяющих фильтру.
            </td>
          </tr>
        </tbody>
        <tbody v-else>
          <tr>
            <td :colspan="auth.isOwner ? 6 : 5" class="sa-loading-row">Загрузка…</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ─── Force-disable modal ─── -->
    <div v-if="targetUser" class="sa-modal-backdrop" @click.self="targetUser = null">
      <div class="sa-modal">
        <div class="sa-modal-head">
          <h3>Сбросить 2FA</h3>
          <button class="sa-modal-x" @click="targetUser = null">×</button>
        </div>
        <div class="sa-modal-body">
          <p>Будет выполнено для пользователя:</p>
          <div class="sa-target-block">
            <div class="sa-target-name">{{ targetUser.full_name || targetUser.email }}</div>
            <div class="sa-target-email">{{ targetUser.email }}</div>
          </div>
          <ul class="sa-modal-list">
            <li v-if="targetUser.mfa_enabled">2FA будет отключена</li>
            <li v-if="targetUser.telegram_linked">Telegram будет отвязан</li>
            <li v-if="targetUser.recovery_codes_remaining > 0">
              Все {{ targetUser.recovery_codes_remaining }} recovery-кодов будут аннулированы
            </li>
            <li>Действие записывается в audit_log</li>
          </ul>
          <p class="sa-warn-strong">
            Пользователь сможет войти с одним паролем. Сообщите ему, чтобы он привязал Telegram
            и снова включил 2FA в настройках безопасности.
          </p>
          <div class="sa-modal-actions">
            <button class="sa-btn-ghost" :disabled="acting" @click="targetUser = null">
              Отмена
            </button>
            <button class="sa-btn-danger" :disabled="acting" @click="confirmForceDisable">
              {{ acting ? "Сброс…" : "Сбросить 2FA" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sa-wrap { padding: 6px 0 40px; }

.sa-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 18px; }
.sa-stat {
  padding: 16px 18px; background: var(--card-bg, rgba(255,255,255,0.82)); backdrop-filter: blur(16px) saturate(1.5); -webkit-backdrop-filter: blur(16px) saturate(1.5); border: 1px solid var(--card-border, rgba(15,23,60,.08)); border-radius: 12px;
  display: flex; flex-direction: column; gap: 4px;
  position: relative; overflow: hidden;
  --sa-accent: transparent;
}
.sa-stat::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--sa-accent);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}
.sa-stat-val { font-size: 22px; font-weight: 400; letter-spacing: -.025em; color: var(--t1, #0F172A); }
.sa-stat-lab { font-size: 10px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; color: var(--t3, var(--t3)); }
.sa-stat-green { --sa-accent: var(--green); }
.sa-stat-blue  { --sa-accent: var(--blue); }
.sa-stat-grey  { --sa-accent: #94A3B8; }

.sa-notice, .sa-error { padding: 11px 15px; border-radius: 11px; font-size: 13px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
.sa-notice { background: rgba(29,158,117,.10); border: 1px solid rgba(29,158,117,.25); color: #14724E; }
.sa-error  { background: rgba(239,68,68,.10); border: 1px solid rgba(239,68,68,.25); color: #B91C1C; }
.sa-error-close { background: none; border: none; color: inherit; font-size: 18px; cursor: pointer; padding: 0 4px; }

.sa-filters { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.sa-search {
  flex: 1; height: 36px; padding: 0 13px;
  border-radius: 10px; border: 1px solid rgba(15,23,60,.12);
  background: var(--bg1, #fff); font-size: 13px; transition: all .15s;
}
.sa-search:focus { outline: none; border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127,119,221,.18); }

.sa-segmented { display: flex; background: rgba(15,23,60,.04); padding: 3px; border-radius: 10px; gap: 2px; }
.sa-seg-btn {
  height: 30px; padding: 0 11px; border: none; background: transparent;
  font-size: 12px; font-weight: 500; cursor: pointer;
  border-radius: 8px; color: var(--t2, #475569); transition: all .15s;
  display: flex; align-items: center; gap: 6px;
}
.sa-seg-btn:hover { color: var(--t1, #0F172A); }
.sa-seg-btn.active { background: var(--bg1, #fff); color: var(--t1, #0F172A); box-shadow: 0 1px 3px rgba(15,23,60,.08); }
.sa-seg-count { color: var(--t3, #94A3B8); font-size: 11px; }
.sa-seg-btn.active .sa-seg-count { color: var(--t3, var(--t3)); }

.sa-table-wrap { background: var(--card-bg, rgba(255,255,255,0.82)); backdrop-filter: blur(16px) saturate(1.5); -webkit-backdrop-filter: blur(16px) saturate(1.5); border: 1px solid var(--card-border, rgba(15,23,60,.08)); border-radius: 12px; overflow: hidden; box-shadow: 0 2px 6px rgba(15,23,60,.04); }
.sa-table { width: 100%; border-collapse: collapse; }
.sa-table th { font-size: 10px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; color: var(--t3, var(--t3)); text-align: left; padding: 11px 15px; border-bottom: 1px solid rgba(15,23,60,.08); background: rgba(15,23,60,.02); }
.sa-th-center { text-align: center; }
.sa-th-right { text-align: right; }
.sa-table td { padding: 13px 15px; font-size: 13px; color: var(--t1, #0F172A); border-bottom: 1px solid rgba(15,23,60,.04); }
.sa-table tbody tr:hover { background: rgba(127,119,221,.03); }
.sa-table tbody tr:last-child td { border-bottom: none; }

.sa-cell-user { min-width: 220px; }
.sa-user-name { font-weight: 500; color: var(--t1, #0F172A); display: flex; gap: 8px; align-items: center; }
.sa-user-email { font-size: 11px; color: var(--t3, var(--t3)); margin-top: 2px; }
.sa-owner-tag { font-size: 9px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; padding: 2px 6px; border-radius: 6px; background: rgba(127,119,221,.12); color: #5B53C2; }

.sa-chip { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 11px; font-size: 11px; font-weight: 500; letter-spacing: .02em; }
.sa-chip-green { background: rgba(29,158,117,.12); color: #14724E; }
.sa-chip-blue  { background: rgba(55,138,221,.12); color: #2865A7; }
.sa-chip-grey  { background: rgba(100,116,139,.10); color: var(--t3, var(--t3)); }

.sa-recovery { font-variant-numeric: tabular-nums; font-size: 13px; color: var(--t1, #0F172A); }
.sa-recovery-sep { color: #CBD5E1; margin: 0 1px; }
.sa-dim { color: #CBD5E1; }

.sa-cell-login { font-size: 12px; color: var(--t2, #475569); }
.sa-cell-login-ip { font-size: 10px; color: var(--t3, #94A3B8); margin-top: 2px; font-family: ui-monospace,"SF Mono",Menlo,monospace; }

.sa-btn-ghost {
  height: 36px; padding: 0 14px; border-radius: 10px; border: none;
  background: rgba(127,119,221,.08); color: #5B53C2;
  font-size: 12px; font-weight: 500; cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px; transition: all .15s;
}
.sa-btn-ghost:hover:not(:disabled) { background: rgba(127,119,221,.14); }
.sa-btn-ghost:disabled { opacity: .5; cursor: not-allowed; }

.sa-btn-danger-mini {
  height: 26px; padding: 0 10px; border-radius: 7px; border: none;
  background: rgba(239,68,68,.08); color: #B91C1C;
  font-size: 11px; font-weight: 500; cursor: pointer; transition: all .15s;
}
.sa-btn-danger-mini:hover:not(:disabled) { background: rgba(239,68,68,.16); }
.sa-btn-danger-mini:disabled { opacity: .35; cursor: not-allowed; }

.sa-empty, .sa-loading-row { text-align: center; padding: 40px; color: var(--t3, #94A3B8); font-size: 13px; }

/* Modal */
.sa-modal-backdrop { position: fixed; inset: 0; z-index: 1000; background: rgba(15,18,40,.45); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: 20px; animation: bgIn .25s; }
@keyframes bgIn { from { opacity: 0; } to { opacity: 1; } }
.sa-modal { background: var(--card-bg, rgba(255,255,255,0.86)); border: 1px solid var(--card-border, transparent); border-radius: 14px; max-width: 480px; width: 100%; box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08); animation: modalIn .45s var(--ease-standard); }
@keyframes modalIn { from { opacity: 0; transform: translateY(20px) scale(.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
.sa-modal-head { padding: 18px 22px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(15,23,60,.06); }
.sa-modal-head h3 { font-size: 15px; font-weight: 500; letter-spacing: -.01em; color: var(--t1, #0F172A); margin: 0; }
.sa-modal-x { background: none; border: none; font-size: 22px; cursor: pointer; color: var(--t3, #94A3B8); padding: 0 4px; }
.sa-modal-x:hover { color: var(--t1, #0F172A); }
.sa-modal-body { padding: 20px 22px; display: flex; flex-direction: column; gap: 12px; font-size: 13px; color: var(--t2, #334155); line-height: 1.55; }

.sa-target-block { padding: 12px 14px; background: rgba(127,119,221,.06); border: 1px solid rgba(127,119,221,.18); border-radius: 10px; }
.sa-target-name { font-weight: 500; color: var(--t1, #0F172A); }
.sa-target-email { font-size: 11px; color: var(--t3, var(--t3)); margin-top: 2px; }
.sa-modal-list { margin: 0; padding-left: 18px; }
.sa-modal-list li { padding: 3px 0; }
.sa-warn-strong { background: rgba(239,159,39,.10); border: 1px solid rgba(239,159,39,.25); color: #B45309; padding: 10px 14px; border-radius: 10px; margin: 0; }
.sa-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }
.sa-btn-danger { height: 38px; padding: 0 16px; border-radius: 11px; border: none; background: rgba(239,68,68,.10); color: #B91C1C; font-size: 13px; font-weight: 500; cursor: pointer; transition: all .15s; }
.sa-btn-danger:hover:not(:disabled) { background: rgba(239,68,68,.18); }
.sa-btn-danger:disabled { opacity: .45; cursor: not-allowed; }

</style>
