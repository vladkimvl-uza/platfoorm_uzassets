<script setup lang="ts">
/**
 * UnitCostPricesModal — курс USD + мировые ориентиры (Brent, золото, медь) и
 * цены энергоносителей. Цену можно задать в сумах напрямую ИЛИ в USD (тогда
 * эффективная цена = USD × курс, пересчёт в реальном времени). Dirty-guard.
 */
import { computed, ref, watch } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { useToast } from "@/composables/useToast";
import { unitCostApi, FUELS, type UCPrices, type UCWorld } from "@/api/unitCost";

const props = defineProps<{ open: boolean; prices: UCPrices; world: UCWorld | null; fuelLabels: Record<string, string> }>();
const emit = defineEmits<{ (e: "close"): void; (e: "saved"): void }>();
const toast = useToast();

const FUEL_UNIT: Record<string, string> = {
  electricity: "сум/кВт·ч", gas: "сум/м³", diesel: "сум/т", mazut: "сум/т", coal: "сум/т", kerosene: "сум/т",
};
const FUEL_USD_UNIT: Record<string, string> = {
  electricity: "$/кВт·ч", gas: "$/м³", diesel: "$/т", mazut: "$/т", coal: "$/т", kerosene: "$/т",
};
const FUEL_COLOR: Record<string, string> = {
  electricity: "#EF9F27", gas: "#378ADD", diesel: "#E24B4A", mazut: "#8B7FFF", coal: "#4B5468", kerosene: "#1D9E75",
};
const WORLD = [
  { key: "usd_rate", label: "Курс USD / сум", unit: "сум за $1" },
  { key: "brent", label: "Brent", unit: "$ / баррель" },
  { key: "gold", label: "Золото", unit: "$ / унция" },
  { key: "copper", label: "Медь", unit: "$ / тонна" },
] as const;

const pdraft = ref<Record<string, { price: string; usd: string }>>({});
const wdraft = ref<Record<string, string>>({});
const saving = ref(false);
let initial = "";

function init() {
  const pd: Record<string, { price: string; usd: string }> = {};
  for (const f of FUELS) {
    const e = props.prices?.[f] || {};
    pd[f] = { price: e.price != null ? String(e.price) : "", usd: e.usd != null ? String(e.usd) : "" };
  }
  const wd: Record<string, string> = {};
  for (const w of WORLD) wd[w.key] = props.world?.[w.key] != null ? String(props.world[w.key]) : "";
  pdraft.value = pd; wdraft.value = wd;
  initial = JSON.stringify({ p: pd, w: wd });
}
watch(() => props.open, (o) => { if (o) init(); }, { immediate: true });
const dirty = computed(() => JSON.stringify({ p: pdraft.value, w: wdraft.value }) !== initial);

function num(v: unknown): number | null { const n = Number(String(v ?? "").replace(",", ".")); return isFinite(n) ? n : null; }
const usdRate = computed(() => num(wdraft.value.usd_rate) || 0);
// эффективная цена (сум): USD×курс если задан USD, иначе прямая
function effective(f: string): number | null {
  const d = pdraft.value[f]; if (!d) return null;
  const u = num(d.usd);
  if (u != null && u > 0 && usdRate.value) return u * usdRate.value;
  return num(d.price);
}
function priceErr(f: string): boolean {
  const d = pdraft.value[f]; if (!d) return false;
  const p = num(d.price), u = num(d.usd);
  return (d.price !== "" && (p == null || p < 0)) || (d.usd !== "" && (u == null || u < 0));
}
const hasErr = computed(() => FUELS.some((f) => priceErr(f)) ||
  WORLD.some((w) => wdraft.value[w.key] !== "" && (num(wdraft.value[w.key]) == null || num(wdraft.value[w.key])! < 0)));
function fmt(v: number | null): string { return v == null ? "—" : v.toLocaleString("ru", { maximumFractionDigits: 0 }); }

