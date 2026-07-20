<script setup lang="ts">
/**
 * CompanyEmployeesTab — премиум-раздел «Сотрудники» в карточке компании.
 *
 * Структурно выстроен по аналогии с вкладкой «Корп. управление»: KPI-стрип
 * сверху, аналитический блок (распределение по отделам с кликом-фильтром),
 * переключатель вида (по отделам / списком / в сети), затем карточки людей.
 * Наведение → быстрая карточка, клик → полноценный профиль (UserCardAnchor →
 * useUserModal). Онлайн-точка, stagger-анимации, honest «нет данных ≠ 0».
 */
import { computed, ref, watch } from "vue";
import { companiesApi, type CompanyEmployee } from "@/api/companies";
import { formatRelativeTime } from "@/api/audit";
import UserAffiliationBadge from "@/components/rbac-v3/UserAffiliationBadge.vue";
import UserCardAnchor from "@/components/user/UserCardAnchor.vue";
import UzaSegment from "@/components/UZA/UzaSegment.vue";

const props = defineProps<{ code: string }>();

const loading = ref(true);
const error = ref<string | null>(null);
const employees = ref<CompanyEmployee[]>([]);
const search = ref("");
const deptFilter = ref<string | null>(null);
const viewMode = ref<"dept" | "list" | "online">("dept");

const VIEW_OPTIONS = [
  { value: "dept", label: "По отделам" },
  { value: "list", label: "Списком" },
  { value: "online", label: "В сети", dot: "#1D9E75" },
];

async function load() {
  if (!props.code) return;
  loading.value = true;
  error.value = null;
  try {
    const res = await companiesApi.getEmployees(props.code);
    employees.value = res.employees;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось загрузить сотрудников";
    employees.value = [];
  } finally {
    loading.value = false;
  }
}
watch(() => props.code, () => { deptFilter.value = null; search.value = ""; load(); }, { immediate: true });

function isOnline(e: CompanyEmployee): boolean {
  if (!e.last_active) return false;
  return Date.now() - new Date(e.last_active).getTime() < 5 * 60 * 1000;
}

// ── KPI ──────────────────────────────────────────────────────────
const activeCount = computed(() => employees.value.filter((e) => e.is_active).length);
const onlineCount = computed(() => employees.value.filter((e) => isOnline(e)).length);
const deptCount = computed(() => {
  const s = new Set<string>();
  for (const e of employees.value) s.add(e.department || "Без отдела");
  return s.size;
});

const kpis = computed(() => [
  { label: "Сотрудников", value: employees.value.length, color: "#7F77DD" },
  { label: "Активных", value: activeCount.value, color: "#1D9E75" },
  { label: "В сети сейчас", value: onlineCount.value, color: "#0E7490" },
  { label: deptCount.value === 1 ? "Отдел" : "Отделов", value: deptCount.value, color: "#A855F7" },
]);

// ── Распределение по отделам (аналитика + фильтр) ────────────────
const deptDistribution = computed(() => {
  const map = new Map<string, number>();
  for (const e of employees.value) {
    const key = e.department || "Без отдела";
    map.set(key, (map.get(key) || 0) + 1);
  }
  const total = employees.value.length || 1;
  return Array.from(map.entries())
    .map(([name, count]) => ({ name, count, pct: Math.round((count / total) * 100) }))
    .sort((a, b) => (a.name === "Без отдела" ? 1 : b.name === "Без отдела" ? -1 : b.count - a.count));
});

function toggleDept(name: string) {
  deptFilter.value = deptFilter.value === name ? null : name;
}

// ── Фильтрация ───────────────────────────────────────────────────
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  let list = employees.value;
  if (deptFilter.value) {
    list = list.filter((e) => (e.department || "Без отдела") === deptFilter.value);
  }
  if (viewMode.value === "online") {
    list = list.filter((e) => isOnline(e));
  }
  if (q) {
    list = list.filter((e) =>
      (e.full_name || "").toLowerCase().includes(q) ||
      (e.email || "").toLowerCase().includes(q) ||
      (e.department || "").toLowerCase().includes(q) ||
      (e.job_title || "").toLowerCase().includes(q) ||
      (e.role || "").toLowerCase().includes(q),
    );
  }
  return list;
});

