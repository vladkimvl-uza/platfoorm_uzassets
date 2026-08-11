<script setup lang="ts">
/**
 * «Мои заявки» — экран МОДЕРИРУЕМОГО пользователя.
 *
 * Зачем: до 03.08.2026 у автора правки не было ВООБЩЕ никакого экрана.
 * Его сохранение перехватывалось модерацией, он видел один тост
 * «Изменение отправлено на модерацию · #a1b2c3d4» — и всё: ни статуса,
 * ни причины отказа, ни возможности отозвать. Эндпоинт /moderation/
 * my-submissions существовал, но не вызывался ниоткуда, а весь интерфейс
 * модерации закрыт правом moderation.review, то есть правом МОДЕРАТОРА.
 *
 * Здесь автор видит: что он предложил, где, когда, на какой стадии,
 * что ответил модератор, и может отозвать заявку, пока она на рассмотрении.
 */
import { computed, onMounted, ref } from "vue";
import {
  moderationApi, STATUS_LABELS,
  type SubmissionListItem, type Submission, type Comment, type SubmissionStatus,
} from "@/api/moderation";
import { useFormatters } from "@/composables/useFormatters";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { useEntityEditor } from "@/composables/useEntityEditor";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import ModalShell from "@/components/ModalShell.vue";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();
const fmt = useFormatters();
const toast = useToast();
const { confirmDialog } = useConfirm();
const entityEditor = useEntityEditor();

const items = ref<SubmissionListItem[]>([]);
const counts = ref<Record<string, number>>({});
const loading = ref(true);
const error = ref<string | null>(null);
const filter = ref<SubmissionStatus | "all">("all");

// Детали одной заявки: что предложено + переписка с модератором.
const detail = ref<Submission | null>(null);
const detailComments = ref<Comment[]>([]);
const detailLoading = ref(false);
const replyText = ref("");
const acting = ref(false);

/** Русские названия модулей — в очереди модератора показывался сырой код. */
const MODULE_RU: Record<string, string> = {
  tasks: "Задачи", projects: "Проекты", comments: "Комментарии",
  kpi: "KPI", financials: "Финансы", business_plan: "Бизнес-план",
  esg: "ESG", governance: "Корп. управление", ratings: "Рейтинги",
  procurement: "Закупки", production: "Производство", companies: "Компании",
};
function moduleRu(code: string): string { return t(MODULE_RU[code] || code); }
function statusRu(code: string): string {
  const meta = (STATUS_LABELS as any)[code];
  return meta ? t(meta.label) : code;
}
function statusColor(code: string): string {
  const meta = (STATUS_LABELS as any)[code];
  return meta ? meta.color : "#94A3B8";
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const r = await moderationApi.mySubmissions({
      status: filter.value === "all" ? undefined : [filter.value],
      per_page: 100,
    });
    items.value = r.items;
    counts.value = r.counts_by_status || {};
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить заявки");
  } finally {
    loading.value = false;
  }
}
onMounted(load);

const pendingCount = computed(
  () => (counts.value.pending || 0) + (counts.value.under_review || 0),
);

async function openDetail(it: SubmissionListItem) {
  detailLoading.value = true;
  detail.value = null;
  detailComments.value = [];
  replyText.value = "";
  try {
    detail.value = await moderationApi.get(it.id);
    detailComments.value = await moderationApi.listComments(it.id).catch(() => []);
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t("Не удалось открыть заявку"));
  } finally {
    detailLoading.value = false;
  }
}
function closeDetail() { detail.value = null; }

async function withdraw() {
  const s = detail.value;
  if (!s) return;
  const ok = await confirmDialog({
    title: t("Отозвать заявку?"),
    message: t("Предложенное изменение не будет применено. Отправить заново можно в любой момент."),
    danger: true,
  });
  if (!ok) return;
  acting.value = true;
  try {
    detail.value = await moderationApi.withdraw(s.id);
    toast.success(t("Заявка отозвана"));
    await load();
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t("Не удалось отозвать заявку"));
  } finally {
    acting.value = false;
  }
}

async function sendReply() {
  const s = detail.value;
  const text = replyText.value.trim();
  if (!s || !text) return;
  acting.value = true;
  try {
    const c = await moderationApi.addComment(s.id, text);
    detailComments.value = [...detailComments.value, c];
    replyText.value = "";
    toast.success(t("Комментарий отправлен модератору"));
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t("Не удалось отправить комментарий"));
  } finally {
    acting.value = false;
  }
}

/** Переход к записи умеем только для задач/проектов (единственные модерируемые
 *  модули). У исторических заявок старых модулей записи здесь не открываем. */
function canOpenTarget(s: Submission | null): boolean {
  return !!(s && s.target_entity_id && (s.target_module === "tasks" || s.target_module === "projects"));
}

