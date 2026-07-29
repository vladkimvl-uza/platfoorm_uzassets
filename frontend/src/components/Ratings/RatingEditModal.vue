<script setup lang="ts">
/**
 * RatingEditModal — create / edit / delete one (company × agency) rating.
 *
 * Behaviour:
 *  - If `existing` prop is null → CREATE mode (POST /ratings)
 *  - If `existing` is set → EDIT mode (PATCH /ratings/{id})
 *  - Delete button visible only in EDIT mode (DELETE /ratings/{id})
 *  - Save returns AgencyRatingBrief OR ModerationQueuedTag (handled by api).
 *
 * Outlook values mirror legacy olkLbl:
 *  Stable / Positive / Negative / Developing / RWN / RWP
 */
import { ref, computed, watch } from "vue";
import { ratingsApi, type AgencyRatingBrief } from "@/api/ratings";
import { isModerationQueued } from "@/api/client";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();


const { confirmDialog } = useConfirm();

const props = defineProps<{
  companyId: string;
  companyName: string;
  agency: string;
  existing: AgencyRatingBrief | null;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved"): void;
}>();

// ─── Form state ───────────────────────────────────────────────────
const rating = ref<string>("");
const score = ref<string>("");
const outlook = ref<string>("");
const ratingDateText = ref<string>("");
const ratingDate = ref<string>("");          // ISO YYYY-MM-DD (best-effort)
const reportUrl = ref<string>("");
const saving = ref<boolean>(false);
const deleting = ref<boolean>(false);
const error = ref<string | null>(null);
const result = ref<string | null>(null);

// Pre-fill from existing
watch(() => props.existing, (e) => {
  rating.value         = e?.rating || "";
  score.value          = e?.score || "";
  outlook.value        = e?.outlook || "";
  ratingDateText.value = e?.rating_date_text || "";
  ratingDate.value     = e?.rating_date || "";
  reportUrl.value      = e?.report_url || "";
  error.value = null;
  result.value = null;
}, { immediate: true });

const isEdit = computed(() => !!props.existing);

// P2 (аудит /ratings): dirty-guard — не терять ввод при клике по фону/«Отмена»/✕.
const isDirty = computed(() => {
  const e = props.existing;
  return rating.value !== (e?.rating || "")
      || score.value !== (e?.score || "")
      || outlook.value !== (e?.outlook || "")
      || ratingDateText.value !== (e?.rating_date_text || "")
      || ratingDate.value !== (e?.rating_date || "")
      || reportUrl.value !== (e?.report_url || "");
});
async function requestClose() {
  if (isDirty.value && !result.value) {
    const ok = await confirmDialog({
      message: t("Есть несохранённые изменения. Закрыть без сохранения?"), danger: true,
    });
    if (!ok) return;
  }
  emit("close");
}

const isEsg = computed(() => {
  const a = props.agency;
  return a === "Sustainable Fitch" || a === "S&P ESG" || a === "CDP" ||
         a === "Sustainalytics" || a === "MSCI";
});

const OUTLOOK_OPTIONS = [
  { value: "", label: "—" },
  { value: "Stable", label: i18nKey("Stable · Стабильный →") },
  { value: "Positive", label: i18nKey("Positive · Позитивный ↑") },
  { value: "Negative", label: i18nKey("Negative · Негативный ↓") },
  { value: "Developing", label: i18nKey("Developing · Развивающийся ↔") },
  { value: "RWN", label: i18nKey("RWN · CW Негативный ⚠") },
  { value: "RWP", label: i18nKey("RWP · CW Позитивный ⚠") },
];

// ─── Date string → ISO helper ─────────────────────────────────────
function parseIsoFromText(text: string): string | null {
  const s = text.trim();
  if (!s) return null;
  // already ISO
  const m1 = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m1) return `${m1[1]}-${m1[2]}-${m1[3]}`;
  // DD.MM.YYYY / DD/MM/YYYY
  const m2 = s.match(/^(\d{1,2})[./](\d{1,2})[./](\d{4})/);
  if (m2) {
    const dd = m2[1].padStart(2, "0");
    const mm = m2[2].padStart(2, "0");
    return `${m2[3]}-${mm}-${dd}`;
  }
  return null;
}

