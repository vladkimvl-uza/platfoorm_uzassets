<script setup lang="ts">
/**
 * UnitCostCompanyModal — редактор продуктов компании: годовой выпуск, удельный
 * расход энергоресурсов (предзаполнен), прочие статьи себестоимости. Живой
 * расчёт удельной себестоимости и доли энергии. Dirty-guard, тосты, анимации.
 */
import { computed, ref, watch } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { useToast } from "@/composables/useToast";
import CreditDonut, { type DonutEntry } from "@/components/CreditPortfolio/CreditDonut.vue";
import MentionableTextarea from "@/components/MentionableTextarea.vue";
import { unitCostApi, FUELS, type UCCompany, type UCPrices, type UCWorld,
         type EditProduct, type EditImport, type EditComment } from "@/api/unitCost";

const props = defineProps<{
  open: boolean; company: UCCompany | null;
  prices: UCPrices; world: UCWorld | null; fuelLabels: Record<string, string>;
  year: number; quarter: string;
}>();
const emit = defineEmits<{ (e: "close"): void; (e: "saved"): void }>();
const toast = useToast();

const FUEL_UNIT: Record<string, string> = {
  electricity: "кВт·ч/ед", gas: "м³/ед", diesel: "т/ед", mazut: "т/ед", coal: "т/ед", kerosene: "т/ед",
};

const FUEL_COLOR: Record<string, string> = {
  electricity: "#EF9F27", gas: "#378ADD", diesel: "#E24B4A", mazut: "#8B7FFF", coal: "#4B5468", kerosene: "#1D9E75",
};
const draft = ref<EditProduct[]>([]);
const imports = ref<EditImport[]>([]);
const comments = ref<EditComment[]>([]);
const newComment = ref("");
const newMentions = ref<string[]>([]);
const saving = ref(false);
let initial = "";

function toEdit(c: UCCompany): EditProduct[] {
  return (c.products || []).map((p) => ({
    name: p.name, unit: p.unit, output: p.output,
    energy: { ...(p.energy || {}) },
    norm: { ...(p.norm || {}) },
    components: (p.components || []).map((x) => ({ name: x.name, value: x.value })),
  }));
}
function init() {
  draft.value = props.company ? toEdit(props.company) : [];
  imports.value = (props.company?.imports || []).map((it) => ({ name: it.name, unit: it.unit, usd: it.usd, qty: it.qty }));
  comments.value = (props.company?.comments || []).map((c) => ({ author: c.author, text: c.text, at: c.at, mentions: c.mentions }));
  newComment.value = ""; newMentions.value = [];
  initial = JSON.stringify({ p: draft.value, i: imports.value, c: comments.value });
}
watch(() => props.open, (o) => { if (o) init(); }, { immediate: true });
const dirty = computed(() => JSON.stringify({ p: draft.value, i: imports.value, c: comments.value }) !== initial
  || newComment.value.trim().length > 0);

// живые донаты компании (по всем продуктам, вес = выпуск||1)
function fuelCost(f: string): number {
  return draft.value.reduce((s, p) => s + num(p.energy[f]) * priceOf(f) * (num(p.output) || 1), 0);
}
const mixDonut = computed<DonutEntry[]>(() =>
  FUELS.map((f) => ({ label: props.fuelLabels[f] || f, color: FUEL_COLOR[f], value: fuelCost(f) }))
    .filter((e) => e.value > 0));
const mixTotal = computed(() => FUELS.reduce((s, f) => s + fuelCost(f), 0));
const structDonut = computed<DonutEntry[]>(() => {
  const energy = mixTotal.value;
  const comps = draft.value.reduce((s, p) =>
    s + (p.components || []).reduce((a, c) => a + num(c.value), 0) * (num(p.output) || 1), 0);
  const out: DonutEntry[] = [];
  if (energy > 0) out.push({ label: "Энергозатраты", color: "#EF9F27", value: energy });
  if (comps > 0) out.push({ label: "Прочие статьи", color: "#7F77DD", value: comps });
  return out;
});
const structTotal = computed(() => structDonut.value.reduce((s, e) => s + e.value, 0));
function donutHover(e: DonutEntry, total: number): [string, string] {
  return [fmtC(e.value), total ? Math.round((e.value / total) * 100) + "%" : ""];
}

