<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { boardsApi } from "@/api/tasks";
import type { BoardBrief } from "@/api/tasks";

const router = useRouter();

const items     = ref<BoardBrief[]>([]);
const total     = ref(0);
const loading   = ref(true);
const error     = ref<string | null>(null);

const search          = ref("");
const sectorFilter    = ref("");
const archivedFilter  = ref(false);

let searchTimer: number | null = null;

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await boardsApi.list({
      search: search.value.trim() || undefined,
      sector: sectorFilter.value || undefined,
      archived: archivedFilter.value,
    });
    items.value = resp.items;
    total.value = resp.total;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить доски";
  } finally {
    loading.value = false;
  }
}

onMounted(load);

watch(search, () => {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(load, 250);
});
watch([sectorFilter, archivedFilter], load);

function openBoard(id: string) {
  void router.push({ name: "board-kanban", params: { id } });
}

const STATUS_META: Record<string, { label: string; color: string }> = {
  init:   { label: "Иниц.",       color: "#94A3B8" },
  new:    { label: "Не начато",   color: "#7F77DD" },
  active: { label: "В процессе",  color: "#378ADD" },
  review: { label: "На согл.",    color: "#EF9F27" },
  done:   { label: "Заверш.",     color: "#1D9E75" },
};
</script>

<template>
  <div class="uza-page">
    <div style="margin-bottom: 18px;">
      <div class="uza-section-label">Проекты</div>
      <h1 style="font-size: 18px; font-weight: 500; color: var(--t1);
                 letter-spacing: -.02em; margin-top: 2px;">Канбан-доски</h1>
      <div style="font-size: 11px; color: var(--t3); margin-top: 3px;">
        {{ total }} {{ total === 1 ? "доска" : "досок" }}
      </div>
    </div>

    <!-- Filter bar -->
    <div class="uza-section" style="padding: 14px 18px; margin-bottom: 14px;
                                     animation: uzaCardIn .55s cubic-bezier(0.34, 1.2, 0.64, 1) 80ms both;">
      <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 220px;">
          <input v-model="search" type="text" placeholder="Поиск по названию доски…" class="uza-input" />
        </div>
        <select v-model="sectorFilter" class="uza-input" style="width: auto; min-width: 200px;">
          <option value="">Все секторы</option>
          <option value="mining">Горнодобывающая</option>
          <option value="oil_gas">Нефть и газ</option>
          <option value="energy">Энергетика</option>
          <option value="transport">Транспорт</option>
          <option value="chemistry">Химия</option>
          <option value="metallurgy">Металлургия</option>
          <option value="telecom">Телекоммуникации</option>
          <option value="other">Прочее</option>
        </select>
        <label style="display: flex; align-items: center; gap: 6px; font-size: 12px;
                      color: var(--t2); cursor: pointer; user-select: none;">
          <input v-model="archivedFilter" type="checkbox" />
          Архивные
        </label>
      </div>
    </div>

    <div v-if="loading" class="uza-card p-12 text-center text-slate-400 text-sm">Загрузка…</div>
    <div v-else-if="error" class="uza-card p-6 text-uza-red text-sm">{{ error }}</div>

    <div v-else-if="items.length === 0" class="uza-card p-12 text-center">
      <div class="text-slate-400 text-sm mb-2">Досок ещё нет.</div>
      <div class="text-xs text-slate-400">
        Доски появятся после миграции <code class="bg-slate-100 px-1 rounded">/pf/boards</code> из Firebase.
      </div>
    </div>

    <!-- Boards grid -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="(b, idx) in items"
        :key="b.id"
        @click="openBoard(b.id)"
        class="uza-card"
        style="cursor: pointer; padding: 16px 18px;
               transition: transform .15s, box-shadow .15s, border-color .15s;
               animation: uzaCardIn .55s cubic-bezier(0.34, 1.2, 0.64, 1) both;"
        :style="{
          animationDelay: `${160 + idx * 40}ms`,
          'border-top': b.color_hex ? `3px solid ${b.color_hex}` : '',
        }"
        onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 12px 32px rgba(15,23,60,.10)'"
        onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow=''"
      >
        <!-- Header -->
        <div class="flex items-start justify-between gap-2 mb-3">
          <div class="flex-1 min-w-0">
            <div class="font-medium text-slate-900 truncate">{{ b.name }}</div>
            <div v-if="b.company_name" class="text-xs text-slate-500 mt-0.5 truncate">
              {{ b.company_name }}
            </div>
          </div>
          <div v-if="b.tasks_total" class="flex-shrink-0 text-[20px] font-normal tabular-nums tracking-uza-tight text-slate-700">
            <span v-count-up="{ value: b.tasks_total, key: `board-total-${b.id}` }">0</span>
          </div>
        </div>

        <div v-if="b.description" class="text-xs text-slate-500 mb-3 line-clamp-2">
          {{ b.description }}
        </div>

        <!-- Status mini-bar -->
        <div v-if="b.tasks_total > 0" class="space-y-1.5">
          <div class="flex items-center gap-1 h-1.5 rounded-uza-pill overflow-hidden bg-slate-100">
            <div
              v-for="(cnt, st) in b.tasks_by_status"
              :key="st"
              :style="{
                width: `${(cnt / b.tasks_total) * 100}%`,
                background: STATUS_META[st]?.color || '#94A3B8',
              }"
              class="h-full"
            ></div>
          </div>
          <div class="flex items-center gap-3 text-[10px] text-slate-500 flex-wrap">
            <span v-for="(cnt, st) in b.tasks_by_status" :key="st" class="flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full" :style="{background: STATUS_META[st]?.color || '#94A3B8'}"></span>
              <span>{{ STATUS_META[st]?.label || st }}: <span class="tabular-nums">{{ cnt }}</span></span>
            </span>
          </div>
        </div>

        <div v-else class="text-[10px] text-slate-400 uppercase tracking-uza-label2">
          Нет задач
        </div>

        <!-- Footer: sector tag -->
        <div v-if="b.sector_code" class="mt-3 pt-3 border-t border-slate-100">
          <span class="text-[10px] uppercase tracking-uza-label2 text-slate-500">
            {{ b.sector_code }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