async function save() {
  if (saving.value || hasErr.value) return;
  const prices: UCPrices = {};
  for (const f of FUELS) {
    const d = pdraft.value[f]; const p = num(d.price), u = num(d.usd);
    const entry: { price?: number; unit: string; usd?: number } = { unit: FUEL_UNIT[f] };
    if (p != null && p >= 0) entry.price = p;
    entry.usd = u != null && u >= 0 ? u : 0;
    prices[f] = entry;
  }
  const w: Partial<UCWorld> = {};
  for (const it of WORLD) { const v = num(wdraft.value[it.key]); if (v != null && v >= 0) (w as Record<string, number>)[it.key] = v; }
  saving.value = true;
  try {
    await unitCostApi.savePrices(prices, w);
    toast.success("Цены и курсы сохранены");
    initial = JSON.stringify({ p: pdraft.value, w: wdraft.value });
    emit("saved");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не сохранено: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally { saving.value = false; }
}
</script>

<template>
  <ModalShell :open="open" size="lg" :dirty="dirty" @close="emit('close')">
    <template #header>
      <div class="ucp-head">
        <div class="ucp-eyebrow">Удельная себестоимость</div>
        <h2 class="ucp-title">Курс, мировые цены и энергоносители</h2>
        <div class="ucp-sub">курс USD влияет на все цены, заданные в долларах — пересчёт мгновенный</div>
      </div>
    </template>

    <div class="ucp-body">
      <!-- Мировые ориентиры -->
      <div class="ucp-block-t">Курс и мировые ориентиры</div>
      <div class="ucp-world">
        <div v-for="w in WORLD" :key="w.key" class="ucp-w">
          <div class="ucp-w-l">{{ w.label }}</div>
          <input v-model="wdraft[w.key]" type="text" inputmode="decimal" class="ucp-inp ucp-inp-c" placeholder="—" />
          <div class="ucp-w-u">{{ w.unit }}</div>
        </div>
      </div>

      <!-- Энергоносители -->
      <div class="ucp-block-t">Цены энергоносителей <span>в сумах напрямую или в USD (тогда × курс)</span></div>
      <div class="ucp-head-row">
        <span></span><span>Цена, сум</span><span>или USD</span><span>Итог, сум</span>
      </div>
      <div v-for="(f, i) in FUELS" :key="f" class="ucp-row" :class="{ err: priceErr(f) }" :style="{ '--d': (i * 45) + 'ms' }">
        <span class="ucp-label"><i :style="{ background: FUEL_COLOR[f] }" />{{ fuelLabels[f] || f }}</span>
        <div class="ucp-inwrap">
          <input v-model="pdraft[f].price" type="text" inputmode="decimal" class="ucp-inp ucp-inp-c"
                 :disabled="!!num(pdraft[f].usd)" placeholder="—" />
          <span class="ucp-u">{{ FUEL_UNIT[f] }}</span>
        </div>
        <div class="ucp-inwrap">
          <input v-model="pdraft[f].usd" type="text" inputmode="decimal" class="ucp-inp ucp-inp-c" placeholder="—" />
          <span class="ucp-u">{{ FUEL_USD_UNIT[f] }}</span>
        </div>
        <span class="ucp-eff" :class="{ usd: !!num(pdraft[f].usd) }">{{ fmt(effective(f)) }}</span>
      </div>
      <div class="ucp-note">Единицы: электроэнергия — кВт·ч, газ — м³, жидкое топливо и уголь — тонна. Задайте цену в USD, чтобы она автоматически пересчитывалась по курсу.</div>
    </div>

    <template #footer>
      <button class="ucp-cancel" type="button" @click="emit('close')">Отмена</button>
      <button class="ucp-save" type="button" :disabled="!dirty || hasErr || saving" @click="save">
        {{ saving ? "Сохранение…" : "Сохранить" }}
      </button>
    </template>
  </ModalShell>
</template>

<style scoped>
.ucp-head { display: flex; flex-direction: column; gap: 2px; }
.ucp-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--t3,#94A3B8); }
.ucp-title { font-size: 16px; font-weight: 600; margin: 2px 0 0; color: var(--t1,#1E2A4A); }
.ucp-sub { font-size: 11px; color: var(--t3,#94A3B8); }

.ucp-body { display: flex; flex-direction: column; gap: 8px; }
.ucp-block-t { display: flex; align-items: baseline; gap: 8px; font-size: 10.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; color: var(--p-deep,#534AB7); margin: 6px 0 4px; }
.ucp-block-t span { font-weight: 500; text-transform: none; letter-spacing: 0; color: var(--t3,#94A3B8); font-size: 10px; }

.ucp-world { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 6px; }
@media (max-width: 640px) { .ucp-world { grid-template-columns: repeat(2, 1fr); } }
.ucp-w { display: flex; flex-direction: column; gap: 4px; background: var(--bg2,#FAFAFD); border-radius: 10px; padding: 9px 11px; }
.ucp-w-l { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t3,#94A3B8); }
.ucp-w-u { font-size: 8.5px; color: var(--t3,#94A3B8); }

.ucp-head-row, .ucp-row { display: grid; grid-template-columns: 1.3fr 1fr 1fr 90px; align-items: center; gap: 10px; }
.ucp-head-row { padding: 0 4px 5px; border-bottom: 0.5px solid rgba(0,0,0,.06); }
.ucp-head-row span { font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em; color: var(--t3,#94A3B8); text-align: right; }
.ucp-head-row span:first-child { text-align: left; }
.ucp-row { padding: 7px 4px; border-radius: 9px; transition: background .14s; animation: ucpRowIn .38s var(--ease-standard,ease) var(--d,0ms) both; }
@keyframes ucpRowIn { from { opacity: 0; transform: translateX(-5px); } to { opacity: 1; transform: translateX(0); } }
.ucp-row:hover { background: var(--bg2,#FAFAFD); }
.ucp-row.err { background: rgba(226,75,74,.05); }
.ucp-label { display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; color: var(--t1,#1E2A4A); }
.ucp-label i { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.ucp-inwrap { display: flex; align-items: center; gap: 6px; }
.ucp-inp { flex: 1; min-width: 0; box-sizing: border-box; font-size: 12.5px; font-family: inherit; color: var(--t1,#1E2A4A);
  padding: 7px 9px; border: 1.5px solid var(--border,#ECEAF5); border-radius: 8px; outline: none; background: #fff;
  transition: box-shadow .14s, border-color .14s; }
.ucp-inp-c { text-align: right; font-variant-numeric: tabular-nums; }
.ucp-inp:focus { box-shadow: 0 0 0 3px rgba(124,111,247,.14); border-color: var(--brand,#6C5CE7); }
.ucp-inp:disabled { opacity: .45; background: var(--bg2,#FAFAFD); }
.ucp-u { font-size: 8.5px; color: var(--t3,#94A3B8); font-weight: 600; white-space: nowrap; }
.ucp-eff { text-align: right; font-size: 12px; font-weight: 700; color: var(--t1,#1E2A4A); font-variant-numeric: tabular-nums; }
.ucp-eff.usd { color: #1D9E75; }
.ucp-note { font-size: 10px; color: var(--t3,#94A3B8); font-style: italic; margin-top: 4px; line-height: 1.4; }

.ucp-cancel { font-size: 12.5px; font-weight: 600; font-family: inherit; color: var(--t2,#4B5468); background: transparent;
  border: 1px solid var(--border-hard,#E5E7EB); border-radius: 10px; padding: 9px 18px; cursor: pointer; margin-left: auto; }
.ucp-save { font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg,#8B7FFF 0%,#6C5CE7 100%); border: none; border-radius: 10px; padding: 9px 22px; cursor: pointer;
  box-shadow: 0 3px 12px rgba(108,92,231,.34); transition: transform .14s, box-shadow .14s, opacity .14s; }
.ucp-save:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108,92,231,.45); }
.ucp-save:disabled { opacity: .5; cursor: default; box-shadow: none; }
</style>
