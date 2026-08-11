<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import BIcon from "@/components/broadcasts/BIcon.vue";
import {
  moderationApi, formatRelativeTime, STATUS_LABELS,
  type Submission, type Comment,
} from "@/api/moderation";
import { useAuthStore } from "@/stores/auth";
import { useUserDirectory } from "@/composables/useUserDirectory";
import { useToast } from "@/composables/useToast";
import { useFormatters } from "@/composables/useFormatters";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();


const fmt = useFormatters();
const { confirmDialog } = useConfirm();

const props = defineProps<{ submissionId: string }>();
const emit = defineEmits<{ close: []; resolved: [] }>();

// Esc закрывает карточку заявки (модалка кастомная, глобального Esc не наследует).
function onKeydown(e: KeyboardEvent) { if (e.key === "Escape") emit("close"); }
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

const auth = useAuthStore();
const dir = useUserDirectory();
const toast = useToast();

/** Русские названия модулей — в карточке выводился сырой код («business_plan»). */
const MODULE_RU: Record<string, string> = {
  tasks: "Задачи", projects: "Проекты", comments: "Комментарии",
  kpi: "KPI", financials: "Финансы", business_plan: "Бизнес-план",
  esg: "ESG", governance: "Корп. управление", ratings: "Рейтинги",
  procurement: "Закупки", production: "Производство", credit: "Кредитный портфель",
  investment: "Инвест-проекты", unit_cost: "Себестоимость", companies: "Компании",
};
function moduleRu(code: string): string { return t(MODULE_RU[code] || code); }

const sub = ref<Submission | null>(null);
const comments = ref<Comment[]>([]);
const loading = ref(false);
const acting = ref(false);
const error = ref<string | null>(null);
const newComment = ref("");
const internalToggle = ref(false);
const commentPosting = ref(false);

// C1: inline resolution panel — replaces window.prompt for reject.
// Решение модератора — только «принять» или «отклонить с комментарием»
// (решение владельца 03.08.2026). Режим «изменить и принять» правил
// proposed_value СЫРЫМ JSON: для согласующего-нетехнаря это тупик, а молчаливая
// правка чужого предложения ещё и подменяла авторство.
type ResolveMode = "approve" | "reject" | null;
const resolveMode = ref<ResolveMode>(null);
const resolveNote = ref("");

// Право решать считает БЭКЕНД и отдаёт полем can_resolve. Здесь было своё
// правило (owner || assigned || coapprover), а при штатной маршрутизации оба
// поля пусты — у обычного модератора не было ни «Принять», ни «Отклонить».
// Фолбэк на старое правило — для ответов, отданных до выката этого поля.
const canResolve = computed(() => {
  const s = sub.value as (typeof sub.value & { can_resolve?: boolean }) | null;
  if (!s) return false;
  if (typeof s.can_resolve === "boolean") return s.can_resolve;
  return auth.isOwner ||
         auth.user?.id === s.assigned_moderator_id ||
         auth.user?.id === s.coapprover_id;
});
const canWithdraw = computed(() => {
  if (!sub.value) return false;
  return auth.user?.id === sub.value.proposer_user_id &&
         !["approved", "rejected", "expired", "withdrawn", "cancelled"].includes(sub.value.status);
});

async function load() {
  loading.value = true;
  error.value = null;
  try {
    // Комментарии грузим отдельной веткой с мягким провалом: раньше они шли
    // одним Promise.all с заявкой, и 403 на комментариях ронял ОБЕ ветки —
    // карточка не открывалась вовсе, вместе с крестиком.
    sub.value = await moderationApi.get(props.submissionId);
    comments.value = await moderationApi
      .listComments(props.submissionId)
      .catch(() => []);
    await dir.ensureLoaded();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || t('Не удалось загрузить');
  } finally { loading.value = false; }
}

onMounted(load);

function openResolvePanel(mode: ResolveMode) {
  resolveMode.value = mode;
  resolveNote.value = "";

}

function cancelResolvePanel() {
  resolveMode.value = null;
  resolveNote.value = "";
}