/** Открыть саму запись, которой касается заявка (задача/проект). */
function openTarget(s: Submission) {
  if (!canOpenTarget(s)) return;
  if (!entityEditor.openFromLink(`/${s.target_module}/${s.target_entity_id}`)) return;
  closeDetail();
}

/** Читаемая сводка предложенного значения — без сырого JSON. */
function proposedLines(s: Submission): { k: string; v: string }[] {
  const src = (s.proposed_value || {}) as Record<string, unknown>;
  const out: { k: string; v: string }[] = [];
  for (const [k, v] of Object.entries(src)) {
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "object") continue;      // вложенное тело не разворачиваем
    out.push({ k, v: String(v) });
    if (out.length >= 12) break;
  }
  return out;
}
</script>

<template>
  <div class="ms">
    <div class="ms-head">
      <div>
        <div class="ms-eyebrow">{{ t("Модерация") }}</div>
        <h1 class="ms-title">{{ t("Мои заявки") }}</h1>
        <div class="ms-sub">
          {{ t("Изменения, которые вы отправили на согласование. Здесь видно, на какой они стадии и что ответил модератор.") }}
        </div>
      </div>
      <div v-if="pendingCount" class="ms-pending">
        <span class="ms-pending-n">{{ pendingCount }}</span>
        <span class="ms-pending-l">{{ t("на рассмотрении") }}</span>
      </div>
    </div>

    <div class="ms-filters" role="tablist">
      <button
        v-for="f in (['all', 'pending', 'under_review', 'approved', 'rejected'] as const)"
        :key="f"
        class="ms-fbtn"
        :class="{ on: filter === f }"
        @click="filter = f; load()"
      >
        {{ f === 'all' ? t('Все') : statusRu(f) }}
        <span v-if="f !== 'all' && counts[f]" class="ms-fbtn-n">{{ counts[f] }}</span>
      </button>
    </div>

    <UzaStateBlock v-if="loading" state="loading" :text="t('Загрузка заявок…')" />
    <UzaStateBlock
      v-else-if="error"
      state="error"
      variant="block"
      :text="error"
      retry
      @retry="load"
    />
    <UzaStateBlock
      v-else-if="!items.length"
      state="empty"
      variant="block"
      :title="t('Заявок нет')"
      :text="t('Когда ваше изменение попадёт на согласование, оно появится здесь — со статусом и ответом модератора.')"
    />

    <div v-else class="ms-list">
      <button
        v-for="(it, i) in items"
        :key="it.id"
        class="ms-row"
        :style="{ '--d': Math.min(i, 14) * 30 + 'ms', '--sc': statusColor(it.status) }"
        @click="openDetail(it)"
      >
        <span class="ms-status">{{ statusRu(it.status) }}</span>
        <span class="ms-main">
          <span class="ms-label">{{ it.target_entity_label || t("(без названия)") }}</span>
          <span class="ms-meta">
            {{ moduleRu(it.target_module) }}
            <span v-if="it.diff_summary" class="ms-diff">· {{ it.diff_summary }}</span>
          </span>
        </span>
        <span class="ms-when">{{ fmt.fmtRelativeTime(it.created_at) }}</span>
        <svg class="ms-chev" width="13" height="13" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 18l6-6-6-6"/>
        </svg>
      </button>
    </div>

    <!-- ─── Детали заявки ─── -->
    <ModalShell :open="!!detail || detailLoading" size="md" :title="t('Заявка на согласование')" @close="closeDetail">
      <UzaStateBlock v-if="detailLoading" state="loading" :text="t('Загрузка…')" />
      <div v-else-if="detail" class="msd" :style="{ '--sc': statusColor(detail.status) }">
        <div class="msd-head">
          <span class="msd-status">{{ statusRu(detail.status) }}</span>
          <span class="msd-when">{{ fmt.fmtDateTime(detail.created_at) }}</span>
        </div>
        <div class="msd-entity">{{ detail.target_entity_label || t("(без названия)") }}</div>
        <div class="msd-module">{{ moduleRu(detail.target_module) }}</div>

        <!-- Что предложено -->
        <div v-if="detail.diff_summary" class="msd-diff">{{ detail.diff_summary }}</div>
        <div v-if="proposedLines(detail).length" class="msd-vals">
          <div class="msd-vals-l">{{ t("Предложенные значения") }}</div>
          <div v-for="(row, i) in proposedLines(detail)" :key="i" class="msd-val">
            <span class="msd-val-k">{{ row.k }}</span>
            <span class="msd-val-v">{{ row.v }}</span>
          </div>
        </div>

        <!-- Ответ модератора -->
        <div v-if="detail.resolution_note" class="msd-note">
          <div class="msd-note-l">{{ t("Комментарий модератора") }}</div>
          <div class="msd-note-v">{{ detail.resolution_note }}</div>
        </div>
        <div v-else-if="detail.status === 'rejected'" class="msd-note msd-note-empty">
          {{ t("Модератор отклонил заявку без пояснения — можно уточнить причину в комментарии ниже.") }}
        </div>

        <!-- Переписка -->
        <div class="msd-chat">
          <div class="msd-chat-l">{{ t("Обсуждение") }}</div>
          <div v-if="!detailComments.length" class="msd-chat-empty">{{ t("Сообщений пока нет") }}</div>
          <div v-for="c in detailComments" :key="c.id" class="msd-msg">
            <span class="msd-msg-t">{{ c.text }}</span>
            <span class="msd-msg-d">{{ fmt.fmtRelativeTime(c.created_at) }}</span>
          </div>
          <div v-if="detail.status === 'pending' || detail.status === 'under_review' || detail.status === 'rejected'" class="msd-reply">
            <input
              v-model="replyText"
              class="msd-input"
              :placeholder="t('Написать модератору…')"
              @keyup.enter="sendReply"
            />
            <button class="msd-btn" :disabled="acting || !replyText.trim()" @click="sendReply">
              {{ t("Отправить") }}
            </button>
          </div>
        </div>
      </div>

      <template #footer>
        <button
          v-if="canOpenTarget(detail)"
          class="msd-btn-ghost"
          @click="openTarget(detail)"
        >
          {{ t("Открыть запись") }}
        </button>
        <button
          v-if="detail && (detail.status === 'pending' || detail.status === 'under_review')"
          class="msd-btn-danger"
          :disabled="acting"
          @click="withdraw"
        >
          {{ t("Отозвать") }}
        </button>
        <button class="msd-btn" @click="closeDetail">{{ t("Закрыть") }}</button>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.ms { padding: 22px 26px 46px; font-family: var(--font, system-ui); }
