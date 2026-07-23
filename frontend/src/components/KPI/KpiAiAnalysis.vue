<template>
  <button class="kpai-btn" @click="openModal" :disabled="loading" title="ИИ-анализ KPI">
    <span class="kpai-btn-ai">Ai</span>{{ loading ? "Анализирую…" : "Анализ ИИ" }}
  </button>

  <Teleport to="body">
    <div v-if="open" class="kpai-back" @click.self="open = false" role="dialog" aria-modal="true">
      <div class="kpai-card">
        <header class="kpai-hd">
          <div class="kpai-hd-txt">
            <div class="kpai-eyebrow">ИИ-АНАЛИЗ KPI · {{ scope === 'company' ? 'КОМПАНИЯ' : 'ПОРТФЕЛЬ' }}</div>
            <h2 class="kpai-title">{{ titleText }}</h2>
            <div v-if="doneAt && !loading && html" class="kpai-sub">{{ MODE_LABEL[mode] }} · FY {{ year }} · {{ doneAt }}</div>
          </div>
          <button class="kpai-x" @click="open = false" aria-label="Закрыть">×</button>
        </header>

        <div class="kpai-ctrls">
          <div class="kpai-seg-row">
            <span class="kpai-seg-lbl">Охват</span>
            <div class="kpai-seg">
              <button :class="{ on: scope === 'portfolio' }" :disabled="loading" @click="setScope('portfolio')">Весь портфель</button>
              <button :class="{ on: scope === 'company' }" :disabled="loading || !selectedCompany" @click="setScope('company')">
                Только «{{ selectedCompany?.company_name_ru || 'компания' }}»
              </button>
            </div>
          </div>
          <div class="kpai-seg-row">
            <span class="kpai-seg-lbl">Режим</span>
            <div class="kpai-seg">
              <button v-for="m in MODES" :key="m.id" :class="{ on: mode === m.id }" :disabled="loading" @click="setMode(m.id)" :title="m.hint">{{ m.label }}</button>
            </div>
            <button class="kpai-run" :disabled="loading" @click="run">
              {{ loading ? "Анализирую…" : (html ? "Пересчитать" : "Запустить анализ") }}
            </button>
          </div>
        </div>

        <div class="kpai-body">
          <div v-if="loading" class="kpai-loading"><span class="kpai-spin"></span><span>{{ step }}</span></div>
          <div v-else-if="error" class="kpai-error">{{ error }}</div>
          <div v-else-if="html" class="kpai-md" v-html="html"></div>
          <div v-else class="kpai-empty">
            <b>Выберите охват и режим, затем запустите анализ.</b>
            <span>ИИ разберёт исполнение KPI, свяжет их с финансовыми показателями (через привязку к строкам ОФР) и — в режиме «Прогноз» — предскажет будущие KPI и предложит новые.</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { kpiApi } from "@/api/bpKpi";
import { kpiCompletionRatio } from "@/utils/kpiRatio";
import { renderMarkdown } from "@/utils/renderMarkdown";
import { useToast } from "@/composables/useToast";

type Mode = "performance" | "correlation" | "forecast";
type Co = { company_id: string; company_name_ru: string; company_code: string | null };
type IndOut = {
  name: string; unit: string | null; plan: number | null; fact: number | null;
  pct: number | null; dir: string; weight: number; bp_key: string | null;
};
type SavedRec = { raw: string; doneAt: string; year: number };

const props = defineProps<{ companies: Co[]; year: number; period: string; selectedId: string | null }>();

const toast = useToast();
const open = ref(false);
const loading = ref(false);
const error = ref("");
const html = ref("");
const doneAt = ref("");
const step = ref("");
const scope = ref<"portfolio" | "company">("portfolio");
const mode = ref<Mode>("performance");
const saved = ref<Record<string, SavedRec>>({});

const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "performance", label: "Исполнение", hint: "Разбор выполнения KPI: веса, риски, направление" },
  { id: "correlation", label: "KPI ↔ Финансы", hint: "Взаимосвязи операционных KPI и финансовых показателей" },
  { id: "forecast", label: "Прогноз", hint: "Прогноз будущих KPI + предложение новых показателей" },
];
const MODE_LABEL: Record<Mode, string> = { performance: "Исполнение", correlation: "KPI↔Финансы", forecast: "Прогноз" };

const selectedCompany = computed(() => props.companies.find(c => c.company_id === props.selectedId) || null);
const titleText = computed(() => scope.value === "company"
  ? (selectedCompany.value?.company_name_ru || "Компания")
  : "Все компании портфеля");

