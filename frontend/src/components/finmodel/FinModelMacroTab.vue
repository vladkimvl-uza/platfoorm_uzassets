<script setup lang="ts">
/**
 * FinModelMacroTab — grid редактор макро-параметров для активного года.
 *
 * 6 полей × 1 год. Показывает global default + company override (если есть).
 * На blur → PUT /finmodel/{co}/{year}/macro
 *
 * Multi-year редактирование пока не делаю — backend на каждый PUT возвращает
 * effective state одного года, поэтому grid layout под (год × поле) надо
 * грузить отдельным fetch'ем на каждый год. Это в следующем handoff.
 */
import { computed, ref, watch } from "vue";
import { finmodelApi, type MacroEffective, type MacroCompanyPayload, type MacroGlobal } from "@/api/finmodel";

const props = defineProps<{
  companyId: string;
  year: number | null;
  /** loaded macro for the active year — passed in by parent to avoid re-fetch */
  macro: MacroEffective | null;
}>();

const emit = defineEmits<{
  "macro-changed": [];
}>();

const global = ref<MacroGlobal[]>([]);
const saving = ref(false);
const saveError = ref<string | null>(null);

// Local editing buffer — populated from props.macro
interface Buf {
  uz_inflation: string;
  us_inflation: string;
  uzs_usd_avg_rate: string;
  uzs_eur_avg_rate: string;
  uzs_rub_avg_rate: string;
  uzs_cny_avg_rate: string;
}
const buf = ref<Buf>({
  uz_inflation: "",
  us_inflation: "",
  uzs_usd_avg_rate: "",
  uzs_eur_avg_rate: "",
  uzs_rub_avg_rate: "",
  uzs_cny_avg_rate: "",
});

function syncBuf() {
  const m = props.macro;
  buf.value = {
    uz_inflation: m?.uz_inflation ?? "",
    us_inflation: m?.us_inflation ?? "",
    uzs_usd_avg_rate: m?.uzs_usd_avg_rate ?? "",
    uzs_eur_avg_rate: m?.uzs_eur_avg_rate ?? "",
    uzs_rub_avg_rate: m?.uzs_rub_avg_rate ?? "",
    uzs_cny_avg_rate: m?.uzs_cny_avg_rate ?? "",
  };
}
watch(() => props.macro, syncBuf, { immediate: true });

async function ensureGlobal() {
  if (global.value.length > 0) return;
  try {
    global.value = await finmodelApi.listMacroGlobal();
  } catch { /* silent — global override is optional context */ }
}
watch(() => props.companyId, ensureGlobal, { immediate: true });

const globalForYear = computed(() =>
  props.year ? global.value.find(g => g.year === props.year) : undefined
);

interface FieldSpec {
  key: keyof Buf;
  label: string;
  unit: string;
  step: string;
}
const FIELDS: FieldSpec[] = [
  { key: "uz_inflation",     label: "Инфляция UZ",      unit: "ratio (0.1 = 10%)", step: "0.001" },
  { key: "us_inflation",     label: "Инфляция US",      unit: "ratio",              step: "0.001" },
  { key: "uzs_usd_avg_rate", label: "UZS / USD avg",    unit: "сум за 1 USD",       step: "1" },
  { key: "uzs_eur_avg_rate", label: "UZS / EUR avg",    unit: "сум за 1 EUR",       step: "1" },
  { key: "uzs_rub_avg_rate", label: "UZS / RUB avg",    unit: "сум за 1 RUB",       step: "0.01" },
  { key: "uzs_cny_avg_rate", label: "UZS / CNY avg",    unit: "сум за 1 CNY",       step: "0.01" },
];

function sourceFor(key: keyof Buf): "company" | "global" | "none" {
  return (props.macro?.source as any)?.[key] ?? "none";
}
function globalDefault(key: keyof Buf): string | null {
  const g = globalForYear.value as any;
  return g ? (g[key] as string | null) : null;
}

async function commitField(key: keyof Buf, raw: string) {
  if (!props.companyId || !props.year) return;
  const cleaned = raw.replace(",", ".").trim();
  // If empty, treat as null (clears company override)
  const value = cleaned === "" ? null : cleaned;
  saveError.value = null;
  saving.value = true;
  try {
    const payload: MacroCompanyPayload = { [key]: value } as MacroCompanyPayload;
    await finmodelApi.putMacro(props.companyId, props.year, payload);
    emit("macro-changed");
  } catch (e: any) {
    saveError.value = e?.response?.data?.detail || e?.message || "Сохранение не удалось";
  } finally {
    saving.value = false;
  }
}

