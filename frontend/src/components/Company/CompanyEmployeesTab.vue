<script setup lang="ts">
/**
 * CompanyEmployeesTab — раздел «Сотрудники» в карточке компании.
 *
 * Визуально 1:1 с вкладкой «Корп. управление»: KPI-карточки (top-accent) →
 * секция-чипы «Отделы» (как «Комитеты совета», клик = фильтр) → секция
 * «Состав» с карточками людей в том же стиле, что и члены совета (круглый
 * аватар, имя, должность, мета-пиллы). Наведение → быстрая карточка, клик →
 * полноценный профиль (UserCardAnchor → useUserModal). Honest «нет данных ≠ 0».
 */
import { computed, ref, watch } from "vue";
import { companiesApi, type CompanyEmployee } from "@/api/companies";
import { formatRelativeTime } from "@/api/audit";
import UserCardAnchor from "@/components/user/UserCardAnchor.vue";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();


const props = defineProps<{ code: string }>();

const loading = ref(true);
const error = ref<string | null>(null);
const employees = ref<CompanyEmployee[]>([]);
const search = ref("");
const deptFilter = ref<string | null>(null);
const NO_DEPARTMENT = "__no_department__";
const departmentKey = (employee: CompanyEmployee) => employee.department || NO_DEPARTMENT;
const departmentLabel = (key: string) => key === NO_DEPARTMENT ? t("Без отдела") : key;

async function load() {
  if (!props.code) return;
  loading.value = true;
  error.value = null;
  try {
    const res = await companiesApi.getEmployees(props.code);
    employees.value = res.employees;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось загрузить сотрудников');
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

// ── KPI (стиль governance) ───────────────────────────────────────
const activeCount = computed(() => employees.value.filter((e) => e.is_active).length);
const onlineCount = computed(() => employees.value.filter((e) => isOnline(e)).length);
const deptList = computed(() => {
  const map = new Map<string, number>();
  for (const e of employees.value) {
    const key = departmentKey(e);
    map.set(key, (map.get(key) || 0) + 1);
  }
  return Array.from(map.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => (a.name === NO_DEPARTMENT ? 1 : b.name === NO_DEPARTMENT ? -1 : b.count - a.count));
});

const kpis = computed(() => [
  { label: i18nKey("Сотрудников"), value: String(employees.value.length), unit: "", color: "#7F77DD" },
  { label: i18nKey("Активных"), value: String(activeCount.value), unit: employees.value.length ? Math.round(activeCount.value / employees.value.length * 100) + "%" : "", color: "#1D9E75" },
  { label: i18nKey("В сети сейчас"), value: String(onlineCount.value), unit: "", color: "#0E7490", live: onlineCount.value > 0 },
  { label: deptList.value.length === 1 ? i18nKey("Отдел") : i18nKey("Отделов"), value: String(deptList.value.length), unit: "", color: "#A855F7" },
]);

// ── Фильтрация ───────────────────────────────────────────────────
function toggleDept(name: string) {
  deptFilter.value = deptFilter.value === name ? null : name;
}

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  let list = employees.value;
  if (deptFilter.value) list = list.filter((e) => departmentKey(e) === deptFilter.value);
  if (q) {
    list = list.filter((e) =>
      (e.full_name || "").toLowerCase().includes(q) ||
      (e.email || "").toLowerCase().includes(q) ||
      (e.department || "").toLowerCase().includes(q) ||
      (e.job_title || "").toLowerCase().includes(q) ||
      (e.role || "").toLowerCase().includes(q),
    );
  }
  // Владелец → выше, затем по отделу, затем по имени.
  return [...list].sort((a, b) => {
    if (a.is_owner !== b.is_owner) return a.is_owner ? -1 : 1;
    const da = departmentKey(a), db = departmentKey(b);
    if (da === NO_DEPARTMENT) return 1;
    if (db === NO_DEPARTMENT) return -1;
    if (da !== db) return da.localeCompare(db, getCurrentIntlLocale());
    return (a.full_name || "").localeCompare(b.full_name || "", getCurrentIntlLocale());
  });
});
</script>