function onMention(u: { username?: string; full_name?: string; email?: string }) {
  const tag = u.username || u.full_name || u.email || "";
  if (tag && !newMentions.value.includes(tag)) newMentions.value.push(tag);
}
function addComment() {
  const t = newComment.value.trim();
  if (!t) return;
  comments.value.push({ text: t, mentions: [...newMentions.value] });
  newComment.value = ""; newMentions.value = [];
}
function fmtDate(iso?: string): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString("ru", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

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

// живой расчёт продукта (факт + отклонение от нормы расхода)
function calc(p: EditProduct) {
  let energy = 0;
  let overUnit = 0;      // сум/ед: (факт − норма)×цена, + перерасход / − экономия
  let hasNorm = false;
  for (const f of FUELS) {
    const act = p.energy[f];
    if (act != null) energy += num(act) * priceOf(f);
    const nrm = p.norm?.[f];
    if (act != null && nrm != null) { hasNorm = true; overUnit += (num(act) - num(nrm)) * priceOf(f); }
  }
  const comps = (p.components || []).reduce((s, c) => s + num(c.value), 0);
  const unit = energy + comps;
  const out = num(p.output);
  return {
    energy, comps, unit, hasNorm,
    share: unit > 0 ? (energy / unit) * 100 : null,
    total: out > 0 ? unit * out : null,
    overUnit: hasNorm ? overUnit : null,
    overrunCost: hasNorm && out > 0 ? overUnit * out : null,
  };
}
// отклонение по конкретному энергоресурсу (для индикатора в редакторе)
function fuelDelta(p: EditProduct, f: string): { d: number; cost: number; over: boolean } | null {
  const act = p.energy[f]; const nrm = p.norm?.[f];
  if (act == null || nrm == null) return null;
  const d = num(act) - num(nrm);
  return { d, cost: d * priceOf(f), over: d > 0 };
}
function fmt(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("ru", { maximumFractionDigits: 2 });
}
// компактная сумма (для донатов и KPI компании — не вылезает за пределы)
function fmtC(v: number | null): string {
  if (v == null) return "—";
  const a = Math.abs(v);
  if (a >= 1e12) return (v / 1e12).toLocaleString("ru", { maximumFractionDigits: 2 }) + " трлн";
  if (a >= 1e9) return (v / 1e9).toLocaleString("ru", { maximumFractionDigits: 1 }) + " млрд";
  if (a >= 1e6) return (v / 1e6).toLocaleString("ru", { maximumFractionDigits: 1 }) + " млн";
  if (a >= 1e3) return (v / 1e3).toLocaleString("ru", { maximumFractionDigits: 1 }) + " тыс";
  return v.toLocaleString("ru", { maximumFractionDigits: 0 });
}
function shareColor(s: number | null): string {
  if (s == null) return "#9AA0AE";
  return s >= 60 ? "#E24B4A" : s >= 35 ? "#EF9F27" : "#1D9E75";
}

// сводные KPI компании (те же показатели, что на дашборде, но по этой компании)
const kpi = computed(() => {
  let total = 0, energy = 0, over = 0, filled = 0;
  let hasOver = false;
  for (const p of draft.value) {
    const c = calc(p);
    if (num(p.output) > 0) {
      filled++;
      if (c.total != null) total += c.total;
      energy += c.energy * num(p.output);
    }
    if (c.overrunCost != null) { over += c.overrunCost; hasOver = true; }
  }
  return {
    total: total || null, energy: energy || null,
    share: total > 0 ? (energy / total) * 100 : null,
    filled, count: draft.value.length,
    overrun: hasOver ? over : null,
  };
});
const overColor = computed(() => {
  const v = kpi.value.overrun; if (v == null) return "#94A3B8";
  return v > 0 ? "#E24B4A" : "#1D9E75";
});

const expanded = ref<number | null>(0);
function toggle(i: number) { expanded.value = expanded.value === i ? null : i; }

function addComponent(p: EditProduct) { p.components.push({ name: "", value: 0 }); }
function removeComponent(p: EditProduct, i: number) { p.components.splice(i, 1); }
function addProduct() {
  draft.value.push({ name: "Новый продукт", unit: "ед.", output: 0, energy: {}, norm: {},
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
  if (newComment.value.trim()) addComment();  // не потерять недобавленный коммент
  saving.value = true;
  try {
    await unitCostApi.saveCompany(props.company.code, draft.value, imports.value, comments.value, props.year, props.quarter);
    toast.success("Себестоимость сохранена");
    initial = JSON.stringify({ p: draft.value, i: imports.value, c: comments.value });
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
      <!-- сводные показатели компании (те же, что на дашборде) -->
      <div class="ucm-kpis">
        <div class="ucm-k" style="--kc:#7F77DD"><span>Себестоимость</span><b>{{ fmtC(kpi.total) }}</b></div>
        <div class="ucm-k" style="--kc:#EF9F27"><span>Энергозатраты</span><b>{{ fmtC(kpi.energy) }}</b></div>
        <div class="ucm-k" style="--kc:#E24B4A"><span>Доля энергии</span><b>{{ kpi.share != null ? kpi.share.toFixed(1) + '%' : '—' }}</b></div>
        <div class="ucm-k" style="--kc:#1D9E75"><span>Заполнено</span><b>{{ kpi.filled }}<i>/{{ kpi.count }}</i></b></div>
        <div class="ucm-k" :style="{ '--kc': overColor }" title="Отклонение факта от нормы расхода, в деньгах">
          <span>Перерасход / Экономия</span>
          <b :style="{ color: overColor }">
            <template v-if="kpi.overrun != null">{{ kpi.overrun > 0 ? '+' : '−' }}{{ fmtC(Math.abs(kpi.overrun)) }}</template>
            <template v-else>—</template>
          </b>
        </div>
      </div>

      <!-- донаты компании -->
      <div v-if="mixDonut.length || structDonut.length" class="ucm-charts">
        <div v-if="mixDonut.length" class="ucm-chart">
          <div class="ucm-chart-t">Энергомикс</div>
          <CreditDonut :entries="mixDonut" :center-value="fmtC(mixTotal)" center-label="энергия"
            :hover-fmt="donutHover" :size="118" />
        </div>
        <div v-if="structDonut.length" class="ucm-chart">
          <div class="ucm-chart-t">Структура</div>
          <CreditDonut :entries="structDonut" :center-value="fmtC(structTotal)" center-label="итого"
            :hover-fmt="donutHover" :size="118" />
        </div>
      </div>

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

            <!-- энергонормы: факт + норма расхода + отклонение -->
            <div class="ucm-sub">Удельный расход энергоресурсов <span>факт и норма на единицу · отклонение = перерасход / экономия</span></div>
            <div class="ucm-energy">
              <div v-for="f in FUELS" :key="f" class="ucm-en">
                <div class="ucm-en-l">{{ fuelLabels[f] || f }} <span class="ucm-en-u">{{ FUEL_UNIT[f] }}</span></div>
                <div class="ucm-en-flds">
                  <label class="ucm-en-fld"><span>факт</span>
                    <input v-model.number="p.energy[f]" type="text" inputmode="decimal" class="ucm-inp ucm-inp-c"
                           placeholder="—" :aria-label="'Факт: ' + fuelLabels[f]" /></label>
                  <label class="ucm-en-fld ucm-en-norm"><span>норма</span>
                    <input v-model.number="p.norm[f]" type="text" inputmode="decimal" class="ucm-inp ucm-inp-c"
                           placeholder="—" :aria-label="'Норма: ' + fuelLabels[f]" /></label>
                </div>
                <div class="ucm-en-foot">
                  <span class="ucm-en-c">{{ p.energy[f] != null ? fmt(num(p.energy[f]) * priceOf(f)) + ' сум' : '' }}</span>
                  <span v-if="fuelDelta(p, f)" class="ucm-en-diff" :class="fuelDelta(p, f)!.over ? 'over' : 'save'"
                        :title="fuelDelta(p, f)!.over ? 'Перерасход к норме' : 'Экономия против нормы'">
                    {{ fuelDelta(p, f)!.over ? '+' : '−' }}{{ fmt(Math.abs(fuelDelta(p, f)!.d)) }}
                  </span>
                </div>
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
              <div v-if="calc(p).overrunCost != null" class="ucm-tot-i">
                <span>{{ calc(p).overUnit! > 0 ? 'Перерасход к норме' : 'Экономия к норме' }}</span>
                <b :style="{ color: calc(p).overUnit! > 0 ? '#E24B4A' : '#1D9E75' }">
                  {{ calc(p).overUnit! > 0 ? '+' : '−' }}{{ fmt(Math.abs(calc(p).overrunCost!)) }} сум
                </b>
              </div>
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

      <!-- Комментарии с @-упоминаниями (история хранится по периоду) -->
      <div class="ucm-cm">
        <div class="ucm-cm-t">Комментарии</div>
        <div v-if="comments.length" class="ucm-cm-list">
          <div v-for="(c, ci) in comments" :key="ci" class="ucm-cm-item">
            <div class="ucm-cm-hd">
              <span class="ucm-cm-author">{{ c.author || "—" }}</span>
              <span class="ucm-cm-date">{{ fmtDate(c.at) }}</span>
            </div>
            <div class="ucm-cm-text">{{ c.text }}</div>
          </div>
        </div>
        <div class="ucm-cm-add">
          <MentionableTextarea v-model="newComment" placeholder="Комментарий… используйте @ для упоминания"
                               @mention="onMention" />
          <button type="button" class="ucm-cm-btn" :disabled="!newComment.trim()" @click="addComment">Добавить</button>
        </div>
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

/* Сводные KPI компании */
.ucm-kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
@media (max-width: 720px) { .ucm-kpis { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 460px) { .ucm-kpis { grid-template-columns: 1fr 1fr; } }
.ucm-k { position: relative; background: var(--bg2,#FAFAFD); border-radius: 11px; padding: 9px 11px 8px;
  display: flex; flex-direction: column; gap: 3px; overflow: hidden; animation: ucmProdIn .4s ease both; }
.ucm-k::before { content:''; position: absolute; top: 0; left: 0; right: 0; height: 2.5px; background: var(--kc,#7F77DD); opacity: .85; }
.ucm-k span { font-size: 8.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em; color: var(--t3,#94A3B8); line-height: 1.2; }
.ucm-k b { font-size: 15px; font-weight: 500; color: var(--t1,#1E2A4A); font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.ucm-k b i { font-size: 10px; font-style: normal; color: var(--t3,#94A3B8); font-weight: 500; }

.ucm-charts { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 4px; }
@media (max-width: 560px) { .ucm-charts { grid-template-columns: 1fr; } }
.ucm-chart { background: var(--bg2,#FAFAFD); border-radius: 12px; padding: 10px 8px 6px; }
.ucm-chart-t { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--p-deep,#534AB7); padding-left: 8px; }

.ucm-cm { border-top: 0.5px solid rgba(0,0,0,.08); padding-top: 12px; margin-top: 2px; }
.ucm-cm-t { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--p-deep,#534AB7); margin-bottom: 8px; }
.ucm-cm-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.ucm-cm-item { background: var(--bg2,#FAFAFD); border-radius: 10px; padding: 8px 11px; animation: ucmProdIn .3s ease both; }
.ucm-cm-hd { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 3px; }
.ucm-cm-author { font-size: 11px; font-weight: 700; color: var(--t1,#1E2A4A); }
.ucm-cm-date { font-size: 9.5px; color: var(--t3,#94A3B8); font-variant-numeric: tabular-nums; }
.ucm-cm-text { font-size: 12px; color: var(--t2,#4B5468); line-height: 1.4; white-space: pre-wrap; word-break: break-word; }
.ucm-cm-add { display: flex; flex-direction: column; gap: 8px; }
.ucm-cm-btn { align-self: flex-end; font-size: 11.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg,#8B7FFF 0%,#6C5CE7 100%); border: none; border-radius: 9px; padding: 7px 16px; cursor: pointer;
  box-shadow: 0 2px 8px rgba(108,92,231,.3); transition: transform .14s, opacity .14s; }
.ucm-cm-btn:hover:not(:disabled) { transform: translateY(-1px); }
.ucm-cm-btn:disabled { opacity: .45; cursor: default; box-shadow: none; }
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
