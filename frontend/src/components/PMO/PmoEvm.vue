<script setup lang="ts">
/**
 * PmoEvm — освоенный объём (Earned Value Management, PMBOK 7).
 *
 * Портфельная сводка (SPI/CPI с индикаторами + BAC/EV/PV/AC + прогноз
 * EAC/VAC/ETC) и таблица по проектам. SPI доступен из прогресса даже без
 * бюджета; стоимостные метрики требуют заполненного бюджета и факта затрат.
 */
import { ref, computed, watch, onMounted } from "vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { pmoApi, type EvmResponse, type EvmProject, type EvmRag } from "@/api/pmo";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { useFormatters } from "@/composables/useFormatters";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();
const fmt = useFormatters();


const props = defineProps<{ companyCode: string; year?: number }>();

const loading = ref(true);
const error = ref<string | null>(null);
const data = ref<EvmResponse | null>(null);

async function load() {
  loading.value = true; error.value = null;
  try {
    data.value = await pmoApi.getEvm(props.companyCode, props.year);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || t('Не удалось рассчитать освоенный объём');
  } finally { loading.value = false; }
}
onMounted(load);
watch(() => [props.companyCode, props.year], load);

const fmtMoney = (n: number | null | undefined) =>
  n == null ? "—" : fmt.fmtNumber(n);
const fmtSigned = (n: number | null | undefined) =>
  n == null ? "—" : fmt.fmtNumber(n, { signed: true });
const fmtIdx = (n: number | null | undefined) => n == null ? "—" : n.toFixed(2);

// Позиция маркера индекса на шкале 0.5..1.5 → 0..100%
function idxPos(v: number | null): number {
  if (v == null) return 50;
  return Math.max(0, Math.min(100, ((v - 0.5) / 1.0) * 100));
}
function idxColor(v: number | null): string {
  if (v == null) return "#94a3b8";
  if (v >= 0.95) return "#1D9E75";
  if (v >= 0.85) return "#D97706";
  return "#E24B4A";
}
function idxVerdict(v: number | null, kind: "spi" | "cpi"): string {
  if (v == null) return t("нет данных");
  if (kind === "spi") {
    if (v >= 1.0) return t("идём по графику / с опережением");
    if (v >= 0.95) return t("почти по графику");
    if (v >= 0.85) return t("лёгкое отставание");
    return t("существенное отставание");
  }
  if (v >= 1.0) return t("в рамках бюджета / экономия");
  if (v >= 0.95) return t("почти в бюджете");
  if (v >= 0.85) return t("лёгкий перерасход");
  return t("существенный перерасход");
}

const RAG_C: Record<EvmRag, string> = { green: "#1D9E75", amber: "#D97706", red: "#E24B4A", na: "#94a3b8" };
const RAG_L: Record<EvmRag, string> = { green: i18nKey("В норме"), amber: i18nKey("Внимание"), red: i18nKey("Риск"), na: "—" };

const hasBudget = computed(() => !!data.value && data.value.budgeted_count > 0);
// ЧЕСТНОЕ ПОКРЫТИЕ. EVM считается только по проектам, где заполнены бюджет,
// факт затрат и плановые даты. На проде это 14 проектов из 589 — индексы
// описывают меньшинство портфеля, и это должно быть видно СРАЗУ, а не сноской.
const coverage = computed(() => {
  const d = data.value;
  if (!d) return { costPct: 0, schedPct: 0, enough: false, total: 0 };
  const total = d.total_count || 0;
  const costPct = total ? Math.round((d.budgeted_count / total) * 100) : 0;
  const schedPct = total ? Math.round(((d.scheduled_count ?? 0) / total) * 100) : 0;
  return { costPct, schedPct, enough: costPct >= 50, total };
});
const sortedProjects = computed<EvmProject[]>(() => {
  if (!data.value) return [];
  const order: Record<EvmRag, number> = { red: 0, amber: 1, green: 2, na: 3 };
  return [...data.value.projects].sort((a, b) => order[a.rag] - order[b.rag]);
});

