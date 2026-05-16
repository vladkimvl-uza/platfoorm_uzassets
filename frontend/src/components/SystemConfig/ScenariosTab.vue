<script setup lang="ts">
/**
 * ScenariosTab.vue — Pack 7.40
 * ─────────────────────────────────────────────────────────────────
 * Третья вкладка /admin/system-config — «Сценарии и прогнозы».
 *
 * Что внутри:
 *   • Объясняющий хедер «Что такое сценарии»
 *   • Карточки сценариев (Базовый/Опт/Пес + custom) — клик переключает активный
 *   • Детали активного сценария (имя, описание, действия)
 *   • Таблица override'ов по годам (редактируемые ячейки)
 *   • Модалка добавления нового custom сценария
 *   • Кнопка удаления (только для custom — seeded неудаляемые)
 *   • Подсказки InfoTooltip везде, максимально простыми словами
 *
 * Изоляция:
 *   Сценарии используются ТОЛЬКО внутри этой вкладки. Глобальные блоки
 *   (Финансы / Tax / EE / BP / Дашборд) продолжают показывать ФАКТ —
 *   не подменяются активным сценарием.
 *
 * Доступ:
 *   • Чтение — любой пользователь
 *   • Запись — только admin (is_owner или admin.users)
 */
import { computed, onMounted, ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useScenarios } from "@/composables/useScenarios";
import type { ScenarioOverride } from "@/api/scenarios";
import InfoTooltip from "./InfoTooltip.vue";

const auth = useAuthStore();
const sc = useScenarios();

// ─── Admin check ───
const isAdmin = computed<boolean>(() => {
  const u: any = auth.user;
  if (!u) return false;
  if (u.is_owner === true || u.is_admin === true) return true;
  const roles: string[] = Array.isArray(u.roles) ? u.roles : [];
  return roles.includes("admin") || roles.includes("ROLE_ADMIN") || roles.includes("ROLE_OWNER");
});

// ─── Edit state ───
// edits.value[scenarioId][year][field] = string
type FieldKey =
  | "inflation_pct" | "cb_rate_pct" | "gdp_growth_pct"
  | "usd_rate" | "eur_rate" | "uz_budget_trln";
const ALL_FIELDS: FieldKey[] = [
  "inflation_pct", "cb_rate_pct", "gdp_growth_pct",
  "usd_rate", "eur_rate", "uz_budget_trln",
];

type RowEdit = Record<FieldKey, string> & { dirty: boolean };
const edits = ref<Record<string, Record<number, RowEdit>>>({});

const errorMsg = ref<string | null>(null);
const successMsg = ref<string | null>(null);

// ─── Add new scenario modal ───
const addOpen = ref(false);
const addForm = ref({ code: "", name_ru: "", description: "", color_hex: "#7F77DD" });
const addError = ref<string | null>(null);
const addSubmitting = ref(false);

// ─── Confirm delete ───
const confirmDeleteId = ref<string | null>(null);

// ─── Available years (from existing overrides + a default span) ───
const yearList = computed<number[]>(() => {
  const set = new Set<number>();
  for (const s of sc.scenarios.value) {
    for (const o of s.overrides) set.add(o.year);
  }
  // Гарантируем что 2025, 2026, 2027 показываются всегда
  set.add(2025);
  set.add(2026);
  set.add(2027);
  return [...set].sort((a, b) => a - b);
});

// ─── Load ───
onMounted(async () => {
  try {
    await sc.load();
    syncEditsFromState();
  } catch (err: any) {
    errorMsg.value =
      err?.response?.data?.detail ||
      err?.message ||
      "Не удалось загрузить сценарии";
  }
});

// Initialize edits buffer from server state
function syncEditsFromState() {
  const next: Record<string, Record<number, RowEdit>> = {};
  for (const s of sc.scenarios.value) {
    next[s.id] = {};
    for (const y of yearList.value) {
      const ov = s.overrides.find((o) => o.year === y);
      next[s.id][y] = {
        inflation_pct: ov?.inflation_pct != null ? String(ov.inflation_pct) : "",
        cb_rate_pct: ov?.cb_rate_pct != null ? String(ov.cb_rate_pct) : "",
        gdp_growth_pct: ov?.gdp_growth_pct != null ? String(ov.gdp_growth_pct) : "",
        usd_rate: ov?.usd_rate != null ? String(ov.usd_rate) : "",
        eur_rate: ov?.eur_rate != null ? String(ov.eur_rate) : "",
        uz_budget_trln: ov?.uz_budget_trln != null ? String(ov.uz_budget_trln) : "",
        dirty: false,
      };
    }
  }
  edits.value = next;
}

// ─── Picker ───
function pickScenario(id: string) {
  sc.setActiveId(id);
  errorMsg.value = null;
  successMsg.value = null;
}

// ─── Editing ───
function getActiveEditRow(year: number): RowEdit | null {
  const id = sc.activeId.value;
  if (!id) return null;
  if (!edits.value[id]) return null;
  return edits.value[id][year] ?? null;
}