/** Группировка по отделам (только для вида «По отделам»). */
const groups = computed(() => {
  const map = new Map<string, CompanyEmployee[]>();
  for (const e of filtered.value) {
    const key = e.department || "Без отдела";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(e);
  }
  return Array.from(map.entries())
    .sort((a, b) => (a[0] === "Без отдела" ? 1 : b[0] === "Без отдела" ? -1 : b[1].length - a[1].length))
    .map(([department, people]) => ({ department, people }));
});

/** Плоский отсортированный список (для видов «Списком» / «В сети»). */
const flatList = computed(() =>
  [...filtered.value].sort((a, b) => (a.full_name || "").localeCompare(b.full_name || "", "ru")),
);
</script>

<template>
  <div class="cet">
    <!-- Header -->
    <div class="cet-hd">
      <div class="cet-hd-l">
        <h2 class="cet-title">Сотрудники</h2>
        <span v-if="!loading" class="cet-count">{{ employees.length }}</span>
      </div>
      <div v-if="!loading && employees.length" class="cet-search-wrap">
        <svg class="cet-search-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
        <input v-model="search" class="cet-search" placeholder="Поиск по имени, отделу, должности…" />
      </div>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="cet-grid" style="margin-top:18px">
      <div v-for="i in 6" :key="i" class="cet-card cet-skel">
        <div class="cet-skel-av"></div>
        <div class="cet-skel-lines"><span></span><span></span></div>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="cet-empty cet-err">{{ error }}</div>

    <!-- Empty (honest: нет данных ≠ 0) -->
    <div v-else-if="!employees.length" class="cet-empty">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
      <div>К этой компании пока не привязан ни один пользователь</div>
      <p>Привязка задаётся в профиле сотрудника (поле «Компания») или администратором.</p>
    </div>

    <template v-else>
      <!-- KPI strip -->
      <div class="cet-kpis">
        <div
          v-for="(k, ki) in kpis"
          :key="k.label"
          class="cet-kpi"
          :style="`--accent:${k.color};--d:${ki}`"
        >
          <div class="cet-kpi-l">{{ k.label }}</div>
          <div class="cet-kpi-v">
            {{ k.value }}
            <span v-if="k.label === 'В сети сейчас' && k.value > 0" class="cet-kpi-live"></span>
          </div>
        </div>
      </div>

      <!-- Распределение по отделам (клик = фильтр) -->
      <div v-if="deptDistribution.length > 1" class="cet-dist">
        <div class="cet-dist-hd">
          <span class="cet-dist-title">По отделам</span>
          <button v-if="deptFilter" class="cet-dist-clear" @click="deptFilter = null">
            Сбросить фильтр
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="cet-dist-bars">
          <button
            v-for="(d, di) in deptDistribution"
            :key="d.name"
            class="cet-dist-bar"
            :class="{ 'cet-dist-bar--on': deptFilter === d.name, 'cet-dist-bar--dim': deptFilter && deptFilter !== d.name }"
            :style="`--d:${di}`"
            @click="toggleDept(d.name)"
          >
            <div class="cet-dist-bar-hd">
              <span class="cet-dist-bar-name">{{ d.name }}</span>
              <span class="cet-dist-bar-cnt">{{ d.count }}</span>
            </div>
            <div class="cet-dist-bar-track">
              <div class="cet-dist-bar-fill" :style="`width:${d.pct}%;--d:${di}`"></div>
            </div>
          </button>
        </div>
      </div>

      <!-- View toggle -->
      <div class="cet-toolbar">
        <UzaSegment v-model="viewMode" :options="VIEW_OPTIONS" size="sm" />
        <span class="cet-toolbar-sub">
          <template v-if="deptFilter">Отдел «{{ deptFilter }}» · </template>{{ filtered.length }} из {{ employees.length }}
        </span>
      </div>

      <!-- No results (после фильтров) -->
      <div v-if="filtered.length === 0" class="cet-empty cet-empty--sm">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
        <div>{{ viewMode === 'online' ? 'Сейчас никого нет в сети' : 'Никто не найден' }}</div>
      </div>

      <!-- Grouped by department -->
      <div v-else-if="viewMode === 'dept'" class="cet-groups">
        <div v-for="(g, gi) in groups" :key="g.department" class="cet-group">
          <div class="cet-group-hd">
            <span class="cet-group-name">{{ g.department }}</span>
            <span class="cet-group-cnt">{{ g.people.length }}</span>
          </div>
          <div class="cet-grid">
            <UserCardAnchor
              v-for="(e, i) in g.people"
              :key="e.id"
              tag="div"
              :user-id="e.id"
              :preview="e"
              class="cet-card"
              :class="{ 'cet-card--off': !e.is_active }"
              :style="{ animationDelay: (gi * 50 + i * 32) + 'ms' }"
            >
              <div class="cet-av" :style="{ background: e.accent }">
                <img v-if="e.avatar_url" :src="e.avatar_url" alt="" />
                <span v-else>{{ e.initials }}</span>
                <span v-if="isOnline(e)" class="cet-online" title="В сети"></span>
              </div>
              <div class="cet-info">
                <div class="cet-name">
                  {{ e.full_name }}
                  <span v-if="e.is_owner" class="cet-owner" title="Владелец">★</span>
                </div>
                <div v-if="e.role || e.job_title" class="cet-role">{{ e.job_title || e.role }}</div>
                <UserAffiliationBadge
                  v-if="e.job_title && e.role"
                  :job-title="e.role" size="sm" class="cet-badge"
                />
                <div class="cet-last">{{ e.last_active ? formatRelativeTime(e.last_active) : 'нет активности' }}</div>
              </div>
              <svg class="cet-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
            </UserCardAnchor>
          </div>
        </div>
      </div>

      <!-- Flat list / online -->
      <div v-else class="cet-grid" style="margin-top:16px">
        <UserCardAnchor
          v-for="(e, i) in flatList"
          :key="e.id"
          tag="div"
          :user-id="e.id"
          :preview="e"
          class="cet-card"
          :class="{ 'cet-card--off': !e.is_active }"
          :style="{ animationDelay: (i * 28) + 'ms' }"
        >
          <div class="cet-av" :style="{ background: e.accent }">
            <img v-if="e.avatar_url" :src="e.avatar_url" alt="" />
            <span v-else>{{ e.initials }}</span>
            <span v-if="isOnline(e)" class="cet-online" title="В сети"></span>
          </div>
          <div class="cet-info">
            <div class="cet-name">
              {{ e.full_name }}
              <span v-if="e.is_owner" class="cet-owner" title="Владелец">★</span>
            </div>
            <div v-if="e.role || e.job_title" class="cet-role">{{ e.job_title || e.role }}</div>
            <div v-if="e.department" class="cet-dept-tag">{{ e.department }}</div>
            <div class="cet-last">{{ e.last_active ? formatRelativeTime(e.last_active) : 'нет активности' }}</div>
          </div>
          <svg class="cet-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
        </UserCardAnchor>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cet { padding: 4px 2px 32px; }

