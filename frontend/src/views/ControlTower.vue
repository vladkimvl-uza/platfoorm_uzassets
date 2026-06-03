<script setup lang="ts">
/**
 * ControlTower.vue — «Прогресс-хаб · Обзор».
 *
 * Всегда показывает ЖИВОЕ текущее состояние (в фильтре период: год/квартал/
 * месяц): прогресс % + «должно быть к сегодня» % + план по кварталам +
 * компании. Плюс «Что изменилось» (было→стало) когда есть срезы.
 * Срезы можно фиксировать (вручную/авто) и удалять. Клик по компании →
 * модалка с лентой изменений.
 */
import { ref, computed, onMounted, watch } from "vue";
import { api } from "@/api/client";
import { useToast } from "@/composables/useToast";

interface Quarter { q: number; label: string; plan_pct: number; fact_pct: number; }
interface Co { company_id: string; code: string; name: string; sector: string; color: string; badge: string; score: number | null; tasks_done: number; tasks_total: number; }
interface Current { label: string; at: string; period: string; score: number; fact_now: number; plan_now: number; tasks_done: number; tasks_total: number; overdue: number; quarters: Quarter[]; companies: Co[]; }
interface CoDelta { company_id: string; code: string; name: string; sector: string; color: string; badge: string; from: number; to: number; delta: number; }
interface Comparison { from: { label: string; at: string; score: number }; to: { label: string; at: string; score: number }; portfolio_delta: number | null; improved: CoDelta[]; fell: CoDelta[]; tasks_closed: number; comments_added: number; }
interface SnapRef { id: string; label: string; at: string; score: number; }
interface Digest { year: number; period: string; has_baseline: boolean; current: Current; comparison: Comparison | null; snapshots: SnapRef[]; }
interface TrailItem { ts: string; actor: string; action: string; field: string | null; old_value?: string | null; new_value?: string | null; title: string; is_critical: boolean; }

const toast = useToast();
const digest = ref<Digest | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const freezing = ref(false);

const year = ref(2026);
const period = ref("all");
const YEARS = [2026, 2025];
const PERIODS = [
  { v: "all", l: "Весь год" },
  { v: "q1", l: "I квартал" }, { v: "q2", l: "II квартал" }, { v: "q3", l: "III квартал" }, { v: "q4", l: "IV квартал" },
  { v: "m1", l: "Январь" }, { v: "m2", l: "Февраль" }, { v: "m3", l: "Март" }, { v: "m4", l: "Апрель" },
  { v: "m5", l: "Май" }, { v: "m6", l: "Июнь" }, { v: "m7", l: "Июль" }, { v: "m8", l: "Август" },
  { v: "m9", l: "Сентябрь" }, { v: "m10", l: "Октябрь" }, { v: "m11", l: "Ноябрь" }, { v: "m12", l: "Декабрь" },
];

const fromId = ref("");
const toId = ref("");
const showSnaps = ref(false);

async function load() {
  loading.value = true; error.value = null;
  try {
    const params: any = { period: period.value };
    if (fromId.value) params.from_id = fromId.value;
    if (toId.value) params.to_id = toId.value;
    const { data } = await api.get<Digest>(`/monitoring/digest/${year.value}`, { params });
    digest.value = data;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
  } finally { loading.value = false; }
}
onMounted(load);
watch([year, period, fromId, toId], load);

async function freeze() {
  if (freezing.value) return;
  freezing.value = true;
  try {
    const { data } = await api.post("/monitoring/snapshot", { year: year.value });
    toast.success(`Срез зафиксирован · прогресс ${data.score}%`, 3500);
    fromId.value = ""; toId.value = "";
    await load();
  } catch (e: any) {
    toast.error("Не удалось зафиксировать: " + (e?.response?.data?.detail || e?.message || ""));
  } finally { freezing.value = false; }
}
async function delSnap(s: SnapRef) {
  if (!confirm(`Удалить срез «${s.label}»?`)) return;
  try {
    await api.delete(`/monitoring/snapshot/${s.id}`);
    toast.success("Срез удалён");
    if (fromId.value === s.id) fromId.value = "";
    if (toId.value === s.id) toId.value = "";
    await load();
  } catch (e: any) {
    toast.error("Не удалось удалить: " + (e?.response?.data?.detail || e?.message || ""));
  }
}

