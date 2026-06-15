<script setup lang="ts">
/**
 * CompanyEmployeesTab — премиум-раздел «Сотрудники» в карточке компании.
 *
 * Показывает пользователей платформы, привязанных к компании через
 * organization_id: аватар (accent), имя, роль, отдел/должность, последняя
 * активность, онлайн-точка. Группировка по отделам, поиск, stagger-анимации.
 * Наведение/клик по карточке → глобальная карточка пользователя (UserCardAnchor).
 */
import { computed, ref, watch } from "vue";
import { companiesApi, type CompanyEmployee } from "@/api/companies";
import { formatRelativeTime } from "@/api/audit";
import UserAffiliationBadge from "@/components/rbac-v3/UserAffiliationBadge.vue";
import UserCardAnchor from "@/components/user/UserCardAnchor.vue";

const props = defineProps<{ code: string }>();

const loading = ref(true);
const error = ref<string | null>(null);
const employees = ref<CompanyEmployee[]>([]);
const search = ref("");

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
watch(() => props.code, load, { immediate: true });

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return employees.value;
  return employees.value.filter((e) =>
    (e.full_name || "").toLowerCase().includes(q) ||
    (e.email || "").toLowerCase().includes(q) ||
    (e.department || "").toLowerCase().includes(q) ||
    (e.job_title || "").toLowerCase().includes(q) ||
    (e.role || "").toLowerCase().includes(q),
  );
});

/** Группировка по отделам (без отдела → «Без отдела»). */
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

const activeCount = computed(() => employees.value.filter((e) => e.is_active).length);

function isOnline(e: CompanyEmployee): boolean {
  if (!e.last_active) return false;
  return Date.now() - new Date(e.last_active).getTime() < 5 * 60 * 1000;
}
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

    <div v-if="!loading && employees.length" class="cet-sub">
      {{ activeCount }} активных · {{ groups.length }} {{ groups.length === 1 ? 'отдел' : 'отделов' }}
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="cet-grid">
      <div v-for="i in 6" :key="i" class="cet-card cet-skel">
        <div class="cet-skel-av"></div>
        <div class="cet-skel-lines"><span></span><span></span></div>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="cet-empty cet-err">{{ error }}</div>

    <!-- Empty -->
    <div v-else-if="!employees.length" class="cet-empty">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
      <div>К этой компании пока не привязан ни один пользователь</div>
      <p>Привязка задаётся в профиле сотрудника (поле «Компания») или администратором.</p>
    </div>

    <!-- Groups -->
    <div v-else class="cet-groups">
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
            :style="{ animationDelay: (gi * 60 + i * 35) + 'ms' }"
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
          </UserCardAnchor>
        </div>
      </div>
    </div>
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
.cet-sub { font-size: 12px; color: var(--t3, #8B889C); margin-top: 4px; }

.cet-search-wrap { position: relative; display: flex; align-items: center; }
.cet-search-ic { position: absolute; left: 11px; width: 15px; height: 15px; color: var(--t3, #94A3B8); pointer-events: none; }
.cet-search {
  width: 280px; max-width: 100%; padding: 8px 12px 8px 34px;
  border: 1.5px solid var(--line, #E8E6F0); border-radius: 10px;
  font-size: 13px; outline: none; font-family: inherit; background: var(--bg2, #F8FAFC);
  transition: border-color .14s, box-shadow .14s;
}
.cet-search:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124,111,247,.14); }

.cet-groups { margin-top: 18px; display: flex; flex-direction: column; gap: 22px; }
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
  transition: transform .16s var(--ease-standard), box-shadow .16s, border-color .16s;
  animation: cetIn .4s var(--ease-standard) both;
}
.cet-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 26px -10px rgba(40,32,80,.28);
  border-color: rgba(124,111,247,.4);
}
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
.cet-badge { margin-top: 5px; }
.cet-last { font-size: 10.5px; color: var(--t3, #A6A3B8); margin-top: 5px; }

.cet-empty {
  margin-top: 40px; text-align: center; color: var(--t3, #8B889C);
  display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 30px;
}
.cet-empty svg { width: 40px; height: 40px; color: #C9C6DA; }
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
</style>