async function submitResolve() {
  if (!sub.value || !resolveMode.value) return;
  const mode = resolveMode.value;
  acting.value = true;
  try {
    if (mode === "approve") {
      await moderationApi.approve(sub.value.id, resolveNote.value || undefined);
    } else if (mode === "reject") {
      if (!resolveNote.value.trim()) {
        toast.error(t('Укажите причину отклонения'));
        acting.value = false;
        return;
      }
      await moderationApi.reject(sub.value.id, resolveNote.value);
    }
    resolveMode.value = null;
    // Явное подтверждение исхода (канон «feedback everywhere»): действие
    // применяет чужую правку к данным — молчаливое закрытие недостаточно.
    toast.success(mode === "approve" ? t('Заявка одобрена') : t('Заявка отклонена'));
    emit("resolved");
  } catch (e: any) {
    // Тост, а не баннер: карточка заявки длинная, баннер вверху модератор,
    // нажавший кнопку внизу, попросту не увидит.
    toast.error(e?.response?.data?.detail || e?.message || t('Действие не выполнено'));
  } finally { acting.value = false; }
}

async function setReview() {
  if (!sub.value) return;
  const note = resolveNote.value || t("Требуется дополнительное рассмотрение");
  acting.value = true;
  try {
    await moderationApi.setReview(sub.value.id, note);
    emit("resolved");
  } catch (e: any) { toast.error(e?.response?.data?.detail || e?.message || t('Действие не выполнено')); }
  finally { acting.value = false; }
}
async function withdraw() {
  if (!sub.value) return;
  if (!(await confirmDialog({ message: t("Отозвать ваше предложение?"), danger: true }))) return;
  acting.value = true;
  try {
    await moderationApi.withdraw(sub.value.id);
    emit("resolved");
  } catch (e: any) { toast.error(e?.response?.data?.detail || e?.message || t('Действие не выполнено')); }
  finally { acting.value = false; }
}

async function retryApply() {
  if (!sub.value) return;
  acting.value = true;
  try {
    sub.value = await moderationApi.retryApply(sub.value.id);
    if (sub.value.apply_status === "applied") {
      // Success — inform parent so list refreshes.
      emit("resolved");
    }
    // On failed/skipped the panel will show the new error inline.
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || t('Retry не удался'));
  } finally { acting.value = false; }
}

// Apply-status pill styling
function applyPillClass(s: string | null): string {
  if (s === "applied") return "mrm-apply-pill mrm-ap-ok";
  if (s === "failed")  return "mrm-apply-pill mrm-ap-err";
  if (s === "skipped") return "mrm-apply-pill mrm-ap-warn";
  return "mrm-apply-pill mrm-ap-info";
}
function applyPillLabel(s: string | null): string {
  if (s === "applied") return t('Применено');
  if (s === "failed")  return t('Ошибка применения');
  if (s === "skipped") return t('Пропущено (нет handler\'а)');
  if (s === "pending") return t('Не применено');
  return "—";
}

async function postComment() {
  const text = newComment.value.trim();
  // Гард от повторной отправки: комментарий висит и на @keyup.enter, и на клике —
  // быстрый двойной Enter иначе создаёт дубль. В полёте — игнорируем.
  if (!sub.value || !text || commentPosting.value) return;
  commentPosting.value = true;
  try {
    const c = await moderationApi.addComment(sub.value.id, text, { is_internal: internalToggle.value });
    comments.value.push(c);
    newComment.value = "";
  } catch (e: any) { toast.error(e?.response?.data?.detail || e?.message || t('Действие не выполнено')); }
  finally { commentPosting.value = false; }
}

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) emit("close");
}

const diffEntries = computed(() => {
  if (!sub.value) return [];
  const before = sub.value.original_value || {};
  const after  = sub.value.proposed_value || {};
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]));
  return keys.map((k) => ({
    key: k,
    before: (before as Record<string, unknown>)[k],
    after:  (after  as Record<string, unknown>)[k],
    changed: JSON.stringify((before as Record<string, unknown>)[k]) !== JSON.stringify((after as Record<string, unknown>)[k]),
  }));
});