function onBlur(key: keyof Buf, e: Event) {
  const target = e.target as HTMLInputElement;
  void commitField(key, target.value);
}
</script>

<template>
  <section class="fm-macro">
    <header class="fm-macro-head">
      <span class="fm-macro-cap">Макро-предположения {{ year ? `· ${year}` : "" }}</span>
      <span v-if="saving" class="fm-macro-saving">Сохраняем…</span>
      <span v-else-if="saveError" class="fm-macro-err">{{ saveError }}</span>
    </header>

    <div v-if="!companyId || !year" class="fm-macro-empty">
      Выберите компанию и год.
    </div>
    <table v-else class="fm-macro-tbl">
      <thead>
        <tr>
          <th class="fm-mh-lbl">Параметр</th>
          <th class="fm-mh-val">Значение</th>
          <th class="fm-mh-src">Источник</th>
          <th class="fm-mh-gl">Global default</th>
          <th class="fm-mh-unit">Единица</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in FIELDS" :key="f.key">
          <td class="fm-m-lbl">{{ f.label }}</td>
          <td class="fm-m-val">
            <input
              type="text"
              class="fm-m-input"
              inputmode="decimal"
              :value="buf[f.key]"
              :step="f.step"
              :placeholder="globalDefault(f.key) ?? '—'"
              @blur="onBlur(f.key, $event)"
              @keydown.enter.prevent="($event.target as HTMLInputElement).blur()"
            />
          </td>
          <td class="fm-m-src">
            <span :class="['fm-src-pill', `fm-src-${sourceFor(f.key)}`]">{{ sourceFor(f.key) }}</span>
          </td>
          <td class="fm-m-gl">{{ globalDefault(f.key) ?? "—" }}</td>
          <td class="fm-m-unit">{{ f.unit }}</td>
        </tr>
      </tbody>
    </table>
    <div v-if="companyId && year" class="fm-macro-hint">
      Пустое значение очищает per-company override — будет использоваться global default.
    </div>
  </section>
</template>

<style scoped>
.fm-macro { padding: 16px 18px; }
.fm-macro-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 12px;
}
.fm-macro-cap {
  font-size: 10px;
  font-weight: 500;
  color: #888780;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.fm-macro-saving { font-size: 10.5px; color: #EF9F27; font-weight: 500; }
.fm-macro-err { font-size: 10.5px; color: #C0322F; font-weight: 500; }

.fm-macro-empty {
  padding: 28px 12px;
  text-align: center;
  font-size: 11px;
  color: #888780;
  font-style: italic;
}

.fm-macro-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}
.fm-macro-tbl th {
  text-align: left;
  padding: 8px 12px;
  background: #FAFAFC;
  border-bottom: 0.5px solid #E5E7EB;
  font-size: 9.5px;
  font-weight: 500;
  color: #888780;
  text-transform: uppercase;
  letter-spacing: .06em;
}
.fm-macro-tbl td {
  padding: 6px 12px;
  border-bottom: 0.5px solid #F1EFE8;
  color: #1E2A4A;
}
.fm-mh-val, .fm-mh-gl { text-align: right; }
.fm-m-val, .fm-m-gl { text-align: right; font-variant-numeric: tabular-nums; }
.fm-m-unit { color: #888780; font-size: 10.5px; }

.fm-m-input {
  width: 140px;
  padding: 3px 8px;
  border-radius: 4px;
  background: rgba(55, 138, 221, .05);
  border: 0.5px solid rgba(55, 138, 221, .25);
  text-align: right;
  font-family: inherit;
  font-size: 11px;
  color: #1E2A4A;
  font-variant-numeric: tabular-nums;
  outline: none;
}
.fm-m-input:focus {
  background: #fff;
  border-color: #378ADD;
  box-shadow: 0 0 0 3px rgba(55, 138, 221, .15);
}

.fm-src-pill {
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 9.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.fm-src-company { background: rgba(127, 119, 221, .12); color: #534AB7; }
.fm-src-global  { background: rgba(55, 138, 221, .10); color: #1F5A99; }
.fm-src-none    { background: rgba(136, 135, 128, .10); color: #888780; }

.fm-macro-hint {
  margin-top: 14px;
  font-size: 10.5px;
  color: #888780;
  font-style: italic;
}
</style>
