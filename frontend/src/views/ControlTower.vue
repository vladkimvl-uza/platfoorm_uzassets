<script setup lang="ts">
/**
 * ControlTower.vue — «Прогресс-хаб · Сравнение» (Контрольная вышка).
 *
 * Сплит-сравнение двух периодов с построчной таблицей по компаниям:
 *   слева период A · по центру Δ · справа период B.
 * Клик по компании → модалка: тренд по всем периодам + метрики A/B +
 * trail-лента изменений (audit-log + история задач). Данные реальные (с 2026).
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
  return new Date(ts).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
function actionRu(a: string): string {
  return ({ status_changed: "сменил статус", field_updated: "обновил", created: "создал", archived: "архивировал" } as any)[a] || a;
}
function freeze() {
  toast.info("Фиксация среза на " + today + " — механизм снимков подключается следующим шагом", 4000);
}
</script>

<template>
  <div class="ph">
    <!-- TOPBAR -->
    <div class="ph-top">
      <div class="ph-brand">
        <div class="ph-logo">UA</div>
        <div>
          <div class="ph-eyebrow">UZASSETS · ЕДИНЫЙ МОНИТОРИНГ</div>
          <div class="ph-tt">Прогресс-хаб · Сравнение</div>
        </div>
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
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1zM4 10h16M8 3v4M16 3v4"/></svg>
        </div>
        <div class="ph-base-tx">
          <div class="ph-base-t">Базовый снимок: {{ today }} · фактические данные {{ year }} приняты за старт</div>
          <div class="ph-base-s">Раньше прогресс не фиксировался. С этой даты — отслеживание по месяцам, кварталам и кастомным периодам.</div>
        </div>
        <button class="ph-freeze" @click="freeze">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          Зафиксировать период
        </button>
      </div>

      <div v-if="loading" class="ph-state">Загрузка…</div>
      <div v-else-if="error" class="ph-state err">{{ error }}</div>

      <template v-else>
        <!-- SPLIT SUMMARY -->
        <div class="ph-split">
          <div class="ph-side a">
            <div class="ph-sl">Период A</div>
            <select v-model.number="idxA" class="ph-pick-sel">
              <option v-for="(p,i) in periodList" :key="i" :value="i">{{ p.label_full }}</option>
            </select>
            <div class="ph-metrics">
              <div><div class="ph-mv">{{ avgA }}<small>%</small></div><div class="ph-mk">Средний прогресс</div></div>
              <div><div class="ph-mv" :style="{ color: critA ? '#E24B4A' : '#1E2A4A' }">{{ critA }}</div><div class="ph-mk">Критично</div></div>
            </div>
            <div class="ph-pills">
              <span class="pill g">{{ normA }} норма</span><span class="pill a">{{ riskA }} риск</span><span class="pill r">{{ critA }} критич</span>
            </div>
          </div>

          <div class="ph-vs">
            <div class="ph-vs-badge" :class="dAvg > 0 ? 'up' : dAvg < 0 ? 'dn' : 'fl'">
              <span class="ph-vs-arrow">{{ dAvg > 0 ? '↑' : dAvg < 0 ? '↓' : '=' }}</span>
            </div>
            <div class="ph-vs-dv">{{ dAvg > 0 ? '+' : '' }}{{ dAvg }}</div>
            <div class="ph-vs-dl">п.п. · A→B</div>
          </div>

          <div class="ph-side b">
            <div class="ph-sl">Период B</div>
            <select v-model.number="idxB" class="ph-pick-sel">
              <option v-for="(p,i) in periodList" :key="i" :value="i">{{ p.label_full }}</option>
            </select>
            <div class="ph-metrics end">
              <div><div class="ph-mv" :style="{ color: critB ? '#E24B4A' : '#1E2A4A' }">{{ critB }}</div><div class="ph-mk">Критично</div></div>
              <div><div class="ph-mv">{{ avgB }}<small>%</small></div><div class="ph-mk">Средний прогресс</div></div>
            </div>
            <div class="ph-pills end">
              <span class="pill r">{{ critB }} критич</span><span class="pill a">{{ riskB }} риск</span><span class="pill g">{{ normB }} норма</span>
            </div>
          </div>
        </div>

        <!-- COMPARISON TABLE -->
        <div class="ph-panel">
          <div class="ph-ph">
            <div>
              <div class="ph-ph-t">Построчное сравнение</div>
              <div class="ph-ph-cap">{{ labA }} ↔ {{ labB }} · {{ metricWord }} · {{ rows.length }} компаний</div>
            </div>
            <div class="ph-ph-hint">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/></svg>
              клик — детали и лента изменений
            </div>
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
                    <div class="cmpmeta"><div class="nm">{{ c.name }}</div><div class="sec">{{ c.sector }}</div></div>
                  </div>
                </td>
                <td>
                  <div class="vcell A" :class="rag(pctA(c))">
                    <span class="vnum">{{ pctA(c) }}%</span>
                    <div class="vbar"><i :style="{ width: Math.min(100,pctA(c))+'%' }" /></div>
                  </div>
                </td>
                <td class="dcell">
                  <span class="dchip" :class="pctB(c)-pctA(c) > 0 ? 'up' : pctB(c)-pctA(c) < 0 ? 'dn' : 'fl'">
                    {{ pctB(c)-pctA(c) > 0 ? '↑'+(pctB(c)-pctA(c)) : pctB(c)-pctA(c) < 0 ? '↓'+(pctA(c)-pctB(c)) : '·' }}
                  </span>
                </td>
                <td>
                  <div class="vcell B" :class="rag(pctB(c))">
                    <div class="vbar"><i :style="{ width: Math.min(100,pctB(c))+'%' }" /></div>
                    <span class="vnum">{{ pctB(c) }}%</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="ph-legend">
            <div><span><i class="lg g" />≥80 норма</span><span><i class="lg p" />60–79</span><span><i class="lg a" />40–59</span><span><i class="lg r" />&lt;40 критично</span></div>
            <div class="ph-legend-mut">Δ зелёный — рост, красный — просадка к периоду A</div>
          </div>
        </div>
      </template>
    </div>

    <!-- ═══════════ МОДАЛКА ═══════════ -->
    <Teleport to="body">
      <Transition name="ph-modal">
        <div v-if="modalCo" class="ph-back" @click.self="closeModal">
          <div class="ph-mod">
            <div class="ph-mod-head" :style="{ '--accent': modalCo.sector_color }">
              <div class="cmpcell">
                <div class="av lg" :style="{ background: modalCo.sector_color }">{{ modalCo.badge }}</div>
                <div><div class="ph-mod-name">{{ modalCo.name }}</div><div class="ph-mod-sec">{{ modalCo.sector }}</div></div>
              </div>
              <button class="ph-x" @click="closeModal" aria-label="Закрыть">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>

            <!-- тренд по всем периодам -->
            <div class="ph-trend">
              <div class="ph-trend-lbl">Тренд по периодам · {{ metricWord }}</div>
              <div class="ph-trend-bars">
                <div v-for="(p,i) in modalCo.periods" :key="i" class="ph-tb" :class="{ selA: i===idxA, selB: i===idxB }">
                  <div class="ph-tb-pct">{{ p.pct }}%</div>
                  <div class="ph-tb-track"><div class="ph-tb-fill" :style="{ height: Math.max(3,p.pct)+'%', background: ragColor(p.pct) }" /></div>
                  <div class="ph-tb-lbl">{{ p.label }}</div>
                </div>
              </div>
            </div>

            <!-- A/B -->
            <div class="ph-mod-ab">
              <div class="ph-ab-cell">
                <div class="ph-ab-lbl">A · {{ labA }}</div>
                <div class="ph-ab-val" :style="{ color: ragColor(pctA(modalCo)) }">{{ pctA(modalCo) }}%</div>
                <div class="ph-ab-sub">{{ modalCo.periods[idxA]?.done }}/{{ modalCo.periods[idxA]?.plan }}</div>
              </div>
              <div class="ph-ab-delta" :class="pctB(modalCo)-pctA(modalCo) > 0 ? 'up' : pctB(modalCo)-pctA(modalCo) < 0 ? 'dn' : 'fl'">
                <div>{{ pctB(modalCo)-pctA(modalCo) > 0 ? '+' : '' }}{{ pctB(modalCo)-pctA(modalCo) }}</div>
                <small>п.п.</small>
              </div>
              <div class="ph-ab-cell">
                <div class="ph-ab-lbl">B · {{ labB }}</div>
                <div class="ph-ab-val" :style="{ color: ragColor(pctB(modalCo)) }">{{ pctB(modalCo) }}%</div>
                <div class="ph-ab-sub">{{ modalCo.periods[idxB]?.done }}/{{ modalCo.periods[idxB]?.plan }}</div>
              </div>
            </div>

            <!-- TRAIL -->
            <div class="ph-trail-head">Лента изменений<span>последние 90 дней</span></div>
            <div class="ph-trail">
              <div v-if="trailLoading" class="ph-trail-state">Загрузка ленты…</div>
              <div v-else-if="trailError" class="ph-trail-state">{{ trailError }}</div>
              <div v-else-if="!trail.length" class="ph-trail-state">Изменений за период нет.</div>
              <div v-for="(it,i) in trail" :key="i" class="ph-tr-item" :class="{ crit: it.is_critical }">
                <div class="ph-tr-rail"><div class="ph-tr-dot" :style="{ background: it.is_critical ? '#E24B4A' : '#7C6FF7' }" /></div>
                <div class="ph-tr-body">
                  <div class="ph-tr-line"><b>{{ it.actor }}</b> {{ actionRu(it.action) }}<template v-if="it.field"> <span class="ph-tr-field">{{ it.field }}</span></template></div>
                  <div v-if="it.old_value || it.new_value" class="ph-tr-change">
                    <span class="old">{{ it.old_value || '—' }}</span>
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
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
.ph {
  --p:#7C6FF7; --p-deep:#534AB7; --navy:#0C1230; --navy2:#141C42;
  --green:#1D9E75; --amber:#EF9F27; --red:#E24B4A; --blue:#378ADD;
  --t1:#0F172A; --t3:#64748B; --t4:#94A3B8; --bd:#EAEBF2; --line:#F0F1F6;
  --ease:cubic-bezier(.34,1.2,.64,1); --ease-out:cubic-bezier(.22,1,.36,1);
  --sh-sm:0 1px 2px rgba(15,23,60,.05); --sh:0 1px 2px rgba(15,23,60,.05),0 12px 32px rgba(15,23,60,.06);
  --sh-lg:0 24px 64px rgba(15,23,60,.20),0 8px 24px rgba(15,23,60,.08);
  color:var(--t1); min-height:100%;
}

/* TOPBAR */
.ph-top { height: 62px; background: linear-gradient(120deg,var(--navy),var(--navy2) 70%,#1C2550); display: flex; align-items: center; padding: 0 24px; gap: 14px; box-shadow: inset 0 -1px 0 rgba(255,255,255,.06); }
.ph-brand { display: flex; align-items: center; gap: 12px; }
.ph-logo { width: 34px; height: 34px; border-radius: 10px; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; font-weight: 700; font-size: 13px; display: grid; place-items: center; letter-spacing: -.02em; box-shadow: 0 4px 14px rgba(108,92,231,.4); }
.ph-eyebrow { font-size: 9px; font-weight: 600; letter-spacing: .12em; color: #9A8FFF; }
.ph-tt { color: #fff; font-size: 15px; font-weight: 600; letter-spacing: -.01em; margin-top: 2px; }
.ph-top-r { margin-left: auto; display: flex; gap: 9px; align-items: center; }
.ph-mode { display: inline-flex; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.09); border-radius: 10px; padding: 3px; }
.ph-mode button { border: none; background: transparent; color: rgba(255,255,255,.58); font: 600 11px inherit; padding: 6px 13px; border-radius: 7px; cursor: pointer; transition: all .18s var(--ease); }
.ph-mode button.on { background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; box-shadow: 0 2px 10px rgba(108,92,231,.45); }
.ph-mode button:not(.on):hover { color: rgba(255,255,255,.85); }
.ph-sel { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.09); color: rgba(255,255,255,.82); font: 600 12px inherit; padding: 8px 13px; border-radius: 10px; cursor: pointer; outline: none; }
.ph-sel option { color: #1E2A4A; }

.ph-page { padding: 18px 24px 80px; max-width: 1380px; margin: 0 auto; }
.ph-state { padding: 60px; text-align: center; color: var(--t3); font-size: 13px; }
.ph-state.err { color: var(--red); }

/* BASELINE */
.ph-base { display: flex; align-items: center; gap: 13px; background: linear-gradient(135deg,#fff,#FBFAFF); border: 1px solid var(--bd); border-left: 3px solid var(--p); border-radius: 13px; padding: 13px 16px; margin-bottom: 18px; box-shadow: var(--sh-sm); }
.ph-base-ic { width: 32px; height: 32px; border-radius: 9px; background: linear-gradient(135deg,#F0EEFF,#E7E3FF); color: var(--p-deep); display: grid; place-items: center; flex-shrink: 0; }
.ph-base-tx { min-width: 0; }
.ph-base-t { font-size: 12.5px; font-weight: 600; color: #1E2A4A; }
.ph-base-s { font-size: 11.5px; color: var(--t3); margin-top: 2px; }
.ph-freeze { margin-left: auto; display: inline-flex; align-items: center; gap: 7px; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border: none; font: 600 12px inherit; padding: 10px 16px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 16px rgba(108,92,231,.3); flex-shrink: 0; transition: transform .16s var(--ease), box-shadow .16s; }
.ph-freeze:hover { transform: translateY(-1px); box-shadow: 0 8px 22px rgba(108,92,231,.4); }

/* SPLIT */
.ph-split { display: grid; grid-template-columns: 1fr 128px 1fr; margin-bottom: 18px; box-shadow: var(--sh); border-radius: 16px; }
.ph-side { background: linear-gradient(180deg,#fff,#FCFCFE); border: 1px solid var(--bd); padding: 18px 22px; }
.ph-side.a { border-radius: 16px 0 0 16px; border-right: none; }
.ph-side.b { border-radius: 0 16px 16px 0; border-left: none; text-align: right; }
.ph-sl { font-size: 10px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--t4); }
.ph-pick-sel { margin: 9px 0 15px; background: #F6F6FC; border: 1px solid var(--bd); border-radius: 9px; padding: 8px 12px; font: 600 12.5px inherit; color: #1E2A4A; cursor: pointer; outline: none; transition: border-color .15s; }
.ph-pick-sel:hover { border-color: var(--p); }
.ph-side.b .ph-pick-sel { text-align: right; }
.ph-metrics { display: flex; gap: 28px; } .ph-metrics.end { justify-content: flex-end; }
.ph-mv { font-size: 32px; font-weight: 700; letter-spacing: -.035em; color: #1E2A4A; font-variant-numeric: tabular-nums; line-height: 1; }
.ph-mv small { font-size: 16px; font-weight: 600; color: var(--t4); margin-left: 1px; }
.ph-mk { font-size: 9.5px; color: var(--t4); text-transform: uppercase; letter-spacing: .05em; margin-top: 7px; }
.ph-pills { display: flex; gap: 7px; margin-top: 14px; } .ph-pills.end { justify-content: flex-end; }
.pill { font-size: 10px; font-weight: 600; padding: 4px 9px; border-radius: 8px; font-variant-numeric: tabular-nums; }
.pill.g { background: #E3F8EE; color: #0F6E56; } .pill.a { background: #FBF0DC; color: #854F0B; } .pill.r { background: #FCE7E7; color: #B23434; }
.ph-vs { background: linear-gradient(180deg,#1A2342,#0F1530); color: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; border: 1px solid #1A2342; }
.ph-vs-badge { width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; font-size: 19px; font-weight: 700; margin-bottom: 3px; }
.ph-vs-badge.up { background: rgba(124,255,196,.16); color: #7CFFC4; box-shadow: 0 0 0 4px rgba(124,255,196,.08); }
.ph-vs-badge.dn { background: rgba(255,155,155,.16); color: #FF9B9B; box-shadow: 0 0 0 4px rgba(255,155,155,.08); }
.ph-vs-badge.fl { background: rgba(255,255,255,.12); color: #fff; }
.ph-vs-dv { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -.03em; }
.ph-vs-dl { font-size: 8.5px; letter-spacing: .07em; text-transform: uppercase; opacity: .65; }

/* TABLE */
.ph-panel { background: #fff; border: 1px solid var(--bd); border-radius: 16px; overflow: hidden; box-shadow: var(--sh); }
.ph-ph { padding: 16px 20px; border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; }
.ph-ph-t { font-size: 13.5px; font-weight: 600; color: #1E2A4A; }
.ph-ph-cap { font-size: 11px; color: var(--t4); margin-top: 2px; }
.ph-ph-hint { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--t4); }
.ph-table { width: 100%; border-collapse: collapse; }
.ph-table thead th { font-size: 9.5px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: var(--t4); padding: 12px 16px; background: #FBFBFE; }
.ph-table thead th.A { text-align: right; color: var(--p-deep); } .ph-table thead th.B { text-align: left; color: var(--blue); } .ph-table thead th.D { text-align: center; }
.ph-table thead th.cmp { text-align: left; padding-left: 20px; }
.ph-table tbody tr { border-top: 1px solid var(--line); cursor: pointer; transition: background .14s; }
.ph-table tbody tr:hover { background: #FAFAFF; }
.cmpcell { display: flex; align-items: center; gap: 11px; padding: 9px 8px 9px 20px; }
.av { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; font-size: 9px; font-weight: 700; flex-shrink: 0; color: #fff; box-shadow: inset 0 1px 1px rgba(255,255,255,.25), 0 2px 6px rgba(15,23,60,.12); }
.av.lg { width: 44px; height: 44px; border-radius: 13px; font-size: 13px; }
.cmpmeta { min-width: 0; }
.nm { font-size: 12.5px; font-weight: 500; color: #1E2A4A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 220px; }
.sec { font-size: 10px; color: var(--t4); margin-top: 1px; }
.vcell { padding: 7px 16px; } .vcell.A { display: flex; align-items: center; justify-content: flex-end; gap: 11px; } .vcell.B { display: flex; align-items: center; gap: 11px; }
.vbar { width: 100px; height: 8px; border-radius: 99px; background: #F0F1F6; overflow: hidden; position: relative; }
.vbar i { position: absolute; top: 0; bottom: 0; border-radius: 99px; transition: width 1s var(--ease-out); }
.vcell.A .vbar i { right: 0; } .vcell.B .vbar i { left: 0; }
.vnum { font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; width: 44px; }
.vcell.A .vnum { text-align: right; }
.g .vnum { color: #0F6E56; } .p .vnum { color: var(--p-deep); } .a .vnum { color: #854F0B; } .r .vnum { color: #B23434; }
.g .vbar i { background: linear-gradient(90deg,#16B583,#1D9E75); } .p .vbar i { background: linear-gradient(90deg,#8B7FFF,#7C6FF7); }
.a .vbar i { background: linear-gradient(90deg,#F2AE3E,#EF9F27); } .r .vbar i { background: linear-gradient(90deg,#EA5A59,#E24B4A); }
.dcell { text-align: center; }
.dchip { display: inline-flex; align-items: center; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 9px; font-variant-numeric: tabular-nums; }
.dchip.up { background: #E3F8EE; color: #0F6E56; } .dchip.dn { background: #FCE7E7; color: #B23434; } .dchip.fl { background: #F1F2F6; color: var(--t4); }
.ph-legend { display: flex; justify-content: space-between; align-items: center; padding: 13px 20px; border-top: 1px solid var(--line); font-size: 10.5px; color: var(--t3); }
.ph-legend > div:first-child { display: flex; gap: 14px; }
.ph-legend .lg { display: inline-block; width: 9px; height: 9px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
.lg.g { background: #1D9E75; } .lg.p { background: #7C6FF7; } .lg.a { background: #EF9F27; } .lg.r { background: #E24B4A; }
.ph-legend-mut { color: var(--t4); }

/* MODAL */
.ph-back { position: fixed; inset: 0; background: rgba(15,18,40,.5); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); z-index: 9999; display: grid; place-items: center; padding: 24px; }
.ph-mod { width: min(620px,100%); max-height: calc(100vh - 48px); background: #fff; border-radius: 18px; box-shadow: var(--sh-lg); display: flex; flex-direction: column; overflow: hidden; }
.ph-mod-head { display: flex; align-items: center; justify-content: space-between; padding: 20px 22px; border-bottom: 1px solid var(--line); background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 9%, #fff), #fff 70%); }
.ph-mod-name { font-size: 16px; font-weight: 600; color: #1E2A4A; letter-spacing: -.01em; }
.ph-mod-sec { font-size: 11px; color: var(--t3); margin-top: 2px; }
.ph-x { border: 0; background: rgba(15,23,60,.04); cursor: pointer; color: #64748B; width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center; transition: all .15s; }
.ph-x:hover { background: rgba(127,119,221,.12); color: var(--p-deep); }

.ph-trend { padding: 18px 22px 6px; }
.ph-trend-lbl { font-size: 10px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: var(--t4); margin-bottom: 12px; }
.ph-trend-bars { display: flex; gap: 10px; align-items: flex-end; }
.ph-tb { flex: 1; display: flex; flex-direction: column; align-items: center; padding: 6px 2px; border-radius: 9px; transition: background .15s; }
.ph-tb.selA { background: rgba(124,111,247,.09); } .ph-tb.selB { background: rgba(55,138,221,.09); }
.ph-tb-pct { font-size: 11px; font-weight: 600; color: #475569; margin-bottom: 5px; font-variant-numeric: tabular-nums; }
.ph-tb-track { width: 100%; max-width: 40px; height: 70px; background: #F0F1F6; border-radius: 7px; display: flex; align-items: flex-end; overflow: hidden; }
.ph-tb-fill { width: 100%; border-radius: 6px; transition: height .7s var(--ease-out); }
.ph-tb-lbl { font-size: 10px; color: var(--t4); margin-top: 6px; font-weight: 500; }

.ph-mod-ab { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; padding: 16px 22px; margin: 6px 22px 0; background: #FAFAFD; border: 1px solid var(--line); border-radius: 13px; }
.ph-ab-cell { text-align: center; }
.ph-ab-lbl { font-size: 9.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--t4); }
.ph-ab-val { font-size: 32px; font-weight: 700; letter-spacing: -.035em; margin-top: 5px; font-variant-numeric: tabular-nums; line-height: 1; }
.ph-ab-sub { font-size: 11px; color: var(--t3); margin-top: 4px; }
.ph-ab-delta { text-align: center; font-size: 19px; font-weight: 700; font-variant-numeric: tabular-nums; padding: 8px 14px; border-radius: 11px; }
.ph-ab-delta.up { background: #E3F8EE; color: #0F6E56; } .ph-ab-delta.dn { background: #FCE7E7; color: #B23434; } .ph-ab-delta.fl { background: #F1F2F6; color: var(--t3); }
.ph-ab-delta small { display: block; font-size: 8.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; opacity: .7; margin-top: 1px; }

.ph-trail-head { display: flex; align-items: baseline; justify-content: space-between; padding: 18px 22px 10px; font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3); }
.ph-trail-head span { font-size: 10px; font-weight: 500; color: var(--t4); text-transform: none; letter-spacing: 0; }
.ph-trail { overflow-y: auto; padding: 0 22px 20px; }
.ph-trail-state { padding: 28px; text-align: center; color: var(--t4); font-size: 12px; }
.ph-tr-item { display: flex; gap: 12px; padding: 12px 0; }
.ph-tr-rail { position: relative; display: flex; justify-content: center; width: 8px; flex-shrink: 0; }
.ph-tr-rail::before { content: ""; position: absolute; top: 14px; bottom: -12px; width: 1.5px; background: var(--line); }
.ph-tr-item:last-child .ph-tr-rail::before { display: none; }
.ph-tr-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 4px; z-index: 1; box-shadow: 0 0 0 3px #fff; }
.ph-tr-body { flex: 1; min-width: 0; }
.ph-tr-line { font-size: 12.5px; color: #334155; } .ph-tr-line b { font-weight: 600; color: #1E2A4A; }
.ph-tr-field { color: var(--p-deep); font-weight: 600; }
.ph-tr-change { display: inline-flex; align-items: center; gap: 8px; margin-top: 5px; font-size: 11.5px; }
.ph-tr-change .old { color: var(--t4); text-decoration: line-through; }
.ph-tr-change svg { color: var(--t4); }
.ph-tr-change .new { color: #0F6E56; font-weight: 600; }
.ph-tr-meta { font-size: 10.5px; color: var(--t4); margin-top: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ph-tr-time { font-size: 10.5px; color: var(--t4); white-space: nowrap; padding-top: 1px; }

.ph-modal-enter-active, .ph-modal-leave-active { transition: opacity .22s ease; }
.ph-modal-enter-from, .ph-modal-leave-to { opacity: 0; }
.ph-modal-enter-active .ph-mod { transition: transform .4s var(--ease); }
.ph-modal-enter-from .ph-mod { transform: scale(.94) translateY(12px); }

@media (max-width: 960px) {
  .ph-split { grid-template-columns: 1fr; }
  .ph-side.a, .ph-side.b { border-radius: 16px; border: 1px solid var(--bd); }
  .vbar { width: 60px; }
}
</style>