/** Русские подписи полей — модератор видел технические имена (assignee_email). */
const FIELD_RU: Record<string, string> = {
  title: "Название", name: "Название", description: "Описание",
  status: "Статус", due_date: "Срок", start_date: "Начало",
  assignee_id: "Ответственный", assignee_email: "Ответственный",
  assignee_name: "Ответственный", priority: "Приоритет",
  progress: "Прогресс", result: "Результат", notes: "Примечание",
  comment: "Комментарий", body: "Текст", weight: "Вес",
  direction_id: "Направление", tags: "Метки", year: "Год",
  plan: "План", fact: "Факт", value: "Значение", amount: "Сумма",
  currency: "Валюта", unit: "Ед. изм.", is_milestone: "Веха",
};
function fieldRu(key: string): string { return t(FIELD_RU[key] || key); }

/** Человеческие статусы задач/проектов — иначе в диффе стоит «review». */
const STATUS_RU: Record<string, string> = {
  new: "Не начато", init: "Инициирование", active: "В процессе",
  review: "На согласовании", done: "Завершено", deferred: "Перенесено",
  quarterly: "Ежеквартально", monthly: "Ежемесячно", ongoing: "Постоянно",
};

function fmtVal(v: unknown, key?: string): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? t("да") : t("нет");
  if (key === "status" && typeof v === "string" && STATUS_RU[v]) return t(STATUS_RU[v]);
  if (typeof v === "number") return fmt.fmtNumber(v);
  if (Array.isArray(v)) return v.length ? v.map((x) => String(x)).join(", ") : "—";
  if (typeof v === "object") {
    // Вложенный объект: показываем поля, а не JSON-строку.
    const parts = Object.entries(v as Record<string, unknown>)
      .filter(([, val]) => val !== null && val !== undefined && val !== "")
      .slice(0, 6)
      .map(([k2, val]) => `${fieldRu(k2)}: ${String(val)}`);
    return parts.length ? parts.join(" · ") : "—";
  }
  return String(v);
}

// По умолчанию показываем ТОЛЬКО изменённое: раньше в списке были все поля
// тела запроса, и модератор глазами искал, что именно поменялось.
const showAllFields = ref(false);
const changedEntries = computed(() => diffEntries.value.filter((d) => d.changed));
const visibleEntries = computed(() =>
  showAllFields.value ? diffEntries.value : changedEntries.value,
);
</script>