function savedKey(m: Mode = mode.value): string {
  return scope.value === "company" && props.selectedId ? `${m}__${props.selectedId}` : m;
}

async function fetchSaved(): Promise<void> {
  try {
    const { api } = await import("@/api/client");
    const r = await api.get("/ai/saved/kpi");
    saved.value = (r.data?.saved || {}) as Record<string, SavedRec>;
  } catch { /* нет доступа/оффлайн — игнор */ }
}
function applyMode(m: Mode): void {
  mode.value = m;
  const o = saved.value[savedKey(m)];
  if (o?.raw) { html.value = renderMarkdown(o.raw); doneAt.value = o.doneAt || ""; }
  else { html.value = ""; doneAt.value = ""; }
  error.value = "";
}
function setMode(m: Mode): void { if (!loading.value) applyMode(m); }
function setScope(s: "portfolio" | "company"): void { if (loading.value) return; scope.value = s; applyMode(mode.value); }

async function openModal(): Promise<void> {
  open.value = true;
  await fetchSaved();
  applyMode(mode.value);
}

async function saveResult(raw: string): Promise<void> {
  const key = savedKey();
  const rec: SavedRec = { raw, doneAt: doneAt.value, year: props.year };
  saved.value = { ...saved.value, [key]: rec };
  try {
    const { api } = await import("@/api/client");
    await api.put(`/ai/saved/kpi/${key}`, { payload: rec });
  } catch { toast.error("Анализ не сохранён на сервере — исчезнет при обновлении. Повторите."); }
}