function onFieldInput(scenarioId: string, year: number, field: FieldKey, value: string) {
  if (!edits.value[scenarioId] || !edits.value[scenarioId][year]) return;
  edits.value[scenarioId][year][field] = value;
  edits.value[scenarioId][year].dirty = isRowDirty(scenarioId, year);
}

function isRowDirty(scenarioId: string, year: number): boolean {
  const scenario = sc.scenarios.value.find((x) => x.id === scenarioId);
  const ov = scenario?.overrides.find((o) => o.year === year);
  const e = edits.value[scenarioId]?.[year];
  if (!e) return false;
  for (const f of ALL_FIELDS) {
    const orig = ov?.[f] != null ? String(ov[f]) : "";
    if (e[f] !== orig) return true;
  }
  return false;
}

function parseDecimal(s: string): number | null {
  if (s == null || s === "") return null;
  const cleaned = String(s).replace(/\s+/g, "").replace(",", ".");
  const n = Number(cleaned);
  return isFinite(n) ? n : null;
}

async function saveRow(year: number) {
  const id = sc.activeId.value;
  if (!id) return;
  const row = edits.value[id]?.[year];
  if (!row || !row.dirty) return;

  errorMsg.value = null;
  successMsg.value = null;

  // Validate
  const parsed: Record<string, number | null> = {};
  const labels: Record<FieldKey, string> = {
    inflation_pct: "инфляции",
    cb_rate_pct: "ставки ЦБ",
    gdp_growth_pct: "роста ВВП",
    usd_rate: "USD",
    eur_rate: "EUR",
    uz_budget_trln: "бюджета",
  };
  for (const f of ALL_FIELDS) {
    const v = parseDecimal(row[f]);
    if (row[f] !== "" && v === null) {
      errorMsg.value = `Год ${year}: некорректное значение ${labels[f]}`;
      return;
    }
    parsed[f] = v;
  }

  try {
    const ov = await sc.upsertOverride(id, year, parsed as any);
    // Sync edit row from new ov
    edits.value[id][year] = {
      inflation_pct: ov.inflation_pct != null ? String(ov.inflation_pct) : "",
      cb_rate_pct: ov.cb_rate_pct != null ? String(ov.cb_rate_pct) : "",
      gdp_growth_pct: ov.gdp_growth_pct != null ? String(ov.gdp_growth_pct) : "",
      usd_rate: ov.usd_rate != null ? String(ov.usd_rate) : "",
      eur_rate: ov.eur_rate != null ? String(ov.eur_rate) : "",
      uz_budget_trln: ov.uz_budget_trln != null ? String(ov.uz_budget_trln) : "",
      dirty: false,
    };
    successMsg.value = `Год ${year}: сохранено`;
    setTimeout(() => {
      if (successMsg.value?.includes(String(year))) successMsg.value = null;
    }, 2500);
  } catch (err: any) {
    errorMsg.value =
      err?.response?.data?.detail ||
      err?.message ||
      "Сохранение не удалось";
  }
}

function resetRow(year: number) {
  const id = sc.activeId.value;
  if (!id) return;
  const scenario = sc.scenarios.value.find((x) => x.id === id);
  const ov = scenario?.overrides.find((o) => o.year === year);
  if (!edits.value[id]?.[year]) return;
  edits.value[id][year] = {
    inflation_pct: ov?.inflation_pct != null ? String(ov.inflation_pct) : "",
    cb_rate_pct: ov?.cb_rate_pct != null ? String(ov.cb_rate_pct) : "",
    gdp_growth_pct: ov?.gdp_growth_pct != null ? String(ov.gdp_growth_pct) : "",
    usd_rate: ov?.usd_rate != null ? String(ov.usd_rate) : "",
    eur_rate: ov?.eur_rate != null ? String(ov.eur_rate) : "",
    uz_budget_trln: ov?.uz_budget_trln != null ? String(ov.uz_budget_trln) : "",
    dirty: false,
  };
}

async function clearYearOverride(year: number) {
  const id = sc.activeId.value;
  if (!id) return;
  errorMsg.value = null;
  try {
    // Full clear: set every override field to NULL via upsert
    await sc.upsertOverride(id, year, {
      inflation_pct: null,
      cb_rate_pct: null,
      gdp_growth_pct: null,
      usd_rate: null,
      eur_rate: null,
      uz_budget_trln: null,
      notes: null,
    });
    // Reload edit row
    edits.value[id][year] = {
      inflation_pct: "", cb_rate_pct: "", gdp_growth_pct: "",
      usd_rate: "", eur_rate: "", uz_budget_trln: "",
      dirty: false,
    };
    successMsg.value = `Год ${year}: override очищен (вернулись к базе)`;
    setTimeout(() => {
      if (successMsg.value?.includes(String(year))) successMsg.value = null;
    }, 2500);
  } catch (err: any) {
    errorMsg.value =
      err?.response?.data?.detail ||
      err?.message ||
      "Очистка не удалась";
  }
}