<template>
  <div class="mrm-backdrop" @click="onBackdropClick">
    <div class="mrm-card" role="dialog" aria-modal="true" :aria-label="t('Карточка заявки на модерацию')">

      <div v-if="loading" class="mrm-loading">{{ t('Загрузка…') }}</div>

      <template v-else-if="sub">
        <div class="mrm-topbar">
          <div class="mrm-tb-l">
            <span class="mrm-tb-icn">
              <BIcon name="shield-check" :size="14" />
            </span>
            <div>
              <div class="mrm-eyebrow">
                {{ t('Модерация ·') }} <span class="mrm-id">#{{ sub.id.slice(0, 8) }}</span> ·
                <span class="mrm-status-pill" :style="{ background: STATUS_LABELS[sub.status].bg, color: STATUS_LABELS[sub.status].color }">
                  {{ t(STATUS_LABELS[sub.status].label) }}
                </span>
              </div>
              <div class="mrm-title">{{ sub.target_entity_label || moduleRu(sub.target_module) }}</div>
            </div>
          </div>
          <button class="mrm-close" :aria-label="t('Закрыть')" @click="emit('close')">
            <BIcon name="x" :size="14" />
          </button>
        </div>

        <div class="mrm-meta">
          <div class="mrm-proposer">
            <span class="mrm-avatar mrm-avatar-ext">{{ dir.initials(sub.proposer_user_id) }}</span>
            <div>
              <div class="mrm-proposer-name">
                {{ dir.shortName(sub.proposer_user_id) }}
                <span v-if="sub.proposer_is_external" class="mrm-ext-pill">EXTERNAL</span>
              </div>
              <div class="mrm-proposer-meta">{{ dir.byId(sub.proposer_user_id)?.email || `id:${sub.proposer_user_id.slice(0,8)}` }}</div>
            </div>
          </div>
          <div class="mrm-meta-r">
            {{ t('Предложено:') }} <b>{{ formatRelativeTime(sub.created_at) }}</b>
            <span v-if="sub.expires_at"> {{ t('· истекает') }} {{ formatRelativeTime(sub.expires_at) }}</span>
          </div>
        </div>

        <div class="mrm-body">

          <div class="mrm-section">
            <div class="mrm-section-hd">{{ t('Контекст') }}</div>
            <div class="mrm-breadcrumbs">
              <span class="mrm-bc-item"><BIcon name="package" :size="14" /> {{ moduleRu(sub.target_module) }}</span>
              <BIcon v-if="sub.target_entity_label" name="chevron-right" :size="13" class="mrm-bc-arr" />
              <span v-if="sub.target_entity_label" class="mrm-bc-item">{{ sub.target_entity_label }}</span>
              <BIcon v-if="sub.target_field" name="chevron-right" :size="13" class="mrm-bc-arr" />
              <span v-if="sub.target_field" class="mrm-bc-item mrm-bc-strong">{{ sub.target_field }}</span>
            </div>
          </div>

          <div v-if="diffEntries.length > 0" class="mrm-section">
            <div class="mrm-section-hd">
              {{ t('Изменения') }}
              <span v-if="changedEntries.length" class="mrm-diff-cnt">{{ changedEntries.length }}</span>
              <button v-if="diffEntries.length > changedEntries.length"
                      class="mrm-diff-toggle" @click="showAllFields = !showAllFields">
                {{ showAllFields
                    ? t('только изменённые')
                    : t('показать все поля ({value0})', { value0: diffEntries.length }) }}
              </button>
            </div>
            <div v-if="!visibleEntries.length" class="mrm-diff-none">
              {{ t('Значения полей не изменились — предложение не меняет данные.') }}
            </div>
            <div v-else class="mrm-diff-grid">
              <div v-for="(d, i) in visibleEntries" :key="d.key" class="mrm-diff-row"
                   :class="{ changed: d.changed }" :style="{ '--d': Math.min(i, 12) * 26 + 'ms' }">
                <div class="mrm-diff-key">{{ fieldRu(d.key) }}</div>
                <div class="mrm-diff-before">
                  <div class="mrm-diff-label">{{ t('Было') }}</div>
                  <div class="mrm-diff-val">{{ fmtVal(d.before, d.key) }}</div>
                </div>
                <BIcon name="arrow-right" :size="15" class="mrm-diff-arr" />
                <div class="mrm-diff-after">
                  <div class="mrm-diff-label">{{ t('Предложено') }}</div>
                  <div class="mrm-diff-val">{{ fmtVal(d.after, d.key) }}</div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="sub.reason" class="mrm-section">
            <div class="mrm-section-hd">{{ t('Обоснование') }}</div>
            <div class="mrm-reason">{{ sub.reason }}</div>
          </div>

          <div v-if="sub.attachments && sub.attachments.length" class="mrm-section">
            <div class="mrm-section-hd">{{ t('Вложения') }}</div>
            <div class="mrm-attachments">
              <span v-for="(a, i) in sub.attachments" :key="i" class="mrm-attach">
                <BIcon name="paperclip" :size="14" />
                {{ (a as Record<string, unknown>).name || t('файл') }}
              </span>
            </div>
          </div>

          <div class="mrm-section">
            <div class="mrm-section-hd">{{ t('Обсуждение ·') }} {{ comments.length }}</div>
            <div v-if="!comments.length" class="mrm-empty-comments">{{ t('Нет комментариев') }}</div>
            <div v-else class="mrm-comments">
              <div v-for="c in comments" :key="c.id" class="mrm-comment" :class="{ internal: c.is_internal }">
                <span class="mrm-c-avatar">{{ c.user_id ? dir.initials(c.user_id) : "—" }}</span>
                <div class="mrm-c-body">
                  <div class="mrm-c-meta">
                    <b>{{ c.user_id ? dir.shortName(c.user_id) : t('(удалён)') }}</b>
                    <span v-if="c.is_internal" class="mrm-c-internal">internal</span>
                    <span class="mrm-c-time">{{ formatRelativeTime(c.created_at) }}</span>
                  </div>
                  <div class="mrm-c-text">{{ c.text }}</div>
                </div>
              </div>
            </div>
            <div class="mrm-c-compose">
              <input v-model="newComment" :placeholder="t('Написать комментарий...')" @keyup.enter="postComment" />
              <label v-if="canResolve" class="mrm-c-internal-check"><input type="checkbox" v-model="internalToggle"> internal</label>
              <button class="mrm-c-send" @click="postComment" :disabled="!newComment.trim()">
                <BIcon name="send" :size="14" /> {{ t('Отправить') }}
              </button>
            </div>
          </div>

          <div v-if="sub.resolution_note" class="mrm-section">
            <div class="mrm-section-hd">{{ t('Резолюция') }}</div>
            <div class="mrm-resolution">{{ sub.resolution_note }}</div>
          </div>

          <!-- B1 follow-up: apply-dispatcher status for approved submissions. -->
          <div v-if="sub.status === 'approved'" class="mrm-section">
            <div class="mrm-section-hd">{{ t('Применение изменения') }}</div>
            <div class="mrm-apply-row">
              <span :class="applyPillClass(sub.apply_status)">
                {{ t(applyPillLabel(sub.apply_status)) }}
              </span>
              <button
                v-if="canResolve && (sub.apply_status === 'failed' || sub.apply_status === 'skipped' || sub.apply_status === 'pending')"
                class="mrm-btn mrm-btn-ghost"
                :disabled="acting"
                @click="retryApply"
              >
                <BIcon name="refresh" :size="14" />
                {{ acting ? '…' : t('Повторить применение') }}
              </button>
            </div>
            <div v-if="sub.apply_error" class="mrm-apply-err">
              {{ sub.apply_error }}
            </div>
          </div>

          <div v-if="error" class="mrm-error">{{ error }}</div>
        </div>

        <!-- Решение по заявке: принять или отклонить с комментарием -->
        <div v-if="resolveMode" class="mrm-resolve-panel" :class="`mrm-rp-${resolveMode}`">
          <div class="mrm-rp-hd">
            <span v-if="resolveMode === 'approve'">{{ t('Принять предложение') }}</span>
            <span v-else>{{ t('Отклонить предложение') }}</span>
          </div>


          <div v-if="resolveMode === 'reject'" class="mrm-rp-tip">
            {{ t('Опишите, что нужно поправить — автор увидит комментарий в своих заявках и сможет прислать исправленный вариант.') }}
          </div>

          <textarea
            v-model="resolveNote"
            class="mrm-rp-note"
            :placeholder="resolveMode === 'reject' ? t('Причина отклонения (обязательно)') : t('Комментарий к решению (необязательно)')"
            rows="2"
          ></textarea>

          <div class="mrm-rp-actions">
            <button class="mrm-btn mrm-btn-ghost" @click="cancelResolvePanel" :disabled="acting">{{ t('Отмена') }}</button>
            <button
              class="mrm-btn"
              :class="resolveMode === 'reject' ? 'mrm-btn-reject' : 'mrm-btn-approve'"
              :disabled="acting"
              @click="submitResolve"
            >
              <span v-if="resolveMode === 'approve'">{{ t('Подтвердить «Принять»') }}</span>
              <span v-else-if="resolveMode === 'reject'">{{ t('Подтвердить «Отклонить»') }}</span>
              <span v-else>{{ t('Сохранить и принять') }}</span>
            </button>
          </div>
        </div>

        <div class="mrm-footer">
          <div class="mrm-foot-l">
            <BIcon name="history" :size="14" />
            {{ t('Все действия логируются в audit log') }}
          </div>
          <div class="mrm-foot-r" v-if="!resolveMode">
            <button v-if="canWithdraw" class="mrm-btn mrm-btn-ghost" :disabled="acting" @click="withdraw">
              {{ t('Отозвать') }}
            </button>
            <template v-if="canResolve && ['pending','under_review'].includes(sub.status)">
              <button class="mrm-btn mrm-btn-ghost" :disabled="acting" @click="setReview">
                <BIcon name="eye" :size="14" /> {{ t('На рассмотрение') }}
              </button>
              <button class="mrm-btn mrm-btn-reject" :disabled="acting" @click="openResolvePanel('reject')">
                <BIcon name="x" :size="14" /> {{ t('Отклонить') }}
              </button>
              <button class="mrm-btn mrm-btn-approve" :disabled="acting" @click="openResolvePanel('approve')">
                <BIcon name="check" :size="14" /> {{ t('Принять') }}
              </button>
            </template>
          </div>
        </div>
      </template>

      <div v-else-if="error" class="mrm-error">{{ error }}</div>
    </div>
  </div>
