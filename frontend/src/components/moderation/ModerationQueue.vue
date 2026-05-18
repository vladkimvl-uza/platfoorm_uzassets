<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  moderationApi, formatRelativeTime,
  STATUS_LABELS, ACTION_LABELS,
  type SubmissionListItem, type SubmissionStatus,
} from "@/api/moderation";
import ModerationReviewModal from "./ModerationReviewModal.vue";
import { useUserDirectory } from "@/composables/useUserDirectory";

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
const filterAssignedToMe = ref(false);
const filterModule = ref<string>("");

const openId = ref<string | null>(props.openSubmissionId);

async function load() {
  loading.value = true;
  loadError.value = null;
  try {
    const r = await moderationApi.queue({
      status: filterStatuses.value.length ? filterStatuses.value : undefined,
      assigned_to: filterAssignedToMe.value ? "me" : undefined,
      module: filterModule.value || undefined,
      page: page.value, per_page: perPage,
    });
    items.value = r.items;
    counts.value = r.counts_by_status;
    total.value = r.total;
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить очередь";
    console.warn("queue load failed", e);
  }
  finally { loading.value = false; }
}

onMounted(async () => {
  await Promise.all([load(), dir.ensureLoaded()]);
});
watch([filterStatuses, filterAssignedToMe, filterModule, page], load, { deep: true });
watch(() => props.openSubmissionId, (v) => { if (v) openId.value = v; });

function toggleStatus(s: SubmissionStatus) {
  if (filterStatuses.value.includes(s)) filterStatuses.value = filterStatuses.value.filter((x) => x !== s);
  else filterStatuses.value = [...filterStatuses.value, s];
}
function clearFilters() {
  filterStatuses.value = []; filterAssignedToMe.value = false; filterModule.value = "";
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
          {{ STATUS_LABELS[s].label }}
          <span class="mq-chip-cnt">{{ counts[s] ?? 0 }}</span>
        </button>
      </div>
      <span class="mq-sep"></span>
      <label class="mq-check"><input type="checkbox" v-model="filterAssignedToMe" /> только мне</label>
      <button v-if="filterStatuses.length || filterAssignedToMe || filterModule" class="mq-clear" @click="clearFilters">сбросить</button>
    </div>

    <div v-if="loadError" class="mq-error">{{ loadError }}</div>
    <div v-else-if="loading && items.length === 0" class="mq-empty">Загрузка…</div>
    <div v-else-if="!loading && items.length === 0" class="mq-empty">
      <i class="ti ti-inbox" style="font-size: 24px; color: #888780;" aria-hidden="true"></i>
      <div>Очередь пуста</div>
    </div>

    <div v-else class="mq-list">
      <div v-for="s in items" :key="s.id" class="mq-row" :class="`status-${s.status}`" @click="open(s.id)">
        <span class="mq-status-pill" :style="{ background: STATUS_LABELS[s.status].bg, color: STATUS_LABELS[s.status].color }">
          {{ STATUS_LABELS[s.status].label }}
        </span>
        <div class="mq-row-body">
          <div class="mq-row-top">
            <span v-if="s.proposer_is_external" class="mq-ext">EXTERNAL</span>
            <span class="mq-proposer">{{ dir.shortName(s.proposer_user_id) }}</span>
            <span class="mq-module">· {{ s.target_module }}</span>
            <span class="mq-action">· {{ ACTION_LABELS[s.action as keyof typeof ACTION_LABELS] || s.action }}</span>
            <span class="mq-time">· {{ formatRelativeTime(s.created_at) }}</span>
          </div>
          <div class="mq-title">{{ s.target_entity_label || s.target_field || "(без названия)" }}</div>
          <div v-if="s.diff_summary" class="mq-diff">{{ s.diff_summary }}</div>
        </div>
        <i class="ti ti-chevron-right mq-row-arrow" aria-hidden="true"></i>
      </div>
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
.mq-clear { background: transparent; border: 0; color: #534AB7; font-size: 10.5px; cursor: pointer; font-family: inherit; text-decoration: underline; }

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
.mq-row.status-pending      { border-left: 3px solid #EF9F27; padding-left: 9px; }
.mq-row.status-under_review { border-left: 3px solid #378ADD; padding-left: 9px; }
.mq-row.status-approved     { border-left: 3px solid #1D9E75; padding-left: 9px; }
.mq-row.status-rejected     { border-left: 3px solid #E24B4A; padding-left: 9px; }
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
  background: rgba(226,75,74,.08); color: #A32D2D;
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
</style>