// ─── Add scenario ───
function openAdd() {
  addError.value = null;
  // Generate suggested code from name later; keep blank initially
  addForm.value = {
    code: "",
    name_ru: "",
    description: "",
    color_hex: "#7F77DD",
  };
  addOpen.value = true;
}
function closeAdd() {
  addOpen.value = false;
  addError.value = null;
}

async function submitAdd() {
  addError.value = null;
  const code = addForm.value.code.trim().toLowerCase();
  const name = addForm.value.name_ru.trim();
  if (!code) {
    addError.value = "Код сценария обязателен (например custom_2030_plan)";
    return;
  }
  if (!/^[a-z0-9_]+$/.test(code)) {
    addError.value = "Код может содержать только латиницу, цифры и нижнее подчёркивание";
    return;
  }
  if (!name) {
    addError.value = "Название сценария обязательно";
    return;
  }
  if (sc.scenarios.value.some((s) => s.code === code)) {
    addError.value = `Сценарий с кодом '${code}' уже существует`;
    return;
  }
  addSubmitting.value = true;
  try {
    const created = await sc.create({
      code,
      name_ru: name,
      description: addForm.value.description.trim() || null,
      color_hex: addForm.value.color_hex || null,
      sort_order: sc.scenarios.value.length,
    });
    // Initialize edits buffer for new scenario
    edits.value[created.id] = {};
    for (const y of yearList.value) {
      edits.value[created.id][y] = {
        inflation_pct: "", cb_rate_pct: "", gdp_growth_pct: "",
        usd_rate: "", eur_rate: "", uz_budget_trln: "",
        dirty: false,
      };
    }
    sc.setActiveId(created.id);
    addOpen.value = false;
    successMsg.value = `Сценарий «${created.name_ru}» создан`;
    setTimeout(() => {
      if (successMsg.value?.includes("создан")) successMsg.value = null;
    }, 2500);
  } catch (err: any) {
    addError.value =
      err?.response?.data?.detail ||
      err?.message ||
      "Создание не удалось";
  } finally {
    addSubmitting.value = false;
  }
}

// ─── Delete scenario ───
function askDelete(id: string) {
  confirmDeleteId.value = id;
}
async function doDelete() {
  const id = confirmDeleteId.value;
  if (!id) return;
  errorMsg.value = null;
  try {
    await sc.remove(id);
    delete edits.value[id];
    confirmDeleteId.value = null;
    successMsg.value = "Сценарий удалён";
    setTimeout(() => {
      if (successMsg.value?.includes("удалён")) successMsg.value = null;
    }, 2500);
  } catch (err: any) {
    errorMsg.value =
      err?.response?.data?.detail ||
      err?.message ||
      "Удаление не удалось";
  }
}

// ─── Display helpers ───
function fmtNum(v: number | null | undefined, suffix = ""): string {
  if (v == null) return "—";
  return v.toLocaleString("ru-RU", { maximumFractionDigits: 4 }) + suffix;
}

// Indicates if a field has an override value (not empty string)
function hasOverride(year: number, field: FieldKey): boolean {
  const r = getActiveEditRow(year);
  if (!r) return false;
  return r[field] !== "" && r[field] != null;
}

function getOverride(id: string, year: number): ScenarioOverride | null {
  const scenario = sc.scenarios.value.find((s) => s.id === id);
  return scenario?.overrides.find((o) => o.year === year) ?? null;
}
</script>

