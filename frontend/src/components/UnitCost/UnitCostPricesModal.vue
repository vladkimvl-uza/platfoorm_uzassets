<script setup lang="ts">
/**
 * UnitCostPricesModal — редактор цен энергоносителей (глобальные, применяются
 * ко всем компаниям при расчёте энергозатрат). Dirty-guard, тосты, анимации.
 */
import { computed, ref, watch } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { useToast } from "@/composables/useToast";
import { unitCostApi, FUELS, type UCPrices } from "@/api/unitCost";

const props = defineProps<{ open: boolean; prices: UCPrices; fuelLabels: Record<string, string> }>();
const emit = defineEmits<{ (e: "close"): void; (e: "saved"): void }>();
const toast = useToast();

const FUEL_UNIT: Record<string, string> = {
  electricity: "сум/кВт·ч", gas: "сум/м³", diesel: "сум/т", mazut: "сум/т", coal: "сум/т", kerosene: "сум/т",
};
const FUEL_ICON: Record<string, string> = {
  electricity: "⚡", gas: "🔥", diesel: "🛢", mazut: "🛢", coal: "⬛", kerosene: "✈",
};

const draft = ref<Record<string, string>>({});
const saving = ref(false);
let initial = "";

function init() {
  const d: Record<string, string> = {};
  for (const f of FUELS) d[f] = props.prices?.[f]?.price != null ? String(props.prices[f].price) : "";
  draft.value = d;
  initial = JSON.stringify(d);
}
watch(() => props.open, (o) => { if (o) init(); }, { immediate: true });
const dirty = computed(() => JSON.stringify(draft.value) !== initial);

function num(v: unknown): number | null { const n = Number(String(v ?? "").replace(",", ".")); return isFinite(n) ? n : null; }
function rowError(f: string): boolean { const n = num(draft.value[f]); return draft.value[f] !== "" && (n == null || n < 0); }
const hasErr = computed(() => FUELS.some((f) => rowError(f)));

async function save() {
  if (saving.value || hasErr.value) return;
  const prices: UCPrices = {};
  for (const f of FUELS) {
    const n = num(draft.value[f]);
    if (n != null && n >= 0) prices[f] = { price: n, unit: FUEL_UNIT[f] };
  }
  saving.value = true;
  try {
    await unitCostApi.savePrices(prices);
    toast.success("Цены энергоносителей сохранены");
    initial = JSON.stringify(draft.value);
    emit("saved");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не сохранено: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally { saving.value = false; }
}
</script>

<template>
  <ModalShell :open="open" size="md" :dirty="dirty" @close="emit('close')">
    <template #header>
      <div class="ucp-head">
        <div class="ucp-eyebrow">Удельная себестоимость</div>
        <h2 class="ucp-title">Цены энергоносителей</h2>
        <div class="ucp-sub">применяются ко всем компаниям при расчёте энергозатрат</div>
      </div>
    </template>

    <div class="ucp-body">
      <div v-for="(f, i) in FUELS" :key="f" class="ucp-row" :class="{ err: rowError(f) }"
           :style="{ '--d': (i * 55) + 'ms' }">
        <span class="ucp-ico">{{ FUEL_ICON[f] }}</span>
        <span class="ucp-label">{{ fuelLabels[f] || f }}</span>
        <div class="ucp-inwrap">
          <input v-model="draft[f]" type="text" inputmode="decimal" class="ucp-inp" placeholder="—"
                 :aria-label="fuelLabels[f]" />
          <span class="ucp-unit">{{ FUEL_UNIT[f] }}</span>
        </div>
      </div>
      <div class="ucp-note">Единицы: электроэнергия — кВт·ч, газ — м³, жидкое топливо и уголь — тонна (согласовано с удельными нормами).</div>
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
.ucp-row { display: grid; grid-template-columns: 30px 1fr 200px; align-items: center; gap: 12px;
  padding: 9px 11px; border-radius: 11px; background: var(--bg2,#FAFAFD); transition: background .14s;
  animation: ucpRowIn .38s var(--ease-standard,ease) var(--d,0ms) both; }
@keyframes ucpRowIn { from { opacity: 0; transform: translateX(-5px); } to { opacity: 1; transform: translateX(0); } }
.ucp-row:hover { background: #F3F1FC; }
.ucp-row.err { background: rgba(226,75,74,.05); }
.ucp-ico { font-size: 15px; text-align: center; }
.ucp-label { font-size: 12.5px; font-weight: 600; color: var(--t1,#1E2A4A); }
.ucp-inwrap { display: flex; align-items: center; gap: 8px; }
.ucp-inp { flex: 1; min-width: 0; box-sizing: border-box; font-size: 13px; font-family: inherit; text-align: right;
  color: var(--t1,#1E2A4A); font-variant-numeric: tabular-nums; padding: 8px 10px; border: 1.5px solid var(--border,#ECEAF5);
  border-radius: 9px; outline: none; background: #fff; transition: box-shadow .14s, border-color .14s; }
.ucp-inp:focus { box-shadow: 0 0 0 3px rgba(124,111,247,.14); border-color: var(--brand,#6C5CE7); }
.ucp-unit { font-size: 10px; color: var(--t3,#94A3B8); font-weight: 600; white-space: nowrap; min-width: 48px; }
.ucp-note { font-size: 10px; color: var(--t3,#94A3B8); font-style: italic; margin-top: 4px; line-height: 1.4; }

.ucp-cancel { font-size: 12.5px; font-weight: 600; font-family: inherit; color: var(--t2,#4B5468); background: transparent;
  border: 1px solid var(--border-hard,#E5E7EB); border-radius: 10px; padding: 9px 18px; cursor: pointer; margin-left: auto; }
.ucp-save { font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg,#8B7FFF 0%,#6C5CE7 100%); border: none; border-radius: 10px; padding: 9px 22px; cursor: pointer;
  box-shadow: 0 3px 12px rgba(108,92,231,.34); transition: transform .14s, box-shadow .14s, opacity .14s; }
.ucp-save:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108,92,231,.45); }
.ucp-save:disabled { opacity: .5; cursor: default; box-shadow: none; }
</style>
