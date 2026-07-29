<script setup lang="ts">
/**
 * SoeHealthParamsModal — редактор показателей SOE Health Check Tool (лист
 * Parameters): 4 порога на коэффициент (границы бендов 1..5), ВЫБОР индикатора
 * (вкл/выкл в Overall) и ВЕС. Dirty-guard, валидация монотонности, per-row
 * сброс, тосты. PUT /financials/soe-health/params.
 */
import { computed, ref, watch } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { api } from "@/api/client";
import { useToast } from "@/composables/useToast";
import type { SoeRatioMeta } from "@/components/Financials/SoeHealthBoard.vue";
import { useI18n } from "@/composables/useI18n";

const props = defineProps<{ open: boolean; ratios: SoeRatioMeta[] }>();
const emit = defineEmits<{ (e: "close"): void; (e: "saved"): void }>();
const toast = useToast();
const { t } = useI18n();

interface RowDraft { thr: string[]; enabled: boolean; weight: string }
const draft = ref<Record<string, RowDraft>>({});
const saving = ref(false);
let initial = "";

function toInput(r: SoeRatioMeta, t: number): string {
  return r.fmt === "pct" ? String(+(t * 100).toFixed(2)) : String(t);
}
function fromInput(r: SoeRatioMeta, s: string): number | null {
  const n = Number(String(s).replace(",", "."));
  if (!isFinite(n)) return null;
  return r.fmt === "pct" ? n / 100 : n;
}
function defEnabled(r: SoeRatioMeta): boolean { return r.default_enabled ?? r.enabled ?? true; }
function defWeight(r: SoeRatioMeta): number { return r.default_weight ?? r.weight ?? 1; }
function init() {
  const d: Record<string, RowDraft> = {};
  for (const r of props.ratios) {
    d[r.key] = {
      thr: r.thresholds.map((t) => toInput(r, t)),
      enabled: r.enabled ?? true,
      weight: String(r.weight ?? 1),
    };
  }
  draft.value = d;
  initial = JSON.stringify(d);
}
watch(() => props.open, (o) => { if (o) init(); }, { immediate: true });
const dirty = computed(() => JSON.stringify(draft.value) !== initial);

const groups = computed(() => {
  const out: { name: string; items: SoeRatioMeta[] }[] = [];
  for (const r of props.ratios) {
    let g = out.find((x) => x.name === r.group);
    if (!g) { g = { name: r.group, items: [] }; out.push(g); }
    g.items.push(r);
  }
  return out;
});
// сумма весов включённых индикаторов (справочно)
const activeWeightSum = computed(() =>
  props.ratios.reduce((s, r) => {
    const d = draft.value[r.key];
    if (!d || !d.enabled) return s;
    const w = Number(String(d.weight).replace(",", "."));
    return s + (isFinite(w) && w >= 0 ? w : 0);
  }, 0));
const enabledCount = computed(() =>
  props.ratios.filter((r) => draft.value[r.key]?.enabled).length);

function rowError(r: SoeRatioMeta): string | null {
  const d = draft.value[r.key];
  if (!d) return null;
  const vals = d.thr.map((s) => fromInput(r, s));
  if (vals.some((v) => v == null)) return t("все 4 порога — числа");
  const nums = vals as number[];
  const mono = r.direction === "gte"
    ? nums.every((v, i) => i === 0 || nums[i - 1] > v)
    : nums.every((v, i) => i === 0 || nums[i - 1] < v);
  if (!mono) return r.direction === "gte" ? t("нужны строго убывающие") : t("нужны строго возрастающие");
  const w = Number(String(d.weight).replace(",", "."));
  if (!isFinite(w) || w < 0) return t("вес — число ≥ 0");
  return null;
}
const hasErrors = computed(() => props.ratios.some((r) => rowError(r) !== null));

function isRowOverridden(r: SoeRatioMeta): boolean {
  const d = draft.value[r.key];
  if (!d) return false;
  const def = r.default_thresholds || r.thresholds;
  const thrDiff = d.thr.map((s) => fromInput(r, s)).some((v, i) => v == null || Math.abs(v - def[i]) > 1e-9);
  const enDiff = d.enabled !== defEnabled(r);
  const wDiff = Math.abs(Number(String(d.weight).replace(",", ".")) - defWeight(r)) > 1e-9;
  return thrDiff || enDiff || wDiff;
}
function resetRow(r: SoeRatioMeta) {
  draft.value[r.key] = {
    thr: (r.default_thresholds || r.thresholds).map((t) => toInput(r, t)),
    enabled: defEnabled(r),
    weight: String(defWeight(r)),
  };
}
function resetAll() {
  for (const r of props.ratios) resetRow(r);
}

