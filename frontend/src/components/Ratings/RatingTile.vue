<script setup lang="ts">
/**
 * RatingTile — карточка рейтинга агентства с INLINE-редактированием.
 *
 * • Отображение: credit (грейд + outlook + дата) или esg (балл + шкала + дата).
 * • Inline-edit под RBAC `ratings.edit` (canEdit-проп) — клик по карандашу →
 *   форма прямо в карточке. Сохранение через ratingsApi (PATCH/POST), которое
 *   уже гейтит permission на бэке, пишет историю (moderation/audit) и
 *   рассылает field_update по WebSocket → синхронизация во всех вью.
 * • Если правка ушла на модерацию (202) — показываем «на модерации».
 * • Премиум: flip view↔edit, focus-ring, save-state, hover-affordance.
 */
import { reactive, ref, computed } from "vue";
import { ratingsApi, type AgencyRatingBrief } from "@/api/ratings";
import { isModerationQueued } from "@/api/client";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();


const props = withDefaults(defineProps<{
  companyId: string;
  agency: string;              // API-строка агентства ("Fitch", "S&P", …)
  label: string;               // отображаемое имя ("Fitch Ratings")
  rating: AgencyRatingBrief | null;
  canEdit?: boolean;
  mode?: "credit" | "esg";
}>(), { canEdit: false, mode: "credit" });

const emit = defineEmits<{ saved: [] }>();

const OUTLOOKS = [
  { v: "", l: "—" },
  { v: "Stable", l: i18nKey("Стабильный") },
  { v: "Positive", l: i18nKey("Позитивный") },
  { v: "Negative", l: i18nKey("Негативный") },
  { v: "Developing", l: i18nKey("Развивающийся") },
  { v: "RWN", l: i18nKey("CW Негативный") },
  { v: "RWP", l: i18nKey("CW Позитивный") },
];
const OUTLOOK_VIEW: Record<string, { l: string; fg: string; bg: string }> = {
  Stable:     { l: i18nKey("Стабильный"),    fg: "#64748B", bg: "#F1F5F9" },
  Positive:   { l: i18nKey("Позитивный"),    fg: "#1D9E75", bg: "#ECFDF5" },
  Negative:   { l: i18nKey("Негативный"),    fg: "#EF4444", bg: "#FEE2E2" },
  Developing: { l: i18nKey("Развивающийся"), fg: "#D97706", bg: "#FEF9C3" },
  RWN:        { l: i18nKey("CW Негативный"), fg: "#EF4444", bg: "#FEE2E2" },
  RWP:        { l: i18nKey("CW Позитивный"), fg: "#1D9E75", bg: "#ECFDF5" },
};

function creditColor(r: string | null | undefined): string {
  if (!r) return "#94A3B8";
  const s = r.toUpperCase();
  if (s.startsWith("BBB") || s.startsWith("A")) return "#1D9E75";
  if (s.startsWith("BB")) return "#D97706";
  if (s.startsWith("B")) return "#E24B4A";
  return "#94A3B8";
}

const outlookView = computed(() =>
  props.rating?.outlook ? OUTLOOK_VIEW[props.rating.outlook] || null : null,
);
const esgPct = computed(() => {
  const n = Number(props.rating?.score);
  return Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : 0;
});
const esgColor = computed(() => {
  const p = esgPct.value;
  return p >= 70 ? "#1D9E75" : p >= 40 ? "#D97706" : "#E24B4A";
});