<template>
  <div class="st-wrap">
    <!-- Header -->
    <div class="st-hdr">
      <div>
        <div class="st-eyebrow">
          Системные константы
          <InfoTooltip placement="bottom" align="left">
            <strong>Зачем это нужно?</strong><br>
            Сценарии нужны чтобы посмотреть «<em>а что если</em>». Например:
            «Что будет с EBITDA портфеля если инфляция упадёт до 7% а ВВП
            вырастет на 8%?». Каждый сценарий — это набор предположений
            о будущем, и платформа считает прогноз именно по этим предположениям.
          </InfoTooltip>
        </div>
        <h1 class="st-title">
          Сценарии и прогнозы
          <InfoTooltip placement="bottom" align="left" :width="320">
            <strong>Только в этой вкладке</strong><br>
            Сценарии работают изолированно — они не влияют на Финансы,
            Tax-блок, EE/BP и главный дашборд. Эти блоки продолжают
            показывать факт. Сценарии используются <em>только здесь</em>,
            а в будущем — в прогнозах (Pack 7.43).
          </InfoTooltip>
        </h1>
        <p class="st-sub">
          Создавайте наборы предположений (сценарии) и задавайте по годам
          альтернативные значения макропоказателей. Базовый сценарий — без
          отклонений, использует факт.
        </p>
      </div>
      <button
        v-if="isAdmin"
        class="st-btn st-btn-p"
        @click="openAdd"
        type="button"
      >
        <svg viewBox="0 0 14 14" class="st-svg" width="13" height="13"><path d="M7 3v8M3 7h8"/></svg>
        Новый сценарий
      </button>
    </div>

    <!-- Status messages -->
    <div v-if="errorMsg" class="st-alert st-alert-bad">{{ errorMsg }}</div>
    <div v-if="successMsg" class="st-alert st-alert-good">{{ successMsg }}</div>
    <div v-if="!isAdmin" class="st-alert st-alert-info">
      Просмотр доступен всем авторизованным пользователям. Редактировать
      сценарии и значения может только администратор (<code>admin.users</code>).
    </div>

    <div v-if="sc.loading.value" class="st-loading">Загрузка…</div>

    <template v-else>
      <!-- Scenario picker -->
      <div class="st-sec-l">
        <span>
          Сценарии
          <InfoTooltip placement="bottom" align="left">
            <strong>Что такое сценарий?</strong><br>
            Это набор предположений о будущем. Например, можно создать сценарий
            «Снижение цен на нефть в 2026» — задать в нём низкие значения USD/UZS
            и инфляции, и посмотреть как изменится прогноз портфеля.
            <br><br>
            Базовый сценарий — без изменений, использует факт. Оптимистичный
            и Пессимистичный — заранее заполнены типовыми отклонениями.
            Можно создавать свои.
          </InfoTooltip>
        </span>
        <span class="hint">клик — выбрать активный · {{ sc.scenarios.value.length }} {{ sc.scenarios.value.length === 1 ? "сценарий" : "сценариев" }}</span>
      </div>

      <div class="st-sc-grid">
        <button
          v-for="s in sc.scenarios.value"
          :key="s.id"
          type="button"
          class="st-sc"
          :class="{ on: s.id === sc.activeId.value }"
          :style="{ '--sc-color': s.color_hex || '#888780' }"
          @click="pickScenario(s.id)"
        >
          <span class="st-sc-l">{{ s.is_seeded ? "Системный" : "Кастомный" }}{{ s.id === sc.activeId.value ? " · активен" : "" }}</span>
          <span class="st-sc-n">{{ s.name_ru }}</span>
          <span v-if="s.description" class="st-sc-d">{{ s.description }}</span>
          <span class="st-sc-overrides">
            {{ s.overrides.length }} {{ s.overrides.length === 1 ? "год" : "года/лет" }} с отклонениями
          </span>
        </button>
      </div>

      <!-- Active scenario detail -->
      <template v-if="sc.activeScenario.value">
        <div class="st-active">
          <div class="st-active-meta">
            <div class="st-active-eyebrow">Активный сценарий</div>
            <div class="st-active-name">
              <span class="st-active-dot" :style="{ background: sc.activeScenario.value.color_hex || '#888780' }"></span>
              {{ sc.activeScenario.value.name_ru }}
              <span class="st-active-code">{{ sc.activeScenario.value.code }}</span>
            </div>
            <div v-if="sc.activeScenario.value.description" class="st-active-desc">
              {{ sc.activeScenario.value.description }}
            </div>
          </div>
          <div class="st-active-actions">
            <button
              v-if="isAdmin && !sc.activeScenario.value.is_seeded"
              type="button"
              class="st-btn st-btn-d"
              @click="askDelete(sc.activeScenario.value.id)"
            >
              <svg viewBox="0 0 14 14" class="st-svg" width="11" height="11"><path d="M3 4h8M5 4V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1M4 4l1 7a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1l1-7"/></svg>
              Удалить
            </button>
            <span v-else-if="sc.activeScenario.value.is_seeded" class="st-active-locked">
              Системный — нельзя удалить
              <InfoTooltip placement="left" align="right" :width="240">
                <strong>Почему нельзя удалить?</strong><br>
                Базовый / Оптимистичный / Пессимистичный — это набор
                предустановленных сценариев на которые ссылается логика
                платформы. Их можно очищать и редактировать, но удалять
                нет. Создайте свой кастомный сценарий рядом.
              </InfoTooltip>
            </span>
          </div>
        </div>

        <!-- Overrides editor -->
        <div class="st-sec-l">
          <span>
            Отклонения от базы по годам
            <InfoTooltip placement="bottom" align="left" :width="320">
              <strong>Что такое «отклонение»?</strong><br>
              Это значение, которое заменяет факт. Например, если в базе
              инфляция на 2026 = 11%, а в сценарии задано 7%, — значит
              «<em>предположим что инфляция упала до 7%</em>».
              <br><br>
              <strong>Пустое поле</strong> = «как в базе». Если поле очистить,
              для этого показателя берётся значение со вкладки «Макроэкономика».
            </InfoTooltip>
          </span>
          <span class="hint">
            пустое поле → используется значение со вкладки «Макроэкономика»
          </span>
        </div>

        <table class="st-tbl">
          <thead>
            <tr>
              <th class="st-th st-th-year">Год</th>
              <th class="st-th">
                Инфляция
                <InfoTooltip placement="bottom" align="left">
                  <strong>Инфляция, % за год</strong><br>
                  На сколько в среднем выросли цены за год. Если 10% — то
                  товар, который стоил 100 сум, теперь стоит 110.
                </InfoTooltip>
                <div class="st-th-hint">%</div>
              </th>
              <th class="st-th">
                Ставка ЦБ
                <InfoTooltip placement="bottom" align="left">
                  <strong>Базовая ставка ЦБ РУ, %</strong><br>
                  Под какой процент банки берут деньги у Центрального банка.
                  Чем выше — тем дороже кредиты в экономике, и наоборот.
                </InfoTooltip>
                <div class="st-th-hint">%</div>
              </th>
              <th class="st-th">
                Рост ВВП
                <InfoTooltip placement="bottom" align="left">
                  <strong>Темп роста ВВП, %</strong><br>
                  На сколько выросла экономика страны за год. Если +5% —
                  экономика на 5% больше чем была в прошлом году.
                </InfoTooltip>
                <div class="st-th-hint">%</div>
              </th>
              <th class="st-th">
                USD / UZS
                <InfoTooltip placement="bottom" align="center">
                  <strong>Курс доллара</strong><br>
                  Сколько узбекских сумов стоит 1 доллар США (в среднем за год).
                </InfoTooltip>
                <div class="st-th-hint">сум за 1 USD</div>
              </th>
              <th class="st-th">
                EUR / UZS
                <InfoTooltip placement="bottom" align="center">
                  <strong>Курс евро</strong><br>
                  Сколько узбекских сумов стоит 1 евро (в среднем за год).
                </InfoTooltip>
                <div class="st-th-hint">сум за 1 EUR</div>
              </th>
              <th class="st-th">
                Бюджет
                <InfoTooltip placement="bottom" align="center">
                  <strong>Бюджет Республики</strong><br>
                  Сколько денег планирует получить государство за год,
                  в триллионах сумов (доходная часть).
                </InfoTooltip>
                <div class="st-th-hint">трлн сум</div>
              </th>
              <th class="st-th st-th-actions">Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="year in yearList"
              :key="year"
              :class="{ 'st-row-dirty': getActiveEditRow(year)?.dirty }"
            >
              <td class="st-td st-td-year">
                <strong>{{ year }}</strong>
                <span
                  v-if="getOverride(sc.activeId.value!, year)"
                  class="st-chip"
                  title="Есть отклонения от базы"
                >override</span>
              </td>
              <td v-for="f in ALL_FIELDS" :key="f" class="st-td">
                <input
                  type="text"
                  class="st-input"
                  :class="{ 'st-input-ovr': hasOverride(year, f) }"
                  :value="getActiveEditRow(year)?.[f] ?? ''"
                  @input="(e) => onFieldInput(sc.activeId.value!, year, f, (e.target as HTMLInputElement).value)"
                  :disabled="!isAdmin"
                  placeholder="—"
                />
              </td>
              <td class="st-td st-td-actions">
                <template v-if="isAdmin">
                  <button
                    type="button"
                    class="st-btn st-btn-sm st-btn-p"
                    :disabled="!getActiveEditRow(year)?.dirty"
                    @click="saveRow(year)"
                  >Сохранить</button>
                  <button
                    v-if="getActiveEditRow(year)?.dirty"
                    type="button"
                    class="st-btn st-btn-sm st-btn-g"
                    @click="resetRow(year)"
                  >Отмена</button>
                  <button
                    v-else
                    type="button"
                    class="st-btn st-btn-sm st-btn-g"
                    :disabled="!getOverride(sc.activeId.value!, year)"
                    @click="clearYearOverride(year)"
                    title="Очистить все отклонения для года (вернуться к базе)"
                  >Очистить</button>
                </template>
                <span v-else class="st-readonly">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </template>

      <!-- Empty state if no scenarios -->
      <div v-if="!sc.activeScenario.value && sc.scenarios.value.length === 0" class="st-empty">
        Сценарии ещё не настроены. Системные сценарии (Базовый/Оптимистичный/Пессимистичный)
        обычно создаются автоматически при первом запуске. Если их нет —
        перезапустите backend (self-heal создаст их).
      </div>

      <!-- Footer help -->
      <footer class="st-foot">
        <div class="st-foot-grid">
          <div class="st-foot-card">
            <div class="st-foot-card-icon" style="background:rgba(127,119,221,.10); color:#534AB7;">1</div>
            <div>
              <strong>Базовый — про факт.</strong> Использует значения
              со вкладки «Макроэкономика» без изменений. Это «<em>что есть
              на самом деле</em>».
            </div>
          </div>
          <div class="st-foot-card">
            <div class="st-foot-card-icon" style="background:rgba(29,158,117,.10); color:#0F6E56;">2</div>
            <div>
              <strong>Оптимистичный — про «лучше».</strong> Заранее заполнены
              пониженная инфляция, ускоренный ВВП, более крепкий сум.
              Подходит для лучших оценок NPV и плановых KPI.
            </div>
          </div>
          <div class="st-foot-card">
            <div class="st-foot-card-icon" style="background:rgba(226,75,74,.10); color:#A32D2D;">3</div>
            <div>
              <strong>Пессимистичный — про «хуже».</strong> Высокая инфляция,
              высокая ставка, ослабление сума. Используйте для стресс-тестов.
            </div>
          </div>
          <div class="st-foot-card">
            <div class="st-foot-card-icon" style="background:rgba(239,159,39,.10); color:#854F0B;">4</div>
            <div>
              <strong>Кастомные — про любую идею.</strong> Создавайте под
              конкретную задачу: «Шок 2026», «План Правительства РУ 2030»,
              «Только бюджетные ограничения». Без лимита.
            </div>
          </div>
        </div>
        <div class="st-foot-bottom">
          Дальнейшее развитие (Pack 7.41–7.43): матрица коэффициентов влияния
          (эластичности), эффект проектов трансформации в цифрах,
          и многолетний прогноз с декомпозицией «база + макро + проекты».
        </div>
      </footer>
    </template>

    <!-- ─── Add scenario modal ─── -->
    <Teleport to="body">
      <div v-if="addOpen" class="st-modal-bd" @click.self="closeAdd">
        <div class="st-modal">
          <button class="st-modal-x" @click="closeAdd" aria-label="Закрыть">
            <svg viewBox="0 0 14 14" class="st-svg" width="13" height="13"><path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/></svg>
          </button>
          <h2 class="st-modal-h">Создать кастомный сценарий</h2>
          <div class="st-form">
            <label class="st-fld">
              <span class="st-fld-l">
                Название
                <InfoTooltip placement="right" align="right">
                  <strong>Название сценария</strong><br>
                  Любое имя по-русски. Например: «Шок 2026», «План
                  Правительства 2030», «Стресс-тест по ставке ЦБ».
                </InfoTooltip>
              </span>
              <input type="text" v-model="addForm.name_ru" class="st-input" placeholder="Например: Шок 2026" />
            </label>
            <label class="st-fld">
              <span class="st-fld-l">
                Код
                <InfoTooltip placement="right" align="right">
                  <strong>Код (англ.)</strong><br>
                  Уникальный идентификатор. Маленькие латинские буквы,
                  цифры и нижнее подчёркивание. Например: <code>shock_2026</code>,
                  <code>government_plan_2030</code>.
                </InfoTooltip>
              </span>
              <input type="text" v-model="addForm.code" class="st-input" placeholder="например shock_2026"/>
            </label>
            <label class="st-fld">
              <span class="st-fld-l">
                Описание <span class="st-fld-hint">(опционально)</span>
              </span>
              <textarea v-model="addForm.description" class="st-input st-textarea" rows="3" placeholder="Кратко: о чём этот сценарий, что моделирует, для чего использовать"></textarea>
            </label>
            <label class="st-fld">
              <span class="st-fld-l">
                Цвет акцента
                <InfoTooltip placement="right" align="right">
                  <strong>Цвет</strong><br>
                  Используется для полоски акцента в карточке сценария
                  и индикации в будущих графиках декомпозиции.
                </InfoTooltip>
              </span>
              <input type="color" v-model="addForm.color_hex" class="st-input st-color"/>
            </label>
            <div v-if="addError" class="st-alert st-alert-bad">{{ addError }}</div>
          </div>
          <div class="st-modal-ftr">
            <button class="st-btn st-btn-g" @click="closeAdd" :disabled="addSubmitting">Отмена</button>
            <button class="st-btn st-btn-p" @click="submitAdd" :disabled="addSubmitting">
              {{ addSubmitting ? "Создание…" : "Создать" }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ─── Delete confirm ─── -->
    <Teleport to="body">
      <div v-if="confirmDeleteId" class="st-modal-bd" @click.self="confirmDeleteId = null">
        <div class="st-modal st-modal-sm">
          <h2 class="st-modal-h">Удалить сценарий?</h2>
          <p class="st-modal-text">
            Все отклонения (override'ы) этого сценария будут удалены безвозвратно.
            Если на сценарий ссылаются какие-то отчёты — удаление будет отклонено.
            Обычно безопаснее очистить override'ы а сам сценарий оставить.
          </p>
          <div class="st-modal-ftr">
            <button class="st-btn st-btn-g" @click="confirmDeleteId = null">Отмена</button>
            <button class="st-btn st-btn-d" @click="doDelete">Удалить</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.st-wrap { font-family: inherit; color: #1E2A4A; }
.st-hdr { display: flex; justify-content: space-between; align-items: flex-end; gap: 22px; flex-wrap: wrap; margin-bottom: 20px; }
.st-eyebrow { font-size: 10.5px; font-weight: 500; color: #888780; text-transform: uppercase; letter-spacing: .08em; display: flex; align-items: center; gap: 2px; }
.st-title { font-size: 22px; font-weight: 500; letter-spacing: -.02em; margin: 4px 0 6px; color: #1E2A4A; display: flex; align-items: center; gap: 4px; }
.st-sub { font-size: 12px; color: #5F5E5A; line-height: 1.55; max-width: 680px; margin: 0; }

.st-alert { padding: 10px 14px; border-radius: 8px; font-size: 12px; margin-bottom: 14px; }
.st-alert-bad  { background: rgba(226, 75, 74, .08); color: #A32D2D; border: 1px solid rgba(226, 75, 74, .18); }
.st-alert-good { background: rgba(29, 158, 117, .08); color: #0F6E56; border: 1px solid rgba(29, 158, 117, .18); }
.st-alert-info { background: rgba(127, 119, 221, .07); color: #534AB7; border: 1px solid rgba(127, 119, 221, .18); }
.st-alert code { background: rgba(15, 23, 60, .07); padding: 1px 6px; border-radius: 4px; font-family: ui-monospace, monospace; font-size: 11px; }

.st-loading { text-align: center; color: #888780; padding: 40px; font-size: 12px; }
.st-empty { text-align: center; color: #888780; padding: 60px 20px; background: #FAFAFC; border-radius: 12px; font-size: 12.5px; }

.st-sec-l { font-size: 10px; color: #888780; text-transform: uppercase; letter-spacing: .07em; font-weight: 500; margin: 20px 0 10px; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.st-sec-l > span:first-child { display: flex; align-items: center; gap: 2px; }
.st-sec-l .hint { font-size: 9.5px; color: #B4B2A9; text-transform: none; letter-spacing: .02em; font-weight: 400; }

/* Scenario picker */
.st-sc-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; margin-bottom: 14px; }
.st-sc { position: relative; padding: 12px 14px 14px; background: #fff; border: 1px solid rgba(0,0,0,.06); border-radius: 9px; cursor: pointer; transition: all .14s; overflow: hidden; text-align: left; font-family: inherit; box-shadow: 0 1px 3px rgba(15, 23, 60, .03); display: flex; flex-direction: column; gap: 4px; min-height: 95px; }
.st-sc::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--sc-color, #B4B2A9); }
.st-sc:hover { border-color: rgba(0,0,0,.10); box-shadow: 0 4px 12px rgba(15, 23, 60, .06); }
.st-sc.on { border-color: rgba(127, 119, 221, .35); box-shadow: 0 4px 16px rgba(127, 119, 221, .10); }
.st-sc-l { font-size: 9.5px; color: #888780; font-weight: 500; text-transform: uppercase; letter-spacing: .07em; }
.st-sc-n { font-size: 14px; font-weight: 500; color: #1E2A4A; letter-spacing: -.005em; line-height: 1.25; }
.st-sc-d { font-size: 11px; color: #5F5E5A; line-height: 1.45; }
.st-sc-overrides { font-size: 10px; color: #888780; margin-top: auto; padding-top: 4px; }

/* Active scenario block */
.st-active { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; padding: 14px 16px; background: #FAFAFC; border-radius: 10px; margin-top: 8px; }
.st-active-meta { flex: 1; min-width: 0; }
.st-active-eyebrow { font-size: 9.5px; color: #888780; font-weight: 500; text-transform: uppercase; letter-spacing: .07em; margin-bottom: 4px; }
.st-active-name { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 500; color: #1E2A4A; letter-spacing: -.005em; }
.st-active-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.st-active-code { font-family: ui-monospace, monospace; font-size: 10.5px; color: #888780; background: rgba(15, 23, 60, .06); padding: 2px 7px; border-radius: 4px; font-weight: 400; }
.st-active-desc { font-size: 11.5px; color: #5F5E5A; line-height: 1.55; margin-top: 6px; max-width: 620px; }
.st-active-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.st-active-locked { font-size: 11px; color: #888780; display: flex; align-items: center; gap: 4px; }

/* Table */
.st-tbl { width: 100%; border-collapse: separate; border-spacing: 0; background: #fff; border-radius: 12px; box-shadow: 0 4px 14px rgba(15, 23, 60, 0.06); overflow: hidden; margin-top: 4px; }
.st-th { text-align: left; padding: 11px 10px; font-size: 10.5px; font-weight: 500; color: #888780; text-transform: uppercase; letter-spacing: .07em; background: #FAFAFC; border-bottom: 1px solid rgba(0, 0, 0, .05); vertical-align: top; }
.st-th-hint { display: block; text-transform: none; letter-spacing: 0; font-size: 9.5px; color: #B4B2A9; font-weight: 400; margin-top: 1px; }
.st-th-year { width: 80px; }
.st-th-actions { width: 195px; }

.st-td { padding: 9px 10px; border-bottom: 1px solid rgba(0, 0, 0, .04); font-size: 12px; vertical-align: middle; }
.st-td-year { font-weight: 500; color: #1E2A4A; font-feature-settings: "tnum"; display: flex; align-items: center; gap: 6px; padding: 9px 10px; }
.st-td-actions { white-space: nowrap; }
.st-chip { font-size: 8.5px; color: #534AB7; background: rgba(127, 119, 221, .12); padding: 2px 6px; border-radius: 999px; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; }

.st-row-dirty { background: rgba(239, 159, 39, .035); }
.st-row-dirty .st-td { border-color: rgba(239, 159, 39, .15); }

.st-input { font: inherit; font-size: 11.5px; padding: 5px 8px; border: 1px solid rgba(0, 0, 0, .12); border-radius: 5px; background: #fff; color: #1E2A4A; width: 100%; min-width: 60px; max-width: 110px; font-feature-settings: "tnum"; transition: border-color .12s, background-color .14s; }
.st-input:focus { outline: none; border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .15); }
.st-input:disabled { background: #FAFAFC; color: #888780; cursor: not-allowed; }
.st-input-ovr { background: rgba(127, 119, 221, .04); border-color: rgba(127, 119, 221, .25); font-weight: 500; }

.st-btn { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; font-weight: 500; padding: 7px 12px; border-radius: 7px; cursor: pointer; transition: all .14s; border: 1px solid transparent; font-family: inherit; }
.st-btn-sm { font-size: 10.5px; padding: 4px 9px; }
.st-btn-p { background: #7F77DD; color: #fff; }
.st-btn-p:hover:not(:disabled) { background: #6B62C9; }
.st-btn-g { background: #fff; color: #5F5E5A; border-color: rgba(0, 0, 0, .12); }
.st-btn-g:hover:not(:disabled) { background: #F5F4F9; color: #1E2A4A; }
.st-btn-d { background: #fff; color: #888780; border-color: rgba(0, 0, 0, .12); }
.st-btn-d:hover:not(:disabled) { background: rgba(226, 75, 74, .08); color: #A32D2D; border-color: rgba(226, 75, 74, .25); }
.st-btn:disabled { opacity: .45; cursor: not-allowed; }

.st-td-actions .st-btn + .st-btn { margin-left: 5px; }
.st-readonly { color: #B4B2A9; font-size: 11px; }
.st-svg { stroke: currentColor; stroke-width: 1.9; fill: none; stroke-linecap: round; stroke-linejoin: round; }

/* Footer */
.st-foot { margin-top: 22px; }
.st-foot-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.st-foot-card { display: flex; gap: 11px; padding: 12px 14px; background: #FAFAFC; border-radius: 9px; font-size: 11.5px; color: #5F5E5A; line-height: 1.55; }
.st-foot-card-icon { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 500; flex-shrink: 0; margin-top: 1px; }
.st-foot-card strong { color: #1E2A4A; font-weight: 500; }
.st-foot-card em { font-style: italic; color: #534AB7; font-weight: 400; }
.st-foot-bottom { margin-top: 12px; padding: 11px 14px; font-size: 10.5px; color: #888780; background: rgba(127, 119, 221, .04); border-radius: 8px; line-height: 1.55; }

/* Modals */
.st-modal-bd { position: fixed; inset: 0; background: rgba(15, 18, 40, 0.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); z-index: 9000; display: flex; align-items: center; justify-content: center; padding: 20px; animation: stBdIn .25s ease both; overflow-y: auto; }
.st-modal { position: relative; background: #fff; border-radius: 14px; box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10); padding: 22px 24px; width: 100%; max-width: 480px; animation: stModalIn .35s cubic-bezier(.34, 1.2, .64, 1) .05s both; max-height: 90vh; overflow-y: auto; }
.st-modal-sm { max-width: 420px; }
.st-modal-x { position: absolute; top: 12px; right: 12px; width: 26px; height: 26px; border-radius: 7px; display: flex; align-items: center; justify-content: center; color: #888780; background: #fff; border: 1px solid rgba(0, 0, 0, .08); cursor: pointer; }
.st-modal-h { font-size: 16px; font-weight: 500; margin: 0 0 14px; color: #1E2A4A; }
.st-modal-text { font-size: 12.5px; color: #5F5E5A; line-height: 1.55; margin: 0 0 18px; }
.st-form { display: flex; flex-direction: column; gap: 12px; margin-bottom: 18px; }
.st-fld { display: flex; flex-direction: column; gap: 4px; }
.st-fld-l { font-size: 11px; color: #888780; font-weight: 500; text-transform: uppercase; letter-spacing: .05em; display: flex; align-items: center; gap: 2px; }
.st-fld-hint { color: #B4B2A9; text-transform: none; letter-spacing: 0; font-weight: 400; margin-left: 4px; }
.st-fld .st-input { max-width: none; font-size: 12.5px; padding: 7px 10px; }
.st-textarea { resize: vertical; min-height: 60px; line-height: 1.55; font-family: inherit; }
.st-color { padding: 2px; height: 36px; }
.st-modal-ftr { display: flex; justify-content: flex-end; gap: 8px; }

@keyframes stBdIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes stModalIn { from { opacity: 0; transform: translateY(20px) scale(.96); } to { opacity: 1; transform: translateY(0) scale(1); } }

@media (max-width: 900px) {
  .st-th, .st-td { padding: 7px 7px; font-size: 11px; }
  .st-input { font-size: 11px; padding: 4px 6px; min-width: 50px; max-width: 80px; }
  .st-btn-sm { font-size: 10px; padding: 3px 7px; }
}
</style>
