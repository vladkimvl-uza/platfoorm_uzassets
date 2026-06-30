<template>
  <Teleport to="body">
    <div class="fme-overlay" @click.self="$emit('close')">
      <div class="fme-modal">
        <header class="fme-head">
          <div>
            <div class="fme-eyebrow">UAP FinModel · Редактор</div>
            <h2 class="fme-ttl">Сценарий «{{ scenarioLabel }}»</h2>
          </div>
          <button class="fme-x" @click="$emit('close')" aria-label="Закрыть">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2.4"
                 stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </header>

        <nav class="fme-tabs">
          <button
            v-for="t in tabs"
            :key="t.id"
            class="fme-tab"
            :class="{ active: activeTab === t.id }"
            @click="activeTab = t.id"
          >{{ t.label }}</button>
        </nav>

        <div class="fme-body">
          <!-- Overview -->
          <div v-if="activeTab === 'overview'" class="fme-grid">
            <div class="fme-field">
              <label>Год начала</label>
              <input type="number" v-model.number="draft.horizon.startYear" disabled />
            </div>
            <div class="fme-field">
              <label>Год конца</label>
              <input type="number" v-model.number="draft.horizon.endYear" disabled />
            </div>
            <div class="fme-field">
              <label>Налог на прибыль (%)</label>
              <input type="number" step="0.5"
                     :value="(draft.assumptions.taxRate * 100).toFixed(1)"
                     @input="setPct($event, 'taxRate')" />
            </div>
            <div class="fme-field">
              <label>WACC (%)</label>
              <input type="number" step="0.5"
                     :value="(draft.assumptions.wacc * 100).toFixed(1)"
                     @input="setPct($event, 'wacc')" />
            </div>
            <div class="fme-field">
              <label>Cost of debt (%)</label>
              <input type="number" step="0.5"
                     :value="(draft.assumptions.effectiveCostOfDebt * 100).toFixed(1)"
                     @input="setPct($event, 'effectiveCostOfDebt')" />
            </div>
            <div class="fme-field">
              <label>Терминальный рост (%)</label>
              <input type="number" step="0.5"
                     :value="(draft.assumptions.terminalGrowth * 100).toFixed(1)"
                     @input="setPct($event, 'terminalGrowth')" />
            </div>
            <div class="fme-field">
              <label>Payout (%)</label>
              <input type="number" step="5"
                     :value="(draft.assumptions.dividendPayout * 100).toFixed(0)"
                     @input="setPct($event, 'dividendPayout')" />
            </div>
            <div class="fme-field">
              <label>Beta</label>
              <input type="number" step="0.05" v-model.number="draft.assumptions.beta" />
            </div>
          </div>

          <!-- Driver editor (volumes/tariffs/costs/capex) -->
          <div v-else-if="isDriverTab(activeTab)" class="fme-driv-editor">
            <table class="fme-driv-tbl">
              <thead>
                <tr>
                  <th class="left">Название</th>
                  <th class="left">Ед.</th>
                  <th
                    v-for="y in allYears"
                    :key="y"
                    :class="{ forecast: !isFactYear(y) }"
                  >{{ y }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="d in currentDriverList" :key="d.id">
                  <td class="left">{{ d.name }}</td>
                  <td class="left fme-muted">{{ d.unit }}</td>
                  <td v-for="y in allYears" :key="y" :class="{ forecast: !isFactYear(y) }">
                    <input
                      type="number"
                      class="fme-cell-input"
                      :value="d.values[y]"
                      @input="onDriverCellInput($event, d.id, y)"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Airport load -->
          <div v-else-if="activeTab === 'airports'" class="fme-ap-edit">
            <div
              v-for="(ap, i) in draft.airportLoad"
              :key="ap.name + i"
              class="fme-ap-row"
            >
              <input type="text" class="fme-ap-name" v-model="ap.name" />
              <input
                type="range" min="0" max="1.2" step="0.01"
                v-model.number="ap.load"
                class="fme-ap-range"
              />
              <span class="fme-ap-pct">{{ (ap.load * 100).toFixed(0) }}%</span>
              <button class="fme-ap-del" @click="draft.airportLoad.splice(i, 1)">×</button>
            </div>
            <button class="fme-add-btn" @click="addAirport">+ Добавить аэропорт</button>
          </div>

          <!-- WC -->
          <div v-else-if="activeTab === 'wc'" class="fme-grid">
            <div class="fme-field">
              <label>DSO (дни)</label>
              <input type="number" v-model.number="draft.drivers.wc.dso" />
            </div>
            <div class="fme-field">
              <label>DIO (дни)</label>
              <input type="number" v-model.number="draft.drivers.wc.dio" />
            </div>
            <div class="fme-field">
              <label>DPO (дни)</label>
              <input type="number" v-model.number="draft.drivers.wc.dpo" />
            </div>
            <div class="fme-field">
              <label>Days advance payments</label>
              <input type="number" v-model.number="draft.drivers.wc.dap" />
            </div>
          </div>

          <!-- Debt -->
          <div v-else-if="activeTab === 'debt'" class="fme-driv-editor">
            <table class="fme-driv-tbl">
              <thead>
                <tr>
                  <th class="left">Тип долга</th>
                  <th v-for="y in allYears" :key="y" :class="{ forecast: !isFactYear(y) }">{{ y }}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td class="left">Long-term debt</td>
                  <td v-for="y in allYears" :key="y" :class="{ forecast: !isFactYear(y) }">
                    <input type="number" class="fme-cell-input"
                           :value="draft.drivers.debt.ltDebt[y]"
                           @input="onDebtInput($event, 'ltDebt', y)" />
                  </td>
                </tr>
                <tr>
                  <td class="left">Short-term debt</td>
                  <td v-for="y in allYears" :key="y" :class="{ forecast: !isFactYear(y) }">
                    <input type="number" class="fme-cell-input"
                           :value="draft.drivers.debt.stDebt[y]"
                           @input="onDebtInput($event, 'stDebt', y)" />
                  </td>
                </tr>
              </tbody>
            </table>
            <div class="fme-field" style="margin-top: 12px; max-width: 220px;">
              <label>Ставка % (effective)</label>
              <input type="number" step="0.5"
                     :value="(draft.drivers.debt.interestRate * 100).toFixed(1)"
                     @input="setInterest" />
            </div>
          </div>
        </div>

        <footer class="fme-foot">
          <button class="fme-btn-ghost" @click="$emit('close')">Отмена</button>
          <button class="fme-btn-prim" @click="save">Сохранить</button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { SCENARIOS, type FmScenarioModel, type ScenarioId, type FmAssumptions, type FmDebt } from "./fmUapSeed";

const props = defineProps<{
  model: FmScenarioModel;
  scenario: ScenarioId;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved", model: FmScenarioModel): void;
}>();

// Editable deep-clone so cancel is risk-free
const draft = reactive<FmScenarioModel>(structuredClone(props.model));

const scenarioLabel = computed(() =>
  SCENARIOS.find((s) => s.id === props.scenario)?.label ?? "—",
);

type TabId = "overview" | "volumes" | "tariffs" | "costs" | "capex" | "wc" | "debt" | "airports";
const tabs: Array<{ id: TabId; label: string }> = [
  { id: "overview", label: "Обзор" },
  { id: "volumes",  label: "Объёмы" },
  { id: "tariffs",  label: "Тарифы" },
  { id: "costs",    label: "OPEX" },
  { id: "capex",    label: "CAPEX" },
  { id: "wc",       label: "WC" },
  { id: "debt",     label: "Долг" },
  { id: "airports", label: "Аэропорты" },
];
const activeTab = ref<TabId>("overview");

const allYears = computed(() => [...draft.horizon.factYears, ...draft.horizon.forecastYears]);
const isFactYear = (y: number) => draft.horizon.factYears.includes(y);

const driverTabs: TabId[] = ["volumes", "tariffs", "costs", "capex"];
function isDriverTab(t: TabId): boolean { return driverTabs.includes(t); }

const currentDriverList = computed(() => {
  switch (activeTab.value) {
    case "volumes": return draft.drivers.volumes;
    case "tariffs": return draft.drivers.tariffs;
    case "costs":   return draft.drivers.costs;
    case "capex":   return draft.drivers.capex;
    default:        return [];
  }
});

function onDriverCellInput(e: Event, driverId: string, year: number) {
  const v = Number((e.target as HTMLInputElement).value);
  if (!Number.isFinite(v)) return;
  for (const d of currentDriverList.value) {
    if (d.id === driverId) { d.values[year] = v; break; }
  }
}

function onDebtInput(e: Event, key: "ltDebt" | "stDebt", year: number) {
  const v = Number((e.target as HTMLInputElement).value);
  if (!Number.isFinite(v)) return;
  draft.drivers.debt[key][year] = v;
}

function setPct(e: Event, key: keyof FmAssumptions) {
  const raw = Number((e.target as HTMLInputElement).value);
  if (!Number.isFinite(raw)) return;
  (draft.assumptions[key] as number) = raw / 100;
}

function setInterest(e: Event) {
  const raw = Number((e.target as HTMLInputElement).value);
  if (!Number.isFinite(raw)) return;
  draft.drivers.debt.interestRate = raw / 100;
}

function addAirport() {
  draft.airportLoad.push({ name: "Новый аэропорт", load: 0.5 });
}

function save() {
  emit("saved", structuredClone(draft));
}

// keep types referenced
void ({} as FmDebt);
</script>

<style scoped>
.fme-overlay {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, 0.45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
  animation: fmeFadeIn 0.25s ease both;
}
@keyframes fmeFadeIn { from { opacity: 0; } to { opacity: 1; } }

.fme-modal {
  width: min(1180px, 96vw);
  height: min(88dvh, 760px);
  background: var(--bg1, #fff);
  border-radius: 14px;
  display: flex; flex-direction: column;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.28), 0 8px 24px rgba(15, 23, 60, 0.12);
  animation: fmeModalIn 0.45s var(--ease-standard);
}
@keyframes fmeModalIn {
  0%   { opacity: 0; transform: translateY(20px) scale(0.95); }
  60%  { opacity: 1; transform: translateY(-4px) scale(1.005); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}

.fme-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 18px 22px 14px;
  border-bottom: 1px solid rgba(15, 23, 60, 0.07);
}
.fme-eyebrow {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, 0.5);
}
.fme-ttl { margin: 4px 0 0; font-size: 17px; font-weight: 500; color: var(--t1, #1E2A4A); letter-spacing: -0.01em; }
.fme-x {
  width: 32px; height: 32px;
  border: 1px solid rgba(15, 23, 60, 0.1);
  border-radius: 8px;
  background: var(--bg1, #fff);
  color: rgba(15, 23, 60, 0.6);
  cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.fme-x:hover { background: var(--bg2, #FAFAFD); color: var(--t1, #1E2A4A); }

.fme-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 22px;
  border-bottom: 1px solid rgba(15, 23, 60, 0.07);
  background: var(--bg2, #FAFAFD);
  overflow-x: auto;
}
.fme-tab {
  background: transparent;
  border: 1px solid transparent;
  padding: 7px 14px;
  border-radius: 8px;
  font: inherit;
  font-size: 11.5px;
  font-weight: 500;
  color: rgba(15, 23, 60, 0.65);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.fme-tab:hover { background: rgba(127, 119, 221, 0.08); color: var(--p-deep); }
.fme-tab.active {
  background: var(--bg1, #fff);
  border-color: rgba(127, 119, 221, 0.4);
  color: var(--p-deep);
  box-shadow: 0 2px 6px rgba(127, 119, 221, 0.18);
}

.fme-body {
  flex: 1;
  overflow: auto;
  padding: 18px 22px;
}

.fme-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
@media (max-width: 900px) { .fme-grid { grid-template-columns: repeat(2, 1fr); } }
.fme-field { display: flex; flex-direction: column; gap: 4px; }
.fme-field label {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, 0.55);
}
.fme-field input {
  font: inherit;
  font-size: 13px;
  padding: 8px 10px;
  border: 1px solid rgba(15, 23, 60, 0.12);
  border-radius: 8px;
  background: var(--bg2, #FAFAFD);
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  transition: border-color 0.15s, background 0.15s;
}
.fme-field input:focus {
  outline: none;
  border-color: #7F77DD;
  background: var(--bg1, #fff);
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.15);
}
.fme-field input:disabled { opacity: 0.6; cursor: not-allowed; }

/* Driver editor tables */
.fme-driv-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.fme-driv-tbl th {
  padding: 6px 8px;
  text-align: right;
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, 0.55);
  border-bottom: 1px solid rgba(15, 23, 60, 0.08);
  white-space: nowrap;
  position: sticky; top: 0;
  background: var(--bg2, #FAFAFD);
}
.fme-driv-tbl th.left { text-align: left; }
.fme-driv-tbl th.forecast { background: #FFFBF4; color: #7A4A00; }
.fme-driv-tbl td {
  padding: 4px 4px;
  text-align: right;
  border-bottom: 1px solid rgba(15, 23, 60, 0.03);
}
.fme-driv-tbl td.left { text-align: left; padding: 6px 8px; color: var(--t1, #1E2A4A); font-weight: 500; }
.fme-driv-tbl td.forecast { background: #FFFBF4; }
.fme-muted { color: rgba(15, 23, 60, 0.5) !important; font-weight: 400 !important; }

.fme-cell-input {
  width: 88px;
  padding: 5px 7px;
  border: 1px solid rgba(15, 23, 60, 0.08);
  border-radius: 5px;
  background: var(--bg1, #fff);
  font: inherit;
  font-size: 11px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--t1, #1E2A4A);
  transition: border-color 0.12s;
}
.fme-cell-input:focus {
  outline: none;
  border-color: #7F77DD;
  box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.15);
}

/* Airport editor */
.fme-ap-edit { display: flex; flex-direction: column; gap: 8px; }
.fme-ap-row {
  display: grid;
  grid-template-columns: 220px 1fr 60px 28px;
  align-items: center;
  gap: 12px;
}
.fme-ap-name {
  padding: 7px 10px;
  border: 1px solid rgba(15, 23, 60, 0.12);
  border-radius: 8px;
  font: inherit;
  font-size: 12px;
  background: var(--bg2, #FAFAFD);
  color: var(--t1, #1E2A4A);
}
.fme-ap-range { width: 100%; accent-color: #7F77DD; }
.fme-ap-pct {
  font-size: 12px;
  font-weight: 600;
  color: var(--p-deep);
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.fme-ap-del {
  width: 26px; height: 26px;
  border-radius: 6px;
  border: 1px solid rgba(226, 75, 74, 0.3);
  color: var(--sev-high);
  background: rgba(226, 75, 74, 0.05);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
.fme-ap-del:hover { background: rgba(226, 75, 74, 0.15); }
.fme-add-btn {
  align-self: flex-start;
  margin-top: 8px;
  padding: 8px 14px;
  background: rgba(127, 119, 221, 0.08);
  border: 1px dashed rgba(127, 119, 221, 0.4);
  color: var(--p-deep);
  border-radius: 8px;
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}
.fme-add-btn:hover { background: rgba(127, 119, 221, 0.15); }

.fme-foot {
  padding: 14px 22px;
  border-top: 1px solid rgba(15, 23, 60, 0.07);
  display: flex; justify-content: flex-end; gap: 8px;
  background: var(--bg2, #FAFAFD);
}
.fme-btn-ghost, .fme-btn-prim {
  font: inherit;
  font-size: 12.5px;
  font-weight: 500;
  padding: 9px 18px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.fme-btn-ghost {
  background: var(--bg1, #fff);
  border: 1px solid rgba(15, 23, 60, 0.12);
  color: rgba(15, 23, 60, 0.65);
}
.fme-btn-ghost:hover { background: #F0F0F8; }
.fme-btn-prim {
  background: linear-gradient(135deg, #7F77DD, var(--p-deep));
  border: 0;
  color: #fff;
  box-shadow: 0 4px 12px rgba(127, 119, 221, 0.35);
}
.fme-btn-prim:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(127, 119, 221, 0.45); }
</style>
