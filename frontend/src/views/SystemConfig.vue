<script setup lang="ts">
/**
 * SystemConfig.vue — /admin/system-config
 * ─────────────────────────────────────────────────────────────────
 * Админ-страница для редактирования системных констант по годам.
 * Pack 7.39 — расширена: теперь две вкладки.
 *
 *   Вкладка «Валюты и бюджет»:
 *     • Курс USD / UZS (среднегодовой)
 *     • Курс EUR / UZS (среднегодовой)
 *     • Бюджет Республики, трлн сум
 *
 *   Вкладка «Макроэкономика»:
 *     • Годовая инфляция, %
 *     • Базовая ставка ЦБ РУ, %
 *     • Темп роста ВВП, %
 *
 * Доступ: admin.users или is_owner.
 *
 * При успешном сохранении вызывает useCurrencyConverter().reload(),
 * чтобы все открытые модалки и блоки моментально подхватили новые значения.
 *
 * Будущие индикаторы (CNY/RUB/прочее): добавляются через миграцию
 * year_registry (новая колонка) + расширение этого UI новой ячейкой.
 *
 * Pack 7.39
 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { systemConfigApi, type YearlyRate } from "@/api/systemConfig";
import { useCurrencyConverter } from "@/composables/useCurrencyConverter";
import { useIsAdmin } from "@/composables/useIsAdmin";
import { parseDecimal } from "@/utils/parseDecimal";
import ModalShell from "@/components/ModalShell.vue";
import ScenariosTab from "@/components/SystemConfig/ScenariosTab.vue";
import CreditNagruzkaTab from "@/components/SystemConfig/CreditNagruzkaTab.vue";
import ElasticityProjectsTab from "@/components/SystemConfig/ElasticityProjectsTab.vue";

const conv = useCurrencyConverter();
const route = useRoute();
const router = useRouter();

// ─── Tabs (URL-deeplink: ?tab=rates|macro|scenarios|credit|elastic) ───
type Tab = "rates" | "macro" | "scenarios" | "credit" | "elastic";
const VALID_TABS = new Set(["rates", "macro", "scenarios", "credit", "elastic"]);
const activeTab = computed<Tab>({
  get: () => {
    const t = String(route.query.tab || "rates");
    return (VALID_TABS.has(t) ? t : "rates") as Tab;
  },
  set: (v) => {
    const next = { ...route.query };
    if (v === "rates") delete next.tab;
    else next.tab = v;
    router.replace({ path: route.path, query: next });
  },
});

const rows = ref<YearlyRate[]>([]);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const successMsg = ref<string | null>(null);

// ─── Edit state ───
type EditState = {
  usd_rate: string;
  eur_rate: string;
  uz_budget_trln: string;
  gdp_bln: string;
  inflation_pct: string;
  cb_rate_pct: string;
  gdp_growth_pct: string;
  dirty: boolean;
};
const edits = ref<Record<number, EditState>>({});

type EditableField =
  | "usd_rate" | "eur_rate" | "uz_budget_trln" | "gdp_bln"
  | "inflation_pct" | "cb_rate_pct" | "gdp_growth_pct";

const ALL_FIELDS: EditableField[] = [
  "usd_rate", "eur_rate", "uz_budget_trln", "gdp_bln",
  "inflation_pct", "cb_rate_pct", "gdp_growth_pct",
];

// ─── Add new year form ───
const addOpen = ref(false);
const addForm = ref({
  year: 2027,
  label: "",
  usd_rate: "", eur_rate: "", uz_budget_trln: "", gdp_bln: "",
  inflation_pct: "", cb_rate_pct: "", gdp_growth_pct: "",
});
const addError = ref<string | null>(null);
const addSubmitting = ref(false);

const confirmDelete = ref<number | null>(null);
// When user confirms unlock for a closed year — yearly row goes into edit mode
const unlockedYears = ref<Set<number>>(new Set());

const isAdmin = useIsAdmin();

function isEditable(year: number): boolean {
  if (!isAdmin.value) return false;
  const row = rows.value.find((r) => r.year === year);
  if (!row) return false;
  // Closed year requires explicit unlock click
  if (row.is_closed && !unlockedYears.value.has(year)) return false;
  return true;
}

function toggleUnlock(year: number) {
  const next = new Set(unlockedYears.value);
  if (next.has(year)) next.delete(year);
  else next.add(year);
  unlockedYears.value = next;
}

// ─── Load ───
async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    rows.value = await systemConfigApi.listYearlyRates();
    const e: Record<number, EditState> = {};
    for (const r of rows.value) {
      e[r.year] = {
        usd_rate:       r.usd_rate != null ? String(r.usd_rate) : "",
        eur_rate:       r.eur_rate != null ? String(r.eur_rate) : "",
        uz_budget_trln: r.uz_budget_trln != null ? String(r.uz_budget_trln) : "",
        gdp_bln: r.gdp_bln != null ? String(r.gdp_bln) : "",
        inflation_pct:  r.inflation_pct != null ? String(r.inflation_pct) : "",
        cb_rate_pct:    r.cb_rate_pct != null ? String(r.cb_rate_pct) : "",
        gdp_growth_pct: r.gdp_growth_pct != null ? String(r.gdp_growth_pct) : "",
        dirty: false,
      };
    }
    edits.value = e;
  } catch (err: any) {
    errorMsg.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить системные константы";
  } finally {
    loading.value = false;
  }
}

onMounted(() => { void load(); });

// ─── Edit handlers ───
function onFieldInput(year: number, field: EditableField, value: string) {
  if (!edits.value[year]) return;
  edits.value[year][field] = value;
  edits.value[year].dirty = isDirty(year);
}

function isDirty(year: number): boolean {
  const e = edits.value[year];
  if (!e) return false;
  const row = rows.value.find((r) => r.year === year);
  if (!row) return false;
  for (const f of ALL_FIELDS) {
    const orig = (row as any)[f] != null ? String((row as any)[f]) : "";
    if (e[f] !== orig) return true;
  }
  return false;
}

async function saveRow(year: number) {
  const e = edits.value[year];
  if (!e || !e.dirty) return;
  errorMsg.value = null;
  successMsg.value = null;

  const parsed: Record<string, number | null> = {};
  const labels: Record<EditableField, string> = {
    usd_rate: "USD", eur_rate: "EUR", uz_budget_trln: "бюджета", gdp_bln: "ВВП",
    inflation_pct: "инфляции", cb_rate_pct: "ставки ЦБ", gdp_growth_pct: "роста ВВП",
  };
  for (const f of ALL_FIELDS) {
    const v = parseDecimal(e[f]);
    if (e[f] !== "" && v === null) {
      errorMsg.value = `Год ${year}: некорректное значение ${labels[f]}`;
      return;
    }
    parsed[f] = v;
  }

  try {
    // Pass allow_closed if year was explicitly unlocked via toggleUnlock()
    const allowClosed = unlockedYears.value.has(year);
    const updated = await systemConfigApi.updateYearlyRate(year, parsed as any, { allowClosed });
    const idx = rows.value.findIndex((r) => r.year === year);
    if (idx >= 0) rows.value[idx] = updated;
    edits.value[year].dirty = false;
    successMsg.value = `Год ${year}: сохранено`;
    await conv.reload();
    setTimeout(() => { if (successMsg.value?.includes(String(year))) successMsg.value = null; }, 2500);
  } catch (err: any) {
    errorMsg.value = err?.response?.data?.detail || err?.message || "Сохранение не удалось";
  }
}

function resetRow(year: number) {
  const row = rows.value.find((r) => r.year === year);
  if (!row || !edits.value[year]) return;
  for (const f of ALL_FIELDS) {
    edits.value[year][f] = (row as any)[f] != null ? String((row as any)[f]) : "";
  }
  edits.value[year].dirty = false;
}

// ─── Add new year ───
function openAdd() {
  addError.value = null;
  const maxYear = rows.value.length
    ? Math.max(...rows.value.map((r) => r.year))
    : new Date().getFullYear();
  addForm.value = {
    year: maxYear + 1,
    label: "",
    usd_rate: "", eur_rate: "", uz_budget_trln: "", gdp_bln: "",
    inflation_pct: "", cb_rate_pct: "", gdp_growth_pct: "",
  };
  addOpen.value = true;
}
function closeAdd() { addOpen.value = false; addError.value = null; }
async function submitAdd() {
  addError.value = null;
  const y = Number(addForm.value.year);
  if (!isFinite(y) || y < 2000 || y > 2100) {
    addError.value = "Год должен быть между 2000 и 2100";
    return;
  }
  if (rows.value.some((r) => r.year === y)) {
    addError.value = `Год ${y} уже существует`;
    return;
  }
  const usd = parseDecimal(addForm.value.usd_rate);
  const eur = parseDecimal(addForm.value.eur_rate);
  const bud = parseDecimal(addForm.value.uz_budget_trln);
  const gdpB = parseDecimal(addForm.value.gdp_bln);
  const inf = parseDecimal(addForm.value.inflation_pct);
  const cb  = parseDecimal(addForm.value.cb_rate_pct);
  const gdp = parseDecimal(addForm.value.gdp_growth_pct);
  addSubmitting.value = true;
  try {
    const created = await systemConfigApi.createYearlyRate({
      year: y,
      label: (addForm.value.label || "").trim() || null,
      usd_rate: usd, eur_rate: eur, uz_budget_trln: bud, gdp_bln: gdpB,
      inflation_pct: inf, cb_rate_pct: cb, gdp_growth_pct: gdp,
    });
    rows.value.push(created);
    rows.value.sort((a, b) => a.year - b.year);
    edits.value[created.year] = {
      usd_rate:       created.usd_rate != null ? String(created.usd_rate) : "",
      eur_rate:       created.eur_rate != null ? String(created.eur_rate) : "",
      uz_budget_trln: created.uz_budget_trln != null ? String(created.uz_budget_trln) : "",
      gdp_bln:        created.gdp_bln != null ? String(created.gdp_bln) : "",
      inflation_pct:  created.inflation_pct != null ? String(created.inflation_pct) : "",
      cb_rate_pct:    created.cb_rate_pct != null ? String(created.cb_rate_pct) : "",
      gdp_growth_pct: created.gdp_growth_pct != null ? String(created.gdp_growth_pct) : "",
      dirty: false,
    };
    addOpen.value = false;
    successMsg.value = `Год ${y} добавлен`;
    await conv.reload();
    setTimeout(() => { if (successMsg.value?.includes(`Год ${y}`)) successMsg.value = null; }, 2500);
  } catch (err: any) {
    addError.value = err?.response?.data?.detail || err?.message || "Создание не удалось";
  } finally {
    addSubmitting.value = false;
  }
}

// ─── Delete ───
// Backend may return 409 with `detail` describing dependent rows
// (financials/KPI/BP за этот год) — показываем структурированно.
async function doDelete() {
  const y = confirmDelete.value;
  if (y == null) return;
  errorMsg.value = null;
  try {
    await systemConfigApi.deleteYearlyRate(y);
    rows.value = rows.value.filter((r) => r.year !== y);
    delete edits.value[y];
    successMsg.value = `Год ${y} удалён`;
    confirmDelete.value = null;
    await conv.reload();
  } catch (err: any) {
    const status = err?.response?.status;
    const detail = err?.response?.data?.detail;
    if (status === 409 && detail) {
      // Cascade-conflict — backend describes what depends on this year
      const lines = typeof detail === "string"
        ? [detail]
        : Object.entries(detail).map(([k, v]) => `• ${k}: ${v}`);
      errorMsg.value = `Год ${y} нельзя удалить — есть зависимые данные:\n${lines.join("\n")}`;
    } else {
      errorMsg.value = err?.response?.data?.detail || err?.message || "Удаление не удалось";
    }
    confirmDelete.value = null;
  }
}

// ─── Preview ───
function previewUsd(amount: number, year: number): string {
  const e = edits.value[year];
  const rate = e ? parseDecimal(e.usd_rate) : null;
  if (!rate || rate <= 0) return "—";
  const usdMln = (amount * 1e9) / rate / 1e6;
  return `${(Math.round(usdMln * 1000) / 1000).toFixed(3)} млн USD`;
}
</script>

<template>
  <div class="sc-wrap">
    <header v-if="activeTab !== 'scenarios' && activeTab !== 'credit' && activeTab !== 'elastic'" class="sc-hdr">
      <div>
        <div class="sc-eyebrow">Системные константы</div>
        <h1 class="sc-title">Курсы валют и макроэкономика</h1>
        <p class="sc-sub">
          Среднегодовые курсы валют, бюджет Республики и макропоказатели по годам —
          используются для конвертации сумм и расчёта производных KPI во всех дашбордах.
        </p>
      </div>
      <button v-if="isAdmin" class="sc-btn sc-btn-p" @click="openAdd">
        <svg viewBox="0 0 14 14" class="sc-svg" width="13" height="13"><path d="M7 3v8M3 7h8"/></svg>
        Добавить год
      </button>
    </header>

    <div v-if="errorMsg && activeTab !== 'scenarios' && activeTab !== 'credit' && activeTab !== 'elastic'" class="sc-alert sc-alert-bad">{{ errorMsg }}</div>
    <div v-if="successMsg && activeTab !== 'scenarios' && activeTab !== 'credit' && activeTab !== 'elastic'" class="sc-alert sc-alert-good">{{ successMsg }}</div>
    <div v-if="!isAdmin && activeTab !== 'scenarios' && activeTab !== 'credit' && activeTab !== 'elastic'" class="sc-alert sc-alert-info">
      Просмотр доступен всем авторизованным пользователям. Для редактирования
      нужно разрешение <code>admin.users</code> (или статус владельца).
    </div>

    <!-- Tabs -->
    <div class="sc-tabs">
      <button type="button" class="sc-tab" :class="{ on: activeTab === 'rates' }" @click="activeTab = 'rates'">
        Валюты и бюджет
      </button>
      <button type="button" class="sc-tab" :class="{ on: activeTab === 'macro' }" @click="activeTab = 'macro'">
        Макроэкономика
      </button>
      <button type="button" class="sc-tab" :class="{ on: activeTab === 'scenarios' }" @click="activeTab = 'scenarios'">
        Сценарии и прогнозы
      </button>
        <button type="button" class="sc-tab" :class="{ on: activeTab === 'credit' }" @click="activeTab = 'credit'">
          Кредитная нагрузка
        </button>
        <button type="button" class="sc-tab" :class="{ on: activeTab === 'elastic' }" @click="activeTab = 'elastic'">
          Эластичность и проекты
        </button>
    </div>

    <!-- ─── Tab 3: Scenarios — renders own data, not yearly-rates ─── -->
    <ScenariosTab v-if="activeTab === 'scenarios'" />
    <CreditNagruzkaTab v-if="activeTab === 'credit'" />
    <ElasticityProjectsTab v-if="activeTab === 'elastic'" />

    <div v-else-if="loading" class="sc-loading">Загрузка…</div>

    <!-- ─── Tab 1: Currency rates + budget ─── -->
    <table v-else-if="rows.length && activeTab === 'rates'" class="sc-tbl">
      <thead>
        <tr>
          <th class="sc-th sc-th-year">Год</th>
          <th class="sc-th">Курс USD / UZS<div class="sc-th-hint">средний за год, сум за 1 USD</div></th>
          <th class="sc-th">Курс EUR / UZS<div class="sc-th-hint">средний за год, сум за 1 EUR</div></th>
          <th class="sc-th">Бюджет Республики<div class="sc-th-hint">доходная часть, трлн сум</div></th>
          <th class="sc-th">ВВП Республики<div class="sc-th-hint">номинальный, млрд сум (для %ВВП)</div></th>
          <th class="sc-th sc-th-preview">Эквивалент 1 млрд сум<div class="sc-th-hint">проверочный расчёт</div></th>
          <th class="sc-th sc-th-actions">Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.year" :class="{ 'sc-row-dirty': edits[r.year]?.dirty }">
          <td class="sc-td sc-td-year">
            <div class="sc-year-stack">
              <strong>{{ r.year }}</strong>
              <span v-if="r.label && r.label !== String(r.year)" class="sc-year-label">{{ r.label }}</span>
            </div>
            <span v-if="r.is_closed && !unlockedYears.has(r.year)" class="sc-chip sc-chip-closed">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>закрыт</span>
            <span v-if="r.is_closed && unlockedYears.has(r.year)" class="sc-chip sc-chip-unlocked">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>разблокирован</span>
            <button
              v-if="isAdmin && r.is_closed"
              type="button"
              class="sc-btn sc-btn-sm sc-btn-g"
              @click="toggleUnlock(r.year)"
              :title="unlockedYears.has(r.year) ? 'Снова заблокировать год' : 'Разблокировать год для редактирования (audit-trail запишет действие)'"
            >
              {{ unlockedYears.has(r.year) ? 'Заблокировать' : 'Разблокировать' }}
            </button>
          </td>
          <td class="sc-td">
            <div class="sc-input-wrap">
              <input type="text" class="sc-input"
                :value="edits[r.year]?.usd_rate ?? ''"
                @input="(e) => onFieldInput(r.year, 'usd_rate', (e.target as HTMLInputElement).value)"
                :disabled="!isEditable(r.year)" placeholder="—" />
              <span class="sc-input-unit">сум</span>
            </div>
          </td>
          <td class="sc-td">
            <div class="sc-input-wrap">
              <input type="text" class="sc-input"
                :value="edits[r.year]?.eur_rate ?? ''"
                @input="(e) => onFieldInput(r.year, 'eur_rate', (e.target as HTMLInputElement).value)"
                :disabled="!isEditable(r.year)" placeholder="—" />
              <span class="sc-input-unit">сум</span>
            </div>
          </td>
          <td class="sc-td">
            <div class="sc-input-wrap">
              <input type="text" class="sc-input"
                :value="edits[r.year]?.uz_budget_trln ?? ''"
                @input="(e) => onFieldInput(r.year, 'uz_budget_trln', (e.target as HTMLInputElement).value)"
                :disabled="!isEditable(r.year)" placeholder="—" />
              <span class="sc-input-unit">трлн</span>
            </div>
          </td>
          <td class="sc-td">
            <div class="sc-input-wrap">
              <input type="text" class="sc-input"
                :value="edits[r.year]?.gdp_bln ?? ''"
                @input="(e) => onFieldInput(r.year, 'gdp_bln', (e.target as HTMLInputElement).value)"
                :disabled="!isEditable(r.year)" placeholder="—" />
              <span class="sc-input-unit">млрд</span>
            </div>
          </td>
          <td class="sc-td sc-td-preview">{{ previewUsd(1, r.year) }}</td>
          <td class="sc-td sc-td-actions">
            <template v-if="isAdmin">
              <button class="sc-btn sc-btn-sm sc-btn-p"
                :disabled="!edits[r.year]?.dirty"
                @click="saveRow(r.year)">Сохранить</button>
              <button v-if="edits[r.year]?.dirty" class="sc-btn sc-btn-sm sc-btn-g"
                @click="resetRow(r.year)">Отмена</button>
              <button v-else class="sc-btn sc-btn-sm sc-btn-d"
                @click="confirmDelete = r.year">
                <svg viewBox="0 0 14 14" class="sc-svg" width="11" height="11"><path d="M3 4h8M5 4V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1M4 4l1 7a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1l1-7"/></svg>
              </button>
            </template>
            <span v-else class="sc-readonly">—</span>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- ─── Tab 2: Macroeconomics ─── -->
    <table v-else-if="rows.length && activeTab === 'macro'" class="sc-tbl">
      <thead>
        <tr>
          <th class="sc-th sc-th-year">Год</th>
          <th class="sc-th">Инфляция<div class="sc-th-hint">годовая, % CPI</div></th>
          <th class="sc-th">Ставка ЦБ<div class="sc-th-hint">базовая ставка ЦБ РУ, %</div></th>
          <th class="sc-th">Рост ВВП<div class="sc-th-hint">темп реального роста, %</div></th>
          <th class="sc-th sc-th-actions">Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.year" :class="{ 'sc-row-dirty': edits[r.year]?.dirty }">
          <td class="sc-td sc-td-year">
            <div class="sc-year-stack">
              <strong>{{ r.year }}</strong>
              <span v-if="r.label && r.label !== String(r.year)" class="sc-year-label">{{ r.label }}</span>
            </div>
            <span v-if="r.is_closed && !unlockedYears.has(r.year)" class="sc-chip sc-chip-closed">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>закрыт</span>
            <span v-if="r.is_closed && unlockedYears.has(r.year)" class="sc-chip sc-chip-unlocked">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>разблокирован</span>
            <button
              v-if="isAdmin && r.is_closed"
              type="button"
              class="sc-btn sc-btn-sm sc-btn-g"
              @click="toggleUnlock(r.year)"
              :title="unlockedYears.has(r.year) ? 'Снова заблокировать год' : 'Разблокировать год для редактирования (audit-trail запишет действие)'"
            >
              {{ unlockedYears.has(r.year) ? 'Заблокировать' : 'Разблокировать' }}
            </button>
          </td>
          <td class="sc-td">
            <div class="sc-input-wrap">
              <input type="text" class="sc-input"
                :value="edits[r.year]?.inflation_pct ?? ''"
                @input="(e) => onFieldInput(r.year, 'inflation_pct', (e.target as HTMLInputElement).value)"
                :disabled="!isEditable(r.year)" placeholder="—" />
              <span class="sc-input-unit">%</span>
            </div>
          </td>
          <td class="sc-td">
            <div class="sc-input-wrap">
              <input type="text" class="sc-input"
                :value="edits[r.year]?.cb_rate_pct ?? ''"
                @input="(e) => onFieldInput(r.year, 'cb_rate_pct', (e.target as HTMLInputElement).value)"
                :disabled="!isEditable(r.year)" placeholder="—" />
              <span class="sc-input-unit">%</span>
            </div>
          </td>
          <td class="sc-td">
            <div class="sc-input-wrap">
              <input type="text" class="sc-input"
                :value="edits[r.year]?.gdp_growth_pct ?? ''"
                @input="(e) => onFieldInput(r.year, 'gdp_growth_pct', (e.target as HTMLInputElement).value)"
                :disabled="!isEditable(r.year)" placeholder="—" />
              <span class="sc-input-unit">%</span>
            </div>
          </td>
          <td class="sc-td sc-td-actions">
            <template v-if="isAdmin">
              <button class="sc-btn sc-btn-sm sc-btn-p"
                :disabled="!edits[r.year]?.dirty"
                @click="saveRow(r.year)">Сохранить</button>
              <button v-if="edits[r.year]?.dirty" class="sc-btn sc-btn-sm sc-btn-g"
                @click="resetRow(r.year)">Отмена</button>
              <button v-else class="sc-btn sc-btn-sm sc-btn-d"
                @click="confirmDelete = r.year">
                <svg viewBox="0 0 14 14" class="sc-svg" width="11" height="11"><path d="M3 4h8M5 4V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1M4 4l1 7a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1l1-7"/></svg>
              </button>
            </template>
            <span v-else class="sc-readonly">—</span>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else-if="activeTab !== 'scenarios' && activeTab !== 'credit' && activeTab !== 'elastic'" class="sc-empty">
      В реестре нет ни одного года. Нажмите «Добавить год» чтобы создать первую запись.
    </div>

    <footer v-if="activeTab !== 'scenarios' && activeTab !== 'credit' && activeTab !== 'elastic'" class="sc-foot">
      <strong>Как это работает:</strong>
      Курсы USD/EUR/UZS — переключатель валют во всех KPI и модалках исполнительного
      дашборда. Бюджет Республики — расчёт «процент бюджета Республики» в налоговом блоке.
      Макроэкономические показатели — справочные значения для аналитических отчётов
      и фильтров. Изменения сохраняются моментально и подхватываются всеми открытыми
      блоками без перезагрузки страницы.
      <br />
      <small>
        Для добавления других валют или индикаторов (CNY, RUB, ставка рефинансирования
        и т.д.) — нужна миграция БД (новая колонка в <code>year_registry</code>).
        Эта страница расширится автоматически после добавления соответствующего поля
        в схему.
      </small>
    </footer>

    <!-- ─── Add modal ─── -->
    <ModalShell :open="addOpen" size="md" title="Добавить год в реестр" @close="closeAdd">
          <div class="sc-form">
            <label class="sc-fld">
              <span class="sc-fld-l">Год</span>
              <input type="number" min="2000" max="2100" v-model.number="addForm.year" class="sc-input"/>
            </label>
            <label class="sc-fld">
              <span class="sc-fld-l">Метка <span class="sc-fld-hint">опциональная подпись, например «FY 2027 · план»</span></span>
              <input type="text" v-model="addForm.label" class="sc-input" placeholder="по умолчанию = год"/>
            </label>
            <div class="sc-form-section">Валюты и бюджет</div>
            <label class="sc-fld">
              <span class="sc-fld-l">Курс USD / UZS <span class="sc-fld-hint">сум за 1 USD</span></span>
              <input type="text" v-model="addForm.usd_rate" class="sc-input" placeholder="например 12576.41"/>
            </label>
            <label class="sc-fld">
              <span class="sc-fld-l">Курс EUR / UZS <span class="sc-fld-hint">сум за 1 EUR</span></span>
              <input type="text" v-model="addForm.eur_rate" class="sc-input" placeholder="например 14140"/>
            </label>
            <label class="sc-fld">
              <span class="sc-fld-l">Бюджет Республики <span class="sc-fld-hint">трлн сум</span></span>
              <input type="text" v-model="addForm.uz_budget_trln" class="sc-input" placeholder="например 350"/>
            </label>
            <div class="sc-form-section">Макроэкономика <span class="sc-form-section-hint">опционально</span></div>
            <label class="sc-fld">
              <span class="sc-fld-l">Инфляция <span class="sc-fld-hint">годовая CPI, %</span></span>
              <input type="text" v-model="addForm.inflation_pct" class="sc-input" placeholder="например 9.5"/>
            </label>
            <label class="sc-fld">
              <span class="sc-fld-l">Ставка ЦБ <span class="sc-fld-hint">базовая, %</span></span>
              <input type="text" v-model="addForm.cb_rate_pct" class="sc-input" placeholder="например 14"/>
            </label>
            <label class="sc-fld">
              <span class="sc-fld-l">Рост ВВП <span class="sc-fld-hint">реальный, %</span></span>
              <input type="text" v-model="addForm.gdp_growth_pct" class="sc-input" placeholder="например 5.6"/>
            </label>
            <div v-if="addError" class="sc-alert sc-alert-bad">{{ addError }}</div>
          </div>
      <template #footer>
        <button class="sc-btn sc-btn-g" @click="closeAdd" :disabled="addSubmitting">Отмена</button>
        <button class="sc-btn sc-btn-p" @click="submitAdd" :disabled="addSubmitting">
          {{ addSubmitting ? "Создание…" : "Создать" }}
        </button>
      </template>
    </ModalShell>

    <!-- ─── Delete confirm ─── -->
    <ModalShell :open="confirmDelete != null" size="sm" :title="'Удалить год ' + (confirmDelete ?? '') + '?'" @close="confirmDelete = null">
          <p class="sc-modal-text">
            Эта операция необратима. Если на этот год есть рейтинги, финансовые
            данные или другие записи — удаление будет отклонено сервером.
            Обычно безопаснее обнулить значения вместо удаления.
          </p>
      <template #footer>
        <button class="sc-btn sc-btn-g" @click="confirmDelete = null">Отмена</button>
        <button class="sc-btn sc-btn-d" @click="doDelete">Удалить</button>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.sc-wrap { padding: 22px 26px; max-width: 1080px; margin: 0 auto; font-family: inherit; color: var(--t1, #1E2A4A); }
.sc-hdr { display: flex; justify-content: space-between; align-items: flex-end; gap: 22px; flex-wrap: wrap; margin-bottom: 22px; }
.sc-eyebrow { font-size: 10.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .08em; }
.sc-title { font-size: 22px; font-weight: 500; letter-spacing: -.02em; margin: 4px 0 6px; color: var(--t1, #1E2A4A); }
.sc-sub { font-size: 12px; color: var(--t3, #5F5E5A); line-height: 1.55; max-width: 680px; margin: 0; }

.sc-alert { padding: 10px 14px; border-radius: 8px; font-size: 12px; margin-bottom: 14px; }
.sc-alert-bad  { background: rgba(226, 75, 74, .08); color: var(--sev-critical); border: 1px solid rgba(226, 75, 74, .18); }
.sc-alert-good { background: rgba(29, 158, 117, .08); color: #0F6E56; border: 1px solid rgba(29, 158, 117, .18); }
.sc-alert-info { background: rgba(127, 119, 221, .07); color: var(--p-deep); border: 1px solid rgba(127, 119, 221, .18); }
.sc-alert code { background: rgba(15, 23, 60, .07); padding: 1px 6px; border-radius: 4px; font-family: ui-monospace, monospace; font-size: 11px; }

/* ─── Tabs ─── */
.sc-tabs { display: inline-flex; gap: 4px; padding: 3px; background: rgba(15, 23, 60, 0.05); border-radius: 9px; margin-bottom: 14px; }
.sc-tab { background: transparent; border: none; font-size: 11.5px; font-weight: 500; color: var(--t3, var(--t-muted)); padding: 6px 14px; border-radius: 6px; cursor: pointer; font-family: inherit; transition: all .14s; letter-spacing: .01em; }
.sc-tab:hover:not(.on) { color: var(--t1, #1E2A4A); background: rgba(255,255,255,.5); }
.sc-tab:hover:not(.on) { color: var(--t1, #1E2A4A); }
.sc-tab.on { background: var(--bg1, #fff); color: var(--t1, #1E2A4A); box-shadow: 0 1px 3px rgba(15, 23, 60, 0.08); }

.sc-loading { text-align: center; color: var(--t3, var(--t-muted)); padding: 40px; font-size: 12px; }
.sc-empty { text-align: center; color: var(--t3, var(--t-muted)); padding: 60px 20px; background: var(--bg2, #FAFAFC); border-radius: 12px; font-size: 12.5px; }

.sc-tbl { width: 100%; border-collapse: separate; border-spacing: 0; background: var(--bg1, #fff); border-radius: 12px; box-shadow: 0 4px 14px rgba(15, 23, 60, 0.06); overflow: hidden; }
.sc-th { text-align: left; padding: 13px 14px; font-size: 10.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .07em; background: var(--bg2, #FAFAFC); border-bottom: 1px solid rgba(0, 0, 0, .05); vertical-align: top; }
.sc-th-hint { display: block; text-transform: none; letter-spacing: 0; font-size: 10px; color: #B4B2A9; font-weight: 400; margin-top: 2px; }
.sc-th-year { width: 90px; }
.sc-th-actions { width: 200px; }
.sc-th-preview { width: 160px; }

.sc-td { padding: 11px 14px; border-bottom: 1px solid rgba(0, 0, 0, .04); font-size: 12.5px; vertical-align: middle; }
.sc-td-year { font-weight: 500; color: var(--t1, #1E2A4A); font-feature-settings: "tnum"; display: flex; align-items: center; gap: 8px; }
.sc-td-preview { color: var(--t3, #5F5E5A); font-size: 11.5px; font-feature-settings: "tnum"; }
.sc-td-actions { white-space: nowrap; }
.sc-chip { font-size: 9.5px; color: var(--t3, var(--t-muted)); background: rgba(15, 23, 60, .06); padding: 2px 7px; border-radius: 999px; font-weight: 500; margin-left: 4px; }
.sc-chip-closed { background: rgba(226, 75, 74, .10); color: var(--sev-high); }
.sc-chip-unlocked { background: rgba(29, 158, 117, .10); color: var(--green); }
.sc-year-stack { display: inline-flex; flex-direction: column; gap: 1px; line-height: 1.2; }
.sc-year-label { font-size: 10px; color: var(--t3, var(--t-muted)); font-weight: 500; letter-spacing: 0.04em; }
.sc-alert-bad { white-space: pre-line; }

.sc-row-dirty { background: rgba(239, 159, 39, .035); }
.sc-row-dirty .sc-td { border-color: rgba(239, 159, 39, .15); }

.sc-input-wrap { position: relative; display: flex; align-items: center; }
.sc-input { font: inherit; font-size: 12.5px; padding: 6px 38px 6px 10px; border: 1px solid rgba(0, 0, 0, .12); border-radius: 6px; background: var(--bg1, #fff); color: var(--t1, #1E2A4A); width: 100%; max-width: 160px; font-feature-settings: "tnum"; transition: border-color .12s; }
.sc-input:focus { outline: none; border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .15); }
.sc-input:disabled { background: var(--bg2, #FAFAFC); color: var(--t3, var(--t-muted)); cursor: not-allowed; }
.sc-input-unit { position: absolute; right: 10px; font-size: 10px; color: var(--t3, var(--t-muted)); font-weight: 500; pointer-events: none; }

.sc-btn { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; font-weight: 500; padding: 7px 12px; border-radius: 7px; cursor: pointer; transition: all .14s; border: 1px solid transparent; font-family: inherit; }
.sc-btn-sm { font-size: 11px; padding: 5px 10px; }
.sc-btn-p { background: #7F77DD; color: #fff; }
.sc-btn-p:hover:not(:disabled) { background: #6B62C9; }
.sc-btn-g { background: var(--bg1, #fff); color: var(--t3, #5F5E5A); border-color: rgba(0, 0, 0, .12); }
.sc-btn-g:hover:not(:disabled) { background: #F5F4F9; color: var(--t1, #1E2A4A); }
.sc-btn-d { background: var(--bg1, #fff); color: var(--t3, var(--t-muted)); border-color: rgba(0, 0, 0, .12); }
.sc-btn-d:hover:not(:disabled) { background: rgba(226, 75, 74, .08); color: var(--sev-critical); border-color: rgba(226, 75, 74, .25); }
.sc-btn:disabled { opacity: .45; cursor: not-allowed; }

.sc-td-actions .sc-btn + .sc-btn { margin-left: 6px; }
.sc-readonly { color: #B4B2A9; font-size: 11px; }
.sc-svg { stroke: currentColor; stroke-width: 1.9; fill: none; stroke-linecap: round; stroke-linejoin: round; }

.sc-foot { margin-top: 22px; padding: 14px 16px; background: var(--bg2, #FAFAFC); border-radius: 10px; font-size: 11.5px; color: var(--t3, #5F5E5A); line-height: 1.6; }
.sc-foot strong { color: var(--t1, #1E2A4A); font-weight: 500; margin-right: 4px; }
.sc-foot small { display: block; margin-top: 6px; font-size: 10.5px; color: var(--t3, var(--t-muted)); }
.sc-foot code { background: rgba(15, 23, 60, .07); padding: 1px 5px; border-radius: 3px; font-family: ui-monospace, monospace; font-size: 10px; }

/* Modals */
.sc-modal-bd { position: fixed; inset: 0; background: rgba(15, 18, 40, 0.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); z-index: 9000; display: flex; align-items: center; justify-content: center; padding: 20px; animation: scBdIn .25s ease both; overflow-y: auto; }
.sc-modal { position: relative; background: var(--card-bg, rgba(255,255,255,0.86)); border: 1px solid var(--card-border, transparent); border-radius: 14px; box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10); padding: 22px 24px; width: 100%; max-width: 480px; animation: scModalIn .35s var(--ease-standard) .05s both; max-height: 90dvh; overflow-y: auto; }
.sc-modal-sm { max-width: 420px; }
.sc-modal-x { position: absolute; top: 12px; right: 12px; width: 26px; height: 26px; border-radius: 7px; display: flex; align-items: center; justify-content: center; color: var(--t3, var(--t-muted)); background: var(--bg1, #fff); border: 1px solid rgba(0, 0, 0, .08); cursor: pointer; }
.sc-modal-h { font-size: 16px; font-weight: 500; margin: 0 0 14px; color: var(--t1, #1E2A4A); }
.sc-modal-text { font-size: 12.5px; color: var(--t3, #5F5E5A); line-height: 1.55; margin: 0 0 18px; }
.sc-form { display: flex; flex-direction: column; gap: 10px; margin-bottom: 18px; }
.sc-form-section { font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .07em; margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(0, 0, 0, .06); }
.sc-form-section-hint { text-transform: none; letter-spacing: 0; font-weight: 400; color: #B4B2A9; margin-left: 6px; }
.sc-fld { display: flex; flex-direction: column; gap: 4px; }
.sc-fld-l { font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; text-transform: uppercase; letter-spacing: .05em; }
.sc-fld-hint { color: #B4B2A9; text-transform: none; letter-spacing: 0; font-weight: 400; margin-left: 4px; }
.sc-fld .sc-input { max-width: none; }
.sc-modal-ftr { display: flex; justify-content: flex-end; gap: 8px; }

@keyframes scBdIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes scModalIn { from { opacity: 0; transform: translateY(20px) scale(.96); } to { opacity: 1; transform: translateY(0) scale(1); } }

@media (max-width: 720px) {
  .sc-tbl { font-size: 11.5px; }
  .sc-td-preview, .sc-th-preview { display: none; }
  .sc-input { max-width: 110px; }
}
@media (max-width: 900px) {
  .sc-input { max-width: 130px; }
}
</style>
