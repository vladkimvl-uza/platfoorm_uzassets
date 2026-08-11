<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import BIcon from "@/components/broadcasts/BIcon.vue";
import {
  moderationApi, formatRelativeTime,
  STATUS_LABELS, ACTION_LABELS,
  type SubmissionListItem, type SubmissionStatus,
} from "@/api/moderation";
import ModerationReviewModal from "./ModerationReviewModal.vue";
import { useUserDirectory } from "@/composables/useUserDirectory";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


/** Карта ПОДПИСЕЙ модулей (для строк очереди и исторических заявок старых
 *  модулей). Набор фактически модерируемых модулей теперь берётся с бэкенда
 *  (policy.moderatable_all = только tasks/projects) — см. moderatableCodes. */
const MODULES: { code: string; label: string }[] = [
  { code: "tasks", label: "Задачи" },
  { code: "projects", label: "Проекты" },
  { code: "comments", label: "Комментарии" },
  { code: "kpi", label: "KPI" },
  { code: "financials", label: "Финансы" },
  { code: "business_plan", label: "Бизнес-план" },
  { code: "esg", label: "ESG" },
  { code: "governance", label: "Корп. управление" },
  { code: "ratings", label: "Рейтинги" },
  { code: "procurement", label: "Закупки" },
  { code: "production", label: "Производство" },
  { code: "credit", label: "Кредитный портфель" },
  { code: "investment", label: "Инвест-проекты" },
  { code: "unit_cost", label: "Себестоимость" },
  { code: "companies", label: "Компании" },
];
function moduleRu(code: string): string {
  const m = MODULES.find((x) => x.code === code);
  return m ? t(m.label) : code;
}

const props = defineProps<{ openSubmissionId: string | null }>();
const emit = defineEmits<{ change: [] }>();

const dir = useUserDirectory();

const items = ref<SubmissionListItem[]>([]);
const counts = ref<Record<string, number>>({});
const total = ref(0);
const page = ref(1);
const perPage = 30;
const loading = ref(false);
const loadError = ref<string | null>(null);

const filterStatuses = ref<SubmissionStatus[]>(["pending", "under_review"]);
// «Только мне» убрано: с 03.08.2026 очередь общая — согласующий не назначается
// правилом, разбирать может любой держатель moderation.review. Фильтр всегда
// давал бы пусто.
const filterModule = ref<string>("");
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / perPage)));

const openId = ref<string | null>(props.openSubmissionId);

// Фактически модерируемые модули — с бэкенда (LOCKED_MODERATABLE = tasks/projects),
// а не хардкод: иначе фильтр предлагал бы 13 модулей, где очередь всегда пуста.
const moderatableCodes = ref<string[]>(["tasks", "projects"]);

async function load() {
  loading.value = true;
  loadError.value = null;
  try {
    const r = await moderationApi.queue({
      status: filterStatuses.value.length ? filterStatuses.value : undefined,
      module: filterModule.value || undefined,
      page: page.value, per_page: perPage,
    });
    items.value = r.items;
    counts.value = r.counts_by_status;
    total.value = r.total;
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || e?.message || t('Не удалось загрузить очередь');
    console.warn("queue load failed", e);
  }
  finally { loading.value = false; }
}

onMounted(async () => {
  await Promise.all([load(), dir.ensureLoaded()]);
  // Набор модерируемых модулей для фильтра — из политики (tasks/projects).
  try {
    const p = await moderationApi.getPolicy();
    if (Array.isArray(p?.moderatable_all) && p.moderatable_all.length) {
      moderatableCodes.value = p.moderatable_all;
    }
  } catch { /* оставляем дефолт tasks/projects */ }
});

/** Ручное обновление очереди + метрик (живого WS/поллинга у очереди нет). */
async function refresh() {
  await load();
  emit("change");
}
watch([filterStatuses, filterModule], () => { page.value = 1; void load(); }, { deep: true });
watch(page, load);
watch(() => props.openSubmissionId, (v) => { if (v) openId.value = v; });

function toggleStatus(s: SubmissionStatus) {
  if (filterStatuses.value.includes(s)) filterStatuses.value = filterStatuses.value.filter((x) => x !== s);
  else filterStatuses.value = [...filterStatuses.value, s];
}
function clearFilters() {
  filterStatuses.value = []; filterModule.value = ""; page.value = 1;
}

function open(id: string) { openId.value = id; }
function closeModal() { openId.value = null; }
async function onResolved() {
  closeModal();
  await load();
  emit("change");
}
</script>

