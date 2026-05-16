<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { auditApi } from '@/api/rbacV3';
import type { RbacV3AuditEvent, RbacV3AuditEventDetail } from '@/api/rbacV3';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';

const events = ref<RbacV3AuditEvent[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);

// Filters
type Period = 24 | 168 | 720 | 0;  // 0 = all
const period = ref<Period>(24);
const moduleFilter = ref<string>('');
const onlyCritical = ref(false);
const search = ref('');
const page = ref(1);

const MODULES = [
  '', 'rbac', 'users', 'roles', 'kpi', 'bp', 'credit', 'invest',
  'procurement', 'esg', 'governance', 'auth', 'admin'
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await auditApi.list({
      hours: period.value || undefined,
      module: moduleFilter.value || undefined,
      only_critical: onlyCritical.value || undefined,
      search: search.value.trim() || undefined,
      page: page.value,
      per_page: 50,
    });
    events.value = resp.items;
    total.value = resp.total;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось загрузить журнал';
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch([period, moduleFilter, onlyCritical], () => { page.value = 1; load(); });

let searchTimer: any = null;
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { page.value = 1; load(); }, 300);
}

// ─── Helpers ────────────────────────────────────────────────────

function fmtRelative(s: string): string {
  const diff = (Date.now() - new Date(s).getTime()) / 1000;
  if (diff < 60) return 'только что';
  if (diff < 3600) return Math.floor(diff / 60) + ' мин';
  if (diff < 86400) return Math.floor(diff / 3600) + ' ч';
  const days = Math.floor(diff / 86400);
  if (days === 1) return 'вчера';
  if (days < 30) return days + ' дн';
  return Math.floor(days / 30) + ' мес';
}

function fmtAbsolute(s: string): string {
  return new Date(s).toLocaleString('ru-RU');
}

interface Severity { color: string; label: string; }

function severity(e: RbacV3AuditEvent): Severity {
  if (e.is_critical || /delete|delete_permanent|revoke|deactivate/i.test(e.action))
    return { color: '#E24B4A', label: 'critical' };
  if (/update|change|grant|assign|create/i.test(e.action))
    return { color: '#EF9F27', label: 'warning' };
  return { color: '#888780', label: 'info' };
}

// Human-readable description of event
function describe(e: RbacV3AuditEvent): string {
  const a = e.action;
  const entity = e.entity_label || e.entity_type || '';
  const mod = e.module || '';

  // RBAC events — most common
  if (a === 'user.create' || a === 'user.invite')
    return `пригласил(а) пользователя ${entity}`;
  if (a === 'user.delete_permanent')
    return `удалил(а) пользователя навсегда: ${entity}`;
  if (a === 'user.deactivate' || a === 'user.disable')
    return `деактивировал(а) пользователя ${entity}`;
  if (a === 'user.activate' || a === 'user.enable')
    return `активировал(а) пользователя ${entity}`;
  if (a === 'user.update')
    return `изменил(а) данные пользователя ${entity}`;
  if (a === 'user.assign_role' || a === 'role.assign')
    return `назначил(а) роль ${entity}`;
  if (a === 'user.remove_role' || a === 'role.unassign')
    return `убрал(а) роль у ${entity}`;
  if (a === 'role.create')
    return `создал(а) роль ${entity}`;
  if (a === 'role.delete')
    return `удалил(а) роль ${entity}`;
  if (a === 'role.update_permissions' || a === 'role.permissions_changed')
    return `изменил(а) разрешения роли ${entity}`;
  if (a === 'group.create')
    return `создал(а) группу ${entity}`;
  if (a === 'group.delete')
    return `удалил(а) группу ${entity}`;
  if (a === 'group.update' || a === 'group.update_members' || a === 'group.update_permissions')
    return `изменил(а) группу ${entity}`;
  if (a === 'email_rule.create')
    return `создал(а) email-правило ${entity}`;
  if (a === 'email_rule.delete')
    return `удалил(а) email-правило ${entity}`;
  if (a === 'auth.login.success' || a === 'login.success')
    return `успешный вход`;
  if (a === 'auth.login.failed' || a === 'login.failed')
    return `неудачная попытка входа`;
  if (a === 'permission.grant')
    return `выдал(а) разрешение ${entity}`;
  if (a === 'permission.revoke')
    return `отозвал(а) разрешение ${entity}`;
  if (a === 'mfa.enabled')
    return `включил(а) MFA`;
  if (a === 'mfa.disabled')
    return `отключил(а) MFA`;

  // Fallback: action + module + entity
  return `${a}${entity ? ': ' + entity : ''}${mod ? ' [' + mod + ']' : ''}`;
}