// ─── helpers ───────────────────────────────────────────────────
function rc(v: number | null | undefined): string {
  if (v == null) return "#94A3B8";
  if (v >= 80) return "#1D9E75"; if (v >= 60) return "#7C6FF7"; if (v >= 40) return "#EF9F27"; return "#E24B4A";
}
function statusWord(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 80) return "норма"; if (v >= 60) return "хорошо"; if (v >= 40) return "внимание"; return "критично";
}
function fmtDate(s: string | undefined): string {
  if (!s) return "—"; if (s === "Сейчас") return s;
  return new Date(s).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
const cur = computed(() => digest.value?.current);
const cmp = computed(() => digest.value?.comparison);
const gap = computed(() => cur.value ? cur.value.fact_now - cur.value.plan_now : 0); // факт − план(должно)

// ─── модалка + trail ──────────────────────────────────────────
const modalCo = ref<any | null>(null);
const trail = ref<TrailItem[]>([]);
const trailLoading = ref(false);
const trailError = ref<string | null>(null);
async function openCompany(c: any) {
  modalCo.value = c;
  trail.value = []; trailError.value = null; trailLoading.value = true;
  try {
    const { data } = await api.get<{ items: TrailItem[] }>(`/companies/${c.code}/activity`, { params: { limit: 40, days: 120 } });
    trail.value = data.items || [];
  } catch (e: any) {
    trailError.value = e?.response?.status === 403 ? "Нет доступа к ленте" : "Не удалось загрузить ленту";
  } finally { trailLoading.value = false; }
}
function closeModal() { modalCo.value = null; }
function trailTime(ts: string): string { return new Date(ts).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); }
function actionRu(a: string): string { return ({ status_changed: "сменил статус", field_updated: "обновил", created: "создал", archived: "архивировал" } as any)[a] || a; }
</script>

