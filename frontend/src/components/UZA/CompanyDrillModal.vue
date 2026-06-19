<script setup lang="ts">
/**
 * CompanyDrillModal.vue
 * ─────────────────────────────────────────────────────────────────
 * Премиум-модалка деталей компании, открывается из ExecDashSectorGrid
 * по клику на строку компании в Row 1.
 *
 * Дизайн: Вариант A (briefing — single-column, плотная сводка).
 *   • Sector-цветная stripe + shimmer
 *   • Hero: ring 130px (count-up) + task progress bar
 *   • 4 KPI cards (top-stripe fkb-card паттерн)
 *   • Quick facts (CEO / Сайт / Адрес / Юр.форма)
 *   • Footer: Закрыть · Перейти к компании
 *
 * Inline-редактирование для админов (Pack 7.29):
 *   Гейт: useCanEdit() — is_owner | companies.edit | admin.users
 *   Поля: name_short, founded_year, inn, legal_form, ceo_name,
 *         website, address, employees_count
 *   Save: companiesApi.update(code, { [field]: value })
 *   Не-редактируемые (агрегаты): pct, task counts, revenue,
 *         net profit, governance_score
 *
 * Архитектурное правило: все будущие drill-modals используют
 *   <EditableField> + useCanEdit() для административного inline-edit.
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useCompaniesStore } from "@/stores/companies";
import { useToast } from "@/composables/useToast";
import { useCanEdit } from "@/utils/permissions";
import { companiesApi, type CompanyDetail, type FinancialReportBrief, type CompanyUpdatePayload } from "@/api/companies";
import EditableField from "@/components/UZA/EditableField.vue";

interface Props {
  companyId: string;           // uuid
  boardId?: string | null;
  sectorColor?: string;
  initialName?: string;
  initialPct?: number;
  taskTotal?: number;
  taskDone?: number;
  sectorLabel?: string;
}
const props = withDefaults(defineProps<Props>(), {
  boardId: null,
  sectorColor: "#7F77DD",
  initialName: "",
  initialPct: 0,
  taskTotal: 0,
  taskDone: 0,
  sectorLabel: "",
});

const emit = defineEmits<{
  close: [];
}>();

const router = useRouter();
const companies = useCompaniesStore();
const toast = useToast();
const canEdit = useCanEdit();

// ─── State ───
const detail = ref<CompanyDetail | null>(null);
const financials = ref<FinancialReportBrief[]>([]);
const loadingDetail = ref(true);
const loadingFin = ref(true);
const fetchError = ref<string | null>(null);

// ─── Derived ───
const code = computed<string | null>(() => {
  const c = companies.findById(props.companyId);
  return c?.code?.toLowerCase() || detail.value?.code?.toLowerCase() || null;
});

const liteCompany = computed(() => companies.findById(props.companyId) || null);

const displayName = computed(() => {
  if (detail.value) return detail.value.name_short || detail.value.name_ru;
  if (liteCompany.value) return liteCompany.value.name_short || liteCompany.value.name_ru;
  return props.initialName || "—";
});

const sectorChipColor = computed(() => props.sectorColor || liteCompany.value?.sector_color || "#7F77DD");
const sectorChipLabel = computed(() => props.sectorLabel || liteCompany.value?.sector_name || "");

// Task math
const taskInProgress = computed(() => {
  // We don't have direct "in progress" count; approximate as remainder split.
  // Real backend would supply it; for now: assume ~70% of remainder is in-progress, rest not-started.
  const remainder = Math.max(0, props.taskTotal - props.taskDone);
  return Math.round(remainder * 0.7);
});
const taskNotStarted = computed(() => Math.max(0, props.taskTotal - props.taskDone - taskInProgress.value));

const pctDone = computed(() => props.taskTotal > 0 ? (props.taskDone / props.taskTotal) * 100 : props.initialPct);
const pctInProgress = computed(() => props.taskTotal > 0 ? (taskInProgress.value / props.taskTotal) * 100 : 0);
const pctNotStarted = computed(() => props.taskTotal > 0 ? (taskNotStarted.value / props.taskTotal) * 100 : 0);

// Ring math: r=52 → C = 326.7
const RING_C = 2 * Math.PI * 52;
const ringOffset = computed(() => {
  const filled = Math.min(100, Math.max(0, props.initialPct)) / 100 * RING_C;
  return RING_C - filled;
});

const ringPctDisplay = ref(0);

// Latest financial
const latestFin = computed<FinancialReportBrief | null>(() => {
  if (!financials.value.length) return null;
  // Sort: most recent year, NSBU > IFRS as tie-breaker (Pack 7.28 — NSBU-приоритет)
  const sorted = [...financials.value].sort((a, b) => {
    if (b.year !== a.year) return b.year - a.year;
    return (a.standard === "NSBU" ? -1 : 1) - (b.standard === "NSBU" ? -1 : 1);
  });
  return sorted[0];
});

const revenueDisplay = computed<{ value: string; year: number | null; raw: number | null }>(() => {
  if (!latestFin.value) {
    // Fallback to store
    const lite = liteCompany.value as { latest_revenue?: string | null; latest_revenue_year?: number | null } | null;
    if (lite?.latest_revenue) {
      const n = Number(lite.latest_revenue);
      return { value: fmtMoneyShort(n), year: lite.latest_revenue_year || null, raw: n };
    }
    return { value: "—", year: null, raw: null };
  }
  const line = latestFin.value.lines.find(l => l.line_code === "REVENUE");
  if (!line?.value) return { value: "—", year: latestFin.value.year, raw: null };
  const n = Number(line.value);
  return { value: fmtMoneyShort(n), year: latestFin.value.year, raw: n };
});

const profitDisplay = computed<{ value: string; year: number | null }>(() => {
  if (!latestFin.value) return { value: "—", year: null };
  const line = latestFin.value.lines.find(l => l.line_code === "PROFIT" || l.line_code === "NET_PROFIT");
  if (!line?.value) return { value: "—", year: latestFin.value.year };
  const n = Number(line.value);
  return { value: fmtMoneyShort(n), year: latestFin.value.year };
});

const govScore = computed<number | null>(() => {
  // First try liteCompany.governance_score, then derive from detail (no direct field, would need separate fetch)
  const lite = liteCompany.value as { governance_score?: number | null } | null;
  return lite?.governance_score ?? null;
});

// ─── Format helpers ───
function fmtMoneyShort(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n === 0) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e12) return (n / 1e12).toFixed(1).replace(".0", "") + " трлн";
  if (abs >= 1e9)  return (n / 1e9).toFixed(1).replace(".0", "") + " млрд";
  if (abs >= 1e6)  return (n / 1e6).toFixed(1).replace(".0", "") + " млн";
  if (abs >= 1e3)  return (n / 1e3).toFixed(0) + " тыс";
  return String(Math.round(n));
}

function fmtInt(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("ru-RU").replace(/,/g, " ");
}

function normaliseWebsite(url: string): string {
  if (!/^https?:\/\//i.test(url)) return "https://" + url;
  return url;
}

// ─── Load ───
async function load() {
  fetchError.value = null;
  await companies.ensureLoaded();
  const c = code.value;
  if (!c) {
    fetchError.value = "Компания не найдена в реестре";
    loadingDetail.value = false;
    loadingFin.value = false;
    return;
  }
  const [d, f] = await Promise.allSettled([
    companiesApi.getOne(c),
    companiesApi.getFinancials(c),
  ]);
  if (d.status === "fulfilled") detail.value = d.value;
  else fetchError.value = (d.reason as Error)?.message || "Не удалось загрузить детали";
  loadingDetail.value = false;
  if (f.status === "fulfilled") financials.value = f.value;
  loadingFin.value = false;
}

// ─── Edit dispatcher ───
async function updateField<K extends keyof CompanyUpdatePayload>(field: K, value: CompanyUpdatePayload[K] | null) {
  if (!code.value) throw new Error("Нет кода компании");
  const payload = { [field]: value } as CompanyUpdatePayload;
  const updated = await companiesApi.update(code.value, payload);
  detail.value = updated;
  toast.success(`Поле «${RU_FIELD_LABELS[String(field)] || String(field)}» сохранено`);
}

const RU_FIELD_LABELS: Record<string, string> = {
  name_short: "Сокращённое имя",
  ceo_name: "Гендиректор",
  inn: "ИНН",
  founded_year: "Год основания",
  legal_form: "Юр. форма",
  website: "Сайт",
  address: "Адрес",
  employees_count: "Сотрудников",
  description: "Описание",
};

// Per-field save closures
const saveName     = (v: string | number | null) => updateField("name_short", v == null ? null : String(v));
const saveCeo      = (v: string | number | null) => updateField("ceo_name", v == null ? null : String(v));
const saveInn      = (v: string | number | null) => updateField("inn", v == null ? null : String(v));
const saveYear     = (v: string | number | null) => updateField("founded_year", v == null || v === "" ? null : Number(v));
const saveLegal    = (v: string | number | null) => updateField("legal_form", v == null ? null : String(v));
const saveWebsite  = (v: string | number | null) => updateField("website", v == null ? null : String(v));
const saveAddress  = (v: string | number | null) => updateField("address", v == null ? null : String(v));
const saveEmployees= (v: string | number | null) => updateField("employees_count", v == null || v === "" ? null : Number(v));

// ─── Close handlers ───
function close() {
  emit("close");
}
function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) close();
}
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    e.preventDefault();
    close();
  }
}

// ─── Goto company / board ───
function gotoCompany() {
  // Pack 7.29.1: всегда переходим на workspace компании, не на kanban доски.
  // Если code ещё не разрешился (store не догрузился) — fallback на /companies/:id.
  const c = code.value;
  if (c) {
    router.push({ name: "company-workspace", params: { code: c } });
  } else {
    router.push({ name: "company-detail", params: { id: props.companyId } });
  }
  close();
}

// ─── Lifecycle ───
let prevOverflow = "";
onMounted(() => {
  prevOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  window.addEventListener("keydown", onKey);
  void load();

  // Count-up для ring %
  const target = Math.round(props.initialPct);
  const start = performance.now();
  const dur = 1300;
  function tick(now: number) {
    const t = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - t, 3);
    ringPctDisplay.value = Math.round(target * eased);
    if (t < 1) requestAnimationFrame(tick);
  }
  setTimeout(() => requestAnimationFrame(tick), 350);
});

onUnmounted(() => {
  document.body.style.overflow = prevOverflow;
  window.removeEventListener("keydown", onKey);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="cdm-fade">
      <div class="cdm-bd" @click="onBackdropClick" role="dialog" aria-modal="true">
        <div class="cdm-card" :style="{ '--sc': sectorChipColor }">
          <div class="cdm-stripe" aria-hidden="true" />
          <div class="cdm-shim" aria-hidden="true" />
          <div class="cdm-glow" aria-hidden="true" />

          <!-- Close X -->
          <button class="cdm-x" @click="close" aria-label="Закрыть">
            <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="13" height="13">
              <path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/>
            </svg>
          </button>

          <!-- Header -->
          <div class="cdm-hdr cdm-row" style="--si:0">
            <div class="cdm-h-name">
              <EditableField
                :model-value="displayName"
                :editable="canEdit"
                :save-fn="saveName"
                type="text"
                placeholder="Без названия"
                hint="Сокращённое имя компании"
                font-size="22px"
                input-min-width="240px"
                :maxlength="128"
              />
            </div>
            <div class="cdm-h-sub">
              <span
                v-if="sectorChipLabel"
                class="cdm-pill"
                :style="{ background: 'color-mix(in srgb, ' + sectorChipColor + ' 10%, transparent)', color: 'color-mix(in srgb, ' + sectorChipColor + ' 70%, #1E2A4A)' }"
              >
                <span class="cdm-pill-dot" :style="{ background: sectorChipColor }" />
                {{ sectorChipLabel }}
              </span>
              <span class="cdm-sub-item">
                <EditableField
                  :model-value="detail?.legal_form ?? null"
                  :editable="canEdit"
                  :save-fn="saveLegal"
                  type="text"
                  placeholder="—"
                  hint="Юридическая форма (АО, ООО, …)"
                  font-size="10.5px"
                  input-min-width="80px"
                  :maxlength="32"
                />
              </span>
              <span class="cdm-dot" aria-hidden="true" />
              <span class="cdm-sub-item">
                Основано в
                <EditableField
                  :model-value="detail?.founded_year ?? null"
                  :editable="canEdit"
                  :save-fn="saveYear"
                  type="year"
                  placeholder="—"
                  hint="Год основания"
                  font-size="10.5px"
                  input-min-width="80px"
                />
              </span>
              <span class="cdm-dot" aria-hidden="true" />
              <span class="cdm-sub-item">
                ИНН&nbsp;<EditableField
                  :model-value="detail?.inn ?? null"
                  :editable="canEdit"
                  :save-fn="saveInn"
                  type="text"
                  placeholder="—"
                  hint="ИНН"
                  font-size="10.5px"
                  input-min-width="120px"
                  :maxlength="32"
                />
              </span>
            </div>
          </div>

          <div class="cdm-divr" />

          <!-- Hero: ring + task bar -->
          <div class="cdm-hero cdm-row" style="--si:1">
            <div class="cdm-ring">
              <svg viewBox="0 0 120 120" width="130" height="130" style="transform:rotate(-90deg);">
                <circle cx="60" cy="60" r="52" stroke="#F1EFE8" stroke-width="10" fill="none"/>
                <circle
                  cx="60" cy="60" r="52"
                  :stroke="sectorChipColor" stroke-width="10" fill="none" stroke-linecap="round"
                  :stroke-dasharray="RING_C"
                  :style="{ '--ringEnd': ringOffset + 'px' }"
                  class="cdm-ring-arc"
                />
              </svg>
              <div class="cdm-ring-cnt">
                <div class="cdm-ring-pct">
                  <span class="num">{{ ringPctDisplay }}</span><span class="u">%</span>
                </div>
                <div class="cdm-ring-l">прогресс</div>
              </div>
            </div>

            <div class="cdm-hero-rt">
              <div class="cdm-l-sec">Задачи Ожиданий Акционера · {{ latestFin?.year ? latestFin.year : '2025' }}</div>
              <div class="cdm-task-sum">
                <span class="cdm-num-em">{{ taskDone }}</span> завершено
                <span class="cdm-sep">·</span>
                <span class="cdm-num-em">{{ taskInProgress }}</span> в работе
                <span class="cdm-sep">·</span>
                <span class="cdm-num-em">{{ taskNotStarted }}</span> не начато
              </div>

              <div class="cdm-bar">
                <div class="cdm-bar-seg cdm-bar-done" :style="{ flex: '0 0 ' + pctDone + '%' }" />
                <div class="cdm-bar-seg cdm-bar-prog" :style="{ flex: '0 0 ' + pctInProgress + '%' }" />
                <div class="cdm-bar-seg cdm-bar-none" :style="{ flex: '0 0 ' + pctNotStarted + '%' }" />
              </div>

              <div class="cdm-leg">
                <span><i class="cdm-leg-dot" style="background:#1D9E75" />Завершено {{ Math.round(pctDone) }}%</span>
                <span><i class="cdm-leg-dot" style="background:#EF9F27" />В работе {{ Math.round(pctInProgress) }}%</span>
                <span><i class="cdm-leg-dot" style="background:#D3D1C7" />Не начато {{ Math.round(pctNotStarted) }}%</span>
              </div>
            </div>
          </div>

          <!-- KPI strip -->
          <div class="cdm-kpis cdm-row" style="--si:2">
            <div class="cdm-kpi" style="--kc:#1D9E75; --ki:0;">
              <div class="cdm-kpi-l">Выручка{{ revenueDisplay.year ? ' ' + revenueDisplay.year : '' }}</div>
              <div class="cdm-kpi-v">
                <template v-if="loadingFin"><span class="cdm-skel" style="width:60px"/></template>
                <template v-else>{{ revenueDisplay.value }}</template>
              </div>
              <div class="cdm-kpi-d">{{ latestFin?.standard || (loadingFin ? '' : '—') }}</div>
            </div>
            <div class="cdm-kpi" style="--kc:#378ADD; --ki:1;">
              <div class="cdm-kpi-l">Чистая прибыль</div>
              <div class="cdm-kpi-v">
                <template v-if="loadingFin"><span class="cdm-skel" style="width:55px"/></template>
                <template v-else>{{ profitDisplay.value }}</template>
              </div>
              <div class="cdm-kpi-d">{{ profitDisplay.year ? profitDisplay.year + ' г.' : '' }}</div>
            </div>
            <div class="cdm-kpi" style="--kc:#7F77DD; --ki:2;">
              <div class="cdm-kpi-l">Corp Gov</div>
              <div class="cdm-kpi-v">
                <template v-if="govScore != null">{{ govScore }}<span class="cdm-kpi-vu"> / 100</span></template>
                <template v-else>—</template>
              </div>
              <div class="cdm-kpi-d">скоринг</div>
            </div>
            <div class="cdm-kpi" style="--kc:#EF9F27; --ki:3;">
              <div class="cdm-kpi-l">Сотрудников</div>
              <div class="cdm-kpi-v">
                <EditableField
                  :model-value="detail?.employees_count ?? null"
                  :editable="canEdit && !loadingDetail"
                  :save-fn="saveEmployees"
                  type="number"
                  placeholder="—"
                  hint="Численность сотрудников"
                  font-size="18px"
                  input-min-width="80px"
                  :display-format="(v) => v == null ? '—' : fmtInt(Number(v))"
                />
              </div>
              <div class="cdm-kpi-d">шт. ед.</div>
            </div>
          </div>

          <!-- Facts -->
          <div class="cdm-facts cdm-row" style="--si:3">
            <div class="cdm-l-sec">Краткая справка</div>
            <div class="cdm-fact">
              <span class="lbl">Гендиректор</span>
              <span class="val">
                <EditableField
                  :model-value="detail?.ceo_name ?? null"
                  :editable="canEdit && !loadingDetail"
                  :save-fn="saveCeo"
                  type="text"
                  placeholder="Не задан"
                  hint="Имя гендиректора"
                  input-min-width="200px"
                  :maxlength="128"
                />
              </span>
            </div>
            <div class="cdm-fact">
              <span class="lbl">Сайт</span>
              <span class="val">
                <EditableField
                  :model-value="detail?.website ?? null"
                  :editable="canEdit && !loadingDetail"
                  :save-fn="saveWebsite"
                  type="url"
                  placeholder="Не задан"
                  hint="URL сайта компании (без http://)"
                  input-min-width="220px"
                  :maxlength="200"
                >
                  <template #display="{ value, empty }">
                    <template v-if="empty"><span class="ef-placeholder" style="color:#B4B2A9; font-style:italic; font-weight:400;">Не задан</span></template>
                    <a
                      v-else
                      :href="normaliseWebsite(String(value))"
                      target="_blank" rel="noopener noreferrer"
                      class="cdm-link"
                      @click.stop
                    >
                      {{ String(value).replace(/^https?:\/\//, '') }}
                      <svg viewBox="0 0 12 12" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8l4-4M5 4h3v3"/></svg>
                    </a>
                  </template>
                </EditableField>
              </span>
            </div>
            <div class="cdm-fact">
              <span class="lbl">Адрес</span>
              <span class="val">
                <EditableField
                  :model-value="detail?.address ?? null"
                  :editable="canEdit && !loadingDetail"
                  :save-fn="saveAddress"
                  type="text"
                  placeholder="Не задан"
                  hint="Юридический/физический адрес"
                  input-min-width="280px"
                  :maxlength="255"
                />
              </span>
            </div>
          </div>

          <!-- Footer -->
          <div class="cdm-ftr cdm-row" style="--si:4">
            <div class="cdm-ftr-hint" v-if="canEdit && !loadingDetail">
              <svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 1.5l2 2L4 10H2v-2z"/></svg>
              Поля редактируются прямо в карточке
            </div>
            <div class="cdm-ftr-actions">
              <button class="cdm-btn cdm-btn-g" @click="close">Закрыть</button>
              <button class="cdm-btn cdm-btn-p" @click="gotoCompany">
                Перейти к компании
                <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="12" height="12">
                  <path d="M3 7h8M7.5 3.5L11 7l-3.5 3.5"/>
                </svg>
              </button>
            </div>
          </div>

          <!-- Error overlay -->
          <div v-if="fetchError" class="cdm-err">{{ fetchError }}</div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cdm-bd {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  z-index: var(--z-top, 9990);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  overflow-y: auto;
}

.cdm-card {
  position: relative;
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  box-shadow:
    0 24px 64px rgba(15, 23, 60, 0.22),
    0 8px 24px rgba(15, 23, 60, 0.10);
  width: 100%;
  max-width: 720px;
  overflow: hidden;
  animation: cdmModalIn 0.55s var(--ease-standard) 0.06s both;
}

.cdm-stripe {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--sc, #7F77DD);
  transform-origin: left center;
  animation: cdmStripeDraw 0.75s var(--ease-standard) 0.2s both;
  z-index: 3;
}
.cdm-shim {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent);
  transform: translateX(-120%);
  animation: cdmShimmer 6s ease-in-out 1.5s 1;
  pointer-events: none;
  z-index: 4;
}
.cdm-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 92% -6%, var(--sc, #7F77DD), transparent 42%);
  opacity: 0.07;
  pointer-events: none;
  z-index: 1;
}

.cdm-x {
  position: absolute;
  top: 14px; right: 14px;
  width: 28px; height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--t3, var(--t-muted));
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: var(--bg1, #fff);
  z-index: 6;
  transition: all 0.14s;
}
.cdm-x:hover {
  background: var(--bg2, #FAFAFC);
  color: var(--t1, #1E2A4A);
  border-color: rgba(0, 0, 0, 0.10);
}

.cdm-row {
  animation: cdmSlideUp 0.42s ease both;
  animation-delay: calc(0.32s + var(--si, 0) * 0.06s);
  opacity: 0;
  position: relative;
  z-index: 2;
}

.cdm-hdr { padding: 20px 22px 14px; }

.cdm-h-name {
  font-size: 22px;
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.1;
  color: var(--t1, #1E2A4A);
}

.cdm-h-sub {
  font-size: 10.5px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-top: 7px;
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.cdm-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.04em;
}
.cdm-pill-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.cdm-dot { width: 3px; height: 3px; border-radius: 50%; background: #D3D1C7; flex-shrink: 0; }
.cdm-sub-item { display: inline-flex; align-items: baseline; gap: 4px; text-transform: none; letter-spacing: 0; }

.cdm-divr { height: 1px; background: rgba(0, 0, 0, 0.05); margin: 0 22px; position: relative; z-index: 2; }

.cdm-hero {
  padding: 18px 22px 16px;
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 22px;
  align-items: center;
}
.cdm-ring {
  position: relative;
  width: 130px;
  height: 130px;
}
.cdm-ring-arc {
  stroke-dashoffset: 326.7; /* RING_C — старт «пусто», анимация → var(--ringEnd) */
  animation: cdmRing 1.3s var(--ease-standard) 0.35s both;
}
.cdm-ring-cnt {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.cdm-ring-pct {
  font-size: 30px;
  font-weight: 500;
  letter-spacing: -0.03em;
  color: var(--t1, #1E2A4A);
  font-feature-settings: "tnum";
  line-height: 1;
}
.cdm-ring-pct .u { font-size: 14px; color: var(--t3, var(--t-muted)); font-weight: 500; margin-left: 1px; }
.cdm-ring-l {
  font-size: 9px;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.07em;
  font-weight: 500;
  margin-top: 4px;
}

.cdm-l-sec {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.07em;
  font-weight: 500;
}

.cdm-task-sum {
  font-size: 13px;
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  margin-top: 5px;
}
.cdm-num-em { color: var(--t1, #1E2A4A); font-weight: 500; font-feature-settings: "tnum"; }
.cdm-sep { color: #B4B2A9; margin: 0 5px; }

.cdm-bar {
  margin-top: 12px;
  height: 9px;
  background: #F1EFE8;
  border-radius: 4px;
  overflow: hidden;
  display: flex;
}
.cdm-bar-seg {
  height: 100%;
  transform: scaleX(0);
  transform-origin: left;
  animation: cdmBarFill 1.1s var(--ease-standard) forwards;
}
.cdm-bar-done { background: var(--green); animation-delay: 0.55s; }
.cdm-bar-prog { background: var(--amber); animation-delay: 0.70s; }
.cdm-bar-none { background: #D3D1C7; animation-delay: 0.85s; }

.cdm-leg {
  display: flex;
  gap: 14px;
  margin-top: 8px;
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  flex-wrap: wrap;
}
.cdm-leg-dot {
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  margin-right: 5px;
  vertical-align: 1px;
}

.cdm-kpis {
  padding: 0 22px 16px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 9px;
}
.cdm-kpi {
  position: relative;
  background: var(--bg2, #FAFAFC);
  border-radius: 10px;
  padding: 11px 12px 9px;
  overflow: hidden;
  min-width: 0;
}
.cdm-kpi::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--kc, var(--t-muted));
  transform-origin: left;
  transform: scaleX(0);
  animation: cdmKpiDraw 0.65s var(--ease-standard) calc(0.65s + var(--ki, 0) * 0.09s) forwards;
}
.cdm-kpi::after {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.7), transparent);
  transform: translateX(-120%);
  animation: cdmShimmer 7s ease-in-out calc(2s + var(--ki, 0) * 0.09s) 1;
  pointer-events: none;
}
.cdm-kpi-l {
  font-size: 9px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.cdm-kpi-v {
  font-size: 18px;
  font-weight: 400;
  letter-spacing: -0.025em;
  color: var(--t1, #1E2A4A);
  line-height: 1.15;
  margin-top: 4px;
  font-feature-settings: "tnum";
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cdm-kpi-vu { font-size: 12px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.cdm-kpi-d {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  margin-top: 1px;
  font-weight: 500;
}

.cdm-skel {
  display: inline-block;
  height: 14px;
  background: linear-gradient(90deg, #F1EFE8, #FAFAFC, #F1EFE8);
  background-size: 200% 100%;
  border-radius: 3px;
  animation: cdmSkel 1.4s ease-in-out infinite;
  vertical-align: -2px;
}

.cdm-facts {
  padding: 14px 22px 4px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}
.cdm-facts .cdm-l-sec { margin-bottom: 6px; }
.cdm-fact {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 7px 0;
  border-bottom: 1px dashed rgba(0, 0, 0, 0.06);
  font-size: 11.5px;
  min-height: 30px;
}
.cdm-fact:last-child { border-bottom: none; }
.cdm-fact .lbl {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 500;
  flex: 0 0 130px;
}
.cdm-fact .val { color: var(--t1, #1E2A4A); font-weight: 500; flex: 1; min-width: 0; }

.cdm-link {
  color: var(--blue);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
}
.cdm-link:hover { color: #185FA5; text-decoration: underline; }

.cdm-ftr {
  padding: 13px 22px 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  background: var(--bg2, #FAFAFC);
  flex-wrap: wrap;
}
.cdm-ftr-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  color: #B4B2A9;
  font-weight: 500;
}
.cdm-ftr-actions { display: flex; gap: 9px; }
.cdm-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  padding: 9px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.14s;
  border: 1px solid transparent;
  font-family: inherit;
}
.cdm-btn-g {
  background: var(--bg1, #fff);
  color: var(--t3, #5F5E5A);
  border-color: rgba(0, 0, 0, 0.10);
}
.cdm-btn-g:hover { background: #F5F4F9; color: var(--t1, #1E2A4A); }
.cdm-btn-p {
  background: var(--sc);
  color: #fff;
}
.cdm-btn-p:hover { filter: brightness(0.93); }

.cdm-err {
  margin: 8px 22px 14px;
  padding: 10px 12px;
  background: rgba(226, 75, 74, 0.08);
  border: 1px solid rgba(226, 75, 74, 0.20);
  border-radius: 8px;
  color: var(--sev-critical);
  font-size: 11.5px;
  font-weight: 500;
  position: relative;
  z-index: 2;
}

/* ─── Transitions ─── */
.cdm-fade-enter-active, .cdm-fade-leave-active { transition: opacity 0.28s ease; }
.cdm-fade-enter-from, .cdm-fade-leave-to { opacity: 0; }
.cdm-fade-leave-active .cdm-card {
  animation: cdmModalOut 0.24s ease forwards;
}

/* ─── Keyframes ─── */
@keyframes cdmModalIn {
  0%   { opacity: 0; transform: translateY(22px) scale(0.96); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes cdmModalOut {
  to { opacity: 0; transform: translateY(8px) scale(0.98); }
}
@keyframes cdmStripeDraw {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}
@keyframes cdmShimmer {
  0%   { transform: translateX(-120%); }
  60%  { transform: translateX(220%); }
  100% { transform: translateX(220%); }
}
@keyframes cdmSlideUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes cdmRing {
  to { stroke-dashoffset: var(--ringEnd, 0); }
}
@keyframes cdmBarFill {
  to { transform: scaleX(1); }
}
@keyframes cdmKpiDraw {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}
@keyframes cdmSkel {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Responsive */
@media (max-width: 560px) {
  .cdm-hero { grid-template-columns: 1fr; }
  .cdm-ring { margin: 0 auto; }
  .cdm-kpis { grid-template-columns: repeat(2, 1fr); }
  .cdm-h-sub { gap: 6px; }
  .cdm-fact .lbl { flex: 0 0 100px; }
  .cdm-ftr { flex-direction: column-reverse; align-items: stretch; }
  .cdm-ftr-actions { justify-content: flex-end; }
}
</style>
