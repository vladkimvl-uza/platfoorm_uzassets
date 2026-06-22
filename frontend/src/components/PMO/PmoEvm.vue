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

const props = defineProps<{ companyCode: string; year?: number }>();

const loading = ref(true);
const error = ref<string | null>(null);
const data = ref<EvmResponse | null>(null);

async function load() {
  loading.value = true; error.value = null;
  try {
    data.value = await pmoApi.getEvm(props.companyCode, props.year);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось рассчитать освоенный объём";
  } finally { loading.value = false; }
}
onMounted(load);
watch(() => [props.companyCode, props.year], load);

const fmtMoney = (n: number | null | undefined) =>
  n == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n);
const fmtSigned = (n: number | null | undefined) =>
  n == null ? "—" : (n > 0 ? "+" : "") + new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n);
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
  if (v == null) return "нет данных";
  if (kind === "spi") {
    if (v >= 1.0) return "идём по графику / с опережением";
    if (v >= 0.95) return "почти по графику";
    if (v >= 0.85) return "лёгкое отставание";
    return "существенное отставание";
  }
  if (v >= 1.0) return "в рамках бюджета / экономия";
  if (v >= 0.95) return "почти в бюджете";
  if (v >= 0.85) return "лёгкий перерасход";
  return "существенный перерасход";
}

const RAG_C: Record<EvmRag, string> = { green: "#1D9E75", amber: "#D97706", red: "#E24B4A", na: "#94a3b8" };
const RAG_L: Record<EvmRag, string> = { green: "В норме", amber: "Внимание", red: "Риск", na: "—" };

const hasBudget = computed(() => !!data.value && data.value.budgeted_count > 0);
const sortedProjects = computed<EvmProject[]>(() => {
  if (!data.value) return [];
  const order: Record<EvmRag, number> = { red: 0, amber: 1, green: 2, na: 3 };
  return [...data.value.projects].sort((a, b) => order[a.rag] - order[b.rag]);
});
</script>

<template>
  <div class="ev">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />
    <UzaStateBlock v-if="loading" state="loading" text="Считаем освоенный объём…" />

    <template v-else-if="data">
      <!-- индексы SPI/CPI -->
      <div class="ev-idx">
        <div class="ev-gauge" :style="{ '--c': idxColor(data.spi) }">
          <div class="ev-gauge-head">
            <span class="ev-gauge-l">SPI · индекс расписания</span>
            <span class="ev-gauge-v">{{ fmtIdx(data.spi) }}</span>
          </div>
          <div class="ev-bar">
            <div class="ev-bar-mid"></div>
            <div class="ev-bar-mark" :style="{ left: idxPos(data.spi) + '%' }"></div>
          </div>
          <div class="ev-gauge-verdict">{{ idxVerdict(data.spi, "spi") }}</div>
        </div>
        <div class="ev-gauge" :style="{ '--c': idxColor(data.cpi) }">
          <div class="ev-gauge-head">
            <span class="ev-gauge-l">CPI · индекс стоимости</span>
            <span class="ev-gauge-v">{{ fmtIdx(data.cpi) }}</span>
          </div>
          <div class="ev-bar">
            <div class="ev-bar-mid"></div>
            <div class="ev-bar-mark" :style="{ left: idxPos(data.cpi) + '%' }"></div>
          </div>
          <div class="ev-gauge-verdict">{{ idxVerdict(data.cpi, "cpi") }}</div>
        </div>
      </div>

      <!-- ключевые величины -->
      <div class="ev-cards">
        <div class="ev-card"><span class="ev-card-l">BAC · бюджет</span><span class="ev-card-v">{{ fmtMoney(data.bac) }}</span></div>
        <div class="ev-card"><span class="ev-card-l">EV · освоено</span><span class="ev-card-v">{{ fmtMoney(data.ev) }}</span></div>
        <div class="ev-card"><span class="ev-card-l">PV · план</span><span class="ev-card-v">{{ fmtMoney(data.pv) }}</span></div>
        <div class="ev-card"><span class="ev-card-l">AC · факт затрат</span><span class="ev-card-v">{{ fmtMoney(data.ac) }}</span></div>
        <div class="ev-card" :class="{ 'ev-neg': (data.sv ?? 0) < 0 }"><span class="ev-card-l">SV · откл. графика</span><span class="ev-card-v">{{ fmtSigned(data.sv) }}</span></div>
        <div class="ev-card" :class="{ 'ev-neg': (data.cv ?? 0) < 0 }"><span class="ev-card-l">CV · откл. стоимости</span><span class="ev-card-v">{{ fmtSigned(data.cv) }}</span></div>
        <div class="ev-card ev-card-accent"><span class="ev-card-l">EAC · прогноз стоимости</span><span class="ev-card-v">{{ fmtMoney(data.eac) }}</span></div>
        <div class="ev-card" :class="{ 'ev-neg': (data.vac ?? 0) < 0 }"><span class="ev-card-l">VAC · прогноз отклонения</span><span class="ev-card-v">{{ fmtSigned(data.vac) }}</span></div>
      </div>

      <div v-if="!hasBudget" class="ev-hint">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/><path d="M8 5 V8.5 M8 10.5 V11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
        Стоимостные метрики (CPI, EV, прогноз) появятся, когда у проектов заполнены <b>бюджет</b> и <b>факт затрат</b>. Сейчас показан индекс расписания SPI по прогрессу.
      </div>

      <!-- по проектам -->
      <div class="ev-tblwrap">
        <UzaStateBlock v-if="!sortedProjects.length" state="empty" variant="block" title="Нет проектов" text="Добавьте проекты в портфель, чтобы видеть освоенный объём." />
        <table v-else class="uza-table ev-tbl">
          <thead>
            <tr>
              <th>Проект</th><th>Прогресс / план</th><th>SPI</th><th>CPI</th>
              <th>SV</th><th>CV</th><th>EAC</th><th>VAC</th><th>Статус</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(p, i) in sortedProjects" :key="p.project_id || i" class="ev-row" :style="{ animationDelay: Math.min(i*0.03, 0.4)+'s' }">
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
              <td><span class="ev-rag" :style="{ color: RAG_C[p.rag], background: RAG_C[p.rag] + '18' }"><span class="ev-rag-dot" :style="{ background: RAG_C[p.rag] }"></span>{{ RAG_L[p.rag] }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="ev-foot">Индексы ≥ 1.0 — хорошо (по графику / в бюджете). На дату {{ new Date(data.as_of).toLocaleDateString("ru-RU") }} · бюджетных проектов: {{ data.budgeted_count }} из {{ data.total_count }}.</div>
    </template>
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

@media (max-width: 760px) { .ev-idx { grid-template-columns: 1fr; } }
</style>