async function save() {
  if (saving.value || hasErrors.value) return;
  const overrides: Record<string, { thresholds?: number[]; enabled?: boolean; weight?: number }> = {};
  for (const r of props.ratios) {
    const d = draft.value[r.key];
    if (!d) continue;
    const o: { thresholds?: number[]; enabled?: boolean; weight?: number } = {};
    const vals = d.thr.map((s) => fromInput(r, s)) as number[];
    const def = r.default_thresholds || r.thresholds;
    if (vals.some((v, i) => Math.abs(v - def[i]) > 1e-9)) o.thresholds = vals;
    if (d.enabled !== defEnabled(r)) o.enabled = d.enabled;
    const w = Number(String(d.weight).replace(",", "."));
    if (Math.abs(w - defWeight(r)) > 1e-9) o.weight = w;
    if (Object.keys(o).length) overrides[r.key] = o;
  }
  saving.value = true;
  try {
    await api.put("/financials/soe-health/params", { overrides });
    toast.success(Object.keys(overrides).length
      ? t("Показатели сохранены ({n} настроено)", { n: Object.keys(overrides).length })
      : t("Сброшено к методике"));
    initial = JSON.stringify(draft.value);
    emit("saved");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t("Не сохранено: {e}", { e: err?.response?.data?.detail || err?.message || t("ошибка") }));
  } finally { saving.value = false; }
}

const BAND_COLORS = ["#1D9E75", "#7DC4A0", "#EF9F27", "#E8590C"];
</script>

<template>
  <ModalShell :open="open" size="lg" :dirty="dirty" @close="emit('close')">
    <template #header>
      <div class="spm-head">
        <div class="spm-eyebrow">SOE Health Check Tool</div>
        <h2 class="spm-title">{{ t("Показатели риска") }}</h2>
        <div class="spm-sub">{{ t("пороги бендов 1→5 · выбор индикаторов в Overall · веса") }}</div>
      </div>
    </template>

    <div class="spm-body">
      <div class="spm-legend">
        <span v-for="(c, i) in BAND_COLORS" :key="i" class="spm-leg" :style="{ color: c, background: c + '16' }">
          {{ t("порог {n}", { n: i + 1 }) }}
        </span>
        <span class="spm-leg-note">{{ t("☑ — в оценке Overall · вес — доля индикатора · лучше ≥ убыв. · лучше ≤ возр.") }}</span>
      </div>

      <div v-for="g in groups" :key="g.name" class="spm-group">
        <div class="spm-group-t">{{ g.name }}</div>
        <div v-for="r in g.items" :key="r.key" class="spm-row"
             :class="{ err: rowError(r), off: draft[r.key] && !draft[r.key].enabled }">
          <div class="spm-r-info">
            <input v-if="draft[r.key]" type="checkbox" class="spm-chk" v-model="draft[r.key].enabled"
                   :title="draft[r.key].enabled ? t('Учитывается в Overall') : t('Исключён из Overall')" />
            <span class="spm-r-label" :title="r.formula">{{ r.label }}</span>
            <span class="spm-r-dir">{{ r.direction === 'gte' ? t('лучше ≥') : t('лучше ≤') }}</span>
            <span v-if="isRowOverridden(r)" class="spm-r-ovr">{{ t("настроено") }}</span>
            <span v-if="draft[r.key]" class="spm-wwrap" :class="{ off: !draft[r.key].enabled }">
              {{ t("вес") }}
              <input type="text" inputmode="decimal" class="spm-w" v-model="draft[r.key].weight"
                     :disabled="!draft[r.key].enabled" :aria-label="r.label + ' ' + t('вес')" />
            </span>
          </div>
          <div class="spm-r-inputs">
            <input v-for="(s, i) in draft[r.key].thr" :key="i" v-model="draft[r.key].thr[i]"
                   type="text" inputmode="decimal" class="spm-inp"
                   :style="{ borderColor: BAND_COLORS[i] + '66' }"
                   :aria-label="r.label + ' ' + t('порог {n}', { n: i + 1 })" />
            <span v-if="r.fmt === 'pct'" class="spm-unit">%</span>
            <span v-else-if="r.fmt === 'days'" class="spm-unit">{{ t("дн") }}</span>
            <button type="button" class="spm-reset" :title="t('Сбросить к методике')"
                    :disabled="!isRowOverridden(r)" @click="resetRow(r)">↺</button>
          </div>
          <div v-if="rowError(r)" class="spm-r-err">{{ rowError(r) }}</div>
        </div>
      </div>
    </div>

    <template #footer>
      <span class="spm-summary">{{ t("в оценке {n} · Σ весов {s}", { n: enabledCount, s: activeWeightSum.toFixed(1) }) }}</span>
      <button class="spm-resetall" type="button" @click="resetAll">{{ t("Сбросить к методике") }}</button>
      <button class="spm-cancel" type="button" @click="emit('close')">{{ t("Отмена") }}</button>
      <button class="spm-save" type="button" :disabled="!dirty || hasErrors || saving" @click="save">
        {{ saving ? t("Сохранение…") : t("Сохранить") }}
      </button>
    </template>
  </ModalShell>
</template>