.cet-hd { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.cet-hd-l { display: flex; align-items: center; gap: 10px; }
.cet-title { font-size: 18px; font-weight: 600; color: var(--t1, #1A1730); margin: 0; }
.cet-count {
  font-size: 12px; font-weight: 600; color: var(--p-deep, #534AB7);
  background: rgba(124,111,247,.12); border-radius: 999px; padding: 2px 10px;
}

.cet-search-wrap { position: relative; display: flex; align-items: center; }
.cet-search-ic { position: absolute; left: 11px; width: 15px; height: 15px; color: var(--t3, #94A3B8); pointer-events: none; }
.cet-search {
  width: 280px; max-width: 100%; padding: 8px 12px 8px 34px;
  border: 1.5px solid var(--line, #E8E6F0); border-radius: 10px;
  font-size: 13px; outline: none; font-family: inherit; background: var(--bg2, #F8FAFC);
  transition: border-color .14s, box-shadow .14s;
}
.cet-search:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124,111,247,.14); }

/* ── KPI strip (эталон: top-accent, число 400, капс-лейбл) ── */
.cet-kpis {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px;
  margin-top: 18px;
}
.cet-kpi {
  background: #fff; border: .5px solid var(--line, #ECEAF4);
  border-top: 3px solid var(--accent, #7F77DD); border-radius: 10px;
  padding: 12px 14px; box-shadow: 0 2px 8px rgba(15,23,60,.04);
  animation: cetKpiIn .42s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both;
  animation-delay: calc(var(--d,0) * 45ms);
  transition: transform .16s var(--ease-standard, cubic-bezier(.4,0,.2,1)), box-shadow .16s;
}
.cet-kpi:hover { transform: translateY(-2px); box-shadow: 0 10px 24px -10px rgba(40,32,80,.22); }
@keyframes cetKpiIn { from { opacity: 0; transform: translateY(9px); } to { opacity: 1; transform: none; } }
.cet-kpi-l { font-size: 9.5px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: var(--t3, #94A3B8); }
.cet-kpi-v {
  font-size: 24px; font-weight: 400; letter-spacing: -.025em; color: var(--t1, #1A1730);
  font-variant-numeric: tabular-nums; margin-top: 4px; display: flex; align-items: center; gap: 8px;
}
.cet-kpi-live {
  width: 8px; height: 8px; border-radius: 50%; background: #1D9E75;
  box-shadow: 0 0 0 0 rgba(29,158,117,.5); animation: cetPulseDot 1.8s ease-out infinite;
}
@keyframes cetPulseDot {
  0% { box-shadow: 0 0 0 0 rgba(29,158,117,.5); }
  70% { box-shadow: 0 0 0 7px rgba(29,158,117,0); }
  100% { box-shadow: 0 0 0 0 rgba(29,158,117,0); }
}

/* ── Распределение по отделам ── */
.cet-dist {
  margin-top: 14px; padding: 14px 16px; border-radius: 12px;
  background: #fff; border: .5px solid var(--line, #ECEAF4);
}
.cet-dist-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.cet-dist-title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t2, #6B6880); }
.cet-dist-clear {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; color: var(--p-deep, #534AB7); background: rgba(124,111,247,.1);
  border: none; border-radius: 999px; padding: 3px 9px; cursor: pointer; font-family: inherit;
  transition: background .14s;
}
.cet-dist-clear:hover { background: rgba(124,111,247,.18); }
.cet-dist-clear svg { width: 11px; height: 11px; }
.cet-dist-bars { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px 16px; }
.cet-dist-bar {
  text-align: left; background: transparent; border: none; padding: 4px; margin: -4px;
  border-radius: 8px; cursor: pointer; font-family: inherit;
  animation: cetKpiIn .42s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both;
  animation-delay: calc(var(--d,0) * 40ms);
  transition: background .14s, opacity .16s;
}
.cet-dist-bar:hover { background: var(--bg2, #F6F5FC); }
.cet-dist-bar--on { background: rgba(124,111,247,.09); }
.cet-dist-bar--dim { opacity: .48; }
.cet-dist-bar-hd { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 5px; }
.cet-dist-bar-name {
  font-size: 12px; font-weight: 500; color: var(--t1, #1A1730);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cet-dist-bar-cnt { font-size: 12px; font-weight: 500; color: var(--t2, #6B6880); font-variant-numeric: tabular-nums; }
.cet-dist-bar-track { height: 6px; border-radius: 999px; overflow: hidden; background: var(--bg3, #EEEDF4); }
.cet-dist-bar-fill {
  height: 100%; border-radius: 999px;
  background: linear-gradient(90deg, #7C6FF7, #A855F7);
  transform-origin: left;
  animation: cetBarFill .75s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both;
  animation-delay: calc(.15s + var(--d,0) * 40ms);
}
@keyframes cetBarFill { from { transform: scaleX(0); } to { transform: scaleX(1); } }

/* ── Toolbar ── */
.cet-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; margin-top: 18px; }
.cet-toolbar-sub { font-size: 12px; color: var(--t3, #8B889C); }

.cet-groups { margin-top: 14px; display: flex; flex-direction: column; gap: 22px; }
.cet-group-hd { display: flex; align-items: center; gap: 8px; margin-bottom: 11px; }
.cet-group-name { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t2, #6B6880); }
.cet-group-cnt { font-size: 11px; color: var(--t3, #94A3B8); background: var(--bg2, #F1F0F7); border-radius: 999px; padding: 1px 8px; }

.cet-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(248px, 1fr)); gap: 12px;
}

.cet-card {
  display: flex; align-items: center; gap: 12px;
  padding: 13px 14px; border-radius: 14px;
  background: var(--bg1, #fff); border: 1px solid var(--line, #ECEAF4);
  cursor: pointer;
  transition: transform .16s var(--ease-standard, cubic-bezier(.4,0,.2,1)), box-shadow .16s, border-color .16s;
  animation: cetIn .4s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both;
}
.cet-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 26px -10px rgba(40,32,80,.28);
  border-color: rgba(124,111,247,.4);
}
.cet-card:hover .cet-chev { opacity: 1; transform: translateX(0); }
.cet-card--off { opacity: .55; }
@keyframes cetIn { from { opacity: 0; transform: translateY(10px) scale(.97); } to { opacity: 1; transform: none; } }

.cet-av {
  position: relative; width: 44px; height: 44px; border-radius: 12px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 600; font-size: 15px; overflow: visible;
  box-shadow: 0 2px 8px -2px rgba(0,0,0,.25);
}
.cet-av img { width: 100%; height: 100%; border-radius: 12px; object-fit: cover; }
.cet-online {
  position: absolute; right: -2px; bottom: -2px; width: 11px; height: 11px;
  border-radius: 50%; background: #1D9E75; box-shadow: 0 0 0 2px var(--bg1, #fff);
}
.cet-info { min-width: 0; flex: 1; }
.cet-name {
  font-size: 13.5px; font-weight: 600; color: var(--t1, #1A1730);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  display: flex; align-items: center; gap: 5px;
}
.cet-owner { color: #EF9F27; font-size: 12px; }
.cet-role {
  font-size: 11.5px; color: var(--t2, #6B6880); margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cet-dept-tag {
  display: inline-block; margin-top: 5px; font-size: 10.5px; color: var(--t2, #6B6880);
  background: var(--bg2, #F1F0F7); border-radius: 6px; padding: 1px 7px;
}
.cet-badge { margin-top: 5px; }
.cet-last { font-size: 10.5px; color: var(--t3, #A6A3B8); margin-top: 5px; }
.cet-chev {
  width: 15px; height: 15px; flex-shrink: 0; color: var(--t3, #C9C6DA);
  opacity: 0; transform: translateX(-4px); transition: opacity .16s, transform .16s;
}

.cet-empty {
  margin-top: 40px; text-align: center; color: var(--t3, #8B889C);
  display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 30px;
}
.cet-empty--sm { margin-top: 20px; padding: 22px; }
.cet-empty svg { width: 40px; height: 40px; color: #C9C6DA; }
.cet-empty--sm svg { width: 30px; height: 30px; }
.cet-empty div { font-size: 14px; color: var(--t2, #6B6880); font-weight: 500; }
.cet-empty p { font-size: 12px; max-width: 360px; margin: 0; line-height: 1.5; }
.cet-err { color: #C5352F; }

/* Skeleton */
.cet-skel { pointer-events: none; animation: none; }
.cet-skel-av { width: 44px; height: 44px; border-radius: 12px; background: var(--bg2, #EEEDF4); flex-shrink: 0; }
.cet-skel-lines { flex: 1; display: flex; flex-direction: column; gap: 7px; }
.cet-skel-lines span { height: 9px; border-radius: 5px; background: var(--bg2, #EEEDF4); }
.cet-skel-lines span:first-child { width: 70%; }
.cet-skel-lines span:last-child { width: 45%; }
.cet-skel-av, .cet-skel-lines span { animation: cetPulse 1.3s ease-in-out infinite; }
@keyframes cetPulse { 0%,100% { opacity: 1; } 50% { opacity: .5; } }

@media (prefers-reduced-motion: reduce) {
  .cet-kpi, .cet-card, .cet-dist-bar, .cet-dist-bar-fill { animation: none; }
}
</style>
