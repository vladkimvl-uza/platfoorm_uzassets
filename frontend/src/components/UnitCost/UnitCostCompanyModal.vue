<script setup lang="ts">
/**
 * UnitCostCompanyModal — редактор продуктов компании: годовой выпуск, удельный
 * расход энергоресурсов (предзаполнен), прочие статьи себестоимости. Живой
 * расчёт удельной себестоимости и доли энергии. Dirty-guard, тосты, анимации.
 */
import { computed, ref, watch } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { useToast } from "@/composables/useToast";
import { unitCostApi, FUELS, type UCCompany, type UCPrices, type UCWorld,
         type EditProduct, type EditImport } from "@/api/unitCost";

const props = defineProps<{
  open: boolean; company: UCCompany | null;
  prices: UCPrices; world: UCWorld | null; fuelLabels: Record<string, string>;
}>();
const emit = defineEmits<{ (e: "close"): void; (e: "saved"): void }>();
const toast = useToast();

const FUEL_UNIT: Record<string, string> = {
  electricity: "кВт·ч/ед", gas: "м³/ед", diesel: "т/ед", mazut: "т/ед", coal: "т/ед", kerosene: "т/ед",
};

const draft = ref<EditProduct[]>([]);
const imports = ref<EditImport[]>([]);
const saving = ref(false);
let initial = "";

function toEdit(c: UCCompany): EditProduct[] {
  return (c.products || []).map((p) => ({
    name: p.name, unit: p.unit, output: p.output,
    energy: { ...(p.energy || {}) },
    components: (p.components || []).map((x) => ({ name: x.name, value: x.value })),
  }));
}
function init() {
  draft.value = props.company ? toEdit(props.company) : [];
  imports.value = (props.company?.imports || []).map((it) => ({ name: it.name, unit: it.unit, usd: it.usd, qty: it.qty }));
  initial = JSON.stringify({ p: draft.value, i: imports.value });
}
watch(() => props.open, (o) => { if (o) init(); }, { immediate: true });
const dirty = computed(() => JSON.stringify({ p: draft.value, i: imports.value }) !== initial);

function num(v: unknown): number { const n = Number(String(v ?? "").replace(",", ".")); return isFinite(n) ? n : 0; }
const usdRate = computed(() => num(props.world?.usd_rate));
// эффективная цена энергоносителя (сум): USD×курс если задан USD, иначе прямая
function priceOf(fuel: string): number {
  const e = props.prices?.[fuel] || {};
  const usd = num(e.usd);
  if (usd > 0 && usdRate.value) return usd * usdRate.value;
  return num(e.price);
}
// импорт: цена в USD × курс × количество
function importCost(it: EditImport): number { return num(it.usd) * usdRate.value * num(it.qty); }
const importTotal = computed(() => imports.value.reduce((s, it) => s + importCost(it), 0));
function addImport() { imports.value.push({ name: "", unit: "т", usd: 0, qty: 0 }); }
function removeImport(i: number) { imports.value.splice(i, 1); }

// живой расчёт продукта
function calc(p: EditProduct) {
  let energy = 0;
  for (const f of FUELS) {
    const nrm = p.energy[f]; if (nrm == null) continue;
    energy += num(nrm) * priceOf(f);
  }
  const comps = (p.components || []).reduce((s, c) => s + num(c.value), 0);
  const unit = energy + comps;
  return {
    energy, comps, unit,
    share: unit > 0 ? (energy / unit) * 100 : null,
    total: num(p.output) > 0 ? unit * num(p.output) : null,
  };
}
function fmt(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("ru", { maximumFractionDigits: 2 });
}
function shareColor(s: number | null): string {
  if (s == null) return "#9AA0AE";
  return s >= 60 ? "#E24B4A" : s >= 35 ? "#EF9F27" : "#1D9E75";
}

const expanded = ref<number | null>(0);
function toggle(i: number) { expanded.value = expanded.value === i ? null : i; }

function addComponent(p: EditProduct) { p.components.push({ name: "", value: 0 }); }
function removeComponent(p: EditProduct, i: number) { p.components.splice(i, 1); }
function addProduct() {
  draft.value.push({ name: "Новый продукт", unit: "ед.", output: 0, energy: {},
    components: [{ name: "Сырьё и материалы", value: 0 }, { name: "Оплата труда", value: 0 }] });
  expanded.value = draft.value.length - 1;
}
function removeProduct(i: number) {
  draft.value.splice(i, 1);
  if (expanded.value === i) expanded.value = null;
}