<style scoped>
.spm-head { display: flex; flex-direction: column; gap: 2px; }
.spm-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--t3, #94A3B8); }
.spm-title { font-size: 16px; font-weight: 600; margin: 2px 0 0; color: var(--t1, #1E2A4A); }
.spm-sub { font-size: 11px; color: var(--t3, #94A3B8); }

.spm-body { display: flex; flex-direction: column; gap: 14px; }
.spm-legend { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.spm-leg { font-size: 9.5px; font-weight: 700; border-radius: 6px; padding: 2px 8px; }
.spm-leg-note { margin-left: auto; font-size: 10px; color: var(--t3, #94A3B8); font-style: italic; }

.spm-group-t { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--p-deep, #534AB7); margin-bottom: 7px; }
.spm-row { padding: 8px 10px; border-radius: 10px; transition: background .14s; animation: spmRowIn .35s ease both; }
@keyframes spmRowIn { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: translateY(0); } }
.spm-row:hover { background: var(--bg2, #FAFAFD); }
.spm-row.err { background: rgba(226,75,74,.05); }
.spm-row.off { opacity: .58; }
.spm-r-info { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.spm-chk { width: 15px; height: 15px; accent-color: var(--brand, #6C5CE7); cursor: pointer; flex-shrink: 0; }
.spm-wwrap { margin-left: auto; font-size: 9.5px; font-weight: 600; color: var(--t3, #94A3B8);
  display: inline-flex; align-items: center; gap: 5px; text-transform: uppercase; letter-spacing: .04em; }
.spm-wwrap.off { opacity: .5; }
.spm-w { width: 46px; box-sizing: border-box; font-size: 12px; font-family: inherit; text-align: center;
  color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; padding: 4px; border: 1.5px solid var(--border, #ECEAF5);
  border-radius: 7px; outline: none; background: var(--bg1, #fff); transition: box-shadow .14s, border-color .14s; }
.spm-w:focus { box-shadow: 0 0 0 3px rgba(124,111,247,.14); border-color: var(--brand, #6C5CE7); }
.spm-w:disabled { opacity: .4; cursor: not-allowed; }
.spm-r-label { font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A); cursor: help; border-bottom: 1px dashed rgba(148,163,184,.5); }
.spm-r-dir { font-size: 9.5px; font-weight: 600; color: var(--t3, #94A3B8); }
.spm-r-ovr { font-size: 8.5px; font-weight: 700; color: #B45309; background: rgba(239,159,39,.16); border-radius: 5px; padding: 1px 6px; }
.spm-r-inputs { display: flex; align-items: center; gap: 6px; }
.spm-inp {
  width: 74px; box-sizing: border-box; font-size: 12.5px; font-family: inherit;
  color: var(--t1, #1E2A4A); text-align: center; font-variant-numeric: tabular-nums;
  padding: 6px 6px; border: 1.5px solid var(--border, #ECEAF5); border-radius: 8px;
  outline: none; background: var(--bg1, #fff); transition: box-shadow .14s, border-color .14s;
}
.spm-inp:focus { box-shadow: 0 0 0 3px rgba(124,111,247,.14); border-color: var(--brand, #6C5CE7) !important; }
.spm-unit { font-size: 10.5px; color: var(--t3, #94A3B8); font-weight: 600; }
.spm-reset {
  margin-left: auto; width: 26px; height: 26px; border-radius: 8px; border: 1px solid var(--border, #ECEAF5);
  background: #fff; color: var(--t3, #94A3B8); font-size: 13px; cursor: pointer; transition: all .14s;
}
.spm-reset:hover:not(:disabled) { color: var(--brand, #6C5CE7); border-color: rgba(124,111,247,.4); }
.spm-reset:disabled { opacity: .35; cursor: default; }
.spm-r-err { font-size: 10px; color: #E24B4A; font-weight: 600; margin-top: 4px; }

.spm-summary { font-size: 11px; font-weight: 600; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; margin-right: 12px; }
.spm-resetall { font-size: 11.5px; font-weight: 600; font-family: inherit; color: var(--t3, #94A3B8); background: transparent; border: 1px dashed var(--border-strong, #D9D7E8); border-radius: 9px; padding: 8px 13px; cursor: pointer; margin-right: auto; transition: all .14s; }
.spm-resetall:hover { color: #E24B4A; border-color: #F3C3C2; }
.spm-cancel { font-size: 12.5px; font-weight: 600; font-family: inherit; color: var(--t2, #4B5468); background: transparent; border: 1px solid var(--border-hard, #E5E7EB); border-radius: 10px; padding: 9px 18px; cursor: pointer; }
.spm-save {
  font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); border: none; border-radius: 10px;
  padding: 9px 22px; cursor: pointer; box-shadow: 0 3px 12px rgba(108,92,231,.34);
  transition: transform .14s, box-shadow .14s, opacity .14s;
}
.spm-save:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108,92,231,.45); }
.spm-save:disabled { opacity: .5; cursor: default; box-shadow: none; }
</style>