// ── Drill-down модалки ──
const selected = ref<EvmProject | null>(null);
const methodOpen = ref(false);
function openProject(p: EvmProject) { selected.value = p; }

// Описание метрик для модалки проекта
interface MetricDef { key: keyof EvmProject; label: string; fmt: "money" | "signed" | "index"; hint: string; }
const PROJECT_METRICS: MetricDef[] = [
  { key: "bac", label: i18nKey("BAC · бюджет"), fmt: "money", hint: i18nKey("Плановый бюджет проекта. Источник — поле «бюджет» в карточке проекта.") },
  { key: "ev", label: i18nKey("EV · освоено"), fmt: "money", hint: i18nKey("Освоенный объём = BAC × прогресс.") },
  { key: "pv", label: i18nKey("PV · план"), fmt: "money", hint: i18nKey("Плановый объём = BAC × плановый % (по базовым/плановым датам).") },
  { key: "ac", label: i18nKey("AC · факт затрат"), fmt: "money", hint: i18nKey("Фактические затраты. Источник — поле «факт затрат» проекта.") },
  { key: "spi", label: i18nKey("SPI · индекс расписания"), fmt: "index", hint: i18nKey("EV ÷ PV. ≥ 1 — идём по графику, < 1 — отставание.") },
  { key: "cpi", label: i18nKey("CPI · индекс стоимости"), fmt: "index", hint: i18nKey("EV ÷ AC. ≥ 1 — в рамках бюджета, < 1 — перерасход.") },
  { key: "sv", label: i18nKey("SV · откл. графика"), fmt: "signed", hint: i18nKey("EV − PV. Отрицательное — отставание в деньгах.") },
  { key: "cv", label: i18nKey("CV · откл. стоимости"), fmt: "signed", hint: i18nKey("EV − AC. Отрицательное — перерасход.") },
  { key: "eac", label: i18nKey("EAC · прогноз стоимости"), fmt: "money", hint: i18nKey("Прогноз итоговой стоимости = BAC ÷ CPI.") },
  { key: "etc", label: i18nKey("ETC · осталось потратить"), fmt: "money", hint: i18nKey("EAC − AC — сколько ещё предстоит потратить.") },
  { key: "vac", label: i18nKey("VAC · прогноз отклонения"), fmt: "signed", hint: i18nKey("BAC − EAC. Отрицательное — прогноз перерасхода.") },
  { key: "tcpi", label: i18nKey("TCPI · требуемая эффективность"), fmt: "index", hint: i18nKey("Какой CPI нужен до конца, чтобы уложиться в бюджет.") },
];
function metricStr(p: EvmProject, m: MetricDef): string {
  const v = p[m.key] as number | null;
  if (m.fmt === "money") return fmtMoney(v);
  if (m.fmt === "signed") return fmtSigned(v);
  return fmtIdx(v);
}
function metricNeg(p: EvmProject, m: MetricDef): boolean {
  const v = p[m.key] as number | null;
  return (m.fmt === "signed") && v != null && v < 0;
}
</script>