async function save() {
  if (saving.value || !props.company) return;
  for (const p of draft.value) {
    if (!p.name.trim()) { toast.error("У продукта пустое название"); return; }
  }
  saving.value = true;
  try {
    await unitCostApi.saveCompany(props.company.code, draft.value, imports.value);
    toast.success("Себестоимость сохранена");
    initial = JSON.stringify({ p: draft.value, i: imports.value });
    emit("saved");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не сохранено: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally { saving.value = false; }
}
</script>

<template>
  <ModalShell :open="open && !!company" size="lg" :dirty="dirty" @close="emit('close')">
    <template v-if="company" #header>
      <div class="ucm-head">
        <div class="ucm-eyebrow">Удельная себестоимость</div>
        <h2 class="ucm-title"><span class="ucm-dot" :style="{ background: company.color }" />{{ company.name }}</h2>
        <div class="ucm-meta">{{ company.sector }} · продуктов: {{ draft.length }}</div>
      </div>
    </template>

    <div v-if="company" class="ucm-body">
      <div v-for="(p, i) in draft" :key="i" class="ucm-prod" :class="{ open: expanded === i }"
           :style="{ '--d': (i * 40) + 'ms' }">
        <!-- шапка продукта -->
        <div class="ucm-prod-hd" @click="toggle(i)">
          <span class="ucm-chevron" :class="{ open: expanded === i }"></span>
          <span class="ucm-prod-name">{{ p.name || 'Без названия' }}</span>
          <span class="ucm-prod-cost">
            {{ fmt(calc(p).unit) }}<span class="ucm-cu">сум/{{ p.unit || 'ед.' }}</span>
          </span>
          <span v-if="calc(p).share != null" class="ucm-prod-share"
                :style="{ color: shareColor(calc(p).share), background: shareColor(calc(p).share) + '16' }">
            энергия {{ calc(p).share!.toFixed(0) }}%
          </span>
        </div>

        <!-- тело -->
        <transition name="ucm-exp">
          <div v-if="expanded === i" class="ucm-prod-body">
            <div class="ucm-row3">
              <label class="ucm-f"><span>Название</span>
                <input v-model="p.name" type="text" class="ucm-inp" /></label>
              <label class="ucm-f ucm-f-sm"><span>Ед. изм.</span>
                <input v-model="p.unit" type="text" class="ucm-inp" /></label>
              <label class="ucm-f ucm-f-sm"><span>Годовой выпуск</span>
                <input v-model.number="p.output" type="text" inputmode="decimal" class="ucm-inp" /></label>
            </div>

            <!-- энергонормы -->
            <div class="ucm-sub">Удельный расход энергоресурсов <span>на единицу продукции</span></div>
            <div class="ucm-energy">
              <div v-for="f in FUELS" :key="f" class="ucm-en">
                <div class="ucm-en-l">{{ fuelLabels[f] || f }}</div>
                <input v-model.number="p.energy[f]" type="text" inputmode="decimal" class="ucm-inp ucm-inp-c"
                       placeholder="—" :aria-label="fuelLabels[f]" />
                <div class="ucm-en-u">{{ FUEL_UNIT[f] }}</div>
                <div class="ucm-en-c">{{ p.energy[f] != null ? fmt(num(p.energy[f]) * priceOf(f)) + ' сум' : '' }}</div>
              </div>
            </div>

            <!-- прочие статьи -->
            <div class="ucm-sub">Прочие статьи себестоимости <span>сум на единицу</span>
              <button type="button" class="ucm-add" @click="addComponent(p)">+ статья</button>
            </div>
            <div class="ucm-comps">
              <div v-for="(c, ci) in p.components" :key="ci" class="ucm-comp">
                <input v-model="c.name" type="text" class="ucm-inp" placeholder="Статья" />
                <input v-model.number="c.value" type="text" inputmode="decimal" class="ucm-inp ucm-inp-c" placeholder="0" />
                <button type="button" class="ucm-del" @click="removeComponent(p, ci)" title="Удалить">✕</button>
              </div>
              <div v-if="!p.components.length" class="ucm-empty">нет статей — добавьте кнопкой «+ статья»</div>
            </div>

            <!-- итог продукта -->
            <div class="ucm-total">
              <div class="ucm-tot-i"><span>Энергозатраты</span><b>{{ fmt(calc(p).energy) }}</b></div>
              <div class="ucm-tot-i"><span>Прочие статьи</span><b>{{ fmt(calc(p).comps) }}</b></div>
              <div class="ucm-tot-i ucm-tot-sum"><span>Удельная себестоимость</span><b>{{ fmt(calc(p).unit) }} сум/{{ p.unit || 'ед.' }}</b></div>
              <div v-if="calc(p).total != null" class="ucm-tot-i"><span>Годовая себестоимость</span><b>{{ fmt(calc(p).total) }} сум</b></div>
              <button type="button" class="ucm-rmprod" @click="removeProduct(i)">Удалить продукт</button>
            </div>
          </div>
        </transition>
      </div>

      <button type="button" class="ucm-addprod" @click="addProduct">+ добавить продукт</button>

      <!-- Импорт: сырьё/комплектующие для производства (в USD, зависит от курса) -->
      <div class="ucm-imp">
        <div class="ucm-imp-hd">
          <div>
            <div class="ucm-imp-t">Импорт для производства</div>
            <div class="ucm-imp-s">закупаемое за рубежом сырьё и комплектующие · цена в USD × курс {{ num(usdRate).toLocaleString("ru") }}</div>
          </div>
          <button type="button" class="ucm-add" @click="addImport">+ позиция</button>
        </div>
        <div v-if="imports.length" class="ucm-imp-list">
          <div class="ucm-imp-head">
            <span>Наименование</span><span>Ед.</span><span>Цена, $</span><span>Кол-во</span><span>Итог, сум</span><span></span>
          </div>
          <div v-for="(it, ii) in imports" :key="ii" class="ucm-imp-row">
            <input v-model="it.name" type="text" class="ucm-inp" placeholder="Импортируемая позиция" />
            <input v-model="it.unit" type="text" class="ucm-inp ucm-inp-c" placeholder="т" />
            <input v-model.number="it.usd" type="text" inputmode="decimal" class="ucm-inp ucm-inp-c" placeholder="0" />
            <input v-model.number="it.qty" type="text" inputmode="decimal" class="ucm-inp ucm-inp-c" placeholder="0" />
            <span class="ucm-imp-cost">{{ fmt(importCost(it)) }}</span>
            <button type="button" class="ucm-del" @click="removeImport(ii)" title="Удалить">✕</button>
          </div>
          <div class="ucm-imp-total">Итого импорт: <b>{{ fmt(importTotal) }} сум</b></div>
        </div>
        <div v-else class="ucm-imp-empty">импорт не указан — добавьте позиции кнопкой «+ позиция»</div>
      </div>
    </div>

    <template #footer>
      <span class="ucm-hint">энергонормы предзаполнены из отчёта энергоёмкости · остальное — вручную</span>
      <button class="ucm-cancel" type="button" @click="emit('close')">Отмена</button>
      <button class="ucm-save" type="button" :disabled="!dirty || saving" @click="save">
        {{ saving ? "Сохранение…" : "Сохранить" }}
      </button>
    </template>
  </ModalShell>
</template>

<style scoped>
.ucm-head { display: flex; flex-direction: column; gap: 2px; }
.ucm-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--t3,#94A3B8); }
.ucm-title { font-size: 16px; font-weight: 600; margin: 2px 0 0; color: var(--t1,#1E2A4A); display: flex; align-items: center; gap: 8px; }
.ucm-dot { width: 10px; height: 10px; border-radius: 50%; }
.ucm-meta { font-size: 11px; color: var(--t3,#94A3B8); }

.ucm-body { display: flex; flex-direction: column; gap: 8px; }
.ucm-prod { border: 1px solid var(--border,#ECEAF5); border-radius: 12px; overflow: hidden; background: #fff;
  animation: ucmProdIn .4s var(--ease-standard,ease) var(--d,0ms) both; transition: box-shadow .16s; }
@keyframes ucmProdIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.ucm-prod.open { box-shadow: 0 4px 16px rgba(15,23,60,.08); }
.ucm-prod-hd { display: grid; grid-template-columns: 16px 1fr max-content max-content; align-items: center; gap: 10px;
  padding: 11px 13px; cursor: pointer; transition: background .14s; }
.ucm-prod-hd:hover { background: var(--bg2,#FAFAFD); }
.ucm-chevron { width: 7px; height: 7px; border-right: 1.6px solid var(--t3,#94A3B8); border-bottom: 1.6px solid var(--t3,#94A3B8);
  transform: rotate(-45deg); transition: transform .2s; }
.ucm-chevron.open { transform: rotate(45deg); }
.ucm-prod-name { font-size: 12.5px; font-weight: 600; color: var(--t1,#1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ucm-prod-cost { font-size: 13px; font-weight: 700; color: var(--p-deep,#534AB7); font-variant-numeric: tabular-nums; white-space: nowrap; }
.ucm-cu { font-size: 9px; color: var(--t3,#94A3B8); font-weight: 500; margin-left: 3px; }
.ucm-prod-share { font-size: 9.5px; font-weight: 700; border-radius: 6px; padding: 2px 7px; white-space: nowrap; }

.ucm-prod-body { padding: 4px 14px 14px; border-top: 0.5px solid rgba(0,0,0,.06); }
.ucm-row3 { display: grid; grid-template-columns: 1fr .6fr .8fr; gap: 10px; margin: 12px 0; }
@media (max-width: 640px) { .ucm-row3 { grid-template-columns: 1fr; } }
.ucm-f { display: flex; flex-direction: column; gap: 4px; }
.ucm-f span { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t3,#94A3B8); }
.ucm-inp { box-sizing: border-box; width: 100%; font-size: 12.5px; font-family: inherit; color: var(--t1,#1E2A4A);
  padding: 7px 9px; border: 1.5px solid var(--border,#ECEAF5); border-radius: 8px; outline: none; background: #fff;
  transition: box-shadow .14s, border-color .14s; }
.ucm-inp:focus { box-shadow: 0 0 0 3px rgba(124,111,247,.14); border-color: var(--brand,#6C5CE7); }
.ucm-inp-c { text-align: right; font-variant-numeric: tabular-nums; }

.ucm-sub { display: flex; align-items: center; gap: 8px; font-size: 10.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .04em; color: var(--p-deep,#534AB7); margin: 14px 0 8px; }
.ucm-sub span { font-weight: 500; text-transform: none; letter-spacing: 0; color: var(--t3,#94A3B8); font-size: 10px; }
.ucm-add { margin-left: auto; font-size: 10px; font-weight: 600; font-family: inherit; color: var(--p-deep,#534AB7);
  background: rgba(124,111,247,.08); border: 1px solid rgba(124,111,247,.28); border-radius: 7px; padding: 3px 9px; cursor: pointer; }
.ucm-add:hover { background: rgba(124,111,247,.16); }

.ucm-energy { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
@media (max-width: 640px) { .ucm-energy { grid-template-columns: 1fr; } }
.ucm-en { display: grid; grid-template-columns: 1fr; gap: 3px; background: var(--bg2,#FAFAFD); border-radius: 9px; padding: 8px 10px; }
.ucm-en-l { font-size: 10px; font-weight: 600; color: var(--t2,#4B5468); }
.ucm-en-u { font-size: 8.5px; color: var(--t3,#94A3B8); }
.ucm-en-c { font-size: 9.5px; color: #1D9E75; font-weight: 600; font-variant-numeric: tabular-nums; min-height: 12px; }

.ucm-comps { display: flex; flex-direction: column; gap: 6px; }
.ucm-comp { display: grid; grid-template-columns: 1fr 120px 26px; gap: 8px; align-items: center;
  animation: ucmProdIn .3s ease both; }
.ucm-del { width: 26px; height: 30px; border-radius: 7px; border: 1px solid var(--border,#ECEAF5); background: #fff;
  color: var(--t3,#94A3B8); cursor: pointer; font-size: 12px; transition: all .14s; }
.ucm-del:hover { color: #E24B4A; border-color: #F3C3C2; }
.ucm-empty { font-size: 10.5px; color: #C4C8D4; font-style: italic; padding: 4px 0; }

.ucm-total { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; margin-top: 14px; padding-top: 12px;
  border-top: 0.5px dashed rgba(0,0,0,.1); }
.ucm-tot-i { display: flex; flex-direction: column; gap: 1px; }
.ucm-tot-i span { font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t3,#94A3B8); }
.ucm-tot-i b { font-size: 12.5px; color: var(--t1,#1E2A4A); font-variant-numeric: tabular-nums; }
.ucm-tot-sum b { color: var(--p-deep,#534AB7); font-size: 13.5px; }
.ucm-rmprod { margin-left: auto; font-size: 10.5px; font-weight: 600; font-family: inherit; color: var(--t3,#94A3B8);
  background: transparent; border: 1px dashed var(--border-strong,#D9D7E8); border-radius: 8px; padding: 6px 11px; cursor: pointer; transition: all .14s; }
.ucm-rmprod:hover { color: #E24B4A; border-color: #F3C3C2; }

.ucm-addprod { font-size: 12px; font-weight: 600; font-family: inherit; color: var(--p-deep,#534AB7);
  background: rgba(124,111,247,.06); border: 1.5px dashed rgba(124,111,247,.35); border-radius: 11px; padding: 11px; cursor: pointer;
  transition: all .14s; margin-top: 2px; }
.ucm-addprod:hover { background: rgba(124,111,247,.12); }

/* Импорт */
.ucm-imp { border: 1px solid var(--border,#ECEAF5); border-radius: 12px; padding: 13px; background: var(--bg2,#FAFAFD); margin-top: 4px; }
.ucm-imp-hd { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.ucm-imp-t { font-size: 12px; font-weight: 700; color: var(--t1,#1E2A4A); }
.ucm-imp-s { font-size: 10px; color: var(--t3,#94A3B8); margin-top: 2px; }
.ucm-imp-head, .ucm-imp-row { display: grid; grid-template-columns: 1fr 60px 90px 90px 110px 26px; gap: 8px; align-items: center; }
.ucm-imp-head { padding: 0 2px 5px; }
.ucm-imp-head span { font-size: 8.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em; color: var(--t3,#94A3B8); text-align: right; }
.ucm-imp-head span:first-child { text-align: left; }
.ucm-imp-row { margin-bottom: 6px; animation: ucmProdIn .3s ease both; }
.ucm-imp-cost { text-align: right; font-size: 11.5px; font-weight: 700; color: #1D9E75; font-variant-numeric: tabular-nums; }
.ucm-imp-total { text-align: right; font-size: 11.5px; color: var(--t2,#4B5468); margin-top: 4px; padding-top: 8px; border-top: 0.5px dashed rgba(0,0,0,.1); }
.ucm-imp-total b { color: var(--p-deep,#534AB7); font-variant-numeric: tabular-nums; }
.ucm-imp-empty { font-size: 10.5px; color: #C4C8D4; font-style: italic; }

.ucm-exp-enter-active, .ucm-exp-leave-active { transition: all .22s var(--ease-standard,ease); overflow: hidden; }
.ucm-exp-enter-from, .ucm-exp-leave-to { opacity: 0; max-height: 0; }
.ucm-exp-enter-to, .ucm-exp-leave-from { opacity: 1; max-height: 900px; }

.ucm-hint { margin-right: auto; font-size: 10px; color: var(--t3,#94A3B8); font-style: italic; }
.ucm-cancel { font-size: 12.5px; font-weight: 600; font-family: inherit; color: var(--t2,#4B5468); background: transparent;
  border: 1px solid var(--border-hard,#E5E7EB); border-radius: 10px; padding: 9px 18px; cursor: pointer; }
.ucm-save { font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg,#8B7FFF 0%,#6C5CE7 100%); border: none; border-radius: 10px; padding: 9px 22px; cursor: pointer;
  box-shadow: 0 3px 12px rgba(108,92,231,.34); transition: transform .14s, box-shadow .14s, opacity .14s; }
.ucm-save:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108,92,231,.45); }
.ucm-save:disabled { opacity: .5; cursor: default; box-shadow: none; }
</style>