async function run(): Promise<void> {
  if (loading.value) return;
  loading.value = true; error.value = ""; html.value = "";
  const single = scope.value === "company" && selectedCompany.value ? selectedCompany.value : null;
  step.value = single ? `Загружаю KPI: ${single.company_name_ru}…` : "Загружаю KPI всех компаний…";
  try {
    const { api } = await import("@/api/client");
    const cos: Co[] = single ? [single] : props.companies;
    const built = await Promise.all(cos.map(async (co) => {
      try {
        const { managers } = await kpiApi.getCompanyYear(co.company_id, props.year);
        const inds: IndOut[] = [];
        for (const mgr of managers) {
          for (const ind of (mgr.indicators || [])) {
            const linked = !!ind.bp_metric_key;
            const plan = linked && ind.bp_plan_resolved != null ? Number(ind.bp_plan_resolved)
              : ind.plan_year != null ? Number(ind.plan_year) : null;
            const fact = linked && ind.bp_fact_resolved != null ? Number(ind.bp_fact_resolved)
              : ind.fact_year != null ? Number(ind.fact_year) : null;
            const ratio = kpiCompletionRatio(plan, fact, ind.direction);
            inds.push({
              name: ind.name, unit: ind.unit, plan, fact,
              pct: ratio != null ? Math.round(ratio * 100) : null,
              dir: ind.direction || "up", weight: Number(ind.weight) || 0,
              bp_key: ind.bp_metric_key || null,
            });
          }
        }
        return inds.length ? { code: co.company_code, name: co.company_name_ru, indicators: inds } : null;
      } catch { return null; }
    }));
    const kpi_rows = built.filter((r): r is NonNullable<typeof r> => r != null);
    if (!kpi_rows.length) {
      error.value = "Нет KPI-данных за этот год. Заведите показатели в редакторе.";
      loading.value = false; return;
    }
    step.value = "ИИ анализирует KPI и связь с финансами…";
    const resp = await api.post("/ai/kpi-analysis", {
      year: props.year, period: props.period, mode: mode.value,
      focus: single ? single.company_name_ru : null,
      kpi_rows,
    }, { timeout: 235000 });
    const raw = (resp.data?.analysis || "") as string;
    if (!raw) { error.value = "ИИ вернул пустой ответ."; loading.value = false; return; }
    html.value = renderMarkdown(raw);
    doneAt.value = new Date().toLocaleString("ru-RU");
    await saveResult(raw);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Ошибка анализа";
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.kpai-btn {
  display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 14px;
  border: none; border-radius: 9px; cursor: pointer; font-size: 13px; font-weight: 600;
  color: #fff; background: linear-gradient(135deg, #7C6FF7, #6355E0);
  box-shadow: 0 2px 8px -2px rgba(99, 85, 224, .5);
}
.kpai-btn:disabled { opacity: .6; cursor: default; }
.kpai-btn-ai {
  display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px;
  border-radius: 5px; background: rgba(255, 255, 255, .22); font-size: 10px; font-weight: 700;
}

.kpai-back {
  position: fixed; inset: 0; z-index: var(--z-modal, 9100); display: flex;
  align-items: flex-start; justify-content: center; padding: 6vh 16px 40px;
  background: rgba(20, 20, 34, .5); backdrop-filter: blur(3px);
}
.kpai-card {
  width: min(900px, 100%); max-height: 88vh; display: flex; flex-direction: column;
  background: var(--surface, #fff); border-radius: 18px; overflow: hidden;
  box-shadow: 0 24px 64px -20px rgba(20, 20, 34, .5);
}
.kpai-hd {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  padding: 20px 24px 14px;
}
.kpai-eyebrow { font-size: 11px; letter-spacing: .14em; color: #7C6FF7; font-weight: 700; }
.kpai-title { margin: 4px 0 0; font-size: 21px; font-weight: 650; color: var(--ink, #1A1A26); }
.kpai-sub { margin-top: 5px; font-size: 12.5px; color: #8A90A0; }
.kpai-x {
  border: none; background: transparent; font-size: 24px; line-height: 1; color: #9AA3B2;
  cursor: pointer; padding: 0 4px;
}

.kpai-ctrls { padding: 0 24px 14px; border-bottom: 1px solid var(--line, #ECECF3); }
.kpai-seg-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 10px; }
.kpai-seg-lbl { font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: #9AA3B2; font-weight: 600; min-width: 56px; }
.kpai-seg { display: inline-flex; background: #F2F2F8; border-radius: 10px; padding: 3px; }
.kpai-seg button {
  border: none; background: transparent; padding: 6px 13px; border-radius: 8px; cursor: pointer;
  font-size: 13px; font-weight: 600; color: #5A6172;
}
.kpai-seg button.on { background: #fff; color: #6355E0; box-shadow: 0 1px 4px -1px rgba(20, 20, 34, .18); }
.kpai-seg button:disabled { opacity: .45; cursor: default; }
.kpai-run {
  margin-left: auto; height: 36px; padding: 0 18px; border: none; border-radius: 9px; cursor: pointer;
  font-size: 13px; font-weight: 650; color: #fff; background: linear-gradient(135deg, #7C6FF7, #6355E0);
}
.kpai-run:disabled { opacity: .6; cursor: default; }

.kpai-body { padding: 18px 24px 26px; overflow-y: auto; }
.kpai-loading { display: flex; align-items: center; gap: 12px; color: #6E6D80; font-size: 14px; padding: 30px 0; }
.kpai-spin {
  width: 18px; height: 18px; border: 2.5px solid #E2E1F0; border-top-color: #7C6FF7;
  border-radius: 50%; animation: kpaiSpin .8s linear infinite;
}
@keyframes kpaiSpin { to { transform: rotate(360deg); } }
.kpai-error { color: #E24B4A; font-size: 14px; padding: 16px 0; }
.kpai-empty { display: flex; flex-direction: column; gap: 8px; text-align: center; padding: 36px 8px; color: #8A90A0; }
.kpai-empty b { color: var(--ink, #1A1A26); font-size: 15px; }
.kpai-empty span { max-width: 60ch; margin: 0 auto; font-size: 13px; line-height: 1.6; }

.kpai-md { font-size: 14px; line-height: 1.65; color: var(--ink2, #2C2C3A); }
.kpai-md :deep(h1), .kpai-md :deep(h2), .kpai-md :deep(h3), .kpai-md :deep(h4) {
  margin: 18px 0 8px; font-weight: 650; color: var(--ink, #1A1A26); line-height: 1.3;
}
.kpai-md :deep(h1) { font-size: 20px; } .kpai-md :deep(h2) { font-size: 17px; } .kpai-md :deep(h3) { font-size: 15px; }
.kpai-md :deep(p) { margin: 8px 0; }
.kpai-md :deep(ul), .kpai-md :deep(ol) { margin: 8px 0; padding-left: 22px; }
.kpai-md :deep(li) { margin: 4px 0; }
.kpai-md :deep(strong) { color: var(--ink, #1A1A26); font-weight: 650; }
.kpai-md :deep(code) { font-family: ui-monospace, Consolas, monospace; font-size: 12.5px; background: #F2F2F8; padding: 1px 5px; border-radius: 5px; }
.kpai-md :deep(table) { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 12.5px; display: block; overflow-x: auto; }
.kpai-md :deep(th), .kpai-md :deep(td) { border: 1px solid var(--line, #ECECF3); padding: 6px 10px; text-align: left; }
.kpai-md :deep(th) { background: #F7F7FB; font-weight: 650; }

@media (max-width: 620px) { .kpai-run { margin-left: 0; } }
</style>