<template>
  <div class="cet">
    <!-- Header (тулбар как в governance) -->
    <div class="cet-hd">
      <div class="cet-hd-l">
        <h2 class="cet-title">{{ t('Сотрудники') }}</h2>
        <span v-if="!loading" class="cet-count">{{ employees.length }}</span>
      </div>
      <div v-if="!loading && employees.length" class="cet-search-wrap">
        <svg class="cet-search-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
        <input v-model="search" class="cet-search" :placeholder="t('Поиск по имени, отделу, должности…')" />
      </div>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="cet-kpis kpi-rail" style="margin-top:16px">
      <div v-for="i in 4" :key="i" class="cet-kpi cet-skel-kpi"></div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="cet-empty cet-err">{{ error }}</div>

    <!-- Empty (honest: нет данных ≠ 0) -->
    <div v-else-if="!employees.length" class="cet-empty">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
      <div>{{ t('К этой компании пока не привязан ни один пользователь') }}</div>
      <p>{{ t('Привязка задаётся в профиле сотрудника (поле «Компания») или администратором.') }}</p>
    </div>

    <template v-else>
      <!-- KPI grid — стиль governance -->
      <div class="cet-kpis kpi-rail">
        <div
          v-for="(k, ki) in kpis"
          :key="k.label"
          class="cet-kpi"
          :style="`--accent:${k.color};--d:${ki}`"
        >
          <div class="cet-kpi-l">{{ t(k.label) }}</div>
          <div class="cet-kpi-v">
            {{ k.value }}
            <span v-if="(k as any).live" class="cet-kpi-live"></span>
          </div>
          <div v-if="k.unit" class="cet-kpi-u">{{ k.unit }}</div>
        </div>
      </div>

      <!-- Отделы — чипы (как «Комитеты совета»), клик = фильтр -->
      <div v-if="deptList.length > 1" class="cet-sec">
        <div class="cet-sec-l">
          {{ t('Отделы') }}
          <button v-if="deptFilter" class="cet-sec-clear" @click="deptFilter = null">{{ t('сбросить фильтр') }}</button>
        </div>
        <div class="cet-chips">
          <button
            v-for="d in deptList"
            :key="d.name"
            class="cet-chip"
            :class="{ 'cet-chip--on': deptFilter === d.name }"
            @click="toggleDept(d.name)"
          >
            {{ departmentLabel(d.name) }}<span class="cet-chip-cnt">{{ d.count }}</span>
          </button>
        </div>
      </div>

      <!-- Состав — карточки людей в стиле членов совета -->
      <div class="cet-sec">
        <div class="cet-sec-l">
          {{ t('Состав (') }}{{ filtered.length }} {{ filtered.length === 1 ? t('чел.') : t('чел.') }})
        </div>

        <div v-if="filtered.length === 0" class="cet-empty cet-empty--sm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
          <div>{{ t('Никто не найден') }}</div>
        </div>

        <div v-else class="cet-members">
          <UserCardAnchor
            v-for="(e, i) in filtered"
            :key="e.id"
            tag="div"
            :user-id="e.id"
            :preview="e"
            class="cet-member"
            :class="{ 'cet-member--off': !e.is_active }"
            :style="{ '--d': i }"
          >
            <div class="cet-mav" :style="{ background: e.accent }">
              <img v-if="e.avatar_url" :src="e.avatar_url" alt="" />
              <span v-else>{{ e.initials }}</span>
              <span v-if="isOnline(e)" class="cet-online" :title="t('В сети')"></span>
            </div>
            <div class="cet-minfo">
              <div class="cet-mname">
                {{ e.full_name }}
                <span v-if="e.is_owner" class="cet-owner" :title="t('Владелец')">★</span>
              </div>
              <div v-if="e.job_title || e.role" class="cet-mpos">{{ e.job_title || e.role }}</div>
              <div class="cet-mmeta">
                <span v-if="e.department" class="cet-mpill">{{ e.department }}</span>
                <span v-if="isOnline(e)" class="cet-mbadge cet-mbadge--on">{{ t('В сети') }}</span>
                <span v-else-if="!e.is_active" class="cet-mbadge">{{ t('Неактивен') }}</span>
              </div>
              <div class="cet-mdates">{{ e.last_active ? formatRelativeTime(e.last_active) : t('нет активности') }}</div>
            </div>
            <svg class="cet-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
          </UserCardAnchor>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cet { padding: 4px 2px 32px; display: flex; flex-direction: column; gap: 14px; }

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