// Detail expansion
const expandedId = ref<string | null>(null);
const detailCache = ref<Record<string, RbacV3AuditEventDetail>>({});
const detailLoading = ref<string | null>(null);

async function toggleDetail(id: string) {
  if (expandedId.value === id) { expandedId.value = null; return; }
  expandedId.value = id;
  if (!detailCache.value[id]) {
    detailLoading.value = id;
    try {
      detailCache.value[id] = await auditApi.get(id);
    } catch (e) {
      console.error(e);
    } finally {
      detailLoading.value = null;
    }
  }
}

function exportCsv() {
  const url = auditApi.exportCsvUrl({
    hours: period.value || undefined,
    module: moduleFilter.value || undefined,
    only_critical: onlyCritical.value || undefined,
    search: search.value.trim() || undefined,
  });
  window.open(url, '_blank');
}

// Group events by day for date-headers in feed
const grouped = computed(() => {
  const groups: { date: string; label: string; events: RbacV3AuditEvent[] }[] = [];
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);

  for (const e of events.value) {
    const d = new Date(e.created_at);
    const key = d.toISOString().slice(0, 10);
    let group = groups.find(g => g.date === key);
    if (!group) {
      let label: string;
      const day = new Date(d); day.setHours(0, 0, 0, 0);
      if (day.getTime() === today.getTime()) label = 'Сегодня';
      else if (day.getTime() === yesterday.getTime()) label = 'Вчера';
      else label = day.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' });
      group = { date: key, label, events: [] };
      groups.push(group);
    }
    group.events.push(e);
  }
  return groups;
});

const hasMorePages = computed(() => events.value.length === 50 && events.value.length < total.value);
function nextPage() { page.value++; load(); }
function prevPage() { if (page.value > 1) { page.value--; load(); } }
</script>