.ms-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; flex-wrap: wrap; }
.ms-eyebrow {
  font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: var(--t3, #94A3B8);
}
.ms-title { font-size: 22px; font-weight: 600; color: var(--t1, #1E2A4A); margin: 4px 0 6px; letter-spacing: -.02em; }
.ms-sub { font-size: 12.5px; color: var(--t2, #4B5468); max-width: 62ch; line-height: 1.5; }
.ms-pending {
  display: flex; flex-direction: column; align-items: center;
  background: rgba(217,119,6,.08); border: 1px solid rgba(217,119,6,.20);
  border-radius: 13px; padding: 10px 18px;
}
.ms-pending-n { font-size: 22px; font-weight: 600; color: #B45309; font-variant-numeric: tabular-nums; }
.ms-pending-l { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: #B45309; }

.ms-filters { display: flex; gap: 5px; flex-wrap: wrap; margin: 18px 0 14px; }
.ms-fbtn {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: inherit; font-size: 12px; font-weight: 500;
  color: var(--t2, #4B5468); background: var(--bg2, #F8F9FC);
  border: 1px solid var(--border, #EEF0F5); border-radius: 999px;
  padding: 6px 13px; cursor: pointer; transition: all .15s;
}
.ms-fbtn:hover { border-color: rgba(124,111,247,.32); color: var(--p-deep, #534AB7); }
.ms-fbtn.on { background: rgba(124,111,247,.12); border-color: rgba(124,111,247,.30); color: var(--p-deep, #534AB7); font-weight: 600; }
.ms-fbtn-n { font-size: 10.5px; opacity: .75; font-variant-numeric: tabular-nums; }

.ms-list { display: flex; flex-direction: column; gap: 6px; }
.ms-row {
  display: grid; grid-template-columns: 118px minmax(0, 1fr) 96px 16px;
  align-items: center; gap: 12px; width: 100%;
  background: #fff; border: 1px solid var(--border, #EEF0F5); border-radius: 12px;
  padding: 11px 14px; cursor: pointer; text-align: left; font-family: inherit;
  position: relative; overflow: hidden;
  animation: msIn .38s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both;
  animation-delay: var(--d, 0ms);
  transition: transform .15s, box-shadow .15s, border-color .15s;
}
.ms-row::before {
  content: ""; position: absolute; left: 0; top: 8px; bottom: 8px; width: 3px;
  background: var(--sc); border-radius: 0 3px 3px 0;
}
.ms-row:hover { transform: translateX(2px); box-shadow: 0 6px 18px rgba(15,23,60,.08); border-color: rgba(124,111,247,.22); }
@keyframes msIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
.ms-status {
  font-size: 10.5px; font-weight: 700; letter-spacing: .03em; text-transform: uppercase;
  color: var(--sc); background: color-mix(in srgb, var(--sc) 13%, transparent);
  border-radius: 999px; padding: 4px 10px; text-align: center; white-space: nowrap;
}
.ms-main { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.ms-label { font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ms-meta { font-size: 11px; color: var(--t3, #94A3B8); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ms-diff { color: var(--t2, #4B5468); }
.ms-when { font-size: 11px; color: var(--t3, #94A3B8); text-align: right; white-space: nowrap; }
.ms-chev { color: var(--t4, #CBD5E1); }

/* ── Детали ── */
.msd-head { display: flex; align-items: center; gap: 9px; margin-bottom: 10px; }
.msd-status {
  font-size: 10px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
  color: var(--sc); background: color-mix(in srgb, var(--sc) 14%, transparent);
  border-radius: 999px; padding: 4px 11px;
}
.msd-when { font-size: 11px; color: var(--t3, #94A3B8); margin-left: auto; }
.msd-entity { font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); line-height: 1.4; }
.msd-module { font-size: 11.5px; color: var(--t3, #94A3B8); margin-bottom: 12px; }
.msd-diff {
  font-size: 12.5px; color: var(--t2, #4B5468); line-height: 1.55;
  border-left: 2.5px solid var(--sc); padding-left: 11px; margin-bottom: 14px;
}
.msd-vals { background: var(--bg2, #F8F9FC); border: 1px solid var(--border, #EEF0F5); border-radius: 12px; padding: 4px 13px; margin-bottom: 14px; }
.msd-vals-l { font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--t3, #94A3B8); padding: 9px 0 5px; }
.msd-val { display: flex; gap: 12px; padding: 7px 0; font-size: 12px; }
.msd-val + .msd-val { border-top: 1px solid var(--border, #EEF0F5); }
.msd-val-k { color: var(--t3, #94A3B8); min-width: 120px; }
.msd-val-v { color: var(--t1, #1E2A4A); margin-left: auto; text-align: right; word-break: break-word; }
.msd-note { background: rgba(29,158,117,.07); border: 1px solid rgba(29,158,117,.20); border-radius: 12px; padding: 11px 13px; margin-bottom: 14px; }
.msd-note-l { font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #0F6E56; margin-bottom: 4px; }
.msd-note-v { font-size: 12.5px; color: var(--t1, #1E2A4A); line-height: 1.55; }
.msd-note-empty { background: var(--bg2, #F8F9FC); border-color: var(--border, #EEF0F5); font-size: 12px; color: var(--t2, #4B5468); }
.msd-chat-l { font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--t3, #94A3B8); margin-bottom: 7px; }
.msd-chat-empty { font-size: 12px; color: var(--t4, #B4B2A9); margin-bottom: 9px; }
.msd-msg { display: flex; gap: 10px; align-items: baseline; padding: 7px 0; border-bottom: 1px solid var(--border, #EEF0F5); }
.msd-msg-t { font-size: 12.5px; color: var(--t1, #1E2A4A); line-height: 1.5; }
.msd-msg-d { font-size: 10.5px; color: var(--t3, #94A3B8); margin-left: auto; white-space: nowrap; }
.msd-reply { display: flex; gap: 8px; margin-top: 11px; }
.msd-input {
  flex: 1; font-family: inherit; font-size: 12.5px; color: var(--t1, #1E2A4A);
  border: 1px solid var(--border-hard, #E5E7EB); border-radius: 10px; padding: 9px 12px; outline: 0;
}
.msd-input:focus { border-color: rgba(124,111,247,.45); box-shadow: 0 0 0 3px rgba(124,111,247,.10); }
.msd-btn {
  font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%);
  border: none; border-radius: 10px; padding: 9px 18px; cursor: pointer;
  box-shadow: 0 3px 12px rgba(108,92,231,.30); transition: transform .14s, box-shadow .14s;
}
.msd-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108,92,231,.42); }
.msd-btn:disabled { opacity: .55; cursor: default; box-shadow: none; }
.msd-btn-ghost {
  margin-right: auto; font-size: 12px; font-weight: 600; font-family: inherit;
  color: var(--p-deep, #534AB7); background: transparent;
  border: 1px solid var(--border-hard, #E5E7EB); border-radius: 10px;
  padding: 8px 14px; cursor: pointer; transition: background .12s, border-color .12s;
}
.msd-btn-ghost:hover { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.35); }
.msd-btn-danger {
  font-size: 12px; font-weight: 600; font-family: inherit; color: #E24B4A;
  background: transparent; border: 1px solid rgba(226,75,74,.35); border-radius: 10px;
  padding: 8px 14px; cursor: pointer; transition: background .12s;
}
.msd-btn-danger:hover:not(:disabled) { background: rgba(226,75,74,.08); }

@media (max-width: 720px) {
  .ms-row { grid-template-columns: 96px minmax(0, 1fr) 16px; }
  .ms-when { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .ms-row { animation: none; }
  .ms-row:hover { transform: none; }
  .msd-btn:hover:not(:disabled) { transform: none; }
}
</style>
