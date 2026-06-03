<script setup lang="ts">
/**
 * ControlTower.vue — «Прогресс-хаб · Сравнение» (Контрольная вышка).
 *
 * Сплит-сравнение двух периодов с построчной таблицей по компаниям:
 *   слева период A · по центру Δ · справа период B.
 * Клик по компании → модалка: метрики A/B + trail-лента изменений
 * (audit-log + история задач). Данные реальные (с 2026).
 */
import { ref, computed, onMounted, watch } from "vue";
import { api } from "@/api/client";
import { useToast } from "@/composables/useToast";

interface Period { key: number; label: string; label_full: string; plan: number; done: number; pct: number; }
interface Company { company_id: string; code: string; name: string; sector: string; sector_color: string; badge: string; periods: Period[]; }
interface TrailItem { kind: string; ts: string; actor: string; action: string; field: string | null; old_value?: string | null; new_value?: string | null; title: string; entity_type: string; is_critical: boolean; }

const toast = useToast();
const companies = ref<Company[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

const year = ref(2026);
type Gran = "month" | "quarter";
const gran = ref<Gran>("quarter");
type Metric = "tasks" | "projects";
const metric = ref<Metric>("tasks");
const idxA = ref(0);
const idxB = ref(1);
const YEARS = [2026, 2025];

async function load() {
  loading.value = true; error.value = null;
  try {
    const { data } = await api.get<{ companies: Company[] }>(`/monitoring/companies/${year.value}`, {
      params: { granularity: gran.value, metric: metric.value },
    });
    companies.value = data.companies;
    const n = data.companies[0]?.periods.length ?? 4;
    if (idxA.value >= n) idxA.value = 0;
    if (idxB.value >= n) idxB.value = Math.min(1, n - 1);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
  } finally { loading.value = false; }
}
onMounted(load);
watch([year, gran, metric], load);

// ─── helpers ───────────────────────────────────────────────────
function rag(v: number): string { return v >= 80 ? "g" : v >= 60 ? "p" : v >= 40 ? "a" : "r"; }
function ragColor(v: number): string { return { g: "#1D9E75", p: "#7C6FF7", a: "#EF9F27", r: "#E24B4A" }[rag(v)]!; }
const periodList = computed(() => companies.value[0]?.periods || []);
const metricWord = computed(() => (metric.value === "tasks" ? "задачи" : "проекты"));
function pctA(c: Company) { return c.periods[idxA.value]?.pct ?? 0; }
function pctB(c: Company) { return c.periods[idxB.value]?.pct ?? 0; }

const rows = computed(() =>
  [...companies.value].sort((x, y) => (pctB(y) - pctA(y)) - (pctB(x) - pctA(x))),
);
const avgA = computed(() => companies.value.length ? Math.round(companies.value.reduce((s, c) => s + pctA(c), 0) / companies.value.length) : 0);
const avgB = computed(() => companies.value.length ? Math.round(companies.value.reduce((s, c) => s + pctB(c), 0) / companies.value.length) : 0);
const critA = computed(() => companies.value.filter((c) => pctA(c) < 40).length);
const critB = computed(() => companies.value.filter((c) => pctB(c) < 40).length);
const normA = computed(() => companies.value.filter((c) => pctA(c) >= 80).length);
const normB = computed(() => companies.value.filter((c) => pctB(c) >= 80).length);
const riskA = computed(() => companies.value.filter((c) => pctA(c) >= 40 && pctA(c) < 80).length);
const riskB = computed(() => companies.value.filter((c) => pctB(c) >= 40 && pctB(c) < 80).length);
const dAvg = computed(() => avgB.value - avgA.value);
const labA = computed(() => periodList.value[idxA.value]?.label_full || "A");
const labB = computed(() => periodList.value[idxB.value]?.label_full || "B");

const today = new Date().toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });

// ─── модалка компании + trail ──────────────────────────────────
const modalCo = ref<Company | null>(null);
const trail = ref<TrailItem[]>([]);
const trailLoading = ref(false);
const trailError = ref<string | null>(null);