<template>
  <div class="mq-wrap">
    <div class="mq-filters">
      <div class="mq-status-chips">
        <button v-for="s in (['pending','under_review','approved','rejected','withdrawn','expired'] as SubmissionStatus[])" :key="s"
                class="mq-chip"
                :class="{ active: filterStatuses.includes(s) }"
                :style="filterStatuses.includes(s) ? { background: STATUS_LABELS[s].bg, color: STATUS_LABELS[s].color } : {}"
                @click="toggleStatus(s)">
          {{ t(STATUS_LABELS[s].label) }}
          <span class="mq-chip-cnt">{{ counts[s] ?? 0 }}</span>
        </button>
      </div>
      <span class="mq-sep"></span>
      <select v-model="filterModule" class="mq-select" :title="t('Фильтр по модулю')">
        <option value="">{{ t('все модули') }}</option>
        <option v-for="code in moderatableCodes" :key="code" :value="code">{{ moduleRu(code) }}</option>
      </select>
      <button v-if="filterStatuses.length || filterModule" class="mq-clear" @click="clearFilters">{{ t('сбросить') }}</button>
      <button class="mq-refresh" :disabled="loading" :title="t('Обновить очередь')" @click="refresh">
        <BIcon name="refresh" :size="14" />
      </button>
    </div>

    <div v-if="loadError" class="mq-error">{{ loadError }}</div>
    <div v-else-if="loading && items.length === 0" class="mq-empty">{{ t('Загрузка…') }}</div>
    <div v-else-if="!loading && items.length === 0" class="mq-empty">
      <BIcon name="inbox" :size="14" />
      <div v-if="filterStatuses.length || filterModule">
        {{ t('По выбранным фильтрам ничего нет') }}
        <button class="mq-clear mq-clear-inline" @click="clearFilters">{{ t('сбросить фильтры') }}</button>
      </div>
      <div v-else>{{ t('Очередь пуста — на согласовании ничего нет') }}</div>
    </div>

    <div v-else class="mq-list">
      <div v-for="s in items" :key="s.id" class="mq-row" :class="`status-${s.status}`"
           role="button" tabindex="0" @click="open(s.id)" @keydown.enter.prevent="open(s.id)" @keydown.space.prevent="open(s.id)">
        <span class="mq-status-pill" :style="{ background: STATUS_LABELS[s.status].bg, color: STATUS_LABELS[s.status].color }">
          {{ t(STATUS_LABELS[s.status].label) }}
        </span>
        <div class="mq-row-body">
          <div class="mq-row-top">
            <span v-if="s.proposer_is_external" class="mq-ext">EXTERNAL</span>
            <span class="mq-proposer">{{ dir.shortName(s.proposer_user_id) }}</span>
            <span class="mq-module">· {{ moduleRu(s.target_module) }}</span>
            <span class="mq-action">· {{ t(ACTION_LABELS[s.action as keyof typeof ACTION_LABELS] || s.action) }}</span>
            <span class="mq-time">· {{ formatRelativeTime(s.created_at) }}</span>
          </div>
          <div class="mq-title">{{ s.target_entity_label || s.target_field || t('(без названия)') }}</div>
          <div v-if="s.diff_summary" class="mq-diff">{{ s.diff_summary }}</div>
        </div>
        <BIcon name="chevron-right" :size="16" class="mq-row-arrow" />
      </div>
    </div>

    <!-- Пагинация: раньше её не было вовсе — за пределы первых 30 заявок
         модератор попасть не мог, хотя бэкенд отдаёт постранично. -->
    <div v-if="totalPages > 1" class="mq-pager">
      <button class="mq-pg" :disabled="page <= 1" @click="page--">← {{ t('Назад') }}</button>
      <span class="mq-pg-info">{{ t('Стр. {value0} из {value1}', { value0: page, value1: totalPages }) }} · {{ total }}</span>
      <button class="mq-pg" :disabled="page >= totalPages" @click="page++">{{ t('Вперёд') }} →</button>
    </div>

    <ModerationReviewModal
      v-if="openId"
      :submission-id="openId"
      @close="closeModal"
      @resolved="onResolved"
    />
  </div>
</template>

<style scoped>
.mq-wrap { display: flex; flex-direction: column; gap: 10px; }