// Премиум-вордмарки агентств: монограмма в бренд-тинт-чипе + название (стилизация,
// не товарные знаки — фирменный цвет агентства + первая буква/аббревиатура).
const AGENCY_MARKS: Record<string, { mono: string; fg: string; bg: string }> = {
  "Fitch":             { mono: "F",   fg: "#15366B", bg: "#E7EDF7" },
  "S&P":               { mono: "S&P", fg: "#B11226", bg: "#FBE9EC" },
  "Moody's":           { mono: "M",   fg: "#0A4DA2", bg: "#E6EEF9" },
  "Sustainable Fitch": { mono: "SF",  fg: "#1D7A53", bg: "#E6F4EC" },
  "S&P ESG":           { mono: "ESG", fg: "#1D7A53", bg: "#E6F4EC" },
  "CDP":               { mono: "CDP", fg: "#0A4DA2", bg: "#E6EEF9" },
};
const agencyMark = computed(() =>
  AGENCY_MARKS[props.agency]
  || { mono: (props.label || "?").trim().charAt(0).toUpperCase() || "?", fg: "#475569", bg: "#F1F5F9" },
);

// ─── Inline-edit state ───────────────────────────────────────────
const editing = ref(false);
const saving = ref(false);
const err = ref<string | null>(null);
const queued = ref(false);
const buf = reactive({ rating: "", outlook: "", score: "", date: "", url: "" });

function startEdit(): void {
  if (!props.canEdit) return;
  buf.rating = props.rating?.rating || "";
  buf.outlook = props.rating?.outlook || "";
  buf.score = props.rating?.score || "";
  buf.date = props.rating?.rating_date_text || "";
  buf.url = props.rating?.report_url || "";
  err.value = null;
  queued.value = false;
  editing.value = true;
}
function cancel(): void { editing.value = false; err.value = null; }

function _isoFromText(t: string): string | null {
  const m = t.match(/(\d{1,2})[./](\d{1,2})[./](\d{4})/);
  if (!m) return null;
  const [, d, mo, y] = m;
  return `${y}-${mo.padStart(2, "0")}-${d.padStart(2, "0")}`;
}