async function openCompany(c: Company) {
  modalCo.value = c;
  trail.value = []; trailError.value = null; trailLoading.value = true;
  try {
    const { data } = await api.get<{ items: TrailItem[] }>(`/companies/${c.code}/activity`, {
      params: { limit: 40, days: 90 },
    });
    trail.value = data.items || [];
  } catch (e: any) {
    trailError.value = e?.response?.status === 403 ? "Нет доступа к ленте этой компании" : "Не удалось загрузить ленту";
  } finally { trailLoading.value = false; }
}
function closeModal() { modalCo.value = null; }

function trailTime(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
function actionRu(a: string): string {
  return ({ status_changed: "сменил статус", field_updated: "обновил поле", created: "создал", archived: "архивировал" } as any)[a] || a;
}

function freeze() {
  toast.info("Фиксация среза на " + today + " — механизм снимков подключается следующим шагом", 4000);
}
</script>

<template>
  <div class="ph">
    <!-- TOPBAR (navy) -->
    <div class="ph-top">
      <div>
        <div class="ph-eyebrow">UZASSETS · ЕДИНЫЙ МОНИТОРИНГ</div>
        <div class="ph-tt">Прогресс-хаб · Сравнение</div>
      </div>
      <div class="ph-top-r">
        <div class="ph-mode">
          <button :class="{ on: metric === 'tasks' }" @click="metric = 'tasks'">Задачи</button>
          <button :class="{ on: metric === 'projects' }" @click="metric = 'projects'">Проекты</button>
        </div>
        <div class="ph-mode">
          <button v-for="g in (['quarter','month'] as Gran[])" :key="g" :class="{ on: gran === g }" @click="gran = g">
            {{ g === 'quarter' ? 'Кварталы' : 'Месяцы' }}
          </button>
        </div>
        <select v-model.number="year" class="ph-sel"><option v-for="y in YEARS" :key="y" :value="y">FY {{ y }}</option></select>
      </div>
    </div>

    <div class="ph-page">
      <!-- BASELINE -->
      <div class="ph-base">
        <div class="ph-base-ic">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1zM4 10h16M8 3v4M16 3v4"/></svg>
        </div>
        <div>
          <div class="ph-base-t">Базовый снимок: {{ today }} · фактические данные {{ year }} приняты за старт</div>
          <div class="ph-base-s">Раньше прогресс не фиксировался. С этой даты — отслеживание по месяцам, кварталам и кастомным периодам.</div>
        </div>
        <button class="ph-freeze" @click="freeze">＋ Зафиксировать период</button>
      </div>

      <div v-if="loading" class="ph-state">Загрузка…</div>
      <div v-else-if="error" class="ph-state err">{{ error }}</div>

      <template v-else>
        <!-- SPLIT SUMMARY -->
        <div class="ph-split">
          <div class="ph-side a">
            <div class="ph-sl">Период A</div>
            <div class="ph-pick">
              <select v-model.number="idxA" class="ph-pick-sel">
                <option v-for="(p,i) in periodList" :key="i" :value="i">{{ p.label_full }}</option>
              </select>
            </div>
            <div class="ph-metrics">
              <div><div class="ph-mv">{{ avgA }}%</div><div class="ph-mk">Средний прогресс</div></div>
              <div><div class="ph-mv">{{ critA }}</div><div class="ph-mk">Критично</div></div>
            </div>
            <div class="ph-pills">
              <span class="pill g">норма {{ normA }}</span><span class="pill a">риск {{ riskA }}</span><span class="pill r">критич {{ critA }}</span>
            </div>
          </div>

          <div class="ph-vs">
            <div class="ph-vs-arrow" :style="{ color: dAvg > 0 ? '#7CFFC4' : dAvg < 0 ? '#FF9B9B' : '#fff' }">{{ dAvg > 0 ? '▲' : dAvg < 0 ? '▼' : '=' }}</div>
            <div class="ph-vs-dv">{{ dAvg > 0 ? '+' : '' }}{{ dAvg }} п.п.</div>
            <div class="ph-vs-dl">Δ A→B</div>
          </div>

          <div class="ph-side b">
            <div class="ph-sl">Период B</div>
            <div class="ph-pick end">
              <select v-model.number="idxB" class="ph-pick-sel">
                <option v-for="(p,i) in periodList" :key="i" :value="i">{{ p.label_full }}</option>
              </select>
            </div>
            <div class="ph-metrics end">
              <div><div class="ph-mv">{{ critB }}</div><div class="ph-mk">Критично</div></div>
              <div><div class="ph-mv">{{ avgB }}%</div><div class="ph-mk">Средний прогресс</div></div>
            </div>
            <div class="ph-pills end">
              <span class="pill r">критич {{ critB }}</span><span class="pill a">риск {{ riskB }}</span><span class="pill g">норма {{ normB }}</span>
            </div>
          </div>
        </div>

        <!-- COMPARISON TABLE -->
        <div class="ph-panel">
          <div class="ph-ph">
            <div class="ph-ph-t">Построчное сравнение · {{ labA }} ↔ {{ labB }} · {{ metricWord }}</div>
            <div class="ph-ph-hint">клик по компании — детали и лента изменений</div>
          </div>
          <table class="ph-table">
            <thead><tr>
              <th class="cmp">Компания</th>
              <th class="A">Период A · {{ periodList[idxA]?.label }}</th>
              <th class="D">Δ</th>
              <th class="B">Период B · {{ periodList[idxB]?.label }}</th>
            </tr></thead>
            <tbody>
              <tr v-for="c in rows" :key="c.company_id" @click="openCompany(c)">
                <td>
                  <div class="cmpcell">
                    <div class="av" :style="{ background: c.sector_color }">{{ c.badge }}</div>
                    <div><div class="nm">{{ c.name }}</div><div class="sec">{{ c.sector }}</div></div>
                  </div>
                </td>
                <td>
                  <div class="vcell A" :class="rag(pctA(c))">
                    <span class="vnum">{{ pctA(c) }}%</span>
                    <div class="vbar"><i :style="{ width: Math.min(100,pctA(c))+'%', background: ragColor(pctA(c)) }" /></div>
                  </div>
                </td>
                <td class="dcell">
                  <span class="dchip" :class="pctB(c)-pctA(c) > 0 ? 'up' : pctB(c)-pctA(c) < 0 ? 'dn' : 'fl'">
                    {{ pctB(c)-pctA(c) > 0 ? '▲ '+(pctB(c)-pctA(c)) : pctB(c)-pctA(c) < 0 ? '▼ '+(pctA(c)-pctB(c)) : '·' }}
                  </span>
                </td>
                <td>
                  <div class="vcell B" :class="rag(pctB(c))">
                    <div class="vbar"><i :style="{ width: Math.min(100,pctB(c))+'%', background: ragColor(pctB(c)) }" /></div>
                    <span class="vnum">{{ pctB(c) }}%</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="ph-legend">
            <div><span><i style="background:#DCFCE7" />≥80</span><span><i style="background:#F0EEFF" />60–79</span><span><i style="background:#FAEEDA" />40–59</span><span><i style="background:#FCE5E5" />&lt;40</span></div>
            <div>Δ зелёный — рост, красный — просадка к периоду A</div>
          </div>
        </div>
      </template>
    </div>

    <!-- ═══════════ МОДАЛКА КОМПАНИИ ═══════════ -->
    <Teleport to="body">
      <Transition name="ph-modal">
        <div v-if="modalCo" class="ph-back" @click.self="closeModal">
          <div class="ph-mod">
            <div class="ph-mod-head">
              <div class="cmpcell">
                <div class="av lg" :style="{ background: modalCo.sector_color }">{{ modalCo.badge }}</div>
                <div><div class="ph-mod-name">{{ modalCo.name }}</div><div class="sec">{{ modalCo.sector }}</div></div>
              </div>
              <button class="ph-x" @click="closeModal" aria-label="Закрыть">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>

            <!-- A/B сравнение метрик -->
            <div class="ph-mod-ab">
              <div class="ph-ab-cell">
                <div class="ph-ab-lbl">{{ labA }}</div>
                <div class="ph-ab-val" :style="{ color: ragColor(pctA(modalCo)) }">{{ pctA(modalCo) }}%</div>
                <div class="ph-ab-sub">{{ modalCo.periods[idxA]?.done }}/{{ modalCo.periods[idxA]?.plan }} {{ metricWord }}</div>
              </div>
              <div class="ph-ab-delta">
                <div :style="{ color: pctB(modalCo)-pctA(modalCo) > 0 ? '#1D9E75' : pctB(modalCo)-pctA(modalCo) < 0 ? '#E24B4A' : '#888780' }">
                  {{ pctB(modalCo)-pctA(modalCo) > 0 ? '+' : '' }}{{ pctB(modalCo)-pctA(modalCo) }} п.п.
                </div>
                <small>динамика</small>
              </div>
              <div class="ph-ab-cell">
                <div class="ph-ab-lbl">{{ labB }}</div>
                <div class="ph-ab-val" :style="{ color: ragColor(pctB(modalCo)) }">{{ pctB(modalCo) }}%</div>
                <div class="ph-ab-sub">{{ modalCo.periods[idxB]?.done }}/{{ modalCo.periods[idxB]?.plan }} {{ metricWord }}</div>
              </div>
            </div>

            <!-- TRAIL -->
            <div class="ph-trail-head">Лента изменений · последние 90 дней</div>
            <div class="ph-trail">
              <div v-if="trailLoading" class="ph-trail-state">Загрузка ленты…</div>
              <div v-else-if="trailError" class="ph-trail-state">{{ trailError }}</div>
              <div v-else-if="!trail.length" class="ph-trail-state">Изменений за период нет.</div>
              <div v-for="(it,i) in trail" :key="i" class="ph-tr-item" :class="{ crit: it.is_critical }">
                <div class="ph-tr-dot" :style="{ background: it.is_critical ? '#E24B4A' : '#7C6FF7' }" />
                <div class="ph-tr-body">
                  <div class="ph-tr-line">
                    <b>{{ it.actor }}</b> {{ actionRu(it.action) }}
                    <template v-if="it.field"> · <span class="ph-tr-field">{{ it.field }}</span></template>
                  </div>
                  <div v-if="it.old_value || it.new_value" class="ph-tr-change">
                    <span class="old">{{ it.old_value || '—' }}</span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
                    <span class="new">{{ it.new_value || '—' }}</span>
                  </div>
                  <div class="ph-tr-meta">{{ it.title }}</div>
                </div>
                <div class="ph-tr-time">{{ trailTime(it.ts) }}</div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.ph { --p:#7C6FF7; --p-deep:#534AB7; --navy:#0C1230; --navy2:#111A3E; --green:#1D9E75; --amber:#EF9F27; --red:#E24B4A; --blue:#378ADD; --t3:#64748B; --t4:#94A3B8; --bd:rgba(99,102,180,.13); --line:#EEF1F5; --ease:cubic-bezier(.34,1.2,.64,1); color:#0F172A; }
.ph-top { height: 60px; background: linear-gradient(135deg,var(--navy),var(--navy2)); display: flex; align-items: center; padding: 0 24px; gap: 14px; }
.ph-eyebrow { font-size: 9px; font-weight: 600; letter-spacing: .1em; color: #8B7FFF; }
.ph-tt { color: #fff; font-size: 15px; font-weight: 600; letter-spacing: -.01em; margin-top: 2px; }
.ph-top-r { margin-left: auto; display: flex; gap: 9px; align-items: center; }
.ph-mode { display: inline-flex; background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.1); border-radius: 9px; padding: 3px; }
.ph-mode button { border: none; background: transparent; color: rgba(255,255,255,.6); font: 600 11px inherit; padding: 6px 13px; border-radius: 7px; cursor: pointer; transition: all .16s var(--ease); }
.ph-mode button.on { background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; }
.ph-sel { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); color: rgba(255,255,255,.8); font-size: 12px; padding: 8px 13px; border-radius: 9px; cursor: pointer; outline: none; }
.ph-sel option { color: #1E2A4A; }

.ph-page { padding: 16px 24px 80px; max-width: 1380px; margin: 0 auto; }
.ph-state { padding: 50px; text-align: center; color: var(--t3); }
.ph-state.err { color: var(--red); }

/* baseline */
.ph-base { display: flex; align-items: center; gap: 12px; background: linear-gradient(135deg,#fff,#FAFAFF); border: 1px solid var(--bd); border-left: 3px solid var(--p); border-radius: 12px; padding: 12px 16px; margin-bottom: 16px; }
.ph-base-ic { width: 30px; height: 30px; border-radius: 8px; background: #F0EEFF; color: var(--p-deep); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.ph-base-t { font-size: 12.5px; font-weight: 600; color: #1E2A4A; }
.ph-base-s { font-size: 11.5px; color: var(--t3); margin-top: 1px; }
.ph-freeze { margin-left: auto; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border: none; font: 600 12px inherit; padding: 9px 15px; border-radius: 9px; cursor: pointer; box-shadow: 0 3px 12px rgba(108,92,231,.28); flex-shrink: 0; }
.ph-freeze:hover { filter: brightness(1.05); }

/* split */
.ph-split { display: grid; grid-template-columns: 1fr 120px 1fr; margin-bottom: 16px; }
.ph-side { background: #fff; border: 1px solid var(--bd); padding: 16px 20px; }
.ph-side.a { border-radius: 14px 0 0 14px; border-right: none; }
.ph-side.b { border-radius: 0 14px 14px 0; border-left: none; text-align: right; }
.ph-sl { font-size: 10px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--t3); }
.ph-pick { margin: 7px 0 13px; } .ph-pick.end { display: flex; justify-content: flex-end; }
.ph-pick-sel { background: #F6F6FC; border: 1px solid var(--bd); border-radius: 8px; padding: 7px 11px; font: 600 12px inherit; color: #1E2A4A; cursor: pointer; outline: none; }
.ph-metrics { display: flex; gap: 24px; } .ph-metrics.end { justify-content: flex-end; }
.ph-mv { font-size: 30px; font-weight: 700; letter-spacing: -.03em; color: #1E2A4A; font-variant-numeric: tabular-nums; line-height: 1; }
.ph-mk { font-size: 10px; color: var(--t3); text-transform: uppercase; letter-spacing: .05em; margin-top: 5px; }
.ph-pills { display: flex; gap: 8px; margin-top: 12px; } .ph-pills.end { justify-content: flex-end; }
.pill { font-size: 10px; font-weight: 600; padding: 3px 9px; border-radius: 7px; }
.pill.g { background: #DCFCE7; color: #0F6E56; } .pill.a { background: #FAEEDA; color: #854F0B; } .pill.r { background: #FCE5E5; color: #B23434; }
.ph-vs { background: linear-gradient(180deg,#1E2A4A,#2A3A5E); color: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; }
.ph-vs-arrow { font-size: 22px; font-weight: 700; }
.ph-vs-dv { font-size: 19px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.ph-vs-dl { font-size: 8.5px; letter-spacing: .08em; text-transform: uppercase; opacity: .7; }

/* table */
.ph-panel { background: #fff; border: 1px solid var(--bd); border-radius: 16px; overflow: hidden; }
.ph-ph { padding: 14px 18px; border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; }
.ph-ph-t { font-size: 13px; font-weight: 600; color: #1E2A4A; }
.ph-ph-hint { font-size: 11px; color: var(--t4); }
.ph-table { width: 100%; border-collapse: collapse; }
.ph-table thead th { font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t4); padding: 11px 14px; background: #FBFBFE; }
.ph-table thead th.A { text-align: right; color: var(--p-deep); } .ph-table thead th.B { text-align: left; color: var(--blue); } .ph-table thead th.D { text-align: center; }
.ph-table thead th.cmp { text-align: left; padding-left: 18px; }
.ph-table tbody tr { border-bottom: 1px solid #F6F7FB; cursor: pointer; transition: background .12s; }
.ph-table tbody tr:hover { background: #FAFBFF; }
.cmpcell { display: flex; align-items: center; gap: 10px; padding: 8px 8px 8px 18px; }
.av { width: 27px; height: 27px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 8.5px; font-weight: 700; flex-shrink: 0; color: #fff; }
.av.lg { width: 40px; height: 40px; border-radius: 11px; font-size: 12px; }
.nm { font-size: 12.5px; font-weight: 500; } .sec { font-size: 10px; color: var(--t4); margin-top: 1px; }
.vcell { padding: 6px 14px; } .vcell.A { display: flex; align-items: center; justify-content: flex-end; gap: 10px; } .vcell.B { display: flex; align-items: center; gap: 10px; }
.vbar { width: 90px; height: 7px; border-radius: 99px; background: var(--line); overflow: hidden; position: relative; }
.vbar i { position: absolute; top: 0; bottom: 0; border-radius: 99px; transition: width 1s var(--ease); }
.vcell.A .vbar i { right: 0; } .vcell.B .vbar i { left: 0; }
.vnum { font-size: 13.5px; font-weight: 700; font-variant-numeric: tabular-nums; width: 46px; }
.vcell.A .vnum { text-align: right; }
.g .vnum { color: #0F6E56; } .p .vnum { color: var(--p-deep); } .a .vnum { color: #854F0B; } .r .vnum { color: #B23434; }
.dcell { text-align: center; font-variant-numeric: tabular-nums; }
.dchip { display: inline-flex; align-items: center; gap: 3px; font-size: 12px; font-weight: 700; padding: 3px 9px; border-radius: 8px; }
.dchip.up { background: #DCFCE7; color: #0F6E56; } .dchip.dn { background: #FCE5E5; color: #B23434; } .dchip.fl { background: #F1F2F6; color: var(--t3); }
.ph-legend { display: flex; justify-content: space-between; padding: 12px 18px; border-top: 1px solid var(--line); font-size: 10px; color: var(--t3); }
.ph-legend > div { display: flex; gap: 12px; }
.ph-legend i { display: inline-block; width: 9px; height: 9px; border-radius: 3px; margin-right: 4px; vertical-align: -1px; }

/* MODAL */
.ph-back { position: fixed; inset: 0; background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); z-index: 9999; display: grid; place-items: center; padding: 24px; }
.ph-mod { width: min(620px,100%); max-height: calc(100vh - 48px); background: #fff; border-radius: 16px; box-shadow: 0 24px 64px rgba(15,23,60,.28); display: flex; flex-direction: column; overflow: hidden; }
.ph-mod-head { display: flex; align-items: center; justify-content: space-between; padding: 18px 20px; border-bottom: 1px solid var(--line); }
.ph-mod-name { font-size: 15px; font-weight: 600; color: #1E2A4A; }
.ph-x { border: 0; background: transparent; cursor: pointer; color: #64748B; width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center; }
.ph-x:hover { background: rgba(127,119,221,.1); color: var(--p-deep); }
.ph-mod-ab { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 14px; padding: 20px; background: #FAFAFD; border-bottom: 1px solid var(--line); }
.ph-ab-cell { text-align: center; }
.ph-ab-lbl { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--t4); }
.ph-ab-val { font-size: 34px; font-weight: 700; letter-spacing: -.03em; margin-top: 4px; font-variant-numeric: tabular-nums; }
.ph-ab-sub { font-size: 11px; color: var(--t3); margin-top: 2px; }
.ph-ab-delta { text-align: center; font-size: 17px; font-weight: 700; font-variant-numeric: tabular-nums; }
.ph-ab-delta small { display: block; font-size: 9px; font-weight: 500; color: var(--t4); text-transform: uppercase; letter-spacing: .05em; margin-top: 2px; }
.ph-trail-head { padding: 14px 20px 8px; font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3); }
.ph-trail { overflow-y: auto; padding: 0 20px 18px; }
.ph-trail-state { padding: 24px; text-align: center; color: var(--t4); font-size: 12px; }
.ph-tr-item { display: flex; gap: 12px; padding: 11px 0; border-bottom: 1px solid #F5F6F8; }
.ph-tr-item:last-child { border-bottom: 0; }
.ph-tr-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; }
.ph-tr-body { flex: 1; min-width: 0; }
.ph-tr-line { font-size: 12.5px; color: #334155; } .ph-tr-line b { font-weight: 600; color: #1E2A4A; }
.ph-tr-field { color: var(--p-deep); font-weight: 500; }
.ph-tr-change { display: inline-flex; align-items: center; gap: 7px; margin-top: 4px; font-size: 11.5px; }
.ph-tr-change .old { color: var(--t4); text-decoration: line-through; }
.ph-tr-change svg { color: var(--t4); }
.ph-tr-change .new { color: #0F6E56; font-weight: 500; }
.ph-tr-meta { font-size: 10.5px; color: var(--t4); margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ph-tr-time { font-size: 10.5px; color: var(--t4); white-space: nowrap; }

.ph-modal-enter-active, .ph-modal-leave-active { transition: opacity .2s ease; }
.ph-modal-enter-from, .ph-modal-leave-to { opacity: 0; }
.ph-modal-enter-active .ph-mod { transition: transform .35s var(--ease); }
.ph-modal-enter-from .ph-mod { transform: scale(.95) translateY(10px); }

@media (max-width: 960px) {
  .ph-split { grid-template-columns: 1fr; }
  .vbar { width: 56px; }
}
</style>