// ─── Save ─────────────────────────────────────────────────────────
async function save() {
  saving.value = true;
  error.value = null;
  result.value = null;

  const payload: Record<string, unknown> = {
    rating: rating.value.trim() || null,
    outlook: outlook.value || null,
    score: score.value.trim() || null,
    rating_date_text: ratingDateText.value.trim() || null,
    report_url: reportUrl.value.trim() || null,
  };

  // Auto-derive ISO date from text if recognisable
  const isoFromText = parseIsoFromText(ratingDateText.value);
  if (ratingDate.value) {
    payload.rating_date = ratingDate.value;
  } else if (isoFromText) {
    payload.rating_date = isoFromText;
  }

  try {
    if (isEdit.value && props.existing) {
      const r = await ratingsApi.update(props.existing.id, payload as Partial<AgencyRatingBrief>);
      if (isModerationQueued(r)) {
      result.value = t("Изменение отправлено на модерацию");
      } else {
      result.value = t("Сохранено");
      }
    } else {
      const r = await ratingsApi.create({
        company_id: props.companyId,
        agency: props.agency,
        rating: rating.value.trim() || undefined,
        outlook: outlook.value || undefined,
        score: score.value.trim() || undefined,
        rating_date_text: ratingDateText.value.trim() || undefined,
        rating_date: (payload.rating_date as string) || undefined,
        report_url: reportUrl.value.trim() || undefined,
      });
      if (isModerationQueued(r)) {
      result.value = t("Создание отправлено на модерацию");
      } else {
      result.value = t("Создано");
      }
    }
    emit("saved");
    setTimeout(() => emit("close"), 1000);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || t('Ошибка сохранения');
  } finally {
    saving.value = false;
  }
}

async function remove() {
  if (!props.existing) return;
  if (!(await confirmDialog({
    message: t('Удалить рейтинг {value0} для {value1}?', { value0: props.agency, value1: props.companyName }),
    danger: true,
  }))) return;
  deleting.value = true;
  error.value = null;
  result.value = null;
  try {
    const r = await ratingsApi.remove(props.existing.id);
    if (r && isModerationQueued(r)) {
      result.value = t("Удаление отправлено на модерацию");
    } else {
      result.value = t("Удалено");
    }
    emit("saved");
    setTimeout(() => emit("close"), 1000);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || t('Ошибка удаления');
  } finally {
    deleting.value = false;
  }
}
</script>