<template>
  <div class="rv3-audit-shell">
    <!-- LEFT: filters sidebar -->
    <div class="rv3-au-filters">
      <div class="rv3-au-section-title">Период</div>
      <div class="rv3-au-period-list">
        <button :class="['rv3-au-period', { on: period === 24 }]"  @click="period = 24">Сутки</button>
        <button :class="['rv3-au-period', { on: period === 168 }]" @click="period = 168">7 дней</button>
        <button :class="['rv3-au-period', { on: period === 720 }]" @click="period = 720">30 дней</button>
        <button :class="['rv3-au-period', { on: period === 0 }]"   @click="period = 0">Всё</button>
      </div>

      <div class="rv3-au-section-title" style="margin-top:18px">Модуль</div>
      <select v-model="moduleFilter" class="rv3-au-select">
        <option v-for="m in MODULES" :key="m" :value="m">{{ m || 'Все модули' }}</option>
      </select>

      <div class="rv3-au-section-title" style="margin-top:18px">Серьёзность</div>
      <label class="rv3-au-cb">
        <input type="checkbox" v-model="onlyCritical" />
        <span class="rv3-au-sw" style="background:#E24B4A"></span>
        <span>Только critical</span>
      </label>

      <button class="rv3-au-export" @click="exportCsv">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v10M4 7l4-4 4 4M3 13h10"/></svg>
        Экспорт в CSV
      </button>
    </div>

    <!-- RIGHT: feed -->
    <div class="rv3-au-feed">
      <!-- Search bar -->
      <div class="rv3-au-search-bar">
        <input
          v-model="search"
          @input="onSearchInput"
          placeholder="Поиск по email, действию, объекту..."
          class="rv3-au-search"
        />
        <span class="rv3-au-counter">показано {{ events.length }} из {{ total }}</span>
      </div>

      <!-- States -->
      <div v-if="loading && events.length === 0" class="rv3-state">Загрузка...</div>
      <div v-else-if="error" class="rv3-state rv3-state-err">{{ error }}</div>
      <div v-else-if="events.length === 0" class="rv3-empty-card">
        <div class="rv3-empty-icon">
          <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#D1D5DB" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12,6 12,12 16,14"/>
          </svg>
        </div>
        <div class="rv3-empty-title">Событий не найдено</div>
        <div class="rv3-empty-text">Измените период или фильтры</div>
      </div>

      <!-- Feed grouped by day -->
      <template v-else>
        <div v-for="group in grouped" :key="group.date" class="rv3-au-group">
          <div class="rv3-au-day">{{ group.label }} · {{ group.events.length }}</div>

          <div v-for="e in group.events" :key="e.id" class="rv3-au-event">
            <div class="rv3-au-avatar-wrap">
              <UserAvatar :email="e.actor_email || ''" :size="30" />
              <span class="rv3-au-dot" :style="{ background: severity(e).color }"></span>
            </div>

            <div class="rv3-au-body">
              <div class="rv3-au-line">
                <strong>{{ e.actor_email || 'система' }}</strong>
                <span class="rv3-au-sep">·</span>
                <span :style="{ color: severity(e).color, fontWeight: e.is_critical ? 500 : 400 }">{{ describe(e) }}</span>
              </div>
              <div class="rv3-au-meta">
                <span :title="fmtAbsolute(e.created_at)">{{ fmtRelative(e.created_at) }} назад</span>
                <span v-if="e.ip_address" class="rv3-au-sep">·</span>
                <span v-if="e.ip_address">{{ e.ip_address }}</span>
                <span v-if="e.module" class="rv3-au-sep">·</span>
                <span v-if="e.module" class="rv3-au-tag">{{ e.module }}</span>
                <span v-if="e.http_status && e.http_status >= 400" class="rv3-au-sep">·</span>
                <span v-if="e.http_status && e.http_status >= 400" class="rv3-au-http-err">HTTP {{ e.http_status }}</span>
              </div>

              <button
                v-if="e.has_diff || e.has_payload"
                class="rv3-au-expand"
                @click="toggleDetail(e.id)"
              >
                {{ expandedId === e.id ? '▾ скрыть' : '▸ подробности' }}
              </button>

              <div v-if="expandedId === e.id" class="rv3-au-detail">
                <div v-if="detailLoading === e.id" class="rv3-au-loading">Загрузка...</div>
                <template v-else-if="detailCache[e.id]">
                  <div v-if="detailCache[e.id].diff" class="rv3-au-block">
                    <div class="rv3-au-block-hd">diff</div>
                    <pre>{{ JSON.stringify(detailCache[e.id].diff, null, 2) }}</pre>
                  </div>
                  <div v-if="detailCache[e.id].payload" class="rv3-au-block">
                    <div class="rv3-au-block-hd">payload</div>
                    <pre>{{ JSON.stringify(detailCache[e.id].payload, null, 2) }}</pre>
                  </div>
                </template>
              </div>
            </div>

            <div class="rv3-au-time" :title="fmtAbsolute(e.created_at)">{{ fmtRelative(e.created_at) }}</div>
          </div>
        </div>

        <!-- Pagination -->
        <div class="rv3-au-pager" v-if="total > 50">
          <button :disabled="page === 1" @click="prevPage" class="rv3-au-page-btn">← Назад</button>
          <span class="rv3-au-page-num">страница {{ page }} из {{ Math.ceil(total / 50) }}</span>
          <button :disabled="!hasMorePages" @click="nextPage" class="rv3-au-page-btn">Вперёд →</button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.rv3-audit-shell {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 1px;
  background: #E5E7EB;
  min-height: calc(100vh - 56px);
}
.rv3-au-filters { background: #fff; padding: 18px; }
.rv3-au-section-title {
  font-size: 10px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 8px;
}
.rv3-au-period-list { display: flex; flex-direction: column; gap: 2px; }
.rv3-au-period {
  padding: 6px 10px;
  background: transparent; border: none; border-radius: 6px;
  font-size: 11px; color: #1E2A4A; font-weight: 500;
  text-align: left; cursor: pointer; font-family: inherit;
}
.rv3-au-period:hover { background: #FAFAFC; }
.rv3-au-period.on { background: rgba(127,119,221,.12); color: #534AB7; }
.rv3-au-select {
  width: 100%; padding: 7px 10px;
  background: #F9FAFB; border: 0.5px solid #E5E7EB; border-radius: 7px;
  font-size: 12px; color: #1E2A4A; outline: none;
  font-family: inherit; cursor: pointer;
}
.rv3-au-cb {
  display: flex; align-items: center; gap: 7px;
  font-size: 11px; color: #1E2A4A; cursor: pointer;
}
.rv3-au-cb input { accent-color: #7F77DD; cursor: pointer; }
.rv3-au-sw { width: 8px; height: 8px; border-radius: 50%; }
.rv3-au-export {
  width: 100%; margin-top: 18px;
  padding: 7px 12px;
  background: transparent; border: 1px solid #E5E7EB; border-radius: 8px;
  color: #1E2A4A; font-size: 11px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  display: flex; align-items: center; justify-content: center; gap: 6px;
}
.rv3-au-export:hover { background: #FAFAFC; border-color: #D1D5DB; }

.rv3-au-feed { background: #fff; padding: 0; overflow-y: auto; }
.rv3-au-search-bar {
  padding: 14px 22px;
  border-bottom: 0.5px solid #E5E7EB;
  display: flex; gap: 10px; align-items: center;
  position: sticky; top: 0; background: #fff; z-index: 5;
}
.rv3-au-search {
  flex: 1; height: 30px; padding: 0 11px;
  background: #F9FAFB; border: 0.5px solid #E5E7EB; border-radius: 7px;
  font-size: 12px; outline: none; font-family: inherit;
}
.rv3-au-counter { font-size: 11px; color: #888780; }

.rv3-state { padding: 60px; text-align: center; font-size: 13px; color: #888780; }
.rv3-state-err { color: #E24B4A; }
.rv3-empty-card {
  margin: 60px auto; max-width: 480px;
  text-align: center; padding: 32px;
}
.rv3-empty-icon { margin-bottom: 14px; }
.rv3-empty-title { font-size: 14px; font-weight: 500; letter-spacing: -.01em; margin-bottom: 6px; }
.rv3-empty-text { font-size: 12px; color: #888780; }

.rv3-au-group { padding: 0 22px; }
.rv3-au-day {
  padding: 14px 0 6px;
  font-size: 10px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase;
}
.rv3-au-event {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 12px; align-items: flex-start;
  padding: 11px 0;
  border-bottom: 0.5px solid #F3F4F8;
}
.rv3-au-event:last-child { border-bottom: none; }
.rv3-au-avatar-wrap { position: relative; flex-shrink: 0; }
.rv3-au-dot {
  position: absolute; bottom: -2px; right: -2px;
  width: 9px; height: 9px;
  border: 1.5px solid #fff; border-radius: 50%;
}
.rv3-au-body { min-width: 0; }
.rv3-au-line { font-size: 12.5px; color: #1E2A4A; line-height: 1.5; }
.rv3-au-line strong { font-weight: 500; }
.rv3-au-sep { color: #888780; margin: 0 4px; }
.rv3-au-meta {
  font-size: 10.5px; color: #888780; margin-top: 3px;
  display: flex; align-items: center; flex-wrap: wrap; gap: 0;
}
.rv3-au-tag {
  padding: 1px 6px;
  background: #F3F4F8; color: #1E2A4A;
  border-radius: 7px;
  font-size: 9.5px; font-weight: 500; letter-spacing: .04em;
}
.rv3-au-http-err {
  padding: 1px 6px;
  background: rgba(226,75,74,.08); color: #A82C2B;
  border-radius: 7px;
  font-size: 9.5px; font-weight: 500;
}
.rv3-au-expand {
  margin-top: 6px;
  background: transparent; border: none;
  color: #534AB7; font-size: 10.5px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  padding: 2px 0;
}
.rv3-au-expand:hover { color: #463E9F; }
.rv3-au-detail {
  margin-top: 6px;
  padding: 10px 12px;
  background: #F9FAFB; border-radius: 7px;
  font-size: 10.5px;
}
.rv3-au-loading { color: #888780; font-style: italic; }
.rv3-au-block + .rv3-au-block { margin-top: 8px; }
.rv3-au-block-hd {
  font-size: 9.5px; font-weight: 500; color: #888780;
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 3px;
}
.rv3-au-block pre {
  margin: 0;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 10.5px; color: #1E2A4A;
  white-space: pre-wrap; word-break: break-all;
  line-height: 1.5;
}
.rv3-au-time {
  font-size: 10.5px; color: #888780; white-space: nowrap;
  flex-shrink: 0;
}

.rv3-au-pager {
  padding: 18px 22px;
  display: flex; align-items: center; justify-content: center; gap: 14px;
  border-top: 0.5px solid #E5E7EB;
}
.rv3-au-page-btn {
  padding: 5px 11px;
  background: transparent; border: 1px solid #E5E7EB; border-radius: 7px;
  color: #1E2A4A; font-size: 11px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-au-page-btn:hover:not(:disabled) { background: #FAFAFC; }
.rv3-au-page-btn:disabled { opacity: .45; cursor: not-allowed; }
.rv3-au-page-num { font-size: 11px; color: #888780; }
</style>