/* ── KPI cards (1:1 с .cw-gov-kpi-card) ── */
/* Полоса склеивается в единую ленту утилитой .kpi-rail (gap задаёт она). */
.cet-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
.cet-kpi {
  background: #fff; border: .5px solid var(--uza-border, #ECEAF4);
  border-top: 3px solid var(--accent, #7F77DD); border-radius: 10px;
  padding: 12px 14px; display: flex; flex-direction: column; gap: 4px;
  box-shadow: 0 2px 8px rgba(15,23,60,.04);
  animation: cetKpiIn .4s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both;
  animation-delay: calc(var(--d,0) * 45ms);
  transition: transform .16s var(--ease-standard, cubic-bezier(.4,0,.2,1)), box-shadow .16s;
}
.cet-kpi:hover { transform: translateY(-2px); box-shadow: 0 10px 24px -10px rgba(40,32,80,.22); }
@keyframes cetKpiIn { from { opacity: 0; transform: translateY(9px); } to { opacity: 1; transform: none; } }
.cet-kpi-l { font-size: 9.5px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: var(--uza-gray, #94A3B8); }
.cet-kpi-v {
  font-size: 22px; font-weight: 400; letter-spacing: -.025em; color: var(--uza-navy, #1A1730);
  font-variant-numeric: tabular-nums; display: flex; align-items: center; gap: 8px;
}
.cet-kpi-u { font-size: 10.5px; color: var(--uza-gray, #94A3B8); }
.cet-kpi-live {
  width: 8px; height: 8px; border-radius: 50%; background: #1D9E75;
  animation: cetPulseDot 1.8s ease-out infinite;
}
@keyframes cetPulseDot {
  0% { box-shadow: 0 0 0 0 rgba(29,158,117,.5); }
  70% { box-shadow: 0 0 0 7px rgba(29,158,117,0); }
  100% { box-shadow: 0 0 0 0 rgba(29,158,117,0); }
}

/* ── Section (1:1 с .cw-gov-section) ── */
.cet-sec {
  background: #fff; border: .5px solid var(--uza-border, #ECEAF4);
  border-radius: 12px; padding: 14px 16px;
}
.cet-sec-l {
  font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
  color: var(--uza-gray, #6B6880); margin-bottom: 12px;
  display: flex; align-items: center; gap: 10px;
}
.cet-sec-clear {
  font-size: 10.5px; font-weight: 500; text-transform: none; letter-spacing: 0;
  color: var(--p-deep, #534AB7); background: rgba(124,111,247,.1);
  border: none; border-radius: 999px; padding: 2px 9px; cursor: pointer; font-family: inherit;
}
.cet-sec-clear:hover { background: rgba(124,111,247,.18); }

/* ── Chips (1:1 с .cw-gov-committee) ── */
.cet-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.cet-chip {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 6px 12px; border-radius: 7px; font-size: 12px; font-weight: 500;
  border: .5px solid var(--uza-border, #ECEAF4); background: #fff; color: var(--uza-navy, #1A1730);
  cursor: pointer; font-family: inherit; transition: background .14s, border-color .14s, transform .12s;
}
.cet-chip:hover { background: var(--bg2, #F6F5FC); transform: translateY(-1px); }
.cet-chip--on { background: rgba(124,111,247,.10); color: var(--p-deep, #534AB7); border-color: rgba(124,111,247,.35); }
.cet-chip-cnt { font-size: 11px; color: var(--uza-gray, #94A3B8); background: var(--bg2, #F1F0F7); border-radius: 999px; padding: 0 7px; }
.cet-chip--on .cet-chip-cnt { background: rgba(124,111,247,.16); color: var(--p-deep, #534AB7); }

/* ── Member cards (1:1 с .cw-gov-member) ── */
.cet-members { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
.cet-member {
  display: flex; gap: 12px; align-items: flex-start; padding: 12px;
  background: var(--uza-bg2, #F8FAFC); border-radius: 10px; border: 1px solid transparent;
  cursor: pointer;
  transition: background .18s, transform .16s var(--ease-standard, cubic-bezier(.4,0,.2,1)), box-shadow .16s, border-color .16s;
  animation: cetMemberIn .4s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both;
  animation-delay: calc(var(--d,0) * 30ms);
}
.cet-member:hover {
  background: var(--uza-bg3, #F1F0F7);
  transform: translateY(-2px);
  box-shadow: 0 10px 24px -12px rgba(40,32,80,.28);
  border-color: rgba(124,111,247,.35);
}
.cet-member:hover .cet-chev { opacity: 1; transform: translateX(0); }
.cet-member--off { opacity: .55; }
@keyframes cetMemberIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

.cet-mav {
  position: relative; width: 40px; height: 40px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 13px; font-weight: 600; letter-spacing: .02em;
  box-shadow: 0 2px 6px rgba(15,23,60,.12);
}
.cet-mav img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
.cet-online {
  position: absolute; right: -1px; bottom: -1px; width: 11px; height: 11px;
  border-radius: 50%; background: #1D9E75; box-shadow: 0 0 0 2px var(--uza-bg2, #fff);
}
.cet-minfo { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.cet-mname {
  font-size: 13px; font-weight: 500; color: var(--uza-navy, #1A1730);
  display: flex; align-items: center; gap: 5px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cet-owner { color: #EF9F27; font-size: 12px; }
.cet-mpos { font-size: 11px; color: var(--uza-gray, #6B6880); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cet-mmeta { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.cet-mpill {
  font-size: 10.5px; font-weight: 500; padding: 1px 8px; border-radius: 999px;
  background: rgba(124,111,247,.12); color: var(--p-deep, #534AB7);
}
.cet-mbadge {
  font-size: 10.5px; font-weight: 500; padding: 1px 8px; border-radius: 999px;
  background: var(--uza-bg3, #F1F0F7); color: var(--uza-gray, #6B6880);
}
.cet-mbadge--on { background: rgba(29,158,117,.12); color: #158063; }
.cet-mdates { font-size: 10.5px; color: var(--t3, #A6A3B8); margin-top: 4px; }
.cet-chev {
  width: 15px; height: 15px; flex-shrink: 0; align-self: center; color: var(--uza-bg4, #C9C6DA);
  opacity: 0; transform: translateX(-4px); transition: opacity .16s, transform .16s;
}

.cet-empty {
  margin: 20px auto; text-align: center; color: var(--t3, #8B889C);
  display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 30px;
}
.cet-empty--sm { margin: 8px auto; padding: 22px; }
.cet-empty svg { width: 40px; height: 40px; color: #C9C6DA; }
.cet-empty--sm svg { width: 28px; height: 28px; }
.cet-empty div { font-size: 14px; color: var(--t2, #6B6880); font-weight: 500; }
.cet-empty p { font-size: 12px; max-width: 360px; margin: 0; line-height: 1.5; }
.cet-err { color: #C5352F; }

/* Skeleton */
.cet-skel-kpi { height: 68px; background: var(--bg2, #EEEDF4); border: none; animation: cetPulse 1.3s ease-in-out infinite; }
@keyframes cetPulse { 0%,100% { opacity: 1; } 50% { opacity: .5; } }

@media (prefers-reduced-motion: reduce) {
  .cet-kpi, .cet-member { animation: none; }
}
</style>