async function save(): Promise<void> {
  saving.value = true;
  err.value = null;
  try {
    const payload: Record<string, unknown> = {
      rating_date_text: buf.date.trim() || null,
      rating_date: _isoFromText(buf.date),
      report_url: buf.url.trim() || null,
    };
    if (props.mode === "esg") {
      payload.score = buf.score.trim() || null;
      payload.rating = buf.rating.trim() || null;
    } else {
      payload.rating = buf.rating.trim() || null;
      payload.outlook = buf.outlook || null;
    }

    const res = props.rating?.id
      ? await ratingsApi.update(props.rating.id, payload as Partial<AgencyRatingBrief>)
      : await ratingsApi.create({ company_id: props.companyId, agency: props.agency, ...payload });

    if (isModerationQueued(res)) {
      queued.value = true;
      setTimeout(() => { editing.value = false; emit("saved"); }, 1400);
    } else {
      editing.value = false;
      emit("saved");
    }
  } catch (e: any) {
    err.value = e?.response?.data?.detail || e?.message || t('Не удалось сохранить');
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="rt" :class="{ 'rt-empty': !rating && !editing, 'rt-editing': editing }">
    <Transition name="rt-flip" mode="out-in">
      <!-- ─── EDIT MODE ─── -->
      <div v-if="editing" key="edit" class="rt-edit">
        <div class="rt-agency">
          <span class="rt-agency-mono" :style="{ background: agencyMark.bg, color: agencyMark.fg }">{{ agencyMark.mono }}</span>
          <span class="rt-agency-name">{{ t(label) }}</span>
        </div>
        <input v-if="mode === 'credit'" v-model="buf.rating" class="rt-in rt-in-grade"
               placeholder="BB+" maxlength="16" :disabled="saving" />
        <input v-else v-model="buf.score" class="rt-in rt-in-grade"
               placeholder="0–100" maxlength="16" :disabled="saving" />
        <select v-if="mode === 'credit'" v-model="buf.outlook" class="rt-in" :disabled="saving">
          <option v-for="o in OUTLOOKS" :key="o.v" :value="o.v">{{ o.l }}</option>
        </select>
        <input v-model="buf.date" class="rt-in" :placeholder="t('дата (окт 2025)')"
               maxlength="64" :disabled="saving" />
        <p v-if="err" class="rt-err">{{ err }}</p>
        <p v-if="queued" class="rt-queued">{{ t('⏳ Отправлено на модерацию') }}</p>
        <div class="rt-actions">
          <button class="rt-btn rt-btn-ghost" @click="cancel" :disabled="saving">{{ t('Отмена') }}</button>
          <button class="rt-btn rt-btn-save" @click="save" :disabled="saving">
            <span v-if="saving" class="rt-spin" aria-hidden="true"></span>
            {{ saving ? "" : t('Сохранить') }}
          </button>
        </div>
      </div>

      <!-- ─── EMPTY (add) ─── -->
      <div v-else-if="!rating" key="empty" class="rt-emptyc" @click="startEdit"
           :class="{ 'rt-clickable': canEdit }">
        <div class="rt-agency">
          <span class="rt-agency-mono" :style="{ background: agencyMark.bg, color: agencyMark.fg }">{{ agencyMark.mono }}</span>
          <span class="rt-agency-name">{{ t(label) }}</span>
        </div>
        <div class="rt-plus">{{ canEdit ? "+" : "—" }}</div>
        <div v-if="canEdit" class="rt-add-hint">{{ t('добавить') }}</div>
      </div>

      <!-- ─── DISPLAY ─── -->
      <div v-else key="view" class="rt-view">
        <button v-if="canEdit" class="rt-edit-btn" @click="startEdit" :title="t('Редактировать рейтинг')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>
          </svg>
        </button>
        <div class="rt-agency">
          <span class="rt-agency-mono" :style="{ background: agencyMark.bg, color: agencyMark.fg }">{{ agencyMark.mono }}</span>
          <span class="rt-agency-name">{{ t(label) }}</span>
        </div>

        <template v-if="mode === 'credit'">
          <div class="rt-value" :style="{ color: creditColor(rating.rating) }">{{ rating.rating }}</div>
          <div v-if="outlookView" class="rt-outlook"
               :style="{ background: outlookView.bg, color: outlookView.fg }">{{ outlookView.l }}</div>
        </template>
        <template v-else>
          <div class="rt-value" :style="{ color: esgColor }">{{ rating.score || rating.rating }}</div>
          <div v-if="rating.score" class="rt-esg-bar">
            <div class="rt-esg-fill" :style="{ width: esgPct + '%', background: esgColor }"></div>
          </div>
          <div v-if="rating.score" class="rt-esg-score" :style="{ color: esgColor }">{{ rating.score }} / 100</div>
        </template>

        <div v-if="rating.rating_date_text" class="rt-date">
          {{ rating.rating_date_text }}
          <a v-if="rating.report_url" :href="rating.report_url" target="_blank"
             class="rt-link" @click.stop :title="t('Открыть отчёт')">↗</a>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.rt {
  position: relative;
  background: var(--card-bg, rgba(255, 255, 255, 0.82));
  border: 1px solid var(--card-border, rgba(99, 102, 180, 0.10));
  border-radius: 12px;
  padding: 11px 12px 10px;
  min-height: 104px;
  transition: border-color 0.16s, box-shadow 0.16s, transform 0.16s;
}
.rt:hover { box-shadow: 0 2px 12px rgba(15, 23, 60, 0.06); }
.rt-editing { border-color: rgba(124, 111, 247, 0.42); box-shadow: 0 4px 18px rgba(108, 92, 231, 0.12); }

.rt-agency { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; min-width: 0; }
.rt-agency-mono {
  flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 18px; height: 16px; padding: 0 4px;
  border-radius: 4px;
  font-size: 9px; font-weight: 700; letter-spacing: 0.02em;
}
.rt-agency-name { font-size: 10px; color: var(--t3, #888780); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rt-value { font-size: 29px; font-weight: 600; line-height: 1; letter-spacing: -0.03em; }
.rt-outlook { display: inline-block; font-size: 10px; font-weight: 500; padding: 1px 7px; border-radius: 5px; margin-top: 6px; }
.rt-date { font-size: 10px; color: var(--t3, #888780); margin-top: 6px; }
.rt-link { color: var(--p, #7C6FF7); text-decoration: none; margin-left: 3px; font-weight: 600; }
.rt-link:hover { text-decoration: underline; }

.rt-esg-bar { height: 3px; background: rgba(0, 0, 0, 0.08); border-radius: 2px; overflow: hidden; margin-top: 7px; }
.rt-esg-fill { height: 100%; border-radius: 2px; transition: width 0.7s cubic-bezier(0.34, 1.2, 0.64, 1); }
.rt-esg-score { font-size: 10px; margin-top: 4px; }

/* edit affordance — появляется на hover */
.rt-edit-btn {
  position: absolute; top: 7px; right: 7px;
  width: 22px; height: 22px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(124, 111, 247, 0.10); color: var(--p-deep, #534AB7);
  border: 1px solid transparent; cursor: pointer;
  opacity: 0; transform: scale(0.9);
  transition: opacity 0.15s, transform 0.15s, background 0.15s;
}
.rt:hover .rt-edit-btn { opacity: 1; transform: scale(1); }
.rt-edit-btn:hover { background: rgba(124, 111, 247, 0.20); }

/* empty */
.rt-empty { border-style: dashed; }
.rt-emptyc { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; min-height: 82px; gap: 2px; }
.rt-clickable { cursor: pointer; }
.rt-clickable:hover { background: rgba(124, 111, 247, 0.04); }
.rt-plus { font-size: 20px; color: var(--p, #7C6FF7); font-weight: 300; }
.rt-add-hint { font-size: 9.5px; color: var(--t3, #888780); text-transform: uppercase; letter-spacing: 0.06em; }
.rt-empty .rt-agency { justify-content: center; }
.rt-emptyc .rt-agency { width: 100%; justify-content: center; }

/* edit form */
.rt-edit { display: flex; flex-direction: column; gap: 6px; }
.rt-in {
  width: 100%; box-sizing: border-box;
  border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 8px;
  background: var(--bg2, #F8FAFC); padding: 6px 9px;
  font-size: 12px; font-family: inherit; color: var(--t1, #1E2A4A); outline: none;
  transition: border-color 0.14s, box-shadow 0.14s;
}
.rt-in:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124, 111, 247, 0.14); }
.rt-in-grade { font-size: 18px; font-weight: 600; letter-spacing: -0.02em; }
.rt-err { font-size: 10.5px; color: var(--sev-high, #E24B4A); margin: 0; }
.rt-queued { font-size: 10.5px; color: var(--p-deep, #534AB7); margin: 0; font-weight: 500; }
.rt-actions { display: flex; gap: 6px; margin-top: 2px; }
.rt-btn { flex: 1; border: none; border-radius: 7px; padding: 7px 0; font-size: 11.5px; font-weight: 600; cursor: pointer; font-family: inherit; transition: all 0.14s; display: inline-flex; align-items: center; justify-content: center; min-height: 30px; }
.rt-btn-ghost { background: transparent; border: 1px solid var(--border-input, #E2E8F0); color: var(--t2, #334155); }
.rt-btn-ghost:hover:not(:disabled) { background: var(--bg3, #F1F5F9); }
.rt-btn-save { background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); color: #fff; box-shadow: 0 2px 10px rgba(108, 92, 231, 0.32); }
.rt-btn-save:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(108, 92, 231, 0.45); }
.rt-btn:disabled { opacity: 0.6; cursor: default; }
.rt-spin { width: 13px; height: 13px; border: 2px solid rgba(255, 255, 255, 0.4); border-top-color: #fff; border-radius: 50%; animation: rtSpin 0.7s linear infinite; }
@keyframes rtSpin { to { transform: rotate(360deg); } }

/* премиум flip view↔edit */
.rt-flip-enter-active, .rt-flip-leave-active { transition: opacity 0.2s, transform 0.2s cubic-bezier(0.34, 1.2, 0.64, 1); }
.rt-flip-enter-from { opacity: 0; transform: scale(0.96); }
.rt-flip-leave-to { opacity: 0; transform: scale(0.98); }

</style>