.mq-filters {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 9px 12px;
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 10px;
}
.mq-status-chips { display: flex; gap: 5px; flex-wrap: wrap; }
.mq-chip {
  background: var(--color-background-secondary);
  border: 0.5px solid rgba(0,0,0,.06);
  color: var(--color-text-secondary);
  padding: 4px 9px;
  border-radius: 9px;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
}
.mq-chip-cnt {
  font-size: 9.5px;
  color: var(--color-text-tertiary);
  font-feature-settings: "tnum";
}
.mq-sep { width: 1px; height: 18px; background: rgba(0,0,0,.08); }
.mq-check { font-size: 11.5px; color: var(--color-text-secondary); display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
.mq-clear { background: transparent; border: 0; color: var(--p-deep); font-size: 10.5px; cursor: pointer; font-family: inherit; text-decoration: underline; }

.mq-empty {
  padding: 60px 20px;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 12.5px;
  display: flex; flex-direction: column; align-items: center; gap: 10px;
}

.mq-list { display: flex; flex-direction: column; gap: 5px; }

.mq-row {
  display: flex; align-items: flex-start; gap: 10px;
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 9px;
  padding: 10px 12px;
  cursor: pointer;
  transition: background .12s, border-color .12s;
}
.mq-row:hover {
  background: rgba(127,119,221,.03);
  border-color: rgba(127,119,221,.25);
}
.mq-row { position: relative; overflow: hidden; --mq-accent: transparent; }
.mq-row::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: var(--mq-accent);
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.mq-row.status-pending      { --mq-accent: var(--amber); }
.mq-row.status-under_review { --mq-accent: var(--blue); }
.mq-row.status-approved     { --mq-accent: var(--green); }
.mq-row.status-rejected     { --mq-accent: var(--sev-high); }
.mq-row.status-withdrawn,
.mq-row.status-expired       { opacity: .65; }

.mq-status-pill {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  flex-shrink: 0;
  margin-top: 2px;
}

.mq-row-body { flex: 1; min-width: 0; }
.mq-row-top { display: flex; gap: 5px; align-items: center; flex-wrap: wrap; }
.mq-ext {
  background: #D4537E; color: #fff;
  padding: 1px 5px; border-radius: 3px;
  font-size: 9px; font-weight: 600; letter-spacing: .04em;
}
.mq-module { font-size: 11px; color: var(--color-text-tertiary); font-family: monospace; }
.mq-proposer { font-size: 11px; color: var(--color-text-primary); font-weight: 500; }
.mq-error {
  padding: 10px 12px; border-radius: 7px;
  background: rgba(226,75,74,.08); color: var(--sev-critical);
  font-size: 11.5px;
}
.mq-action { font-size: 11px; color: var(--color-text-tertiary); }
.mq-time   { font-size: 10px; color: var(--color-text-tertiary); margin-left: auto; }

.mq-title {
  font-size: 12.5px;
  color: var(--color-text-primary);
  margin-top: 3px;
  font-weight: 500;
}
.mq-diff {
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-top: 2px;
  line-height: 1.4;
}

.mq-row-arrow {
  font-size: 14px;
  color: var(--color-text-tertiary);
  align-self: center;
}

.mq-select {
  font-family: inherit; font-size: 11.5px; color: var(--t2, #4B5468);
  background: var(--color-background-primary, #fff);
  border: 0.5px solid var(--color-border-tertiary, #E5E7EB);
  border-radius: 8px; padding: 5px 9px; cursor: pointer;
}
.mq-clear-inline { margin-left: 8px; }
.mq-refresh {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; margin-left: auto; padding: 0;
  background: var(--color-background-primary, #fff);
  border: 0.5px solid var(--color-border-tertiary, #E5E7EB);
  border-radius: 8px; color: var(--t2, #4B5468); cursor: pointer;
  transition: background .12s, color .12s;
}
.mq-refresh:hover:not(:disabled) { background: color-mix(in srgb, var(--p-deep, #534AB7) 8%, transparent); color: var(--p-deep, #534AB7); }
.mq-refresh:disabled { opacity: .5; cursor: default; }
.mq-row:focus-visible { outline: 2px solid var(--p-deep, #534AB7); outline-offset: -2px; }
.mq-pager {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  padding: 8px 0 2px;
}
.mq-pg {
  font-family: inherit; font-size: 11.5px; font-weight: 500;
  color: var(--t2, #4B5468); background: var(--color-background-primary, #fff);
  border: 0.5px solid var(--color-border-tertiary, #E5E7EB);
  border-radius: 8px; padding: 6px 12px; cursor: pointer;
  transition: border-color .14s, color .14s;
}
.mq-pg:hover:not(:disabled) { border-color: rgba(124,111,247,.4); color: var(--p-deep, #534AB7); }
.mq-pg:disabled { opacity: .45; cursor: default; }
.mq-pg-info { font-size: 11px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
</style>