<template>
  <div class="ph">
    <!-- TOPBAR -->
    <div class="ph-top">
      <div class="ph-brand">
        <div class="ph-logo">UA</div>
        <div><div class="ph-eyebrow">UZASSETS · ЕДИНЫЙ МОНИТОРИНГ</div><div class="ph-tt">Прогресс-хаб · Обзор</div></div>
      </div>
      <div class="ph-top-r">
        <select v-model="period" class="ph-sel">
          <option v-for="p in PERIODS" :key="p.v" :value="p.v">{{ p.l }}</option>
        </select>
        <select v-model.number="year" class="ph-sel"><option v-for="y in YEARS" :key="y" :value="y">FY {{ y }}</option></select>
      </div>
    </div>

    <div class="ph-page">
      <div v-if="loading" class="ph-state">Загрузка…</div>
      <div v-else-if="error" class="ph-state err">{{ error }}</div>

      <template v-else-if="cur">
        <!-- БАР СРЕЗОВ -->
        <div class="ph-snapbar">
          <div class="ph-snapbar-l">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1zM4 10h16M8 3v4M16 3v4"/></svg>
            <span><b>{{ digest!.snapshots.length }}</b> срез{{ digest!.snapshots.length === 1 ? '' : digest!.snapshots.length < 5 && digest!.snapshots.length ? 'а' : 'ов' }}</span>
            <button v-if="digest!.snapshots.length" class="ph-link" @click="showSnaps = !showSnaps">{{ showSnaps ? 'скрыть' : 'управлять' }}</button>
          </div>
          <button class="ph-freeze" @click="freeze" :disabled="freezing">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
            {{ freezing ? "Фиксирую…" : "Зафиксировать срез" }}
          </button>
        </div>
        <div v-if="showSnaps && digest!.snapshots.length" class="ph-snaplist">
          <div v-for="s in digest!.snapshots" :key="s.id" class="ph-snaprow">
            <span class="ph-snap-dot" :style="{ background: rc(s.score) }" />
            <span class="ph-snap-lbl">{{ s.label }}</span>
            <span class="ph-snap-score" :style="{ color: rc(s.score) }">{{ s.score }}%</span>
            <span class="ph-snap-at">{{ fmtDate(s.at) }}</span>
            <button class="ph-snap-del" @click="delSnap(s)" title="Удалить срез">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>
            </button>
          </div>
        </div>

        <!-- ВЕРДИКТ + ПЛАН НА СЕГОДНЯ -->
        <div class="ph-verdict">
          <div class="ph-vd-main">
            <div class="ph-vd-label">Прогресс по задачам · {{ PERIODS.find(p=>p.v===period)?.l }}</div>
            <div class="ph-vd-num" :style="{ color: rc(cur.fact_now) }">{{ cur.fact_now }}<small>%</small></div>
            <div class="ph-vd-sub">{{ cur.tasks_done }} из {{ cur.tasks_total }} выполнено</div>
          </div>
          <div class="ph-vd-plan">
            <div class="ph-plan-row">
              <span class="ph-plan-cap">К сегодня должно быть</span>
              <span class="ph-plan-val">{{ cur.plan_now }}%</span>
            </div>
            <div class="ph-plan-bar">
              <div class="ph-plan-target" :style="{ left: Math.min(100,cur.plan_now) + '%' }" />
              <div class="ph-plan-fact" :style="{ width: Math.min(100,cur.fact_now) + '%', background: rc(cur.fact_now) }" />
            </div>
            <div class="ph-plan-gap" :class="gap >= 0 ? 'ok' : 'bad'">
              {{ gap >= 0 ? '↑ опережение ' + gap + ' пп' : '↓ отставание ' + Math.abs(gap) + ' пп' }}
              <span class="ph-plan-status" :style="{ color: rc(cur.fact_now), background: rc(cur.fact_now)+'14' }">{{ statusWord(cur.fact_now) }}</span>
            </div>
            <div class="ph-plan-over"><b style="color:#E24B4A">{{ cur.overdue }}</b> просрочено сейчас</div>
          </div>
        </div>

        <!-- ПЛАН ПО КВАРТАЛАМ -->
        <div class="ph-card">
          <div class="ph-card-h"><span class="ph-eyebrow2">ПЛАН ПО КВАРТАЛАМ</span><span class="ph-card-cap">сколько должно быть выполнено нарастающим (план) и факт</span></div>
          <div class="ph-qs">
            <div v-for="q in cur.quarters" :key="q.q" class="ph-q">
              <div class="ph-q-bars">
                <div class="ph-q-plan" :style="{ height: Math.max(2,q.plan_pct) + '%' }" :title="`План: ${q.plan_pct}%`" />
                <div class="ph-q-fact" :style="{ height: Math.max(2,q.fact_pct) + '%', background: rc(q.fact_pct) }" :title="`Факт: ${q.fact_pct}%`" />
              </div>
              <div class="ph-q-vals"><b :style="{ color: rc(q.fact_pct) }">{{ q.fact_pct }}%</b><span>/ {{ q.plan_pct }}%</span></div>
              <div class="ph-q-lbl">{{ q.label }} кв</div>
            </div>
          </div>
          <div class="ph-q-legend"><span><i class="lg-plan" /> План (дедлайн ≤ конца квартала)</span><span><i class="lg-fact" /> Факт (выполнено)</span></div>
        </div>

        <!-- ЧТО ИЗМЕНИЛОСЬ (если есть срез) -->
        <div v-if="cmp" class="ph-card ph-change">
          <div class="ph-card-h">
            <div><span class="ph-eyebrow2">ЧТО ИЗМЕНИЛОСЬ</span><span class="ph-card-cap">{{ fmtDate(cmp.from.at) }} → {{ fmtDate(cmp.to.at) }}</span></div>
            <div class="ph-change-delta" :class="(cmp.portfolio_delta||0) > 0 ? 'up' : (cmp.portfolio_delta||0) < 0 ? 'dn' : 'fl'">
              {{ cmp.from.score }}% → {{ cmp.to.score }}%
              <b>{{ (cmp.portfolio_delta||0) > 0 ? '+' : '' }}{{ cmp.portfolio_delta }} пп</b>
            </div>
          </div>
          <div class="ph-cols">
            <div class="ph-col">
              <div class="ph-col-h up">Улучшились<span>{{ cmp.improved.length }}</span></div>
              <div v-if="cmp.improved.length" class="ph-col-list">
                <div v-for="c in cmp.improved" :key="c.company_id" class="ph-co" @click="openCompany(c)">
                  <div class="av" :style="{ background: c.color }">{{ c.badge }}</div>
                  <div class="ph-co-m"><div class="ph-co-n">{{ c.name }}</div><div class="ph-co-s">{{ c.sector }}</div></div>
                  <div class="ph-co-p"><span class="f">{{ c.from }}</span><span class="t" :style="{ color: rc(c.to) }">{{ c.to }}%</span></div>
                  <div class="ph-co-d up">+{{ c.delta }}</div>
                </div>
              </div>
              <div v-else class="ph-col-e">Никто не вырос</div>
            </div>
            <div class="ph-col">
              <div class="ph-col-h dn">Провалились<span>{{ cmp.fell.length }}</span></div>
              <div v-if="cmp.fell.length" class="ph-col-list">
                <div v-for="c in cmp.fell" :key="c.company_id" class="ph-co" @click="openCompany(c)">
                  <div class="av" :style="{ background: c.color }">{{ c.badge }}</div>
                  <div class="ph-co-m"><div class="ph-co-n">{{ c.name }}</div><div class="ph-co-s">{{ c.sector }}</div></div>
                  <div class="ph-co-p"><span class="f">{{ c.from }}</span><span class="t" :style="{ color: rc(c.to) }">{{ c.to }}%</span></div>
                  <div class="ph-co-d dn">{{ c.delta }}</div>
                </div>
              </div>
              <div v-else class="ph-col-e">Никто не провалился — хорошо</div>
            </div>
          </div>
          <div class="ph-change-meta">
            <span><b :style="{ color: cmp.tasks_closed>0 ? '#1D9E75' : '#1E2A4A' }">{{ cmp.tasks_closed>0 ? '+'+cmp.tasks_closed : cmp.tasks_closed }}</b> задач закрыто</span>
            <span class="dot">·</span>
            <span><b :style="{ color: cmp.comments_added ? '#7C6FF7' : '#1E2A4A' }">{{ cmp.comments_added }}</b> комментариев</span>
          </div>
        </div>
        <div v-else class="ph-hint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/></svg>
          Зафиксируйте срез — и здесь появится «было → стало»: кто вырос, кто провалился. Срезы фиксируются и автоматически (раз в день).
        </div>

        <!-- КОМПАНИИ (live) -->
        <div class="ph-card">
          <div class="ph-card-h"><span class="ph-eyebrow2">ПО КОМПАНИЯМ</span><span class="ph-card-cap">{{ cur.companies.length }} · клик — лента изменений</span></div>
          <div class="ph-co-list2">
            <div v-for="c in cur.companies" :key="c.company_id" class="ph-co2" :style="{ borderLeftColor: rc(c.score) }" @click="openCompany(c)">
              <div class="av" :style="{ background: c.color }">{{ c.badge }}</div>
              <div class="ph-co-m"><div class="ph-co-n">{{ c.name }}</div><div class="ph-co-s">{{ c.sector }}</div></div>
              <div class="ph-co-track"><span :style="{ width: Math.min(100, c.score || 0) + '%', background: rc(c.score) }" /></div>
              <span class="ph-co-pct" :style="{ color: rc(c.score) }">{{ c.score ?? '—' }}<template v-if="c.score!=null">%</template></span>
              <span class="ph-co-cnt">{{ c.tasks_done }}/{{ c.tasks_total }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- МОДАЛКА -->
    <Teleport to="body">
      <Transition name="ph-modal">
        <div v-if="modalCo" class="ph-back" @click.self="closeModal">
          <div class="ph-mod">
            <div class="ph-mod-head" :style="{ '--accent': modalCo.color }">
              <div class="cmpcell"><div class="av lg" :style="{ background: modalCo.color }">{{ modalCo.badge }}</div><div><div class="ph-mod-name">{{ modalCo.name }}</div><div class="ph-mod-sec">{{ modalCo.sector }}</div></div></div>
              <button class="ph-x" @click="closeModal"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
            </div>
            <div v-if="modalCo.delta != null" class="ph-mod-ab">
              <div class="ph-ab-c"><div class="ph-ab-l">Было</div><div class="ph-ab-v" :style="{ color: rc(modalCo.from) }">{{ modalCo.from }}%</div></div>
              <div class="ph-ab-d" :class="modalCo.delta > 0 ? 'up' : modalCo.delta < 0 ? 'dn' : 'fl'"><div>{{ modalCo.delta > 0 ? '+' : '' }}{{ modalCo.delta }}</div><small>пп</small></div>
              <div class="ph-ab-c"><div class="ph-ab-l">Стало</div><div class="ph-ab-v" :style="{ color: rc(modalCo.to) }">{{ modalCo.to }}%</div></div>
            </div>
            <div v-else class="ph-mod-ab single">
              <div class="ph-ab-c"><div class="ph-ab-l">Прогресс</div><div class="ph-ab-v" :style="{ color: rc(modalCo.score) }">{{ modalCo.score ?? '—' }}<template v-if="modalCo.score!=null">%</template></div><div class="ph-ab-l2">{{ modalCo.tasks_done }}/{{ modalCo.tasks_total }} задач</div></div>
            </div>
            <div class="ph-trail-head">Лента изменений<span>последние 120 дней</span></div>
            <div class="ph-trail">
              <div v-if="trailLoading" class="ph-trail-state">Загрузка…</div>
              <div v-else-if="trailError" class="ph-trail-state">{{ trailError }}</div>
              <div v-else-if="!trail.length" class="ph-trail-state">Изменений нет.</div>
              <div v-for="(it,i) in trail" :key="i" class="ph-tr">
                <div class="ph-tr-rail"><div class="ph-tr-dot" :style="{ background: it.is_critical ? '#E24B4A' : '#7C6FF7' }" /></div>
                <div class="ph-tr-b">
                  <div class="ph-tr-l"><b>{{ it.actor }}</b> {{ actionRu(it.action) }}<template v-if="it.field"> <span class="fld">{{ it.field }}</span></template></div>
                  <div v-if="it.old_value || it.new_value" class="ph-tr-c"><span class="o">{{ it.old_value || '—' }}</span><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 12h14M13 6l6 6-6 6"/></svg><span class="n">{{ it.new_value || '—' }}</span></div>
                  <div class="ph-tr-meta">{{ it.title }}</div>
                </div>
                <div class="ph-tr-t">{{ trailTime(it.ts) }}</div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.ph { --p:#7C6FF7; --p-deep:#534AB7; --navy:#0C1230; --navy2:#141C42; --t3:#64748B; --t4:#94A3B8; --bd:#EAEBF2; --line:#F0F1F6; --ease:cubic-bezier(.34,1.2,.64,1); --ease-out:cubic-bezier(.22,1,.36,1); --sh-sm:0 1px 2px rgba(15,23,60,.05); --sh:0 1px 2px rgba(15,23,60,.05),0 12px 32px rgba(15,23,60,.06); --sh-lg:0 24px 64px rgba(15,23,60,.2),0 8px 24px rgba(15,23,60,.08); color:#0F172A; }
.ph-top { height: 62px; background: linear-gradient(120deg,var(--navy),var(--navy2) 70%,#1C2550); display: flex; align-items: center; padding: 0 24px; }
.ph-brand { display: flex; align-items: center; gap: 12px; }
.ph-logo { width: 34px; height: 34px; border-radius: 10px; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; font-weight: 700; font-size: 13px; display: grid; place-items: center; box-shadow: 0 4px 14px rgba(108,92,231,.4); }
.ph-eyebrow { font-size: 9px; font-weight: 600; letter-spacing: .12em; color: #9A8FFF; }
.ph-tt { color: #fff; font-size: 15px; font-weight: 600; margin-top: 2px; }
.ph-top-r { margin-left: auto; display: flex; gap: 9px; }
.ph-sel { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.09); color: rgba(255,255,255,.82); font: 600 12px inherit; padding: 8px 13px; border-radius: 10px; cursor: pointer; outline: none; }
.ph-sel option { color: #1E2A4A; }
.ph-page { padding: 18px 24px 80px; max-width: 1080px; margin: 0 auto; }
.ph-state { padding: 60px; text-align: center; color: var(--t3); }
.ph-state.err { color: #E24B4A; }

/* snapbar */
.ph-snapbar { display: flex; align-items: center; justify-content: space-between; padding: 11px 16px; background: linear-gradient(135deg,#fff,#FBFAFF); border: 1px solid var(--bd); border-radius: 12px; box-shadow: var(--sh-sm); margin-bottom: 14px; }
.ph-snapbar-l { display: flex; align-items: center; gap: 9px; font-size: 12.5px; color: var(--t3); }
.ph-snapbar-l svg { color: var(--p-deep); } .ph-snapbar-l b { color: #1E2A4A; }
.ph-link { border: 0; background: transparent; color: var(--p-deep); font: 600 11.5px inherit; cursor: pointer; text-decoration: underline; }
.ph-freeze { display: inline-flex; align-items: center; gap: 7px; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border: none; font: 600 12px inherit; padding: 9px 15px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 16px rgba(108,92,231,.3); transition: transform .16s var(--ease); }
.ph-freeze:hover:not(:disabled) { transform: translateY(-1px); } .ph-freeze:disabled { opacity: .6; cursor: default; }
.ph-snaplist { background: #fff; border: 1px solid var(--bd); border-radius: 12px; box-shadow: var(--sh-sm); margin-bottom: 14px; overflow: hidden; }
.ph-snaprow { display: grid; grid-template-columns: 10px 1fr auto auto 30px; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--line); }
.ph-snaprow:last-child { border-bottom: 0; }
.ph-snap-dot { width: 9px; height: 9px; border-radius: 50%; }
.ph-snap-lbl { font-size: 12.5px; font-weight: 500; color: #1E2A4A; }
.ph-snap-score { font-size: 12.5px; font-weight: 700; font-variant-numeric: tabular-nums; }
.ph-snap-at { font-size: 11px; color: var(--t4); }
.ph-snap-del { border: 0; background: transparent; color: var(--t4); cursor: pointer; padding: 4px; border-radius: 7px; }
.ph-snap-del:hover { color: #E24B4A; background: #FCE7E7; }

/* verdict */
.ph-verdict { display: grid; grid-template-columns: 1fr 1.4fr; gap: 0; background: linear-gradient(135deg,#fff,#FBFAFF); border: 1px solid var(--bd); border-radius: 16px; box-shadow: var(--sh); overflow: hidden; margin-bottom: 16px; }
.ph-vd-main { padding: 22px 26px; border-right: 1px solid var(--line); }
.ph-vd-label { font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3); }
.ph-vd-num { font-size: 56px; font-weight: 700; letter-spacing: -.045em; line-height: 1; margin-top: 8px; font-variant-numeric: tabular-nums; }
.ph-vd-num small { font-size: 24px; }
.ph-vd-sub { font-size: 12px; color: var(--t3); margin-top: 8px; }
.ph-vd-plan { padding: 22px 26px; display: flex; flex-direction: column; justify-content: center; gap: 10px; }
.ph-plan-row { display: flex; align-items: baseline; justify-content: space-between; }
.ph-plan-cap { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t3); }
.ph-plan-val { font-size: 22px; font-weight: 700; color: #1E2A4A; font-variant-numeric: tabular-nums; }
.ph-plan-bar { position: relative; height: 10px; border-radius: 6px; background: #F0F1F6; overflow: visible; }
.ph-plan-fact { position: absolute; left: 0; top: 0; height: 100%; border-radius: 6px; transition: width .7s var(--ease-out); }
.ph-plan-target { position: absolute; top: -3px; bottom: -3px; width: 3px; border-radius: 2px; background: #1E2A4A; transition: left .7s var(--ease-out); z-index: 2; }
.ph-plan-gap { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 700; }
.ph-plan-gap.ok { color: #0F6E56; } .ph-plan-gap.bad { color: #B23434; }
.ph-plan-status { margin-left: auto; font-size: 12px; font-weight: 600; padding: 5px 12px; border-radius: 9px; }
.ph-plan-over { font-size: 11.5px; color: var(--t3); } .ph-plan-over b { font-variant-numeric: tabular-nums; }

/* cards */
.ph-card { background: #fff; border: 1px solid var(--bd); border-radius: 16px; box-shadow: var(--sh); margin-bottom: 16px; overflow: hidden; }
.ph-card-h { display: flex; align-items: center; justify-content: space-between; padding: 15px 20px; border-bottom: 1px solid var(--line); }
.ph-eyebrow2 { font-size: 10px; font-weight: 600; letter-spacing: .07em; color: var(--p-deep); }
.ph-card-cap { font-size: 11px; color: var(--t4); margin-left: 10px; }

/* quarters */
.ph-qs { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; padding: 18px 24px 8px; }
.ph-q { display: flex; flex-direction: column; align-items: center; }
.ph-q-bars { position: relative; width: 100%; max-width: 80px; height: 110px; display: flex; align-items: flex-end; justify-content: center; gap: 6px; }
.ph-q-plan { width: 22px; border-radius: 6px 6px 3px 3px; background: repeating-linear-gradient(135deg,#D7D9E0 0 4px,#EAEBEF 4px 8px); transition: height .7s var(--ease-out); }
.ph-q-fact { width: 22px; border-radius: 6px 6px 3px 3px; transition: height .7s var(--ease-out); }
.ph-q-vals { margin-top: 8px; font-size: 11.5px; font-variant-numeric: tabular-nums; } .ph-q-vals b { font-weight: 700; } .ph-q-vals span { color: var(--t4); }
.ph-q-lbl { font-size: 11px; font-weight: 500; color: var(--t3); margin-top: 2px; }
.ph-q-legend { display: flex; gap: 18px; padding: 10px 24px 16px; font-size: 11px; color: var(--t3); }
.ph-q-legend span { display: inline-flex; align-items: center; gap: 6px; }
.ph-q-legend i { width: 11px; height: 11px; border-radius: 3px; } .lg-plan { background: repeating-linear-gradient(135deg,#D7D9E0 0 3px,#EAEBEF 3px 6px); } .lg-fact { background: #7C6FF7; }

/* change */
.ph-change-delta { font-size: 13px; font-weight: 500; color: var(--t3); font-variant-numeric: tabular-nums; }
.ph-change-delta b { margin-left: 8px; padding: 3px 9px; border-radius: 8px; }
.ph-change-delta.up b { background: #E3F8EE; color: #0F6E56; } .ph-change-delta.dn b { background: #FCE7E7; color: #B23434; } .ph-change-delta.fl b { background: #F1F2F6; color: var(--t3); }
.ph-cols { display: grid; grid-template-columns: 1fr 1fr; }
.ph-col { border-right: 1px solid var(--line); } .ph-col:last-child { border-right: 0; }
.ph-col-h { display: flex; align-items: center; gap: 8px; padding: 12px 18px; font-size: 12px; font-weight: 600; border-bottom: 1px solid var(--line); }
.ph-col-h.up { color: #0F6E56; } .ph-col-h.dn { color: #B23434; }
.ph-col-h span { margin-left: auto; font-size: 11px; background: #F1F2F6; color: var(--t3); padding: 2px 9px; border-radius: 8px; }
.ph-co { display: grid; grid-template-columns: 28px 1fr auto auto; align-items: center; gap: 10px; padding: 9px 18px; cursor: pointer; transition: background .12s; }
.ph-co:hover { background: #FAFAFF; }
.av { width: 28px; height: 28px; border-radius: 8px; display: grid; place-items: center; font-size: 8.5px; font-weight: 700; color: #fff; box-shadow: inset 0 1px 1px rgba(255,255,255,.25),0 2px 6px rgba(15,23,60,.12); }
.av.lg { width: 44px; height: 44px; border-radius: 13px; font-size: 13px; }
.ph-co-m { min-width: 0; } .ph-co-n { font-size: 12px; font-weight: 500; color: #1E2A4A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } .ph-co-s { font-size: 10px; color: var(--t4); }
.ph-co-p { display: flex; align-items: baseline; gap: 6px; font-variant-numeric: tabular-nums; } .ph-co-p .f { font-size: 10.5px; color: var(--t4); text-decoration: line-through; } .ph-co-p .t { font-size: 13px; font-weight: 700; }
.ph-co-d { font-size: 12.5px; font-weight: 700; min-width: 32px; text-align: right; font-variant-numeric: tabular-nums; } .ph-co-d.up { color: #0F6E56; } .ph-co-d.dn { color: #B23434; }
.ph-col-e { padding: 24px; text-align: center; color: var(--t4); font-size: 12px; }
.ph-change-meta { display: flex; align-items: center; gap: 10px; padding: 13px 20px; border-top: 1px solid var(--line); font-size: 12.5px; color: var(--t3); } .ph-change-meta b { font-variant-numeric: tabular-nums; } .ph-change-meta .dot { color: var(--t4); }

.ph-hint { display: flex; align-items: center; gap: 9px; margin-bottom: 16px; padding: 13px 16px; background: rgba(124,111,247,.05); border: 1px solid rgba(124,111,247,.16); border-radius: 12px; font-size: 12px; color: var(--t3); } .ph-hint svg { color: var(--p); flex-shrink: 0; }

/* companies live */
.ph-co-list2 { padding: 4px 0; }
.ph-co2 { display: grid; grid-template-columns: 28px 2fr 3fr 52px 60px; align-items: center; gap: 12px; padding: 10px 20px; border-bottom: 1px solid var(--line); border-left: 3px solid transparent; cursor: pointer; transition: background .12s; }
.ph-co2:hover { background: #FAFAFF; } .ph-co2:last-child { border-bottom: 0; }
.ph-co-track { height: 7px; border-radius: 5px; background: #F0F1F6; overflow: hidden; } .ph-co-track > span { display: block; height: 100%; border-radius: 5px; transition: width .7s var(--ease-out); }
.ph-co-pct { font-size: 13px; font-weight: 700; text-align: right; font-variant-numeric: tabular-nums; }
.ph-co-cnt { font-size: 10.5px; color: var(--t4); text-align: right; font-variant-numeric: tabular-nums; }

/* modal */
.ph-back { position: fixed; inset: 0; background: rgba(15,18,40,.5); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); z-index: 9999; display: grid; place-items: center; padding: 24px; }
.ph-mod { width: min(580px,100%); max-height: calc(100vh - 48px); background: #fff; border-radius: 18px; box-shadow: var(--sh-lg); display: flex; flex-direction: column; overflow: hidden; }
.ph-mod-head { display: flex; align-items: center; justify-content: space-between; padding: 20px 22px; border-bottom: 1px solid var(--line); background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 9%, #fff), #fff 70%); }
.cmpcell { display: flex; align-items: center; gap: 12px; }
.ph-mod-name { font-size: 16px; font-weight: 600; color: #1E2A4A; } .ph-mod-sec { font-size: 11px; color: var(--t3); margin-top: 2px; }
.ph-x { border: 0; background: rgba(15,23,60,.04); cursor: pointer; color: #64748B; width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center; } .ph-x:hover { background: rgba(127,119,221,.12); color: var(--p-deep); }
.ph-mod-ab { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; padding: 18px 22px; margin: 16px 22px 0; background: #FAFAFD; border: 1px solid var(--line); border-radius: 13px; }
.ph-mod-ab.single { grid-template-columns: 1fr; }
.ph-ab-c { text-align: center; } .ph-ab-l { font-size: 9.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--t4); } .ph-ab-l2 { font-size: 11px; color: var(--t3); margin-top: 4px; }
.ph-ab-v { font-size: 34px; font-weight: 700; letter-spacing: -.035em; margin-top: 5px; font-variant-numeric: tabular-nums; line-height: 1; }
.ph-ab-d { text-align: center; font-size: 19px; font-weight: 700; padding: 8px 14px; border-radius: 11px; font-variant-numeric: tabular-nums; } .ph-ab-d.up { background: #E3F8EE; color: #0F6E56; } .ph-ab-d.dn { background: #FCE7E7; color: #B23434; } .ph-ab-d.fl { background: #F1F2F6; color: var(--t3); } .ph-ab-d small { display: block; font-size: 8.5px; text-transform: uppercase; opacity: .7; }
.ph-trail-head { display: flex; align-items: baseline; justify-content: space-between; padding: 18px 22px 10px; font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3); } .ph-trail-head span { font-size: 10px; font-weight: 500; color: var(--t4); text-transform: none; letter-spacing: 0; }
.ph-trail { overflow-y: auto; padding: 0 22px 20px; }
.ph-trail-state { padding: 28px; text-align: center; color: var(--t4); font-size: 12px; }
.ph-tr { display: flex; gap: 12px; padding: 12px 0; }
.ph-tr-rail { position: relative; display: flex; justify-content: center; width: 8px; flex-shrink: 0; }
.ph-tr-rail::before { content: ""; position: absolute; top: 14px; bottom: -12px; width: 1.5px; background: var(--line); } .ph-tr:last-child .ph-tr-rail::before { display: none; }
.ph-tr-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 4px; box-shadow: 0 0 0 3px #fff; }
.ph-tr-b { flex: 1; min-width: 0; }
.ph-tr-l { font-size: 12.5px; color: #334155; } .ph-tr-l b { font-weight: 600; color: #1E2A4A; } .fld { color: var(--p-deep); font-weight: 600; }
.ph-tr-c { display: inline-flex; align-items: center; gap: 8px; margin-top: 5px; font-size: 11.5px; } .ph-tr-c .o { color: var(--t4); text-decoration: line-through; } .ph-tr-c .n { color: #0F6E56; font-weight: 600; } .ph-tr-c svg { color: var(--t4); }
.ph-tr-meta { font-size: 10.5px; color: var(--t4); margin-top: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ph-tr-t { font-size: 10.5px; color: var(--t4); white-space: nowrap; }
.ph-modal-enter-active,.ph-modal-leave-active { transition: opacity .22s ease; } .ph-modal-enter-from,.ph-modal-leave-to { opacity: 0; } .ph-modal-enter-active .ph-mod { transition: transform .4s var(--ease); } .ph-modal-enter-from .ph-mod { transform: scale(.94) translateY(12px); }

@media (max-width: 820px) { .ph-verdict { grid-template-columns: 1fr; } .ph-vd-main { border-right: 0; border-bottom: 1px solid var(--line); } .ph-cols { grid-template-columns: 1fr; } .ph-col { border-right: 0; border-bottom: 1px solid var(--line); } }
</style>