</template>

<style scoped>
.mrm-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15,18,40,.45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  z-index: 1500;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
  animation: mrmFade .25s var(--ease-standard);
}
@keyframes mrmFade { from { opacity: 0; } to { opacity: 1; } }

.mrm-card {
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  width: 720px; max-width: 100%;
  max-height: 90dvh;
  display: flex; flex-direction: column;
  overflow: hidden;
  animation: mrmIn .45s var(--ease-standard);
}
@keyframes mrmIn {
  from { opacity: 0; transform: scale(.96) translateY(-8px); }
  to   { opacity: 1; transform: scale(1)    translateY(0);    }
}

.mrm-loading { padding: 60px; text-align: center; color: var(--color-text-tertiary); font-size: 13px; }

.mrm-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 12px 18px;
  display: flex; align-items: center; justify-content: space-between;
}
.mrm-tb-l { display: flex; align-items: center; gap: 10px; }
.mrm-tb-icn {
  width: 30px; height: 30px;
  border-radius: 7px;
  background: rgba(239,159,39,.2);
  color: #FAC775;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 16px;
}
.mrm-eyebrow {
  font-size: 10px;
  color: rgba(255,255,255,.55);
  text-transform: uppercase;
  letter-spacing: .08em;
  font-weight: 500;
  display: flex; align-items: center; gap: 5px;
}
.mrm-id { font-family: monospace; }
.mrm-status-pill {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .04em;
  color: #fff !important;
  background: rgba(255,255,255,.15) !important;
}
.mrm-title { font-size: 14px; color: #fff; font-weight: 500; margin-top: 1px; }
.mrm-close {
  background: rgba(255,255,255,.1);
  border: 0;
  color: #fff;
  width: 26px; height: 26px;
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 14px;
}

.mrm-meta {
  padding: 11px 18px;
  background: var(--bg2, #FAFAFC);
  border-bottom: 0.5px solid rgba(0,0,0,.05);
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.mrm-proposer { display: flex; align-items: center; gap: 8px; }
.mrm-avatar {
  width: 30px; height: 30px;
  border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 500;
}
.mrm-avatar-ext { background: rgba(212,83,126,.15); color: #993556; }
.mrm-proposer-name { font-size: 12px; color: var(--color-text-primary); font-weight: 500; display: flex; align-items: center; gap: 6px; }
.mrm-proposer-meta { font-size: 10px; color: var(--color-text-tertiary); }
.mrm-ext-pill {
  background: #D4537E; color: #fff;
  padding: 1px 5px; border-radius: 3px;
  font-size: 8.5px; font-weight: 600; letter-spacing: .04em;
}
.mrm-meta-r { font-size: 11px; color: var(--color-text-secondary); margin-left: auto; }

.mrm-body { padding: 14px 18px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 14px; }

.mrm-section-hd {
  font-size: 9.5px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 500;
  margin-bottom: 6px;
}

.mrm-breadcrumbs {
  background: var(--color-background-secondary);
  border-radius: 7px;
  padding: 9px 12px;
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  font-size: 11.5px;
}
.mrm-bc-item { color: var(--color-text-secondary); display: inline-flex; align-items: center; gap: 4px; }
.mrm-bc-strong { color: var(--color-text-primary); font-weight: 500; }
.mrm-bc-arr { font-size: 10px; color: var(--color-text-tertiary); }

.mrm-diff-grid { display: flex; flex-direction: column; gap: 6px; }
.mrm-diff-row {
  display: grid;
  grid-template-columns: 120px 1fr 24px 1fr;
  gap: 8px;
  align-items: stretch;
}
.mrm-diff-key { font-size: 11px; color: var(--color-text-tertiary); padding-top: 11px; font-family: monospace; }
.mrm-diff-before, .mrm-diff-after {
  background: var(--color-background-secondary);
  border-radius: 6px;
  padding: 7px 10px;
}
.mrm-diff-row.changed .mrm-diff-before {
  background: rgba(226,75,74,.05);
  border: 0.5px solid rgba(226,75,74,.2);
}
.mrm-diff-row.changed .mrm-diff-after {
  background: rgba(29,158,117,.05);
  border: 0.5px solid rgba(29,158,117,.2);
}
.mrm-diff-label {
  font-size: 8.5px;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--color-text-tertiary);
}
.mrm-diff-row.changed .mrm-diff-before .mrm-diff-label { color: var(--sev-critical); font-weight: 600; }
.mrm-diff-row.changed .mrm-diff-after  .mrm-diff-label { color: #0F6E56; font-weight: 600; }
.mrm-diff-val { font-size: 13px; color: var(--color-text-primary); font-weight: 500; font-feature-settings: "tnum"; margin-top: 2px; word-break: break-word; }
.mrm-diff-arr {
  align-self: center; text-align: center;
  font-size: 16px; color: var(--color-text-tertiary);
}

.mrm-reason {
  background: var(--color-background-secondary);
  border-radius: 7px;
  padding: 9px 12px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}
.mrm-resolution {
  background: rgba(127,119,221,.06);
  border-radius: 7px;
  padding: 8px 12px;
  font-size: 11.5px;
  color: var(--color-text-primary);
  line-height: 1.45;
  position: relative; overflow: hidden;
}
.mrm-resolution::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #7F77DD;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}

.mrm-attachments { display: flex; gap: 5px; flex-wrap: wrap; }
.mrm-attach {
  background: var(--color-background-secondary);
  border: 0.5px solid var(--color-border-tertiary);
  padding: 3px 9px;
  border-radius: 6px;
  font-size: 11px;
  color: var(--color-text-secondary);
  display: inline-flex; align-items: center; gap: 4px;
}

.mrm-comments { display: flex; flex-direction: column; gap: 7px; }
.mrm-empty-comments { font-size: 11px; color: var(--color-text-tertiary); padding: 6px 0; }
.mrm-comment { display: flex; gap: 8px; }
.mrm-c-avatar {
  width: 24px; height: 24px;
  border-radius: 50%;
  background: rgba(127,119,221,.15);
  color: var(--p-deep);
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 9.5px; font-weight: 500;
  flex-shrink: 0;
}
.mrm-c-body {
  flex: 1;
  background: var(--color-background-secondary);
  border-radius: 7px;
  padding: 7px 10px;
  font-size: 11.5px;
  color: var(--color-text-primary);
  line-height: 1.4;
}
.mrm-comment.internal .mrm-c-body { background: rgba(239,159,39,.08); border: 0.5px solid rgba(239,159,39,.2); }
.mrm-c-meta { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; font-size: 10.5px; }
.mrm-c-meta b { font-family: monospace; }
.mrm-c-internal { background: rgba(239,159,39,.15); color: #854F0B; padding: 1px 5px; border-radius: 3px; font-size: 8.5px; font-weight: 600; }
.mrm-c-time { color: var(--color-text-tertiary); }
.mrm-c-text { white-space: pre-wrap; }

.mrm-c-compose {
  display: flex; gap: 6px; align-items: center; margin-top: 8px;
}
.mrm-c-compose input {
  flex: 1;
  padding: 7px 10px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 7px;
  font-size: 11.5px;
  font-family: inherit;
  outline: none;
}
.mrm-c-internal-check { font-size: 10px; color: var(--color-text-tertiary); display: inline-flex; align-items: center; gap: 3px; cursor: pointer; }
.mrm-c-send {
  background: rgba(127,119,221,.1);
  color: var(--p-deep);
  border: 0;
  padding: 7px 12px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
}
.mrm-c-send:disabled { opacity: .4; cursor: not-allowed; }

.mrm-error {
  background: rgba(226,75,74,.08);
  color: var(--sev-critical);
  padding: 9px 12px;
  border-radius: 6px;
  font-size: 11.5px;
}

.mrm-footer {
  padding: 11px 18px;
  background: var(--bg2, #FAFAFC);
  border-top: 0.5px solid rgba(0,0,0,.05);
  display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;
}
.mrm-foot-l {
  font-size: 11px;
  color: var(--color-text-tertiary);
  display: inline-flex; align-items: center; gap: 5px;
}
.mrm-foot-r { display: flex; gap: 6px; flex-wrap: wrap; }

.mrm-btn {
  border: 0;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
  transition: background .12s, color .12s;
}
.mrm-btn:disabled { opacity: .5; cursor: not-allowed; }
.mrm-btn-ghost { background: transparent; border: 0.5px solid var(--color-border-tertiary); color: var(--color-text-secondary); }
.mrm-btn-ghost:hover:not(:disabled) { background: rgba(0,0,0,.03); }
.mrm-btn-reject { background: rgba(226,75,74,.1); color: var(--sev-critical); }
.mrm-btn-reject:hover:not(:disabled) { background: rgba(226,75,74,.2); }
.mrm-btn-approve { background: var(--green); color: #fff; }
.mrm-btn-approve:hover:not(:disabled) { background: #0F6E56; }

/* C1: inline resolve panel above footer */
.mrm-resolve-panel {
  padding: 12px 18px;
  border-top: 0.5px solid rgba(0,0,0,.08);
  background: var(--bg2, #FAFAFC);
  display: flex; flex-direction: column; gap: 8px;
}
.mrm-rp-approve     { background: rgba(29,158,117,.04); }
.mrm-rp-reject      { background: rgba(226,75,74,.04); }
.mrm-rp-tip {
  font-size: 11.5px; color: var(--t2, #4B5468); line-height: 1.5;
  background: rgba(217,119,6,.07); border: 1px solid rgba(217,119,6,.18);
  border-radius: 9px; padding: 8px 11px; margin-bottom: 8px;
}
.mrm-rp-hd {
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .06em; color: var(--color-text-secondary);
}
.mrm-rp-json {
  width: 100%; padding: 8px 10px;
  border: 0.5px solid var(--color-border-tertiary); border-radius: 6px;
  font-family: monospace; font-size: 11px; line-height: 1.5;
  color: var(--color-text-primary); background: var(--bg1, #fff);
  resize: vertical; outline: none; box-sizing: border-box;
}
.mrm-rp-json:focus { border-color: #7F77DD; }
.mrm-rp-note {
  width: 100%; padding: 7px 10px;
  border: 0.5px solid var(--color-border-tertiary); border-radius: 6px;
  font-family: inherit; font-size: 12px;
  resize: vertical; outline: none; box-sizing: border-box;
  background: var(--bg1, #fff);
}
.mrm-rp-note:focus { border-color: #7F77DD; }
.mrm-rp-err {
  font-size: 11px; color: var(--sev-critical);
  background: rgba(226,75,74,.08); padding: 5px 9px; border-radius: 5px;
}
.mrm-rp-actions { display: flex; gap: 6px; justify-content: flex-end; }

/* Apply-dispatcher status */
.mrm-apply-row {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.mrm-apply-pill {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 9px; border-radius: 5px;
  font-size: 11px; font-weight: 500;
  text-transform: uppercase; letter-spacing: .04em;
}
.mrm-ap-ok   { background: rgba(29,158,117,.1);  color: #0F6E56; }
.mrm-ap-err  { background: rgba(226,75,74,.1);   color: var(--sev-critical); }
.mrm-ap-warn { background: rgba(239,159,39,.1);  color: #854F0B; }
.mrm-ap-info { background: rgba(127,119,221,.1); color: var(--p-deep); }
.mrm-apply-result {
  font-family: monospace; font-size: 10.5px;
  color: var(--color-text-secondary);
  background: var(--color-background-secondary);
  padding: 3px 7px; border-radius: 5px;
  flex: 1; min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mrm-apply-err {
  margin-top: 6px;
  background: rgba(226,75,74,.06);
  color: var(--sev-critical);
  padding: 6px 9px;
  border-radius: 5px;
  font-size: 11px;
  font-family: monospace;
  line-height: 1.45;
  white-space: pre-wrap;
}

.mrm-diff-cnt {
  font-size: 10px; font-weight: 700; color: var(--p-deep, #534AB7);
  background: rgba(124,111,247,.12); border-radius: 999px; padding: 2px 8px; margin-left: 7px;
}
.mrm-diff-toggle {
  margin-left: auto; font-family: inherit; font-size: 11px; font-weight: 500;
  color: var(--p-deep, #534AB7); background: transparent; border: 0;
  cursor: pointer; text-decoration: underline; text-underline-offset: 2px;
}
.mrm-diff-none { font-size: 12px; color: var(--t3, #94A3B8); padding: 8px 2px; }
.mrm-diff-row { animation: mrmDiffIn .3s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both; animation-delay: var(--d, 0ms); }
@keyframes mrmDiffIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .mrm-diff-row { animation: none; } }
</style>