<template>
  <Transition name="uza-fade" appear>
    <div class="rem-bg" @click.self="requestClose">
      <div class="rem-card">
        <div class="rem-h">
          <div class="rem-h-l">
            <div class="rem-h-cat">
              <span class="rem-h-pill" :class="{ esg: isEsg }">{{ isEsg ? "ESG" : t('Кредит') }}</span>
              {{ agency }}
            </div>
            <div class="rem-h-t">
              {{ isEdit ? t('Редактировать рейтинг') : t('Добавить рейтинг') }}
            </div>
            <div class="rem-h-s">{{ companyName }}</div>
          </div>
          <button class="rem-h-x" @click="requestClose">✕</button>
        </div>

        <div class="rem-body">
          <div class="rem-grid">
            <!-- Rating -->
            <div class="rem-fld">
              <label class="rem-fld-l">{{ t('Рейтинг') }}</label>
              <input
                v-model="rating"
                type="text"
                class="rem-fld-i"
                :placeholder="isEsg ? t('напр. 54 или Level 3') : t('напр. BB+, AA-, …')"
                autofocus
              />
              <div class="rem-fld-hint">
                <template v-if="isEsg">
                  {{ t('Sustainable Fitch / S&amp;P ESG: число 1-5 (tier) или 0-100 (score). CDP: A/A-/B/B-/C/C-/D') }}
                </template>
                <template v-else>
                  {{ t('Шкала: D · CCC · B · BB · BBB · A · AA · AAA (+/-)') }}
                </template>
              </div>
            </div>

            <!-- Score (ESG only) -->
            <div class="rem-fld" v-if="isEsg">
              <label class="rem-fld-l">{{ t('Score (доп.)') }}</label>
              <input
                v-model="score"
                type="text"
                class="rem-fld-i"
                :placeholder="t('опционально, напр. 54')"
              />
              <div class="rem-fld-hint">{{ t('Если рейтинг = «Level 3», score = «54» (отображается как «3 · 54»)') }}</div>
            </div>

            <!-- Outlook -->
            <div class="rem-fld">
              <label class="rem-fld-l">Outlook</label>
              <select v-model="outlook" class="rem-fld-i">
                <option v-for="o in OUTLOOK_OPTIONS" :key="o.value" :value="o.value">{{ t(o.label) }}</option>
              </select>
            </div>

            <!-- Date text -->
            <div class="rem-fld">
              <label class="rem-fld-l">{{ t('Дата (текст)') }}</label>
              <input
                v-model="ratingDateText"
                type="text"
                class="rem-fld-i"
                :placeholder="t('напр. июл 2025 или 27.02.2026')"
              />
              <div class="rem-fld-hint">{{ t('Свободный формат — отображается в таблице как есть') }}</div>
            </div>

            <!-- ISO date (optional, for sorting) -->
            <div class="rem-fld">
              <label class="rem-fld-l">{{ t('Дата ISO (опц.)') }}</label>
              <input
                v-model="ratingDate"
                type="date"
                class="rem-fld-i"
              />
              <div class="rem-fld-hint">{{ t('Точная дата для сортировки «Последние изменения»') }}</div>
            </div>

            <!-- Report URL -->
            <div class="rem-fld rem-fld-wide">
              <label class="rem-fld-l">{{ t('Ссылка на отчёт') }}</label>
              <input
                v-model="reportUrl"
                type="url"
                class="rem-fld-i"
                placeholder="https://www.sustainablefitch.com/..."
              />
            </div>
          </div>

          <div v-if="error" class="rem-err">⚠ {{ error }}</div>
          <div v-if="result" class="rem-ok">{{ result }}</div>
        </div>

        <div class="rem-foot">
          <button
            v-if="isEdit"
            class="rem-btn rem-btn-del"
            :disabled="saving || deleting"
            @click="remove"
          >
            {{ deleting ? t('Удаление…') : t('Удалить') }}
          </button>
          <div style="flex:1"></div>
          <button class="rem-btn" :disabled="saving || deleting" @click="requestClose">{{ t('Отмена') }}</button>
          <button class="rem-btn rem-btn-primary" :disabled="saving || deleting || !rating.trim()" @click="save">
            {{ saving ? t('Сохранение…') : (isEdit ? t('Сохранить') : t('Создать')) }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.rem-bg {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, .35);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  z-index: 9000;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.rem-card {
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 16px;
  border: 1px solid rgba(0, 0, 0, .08);
  box-shadow: 0 24px 64px rgba(0, 0, 0, .22);
  width: 560px; max-width: 100%;
  max-height: 90dvh;
  display: flex; flex-direction: column;
  overflow: hidden;
}

.rem-h {
  padding: 16px 22px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
}
.rem-h-l { min-width: 0; flex: 1; }
.rem-h-cat {
  font-size: 11px; color: var(--t3, var(--t-muted));
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 4px;
  font-weight: 500;
}
.rem-h-pill {
  display: inline-block;
  background: rgba(55, 138, 221, .12); color: var(--blue);
  font-size: 10px; font-weight: 700;
  padding: 2px 7px;
  border-radius: 4px;
  letter-spacing: .04em;
}
.rem-h-pill.esg { background: rgba(29, 158, 117, .12); color: var(--green); }
.rem-h-t { font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); }
.rem-h-s { font-size: 12px; color: var(--t3, #5F5E5A); margin-top: 4px; }
.rem-h-x {
  border: 0; background: #F4F3F9;
  width: 30px; height: 30px; border-radius: 8px;
  cursor: pointer; font-size: 14px; color: var(--t3, var(--t-muted));
  flex-shrink: 0;
}
.rem-h-x:hover { background: rgba(226, 75, 74, .12); color: var(--sev-critical); }

.rem-body {
  flex: 1; overflow-y: auto;
  padding: 16px 22px;
}

.rem-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.rem-fld { display: flex; flex-direction: column; gap: 4px; }
.rem-fld-wide { grid-column: span 2; }
.rem-fld-l {
  font-size: 10px; font-weight: 600;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .06em;
}
.rem-fld-i {
  font-size: 13px;
  padding: 8px 11px;
  border: 1px solid rgba(0, 0, 0, .1);
  border-radius: 7px;
  font-family: inherit;
  background: var(--bg1, #fff);
  color: var(--t1, #1E2A4A);
  font-feature-settings: "tnum";
  outline: none;
  transition: border-color .12s, box-shadow .12s;
}
.rem-fld-i:focus {
  border-color: #7F77DD;
  box-shadow: 0 0 0 3px rgba(127, 119, 221, .1);
}
.rem-fld-hint {
  font-size: 10.5px;
  color: var(--t3, var(--t-muted));
  margin-top: 1px;
  line-height: 1.4;
}

.rem-err {
  margin-top: 14px;
  padding: 10px 14px;
  background: rgba(226, 75, 74, .08);
  border-radius: 6px;
  color: var(--sev-critical);
  font-size: 12px;
  position: relative; overflow: hidden;
}
.rem-err::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--sev-high);
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.rem-ok {
  margin-top: 14px;
  padding: 10px 14px;
  background: rgba(29, 158, 117, .08);
  border-radius: 6px;
  color: #0F6E56;
  font-size: 12px;
  position: relative; overflow: hidden;
}
.rem-ok::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--green);
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}

.rem-foot {
  padding: 12px 22px;
  border-top: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; gap: 8px;
  background: var(--bg2, #FAFAFC);
}
.rem-btn {
  font-size: 12px; font-weight: 500;
  padding: 7px 14px;
  border-radius: 7px;
  border: 1px solid rgba(15, 23, 60, .12);
  background: var(--bg1, #fff);
  color: var(--t1, #1E2A4A);
  cursor: pointer;
  font-family: inherit;
  transition: all .12s;
}
.rem-btn:hover:not(:disabled) { background: #F4F3F9; }
.rem-btn:disabled { opacity: .4; cursor: not-allowed; }
.rem-btn-primary {
  background: #7F77DD; color: #fff; border-color: #7F77DD;
}
.rem-btn-primary:hover:not(:disabled) { background: #6F66D0; }
.rem-btn-del {
  background: var(--bg1, #fff);
  color: var(--sev-critical);
  border-color: rgba(226, 75, 74, .3);
}
.rem-btn-del:hover:not(:disabled) {
  background: rgba(226, 75, 74, .08);
  border-color: var(--sev-high);
}

.rem-modal-enter-active, .rem-modal-leave-active { transition: opacity .2s; }
.rem-modal-enter-active .rem-card,
.rem-modal-leave-active .rem-card { transition: transform .2s, opacity .2s; }
.rem-modal-enter-from .rem-card,
.rem-modal-leave-to .rem-card { transform: scale(.96); opacity: 0; }
.rem-modal-enter-from, .rem-modal-leave-to { opacity: 0; }

@media (max-width: 480px) {
  .rem-card { width: 100%; max-width: calc(100% - 16px); max-height: 92dvh; }
  .rem-grid { grid-template-columns: 1fr; gap: 12px; }
  .rem-fld-wide { grid-column: span 1; }
  .rem-h, .rem-body, .rem-foot { padding-left: 16px; padding-right: 16px; }
  .rem-foot { flex-wrap: wrap; }
}
</style>