<template>
  <div class="ev">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />
    <UzaStateBlock v-if="loading" state="loading" :text="t('Считаем освоенный объём…')" />

    <template v-else-if="data">
      <!-- инфо: откуда данные -->
      <div class="ev-top">
        <button class="ev-info" @click="methodOpen = true">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/><path d="M8 7.2 V11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="8" cy="5" r="0.9" fill="currentColor"/></svg>
          {{ t('Как считается и откуда данные') }}
        </button>
      </div>

      <!-- индексы SPI/CPI -->
      <div class="ev-idx">
        <div class="ev-gauge ev-gauge-click" :style="{ '--c': idxColor(data.spi) }" @click="methodOpen = true">
          <div class="ev-gauge-head">
            <span class="ev-gauge-l">{{ t('SPI · индекс расписания') }}</span>
            <span class="ev-gauge-v">{{ fmtIdx(data.spi) }}</span>
          </div>
          <div class="ev-bar">
            <div class="ev-bar-mid"></div>
            <div class="ev-bar-mark" :style="{ left: idxPos(data.spi) + '%' }"></div>
          </div>
          <div class="ev-gauge-verdict">{{ idxVerdict(data.spi, "spi") }}</div>
        </div>
        <div class="ev-gauge ev-gauge-click" :style="{ '--c': idxColor(data.cpi) }" @click="methodOpen = true">
          <div class="ev-gauge-head">
            <span class="ev-gauge-l">{{ t('CPI · индекс стоимости') }}</span>
            <span class="ev-gauge-v">{{ fmtIdx(data.cpi) }}</span>
          </div>
          <div class="ev-bar">
            <div class="ev-bar-mid"></div>
            <div class="ev-bar-mark" :style="{ left: idxPos(data.cpi) + '%' }"></div>
          </div>
          <div class="ev-gauge-verdict">{{ idxVerdict(data.cpi, "cpi") }}</div>
        </div>
      </div>

      <!-- Покрытие: по скольким проектам вообще есть чем считать -->
      <div v-if="coverage.total && (!coverage.enough || coverage.schedPct < 50)" class="ev-cover">
        <span class="ev-cover-badge">{{ t('Данных недостаточно') }}</span>
        <span class="ev-cover-txt">
          {{ t('Стоимостные метрики — по {value0} из {value1} проектов ({value2}%), индекс срока — по {value3} ({value4}%).', {
            value0: data.budgeted_count, value1: coverage.total, value2: coverage.costPct,
            value3: data.scheduled_count ?? 0, value4: coverage.schedPct,
          }) }}
          {{ t('Цифры ниже описывают только эту часть портфеля — заполните бюджет, факт затрат и плановые даты в карточках проектов.') }}
        </span>
      </div>

      <!-- ключевые величины -->
      <div class="ev-cards">
        <div class="ev-card"><span class="ev-card-l">{{ t('BAC · бюджет') }}</span><span class="ev-card-v">{{ fmtMoney(data.bac) }}</span></div>
        <div class="ev-card"><span class="ev-card-l">{{ t('EV · освоено') }}</span><span class="ev-card-v">{{ fmtMoney(data.ev) }}</span></div>
        <div class="ev-card"><span class="ev-card-l">{{ t('PV · план') }}</span><span class="ev-card-v">{{ fmtMoney(data.pv) }}</span></div>
        <div class="ev-card"><span class="ev-card-l">{{ t('AC · факт затрат') }}</span><span class="ev-card-v">{{ fmtMoney(data.ac) }}</span></div>
        <div class="ev-card" :class="{ 'ev-neg': (data.sv ?? 0) < 0 }"><span class="ev-card-l">{{ t('SV · откл. графика') }}</span><span class="ev-card-v">{{ fmtSigned(data.sv) }}</span></div>
        <div class="ev-card" :class="{ 'ev-neg': (data.cv ?? 0) < 0 }"><span class="ev-card-l">{{ t('CV · откл. стоимости') }}</span><span class="ev-card-v">{{ fmtSigned(data.cv) }}</span></div>
        <div class="ev-card ev-card-accent"><span class="ev-card-l">{{ t('EAC · прогноз стоимости') }}</span><span class="ev-card-v">{{ fmtMoney(data.eac) }}</span></div>
        <div class="ev-card" :class="{ 'ev-neg': (data.vac ?? 0) < 0 }"><span class="ev-card-l">{{ t('VAC · прогноз отклонения') }}</span><span class="ev-card-v">{{ fmtSigned(data.vac) }}</span></div>
      </div>

      <div v-if="!hasBudget" class="ev-hint">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/><path d="M8 5 V8.5 M8 10.5 V11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
        {{ t('Стоимостные метрики (CPI, EV, прогноз) появятся, когда у проектов заполнены') }} <b>{{ t('бюджет') }}</b> {{ t('и') }} <b>{{ t('факт затрат') }}</b>{{ t('. Сейчас показан индекс расписания SPI по прогрессу.') }}
      </div>

      <!-- по проектам -->
      <div class="ev-tblwrap">
        <UzaStateBlock v-if="!sortedProjects.length" state="empty" variant="block" :title="t('Нет проектов')" :text="t('Добавьте проекты в портфель, чтобы видеть освоенный объём.')" />
        <table v-else class="uza-table ev-tbl">
          <thead>
            <tr>
              <th>{{ t('Проект') }}</th><th>{{ t('Прогресс / план') }}</th><th>SPI</th><th>CPI</th>
              <th>SV</th><th>CV</th><th>EAC</th><th>VAC</th><th>{{ t('Статус') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(p, i) in sortedProjects" :key="p.project_id || i" class="ev-row ev-row-click" :style="{ animationDelay: Math.min(i*0.03, 0.4)+'s' }" @click="openProject(p)">
              <td class="ev-pname">{{ p.title }}</td>
              <td>
                <div class="ev-prog">
                  <span class="ev-prog-track"><span class="ev-prog-fill" :style="{ width: p.progress_percent + '%' }"></span><span v-if="p.planned_percent != null" class="ev-prog-plan" :style="{ left: p.planned_percent + '%' }"></span></span>
                  <span class="ev-prog-n">{{ p.progress_percent }}%<span v-if="p.planned_percent != null" class="ev-prog-plan-n"> / {{ p.planned_percent }}%</span></span>
                </div>
              </td>
              <td><span class="ev-idxchip" :style="{ color: idxColor(p.spi), background: idxColor(p.spi) + '18' }">{{ fmtIdx(p.spi) }}</span></td>
              <td><span class="ev-idxchip" :style="{ color: idxColor(p.cpi), background: idxColor(p.cpi) + '18' }">{{ fmtIdx(p.cpi) }}</span></td>
              <td class="is-mono" :class="{ 'ev-tneg': (p.sv ?? 0) < 0 }">{{ fmtSigned(p.sv) }}</td>
              <td class="is-mono" :class="{ 'ev-tneg': (p.cv ?? 0) < 0 }">{{ fmtSigned(p.cv) }}</td>
              <td class="is-mono">{{ fmtMoney(p.eac) }}</td>
              <td class="is-mono" :class="{ 'ev-tneg': (p.vac ?? 0) < 0 }">{{ fmtSigned(p.vac) }}</td>
              <td><span class="ev-rag" :style="{ color: RAG_C[p.rag], background: RAG_C[p.rag] + '18' }"><span class="ev-rag-dot" :style="{ background: RAG_C[p.rag] }"></span>{{ t(RAG_L[p.rag]) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="ev-foot">{{ t('Индексы ≥ 1.0 — хорошо (по графику / в бюджете). На дату') }} {{ new Date(data.as_of).toLocaleDateString(getCurrentIntlLocale()) }} {{ t('· бюджетных проектов:') }} {{ data.budgeted_count }} {{ t('из') }} {{ data.total_count }}{{ t('. Клик по проекту — детальный разбор.') }}</div>
    </template>

    <!-- ── Модалка проекта (drill-down) ── -->
    <Transition name="ev-modal">
      <div v-if="selected" class="ev-ov" @click.self="selected = null">
        <div class="ev-modal">
          <div class="ev-mh">
            <div>
              <div class="ev-mh-eyebrow">{{ t('EVM проекта') }}</div>
              <div class="ev-mh-title">{{ selected.title }}</div>
            </div>
            <span class="ev-rag ev-rag-lg" :style="{ color: RAG_C[selected.rag], background: RAG_C[selected.rag] + '18' }"><span class="ev-rag-dot" :style="{ background: RAG_C[selected.rag] }"></span>{{ t(RAG_L[selected.rag]) }}</span>
          </div>
          <div class="ev-mb">
            <div class="ev-mprog">
              <div class="ev-mprog-head"><span>{{ t('Прогресс vs план') }}</span><span class="ev-mprog-n">{{ selected.progress_percent }}%<span v-if="selected.planned_percent != null"> {{ t('· план') }} {{ selected.planned_percent }}%</span></span></div>
              <div class="ev-prog-track ev-prog-track-lg"><span class="ev-prog-fill" :style="{ width: selected.progress_percent + '%' }"></span><span v-if="selected.planned_percent != null" class="ev-prog-plan" :style="{ left: selected.planned_percent + '%' }"></span></div>
            </div>
            <div class="ev-mini2">
              <div class="ev-mini" :style="{ '--c': idxColor(selected.spi) }"><span class="ev-mini-l">SPI</span><span class="ev-mini-v">{{ fmtIdx(selected.spi) }}</span><span class="ev-mini-x">{{ idxVerdict(selected.spi, "spi") }}</span></div>
              <div class="ev-mini" :style="{ '--c': idxColor(selected.cpi) }"><span class="ev-mini-l">CPI</span><span class="ev-mini-v">{{ fmtIdx(selected.cpi) }}</span><span class="ev-mini-x">{{ idxVerdict(selected.cpi, "cpi") }}</span></div>
            </div>
            <div class="ev-metrics">
              <div v-for="m in PROJECT_METRICS" :key="String(m.key)" class="ev-metric">
                <div class="ev-metric-top"><span class="ev-metric-l">{{ t(m.label) }}</span><span class="ev-metric-v" :class="{ 'ev-tneg': metricNeg(selected, m) }">{{ metricStr(selected, m) }}</span></div>
                <div class="ev-metric-hint">{{ t(m.hint) }}</div>
              </div>
            </div>
            <div class="ev-src">
              <div class="ev-src-t">{{ t('Источник данных') }}</div>
              <div class="ev-src-r"><b>{{ t('Прогресс') }}</b> {{ t('— взвешенный расчёт по статусам задач проекта.') }}</div>
              <div class="ev-src-r"><b>{{ t('План') }}</b> {{ t('— доля прошедшего планового времени по базовым/плановым датам.') }}</div>
              <div class="ev-src-r" :class="{ 'ev-src-warn': selected.bac == null }"><b>{{ t('Бюджет / факт') }}</b> — {{ selected.bac == null ? t('не заполнены: добавьте бюджет и факт затрат в карточке проекта, чтобы видеть CPI, EV и прогноз') : t('из полей проекта (бюджет и факт затрат)') }}.</div>
            </div>
          </div>
          <div class="ev-mf"><button class="ev-btn" @click="selected = null">{{ t('Закрыть') }}</button></div>
        </div>
      </div>
    </Transition>

    <!-- ── Модалка методологии / источника данных ── -->
    <Transition name="ev-modal">
      <div v-if="methodOpen" class="ev-ov" @click.self="methodOpen = false">
        <div class="ev-modal">
          <div class="ev-mh"><div><div class="ev-mh-eyebrow">{{ t('Методология') }}</div><div class="ev-mh-title">{{ t('Освоенный объём (EVM)') }}</div></div></div>
          <div class="ev-mb">
            <p class="ev-doc-p">{{ t('EVM сравнивает') }} <b>{{ t('план') }}</b>, <b>{{ t('выполнение') }}</b> {{ t('и') }} <b>{{ t('затраты') }}</b> {{ t('в одних единицах и даёт ранние сигналы отклонений по срокам и бюджету.') }}</p>
            <div class="ev-defs">
              <div class="ev-def"><span class="ev-def-k">PV</span><span>{{ t('плановый объём — сколько должно быть освоено к сегодня (BAC × плановый %).') }}</span></div>
              <div class="ev-def"><span class="ev-def-k">EV</span><span>{{ t('освоенный объём — сколько фактически выполнено (BAC × прогресс).') }}</span></div>
              <div class="ev-def"><span class="ev-def-k">AC</span><span>{{ t('фактические затраты на выполненную работу.') }}</span></div>
              <div class="ev-def"><span class="ev-def-k">SPI</span><span>{{ t('= EV ÷ PV. ≥ 1 — идём по графику.') }}</span></div>
              <div class="ev-def"><span class="ev-def-k">CPI</span><span>{{ t('= EV ÷ AC. ≥ 1 — в рамках бюджета.') }}</span></div>
              <div class="ev-def"><span class="ev-def-k">EAC</span><span>{{ t('= BAC ÷ CPI — прогноз итоговой стоимости.') }}</span></div>
            </div>
            <div class="ev-src">
              <div class="ev-src-t">{{ t('Откуда берутся данные') }}</div>
              <div class="ev-src-r"><b>{{ t('Прогресс') }}</b> {{ t('— из статусов задач каждого проекта (взвешенный расчёт, единый с расписанием и дашбордами).') }}</div>
              <div class="ev-src-r"><b>{{ t('Плановый %') }}</b> {{ t('— доля прошедшего планового времени по базовым/плановым датам проекта на сегодня.') }}</div>
              <div class="ev-src-r"><b>{{ t('Бюджет (BAC) и факт (AC)') }}</b> {{ t('— поля проекта «бюджет» и «факт затрат». Пока они пусты, считается только индекс расписания SPI; стоимостные метрики появятся после заполнения.') }}</div>
            </div>
          </div>
          <div class="ev-mf"><button class="ev-btn" @click="methodOpen = false">{{ t('Закрыть') }}</button></div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.ev { padding: 4px 2px 24px; }

/* gauges */
.ev-idx { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
.ev-gauge { border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 14px; background: var(--bg1, #fff); padding: 14px 16px; border-top: 2px solid var(--c); animation: evIn .4s var(--ease-out, cubic-bezier(.16,1,.3,1)) both; }
.ev-gauge-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.ev-gauge-l { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94a3b8); font-weight: 600; }
.ev-gauge-v { font-size: 26px; font-weight: 400; color: var(--c); font-variant-numeric: tabular-nums; line-height: 1; }
.ev-bar { position: relative; height: 8px; margin: 12px 0 9px; border-radius: 4px; background: linear-gradient(90deg, rgba(226,75,74,.18), rgba(217,119,6,.16) 50%, rgba(29,158,117,.18)); }
.ev-bar-mid { position: absolute; left: 50%; top: -3px; bottom: -3px; width: 2px; background: rgba(30,42,74,.25); border-radius: 1px; transform: translateX(-50%); }
.ev-bar-mark { position: absolute; top: 50%; width: 13px; height: 13px; border-radius: 50%; background: var(--c); border: 2px solid #fff; box-shadow: 0 1px 4px rgba(15,23,60,.25); transform: translate(-50%, -50%); transition: left .6s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.ev-gauge-verdict { font-size: 11px; color: var(--t2, #475569); }

/* cards */
.ev-cover {
  display: flex; align-items: flex-start; gap: 9px; flex-wrap: wrap;
  background: rgba(217,119,6,.07); border: 1px solid rgba(217,119,6,.22);
  border-radius: 11px; padding: 10px 13px; margin-bottom: 14px;
}
.ev-cover-badge {
  font-size: 9.5px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
  color: #B45309; background: rgba(217,119,6,.14); border-radius: 999px;
  padding: 3px 9px; white-space: nowrap; flex-shrink: 0;
}
.ev-cover-txt { font-size: 11.5px; color: var(--t2, #4B5468); line-height: 1.5; }
.ev-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 9px; margin-bottom: 14px; }
.ev-card { display: flex; flex-direction: column; gap: 3px; padding: 10px 12px; border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 11px; background: var(--bg1, #fff); }
.ev-card-l { font-size: 9px; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); font-weight: 600; }
.ev-card-v { font-size: 15px; font-weight: 500; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.ev-card-accent { background: rgba(127,119,221,.05); border-color: rgba(127,119,221,.2); }
.ev-neg .ev-card-v { color: #e24b4a; }

.ev-hint { display: flex; align-items: center; gap: 9px; padding: 10px 13px; margin-bottom: 14px; border-radius: 10px; background: rgba(217,119,6,.07); border: 1px solid rgba(217,119,6,.2); color: var(--t2, #475569); font-size: 11.5px; }
.ev-hint svg { color: #d97706; flex-shrink: 0; }
.ev-hint b { font-weight: 600; color: var(--t1, #1e2a4a); }

/* table */
.ev-tblwrap { overflow-x: auto; }
.ev-tbl { font-size: var(--fs-sm, 11.5px); min-width: 800px; }
.ev-row { animation: evRowIn .4s var(--ease-out) both; transition: background .14s; }
.ev-row:hover { background: rgba(124,111,247,.04); }
.ev-pname { font-weight: 500; color: var(--t1, #1e2a4a); max-width: 220px; }
.ev-prog { display: flex; align-items: center; gap: 8px; }
.ev-prog-track { position: relative; flex: 1; min-width: 70px; height: 6px; border-radius: 3px; background: rgba(30,42,74,.08); overflow: visible; }
.ev-prog-fill { position: absolute; inset: 0 auto 0 0; height: 100%; border-radius: 3px; background: linear-gradient(90deg, #7f77dd, #1d9e75); transition: width .5s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.ev-prog-plan { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--t2, #475569); border-radius: 1px; transform: translateX(-50%); }
.ev-prog-n { font-size: 10px; color: var(--t2, #475569); font-variant-numeric: tabular-nums; white-space: nowrap; }
.ev-prog-plan-n { color: var(--t3, #94a3b8); }
.ev-idxchip { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; font-variant-numeric: tabular-nums; }
.ev-tneg { color: #e24b4a; }
.ev-rag { display: inline-flex; align-items: center; gap: 5px; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 8px; white-space: nowrap; }
.ev-rag-dot { width: 6px; height: 6px; border-radius: 50%; }
.ev-foot { margin-top: 12px; font-size: 10.5px; color: var(--t3, #94a3b8); }

@keyframes evIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes evRowIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

/* interactive */
.ev-top { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.ev-info { display: inline-flex; align-items: center; gap: 6px; padding: 5px 11px; border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 9px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 11px; font-weight: 500; font-family: inherit; cursor: pointer; transition: all .16s; }
.ev-info:hover { border-color: #7f77dd; color: #7f77dd; background: rgba(127,119,221,.05); }
.ev-info svg { color: #7f77dd; }
.ev-gauge-click { cursor: pointer; }
.ev-gauge-click:hover { box-shadow: 0 6px 18px rgba(15,23,60,.08); transform: translateY(-1px); }
.ev-row-click { cursor: pointer; }

/* modal */
.ev-ov { position: fixed; inset: 0; z-index: var(--z-modal, 9100); background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(7px); backdrop-filter: blur(7px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.ev-modal { background: var(--bg1, #fff); border-radius: 16px; width: min(620px, 96vw); max-height: 92dvh; overflow: hidden; display: flex; flex-direction: column; box-shadow: var(--shl, 0 24px 64px rgba(15,23,60,.22)); }
.ev-mh { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(99,102,180,.12)); }
.ev-mh-eyebrow { font-size: 9.5px; text-transform: uppercase; letter-spacing: .08em; color: var(--p, #7f77dd); font-weight: 700; }
.ev-mh-title { font-size: 16px; font-weight: 500; color: var(--t1, #1e2a4a); margin-top: 3px; }
.ev-rag-lg { font-size: 10.5px; padding: 4px 11px; border-radius: 8px; flex-shrink: 0; }
.ev-mb { padding: 16px 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }
.ev-mf { padding: 13px 20px; border-top: 1px solid var(--border, rgba(99,102,180,.12)); display: flex; justify-content: flex-end; background: var(--bg2, #fafafc); }
.ev-btn { padding: 8px 18px; border-radius: 9px; border: none; background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; box-shadow: 0 2px 8px rgba(127,119,221,.28); transition: transform .15s; }
.ev-btn:hover { transform: translateY(-1px); }

.ev-mprog-head { display: flex; align-items: baseline; justify-content: space-between; font-size: 11px; color: var(--t3, #94a3b8); font-weight: 600; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 7px; }
.ev-mprog-n { text-transform: none; letter-spacing: 0; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.ev-prog-track-lg { height: 9px; border-radius: 5px; }

.ev-mini2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ev-mini { display: flex; flex-direction: column; gap: 2px; padding: 11px 13px; border-radius: 11px; background: var(--bg2, #fafafc); border-top: 2px solid var(--c); }
.ev-mini-l { font-size: 10px; font-weight: 700; color: var(--t3, #94a3b8); }
.ev-mini-v { font-size: 22px; font-weight: 400; color: var(--c); font-variant-numeric: tabular-nums; line-height: 1.1; }
.ev-mini-x { font-size: 10.5px; color: var(--t2, #475569); }

.ev-metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.ev-metric { padding: 9px 11px; border: 1px solid var(--border, rgba(99,102,180,.1)); border-radius: 10px; animation: evRowIn .35s var(--ease-out) both; }
.ev-metric-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.ev-metric-l { font-size: 10px; text-transform: uppercase; letter-spacing: .03em; color: var(--t3, #94a3b8); font-weight: 600; }
.ev-metric-v { font-size: 13.5px; font-weight: 600; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.ev-metric-hint { font-size: 10px; color: var(--t3, #94a3b8); margin-top: 3px; line-height: 1.4; }

.ev-src { background: rgba(127,119,221,.04); border: 1px solid rgba(127,119,221,.14); border-radius: 11px; padding: 12px 14px; }
.ev-src-t { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--p-deep, #6b62cc); font-weight: 700; margin-bottom: 7px; }
.ev-src-r { font-size: 11.5px; color: var(--t2, #475569); line-height: 1.5; }
.ev-src-r b { color: var(--t1, #1e2a4a); font-weight: 600; }
.ev-src-warn { color: #b45309; }
.ev-src-warn b { color: #b45309; }

.ev-doc-p { font-size: 12.5px; color: var(--t1, #1e2a4a); line-height: 1.55; margin: 0; }
.ev-doc-p b { font-weight: 600; }
.ev-defs { display: flex; flex-direction: column; gap: 6px; }
.ev-def { display: flex; gap: 10px; font-size: 12px; color: var(--t2, #475569); line-height: 1.45; }
.ev-def-k { flex-shrink: 0; width: 42px; font-weight: 700; color: var(--p-deep, #6b62cc); font-size: 11px; padding-top: 1px; }

.ev-modal-enter-active { transition: opacity .2s ease; }
.ev-modal-enter-active .ev-modal { transition: transform .32s var(--ease-out, cubic-bezier(.16,1,.3,1)), opacity .2s ease; }
.ev-modal-leave-active { transition: opacity .16s ease; }
.ev-modal-enter-from { opacity: 0; }
.ev-modal-enter-from .ev-modal { transform: scale(.95) translateY(14px); opacity: 0; }
.ev-modal-leave-to { opacity: 0; }

@media (max-width: 760px) { .ev-idx { grid-template-columns: 1fr; } .ev-metrics, .ev-mini2 { grid-template-columns: 1fr; } }

/* Доступность: пользователю с настройкой «меньше движения» анимации не нужны —
   в PMO их много (каскады строк, полосы Гантта, всплытие модалок). */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .001ms !important;
    scroll-behavior: auto !important;
  }
}
</style>
