<script setup lang="ts">
/**
 * ControlTower.vue — «Прогресс-хаб · Обзор».
 *
 * Каркас для высшего руководства: «Что изменилось» между двумя срезами
 * (или последним срезом ↔ сейчас). Вердикт по портфелю + кто вырос / кто
 * провалился + активность. Метрика — «Исполнение обязательств» (из задач,
 * чей срок наступил, сколько выполнено).
 *
 * Снимки — позвоночник: GET /monitoring/digest, POST /monitoring/snapshot.
 * Клик по компании → модалка с trail-лентой изменений.
 */
import { ref, computed, onMounted, watch } from "vue";
import { api } from "@/api/client";
import { useToast } from "@/composables/useToast";

interface Side { label: string; at: string; score: number | null; }
interface CoDelta { company_id: string; code: string; name: string; sector: string; color: string; badge: string; from: number; to: number; delta: number; }
interface SnapRef { id: string; label: string; at: string; }
interface Digest {
  year: number; needs_baseline: boolean;
  from?: Side; to?: Side; portfolio_delta?: number | null;
  improved?: CoDelta[]; fell?: CoDelta[];
  tasks_closed?: number; overdue_now?: number; comments_added?: number;
  snapshots?: SnapRef[];
}
interface TrailItem { ts: string; actor: string; action: string; field: string | null; old_value?: string | null; new_value?: string | null; title: string; is_critical: boolean; }

const toast = useToast();
const digest = ref<Digest | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const freezing = ref(false);

const year = ref(2026);
const YEARS = [2026, 2025];
const fromId = ref<string>("");   // "" = авто (последний снимок)
const toId = ref<string>("");     // "" = Сейчас

async function load() {
  loading.value = true; error.value = null;
  try {
    const params: any = {};
    if (fromId.value) params.from_id = fromId.value;
    if (toId.value) params.to_id = toId.value;
    const { data } = await api.get<Digest>(`/monitoring/digest/${year.value}`, { params });
    digest.value = data;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
  } finally { loading.value = false; }
}
onMounted(load);
watch([year, fromId, toId], load);

async function freeze() {
  if (freezing.value) return;
  freezing.value = true;
  try {
    const { data } = await api.post("/monitoring/snapshot", { year: year.value });
    toast.success(`Срез зафиксирован · исполнение ${data.score}%`, 3500);
    fromId.value = ""; toId.value = "";
    await load();
  } catch (e: any) {
    toast.error("Не удалось зафиксировать срез: " + (e?.response?.data?.detail || e?.message || ""));
  } finally { freezing.value = false; }
}

// ─── helpers ───────────────────────────────────────────────────
function scoreColor(v: number | null | undefined): string {
  if (v == null) return "#94A3B8";
  if (v >= 80) return "#1D9E75"; if (v >= 60) return "#7C6FF7"; if (v >= 40) return "#EF9F27"; return "#E24B4A";
}
function statusWord(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 80) return "норма"; if (v >= 60) return "хорошо"; if (v >= 40) return "внимание"; return "критично";
}
function fmtDate(s: string | undefined): string {
  if (!s) return "—";
  if (s === "Сейчас") return s;
  return new Date(s).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
const dlt = computed(() => digest.value?.portfolio_delta ?? null);

// ─── модалка компании + trail ──────────────────────────────────
const modalCo = ref<CoDelta | null>(null);
const trail = ref<TrailItem[]>([]);
const trailLoading = ref(false);
const trailError = ref<string | null>(null);
async function openCompany(c: CoDelta) {
  modalCo.value = c;
  trail.value = []; trailError.value = null; trailLoading.value = true;
  try {
    const { data } = await api.get<{ items: TrailItem[] }>(`/companies/${c.code}/activity`, { params: { limit: 40, days: 120 } });
    trail.value = data.items || [];
  } catch (e: any) {
    trailError.value = e?.response?.status === 403 ? "Нет доступа к ленте этой компании" : "Не удалось загрузить ленту";
  } finally { trailLoading.value = false; }
}
function closeModal() { modalCo.value = null; }
function trailTime(ts: string): string { return new Date(ts).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); }
function actionRu(a: string): string { return ({ status_changed: "сменил статус", field_updated: "обновил", created: "создал", archived: "архивировал" } as any)[a] || a; }
</script>

<template>
  <div class="ph">
    <div class="ph-top">
      <div class="ph-brand">
        <div class="ph-logo">UA</div>
        <div><div class="ph-eyebrow">UZASSETS · ЕДИНЫЙ МОНИТОРИНГ</div><div class="ph-tt">Прогресс-хаб · Обзор</div></div>
      </div>
      <div class="ph-top-r">
        <select v-model.number="year" class="ph-sel"><option v-for="y in YEARS" :key="y" :value="y">FY {{ y }}</option></select>
      </div>
    </div>

    <div class="ph-page">
      <div v-if="loading" class="ph-state">Загрузка обзора…</div>
      <div v-else-if="error" class="ph-state err">{{ error }}</div>

      <!-- НЕТ БАЗОВОГО СРЕЗА -->
      <div v-else-if="digest?.needs_baseline" class="ph-empty">
        <div class="ph-empty-ic">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1zM4 10h16M8 3v4M16 3v4"/></svg>
        </div>
        <div class="ph-empty-t">Отслеживание ещё не запущено</div>
        <div class="ph-empty-s">Зафиксируйте базовый срез — он станет точкой отсчёта. После следующего среза появится обзор «Что изменилось»: кто вырос, кто провалился, что закрыто.</div>
        <button class="ph-freeze big" @click="freeze" :disabled="freezing">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          {{ freezing ? "Фиксирую…" : "Зафиксировать базовый срез" }}
        </button>
      </div>

      <!-- ОБЗОР -->
      <template v-else-if="digest && digest.from && digest.to">
        <!-- заголовок периода + переключатели -->
        <div class="ph-head">
          <div class="ph-head-l">
            <div class="ph-eyebrow2">ОБЗОР ЗА ПЕРИОД</div>
            <div class="ph-period">{{ fmtDate(digest.from.at) }} → {{ fmtDate(digest.to.at) }}</div>
          </div>
          <div class="ph-head-r">
            <div class="ph-pick-wrap">
              <span>С</span>
              <select v-model="fromId" class="ph-sel2">
                <option value="">последний срез</option>
                <option v-for="s in digest.snapshots" :key="s.id" :value="s.id">{{ s.label }}</option>
              </select>
            </div>
            <div class="ph-pick-wrap">
              <span>По</span>
              <select v-model="toId" class="ph-sel2">
                <option value="">Сейчас</option>
                <option v-for="s in digest.snapshots" :key="s.id" :value="s.id">{{ s.label }}</option>
              </select>
            </div>
            <button class="ph-freeze" @click="freeze" :disabled="freezing">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
              {{ freezing ? "…" : "Зафиксировать срез" }}
            </button>
          </div>
        </div>

        <!-- ВЕРДИКТ ПОРТФЕЛЯ -->
        <div class="ph-verdict">
          <div class="ph-vd-label">Исполнение обязательств <span>из задач, чей срок наступил</span></div>
          <div class="ph-vd-row">
            <div class="ph-vd-from">{{ digest.from.score ?? '—' }}<small v-if="digest.from.score!=null">%</small></div>
            <svg class="ph-vd-arr" width="34" height="20" viewBox="0 0 34 20" fill="none" stroke="#CBD2E0" stroke-width="2"><path d="M2 10h26M22 4l8 6-8 6" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <div class="ph-vd-to" :style="{ color: scoreColor(digest.to.score) }">{{ digest.to.score ?? '—' }}<small v-if="digest.to.score!=null">%</small></div>
            <div v-if="dlt != null" class="ph-vd-delta" :class="dlt > 0 ? 'up' : dlt < 0 ? 'dn' : 'fl'">
              {{ dlt > 0 ? '↑ +' : dlt < 0 ? '↓ ' : '' }}{{ dlt === 0 ? 'без изменений' : Math.abs(dlt) + ' пп' }}
            </div>
            <div class="ph-vd-status" :style="{ color: scoreColor(digest.to.score), background: scoreColor(digest.to.score)+'14' }">{{ statusWord(digest.to.score) }}</div>
          </div>
          <div class="ph-vd-meta">
            <span><b :style="{ color: digest.tasks_closed && digest.tasks_closed>0 ? '#1D9E75' : '#1E2A4A' }">{{ digest.tasks_closed! > 0 ? '+'+digest.tasks_closed : digest.tasks_closed }}</b> задач закрыто за период</span>
            <span class="dot">·</span>
            <span><b :style="{ color: digest.comments_added ? '#7C6FF7' : '#1E2A4A' }">{{ digest.comments_added || 0 }}</b> комментар{{ (digest.comments_added || 0) === 1 ? 'ий' : (digest.comments_added || 0) < 5 && (digest.comments_added || 0) > 0 ? 'ия' : 'иев' }}</span>
            <span class="dot">·</span>
            <span><b style="color:#E24B4A">{{ digest.overdue_now }}</b> просрочено сейчас</span>
          </div>
        </div>

        <!-- ДВЕ КОЛОНКИ: выросли / провалились -->
        <div class="ph-cols">
          <div class="ph-col">
            <div class="ph-col-head up"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 19l7-14 7 14" stroke-linecap="round" stroke-linejoin="round" fill="none"/><path d="M5 19l7-7 7 7"/></svg>Улучшились<span class="ph-col-n">{{ digest.improved?.length || 0 }}</span></div>
            <div v-if="digest.improved?.length" class="ph-col-list">
              <div v-for="c in digest.improved" :key="c.company_id" class="ph-co" @click="openCompany(c)">
                <div class="av" :style="{ background: c.color }">{{ c.badge }}</div>
                <div class="ph-co-meta"><div class="ph-co-nm">{{ c.name }}</div><div class="ph-co-sec">{{ c.sector }}</div></div>
                <div class="ph-co-prog"><span class="from">{{ c.from }}</span><span class="to" :style="{ color: scoreColor(c.to) }">{{ c.to }}%</span></div>
                <div class="ph-co-d up">+{{ c.delta }}</div>
              </div>
            </div>
            <div v-else class="ph-col-empty">Никто не вырос за период</div>
          </div>

          <div class="ph-col">
            <div class="ph-col-head dn"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 5l7 14 7-14" stroke-linecap="round" stroke-linejoin="round" fill="none"/><path d="M5 5l7 7 7-7"/></svg>Провалились<span class="ph-col-n">{{ digest.fell?.length || 0 }}</span></div>
            <div v-if="digest.fell?.length" class="ph-col-list">
              <div v-for="c in digest.fell" :key="c.company_id" class="ph-co" @click="openCompany(c)">
                <div class="av" :style="{ background: c.color }">{{ c.badge }}</div>
                <div class="ph-co-meta"><div class="ph-co-nm">{{ c.name }}</div><div class="ph-co-sec">{{ c.sector }}</div></div>
                <div class="ph-co-prog"><span class="from">{{ c.from }}</span><span class="to" :style="{ color: scoreColor(c.to) }">{{ c.to }}%</span></div>
                <div class="ph-co-d dn">{{ c.delta }}</div>
              </div>
            </div>
            <div v-else class="ph-col-empty">Никто не провалился — хорошо</div>
          </div>
        </div>

        <!-- если to=Сейчас и нет дельт — подсказка -->
        <div v-if="!digest.improved?.length && !digest.fell?.length" class="ph-hint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/></svg>
          Между точками сравнения пока нет изменений по компаниям. Зафиксируйте новый срез позже — и обзор покажет, кто вырос, а кто просел.
        </div>

        <div class="ph-actions">
          <button class="ph-act" disabled>Полный отчёт <span class="soon">скоро</span></button>
          <button class="ph-act" disabled>→ Telegram <span class="soon">скоро</span></button>
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
            <div class="ph-mod-ab">
              <div class="ph-ab-cell"><div class="ph-ab-lbl">Было</div><div class="ph-ab-val" :style="{ color: scoreColor(modalCo.from) }">{{ modalCo.from }}%</div></div>
              <div class="ph-ab-delta" :class="modalCo.delta > 0 ? 'up' : modalCo.delta < 0 ? 'dn' : 'fl'"><div>{{ modalCo.delta > 0 ? '+' : '' }}{{ modalCo.delta }}</div><small>пп</small></div>
              <div class="ph-ab-cell"><div class="ph-ab-lbl">Стало</div><div class="ph-ab-val" :style="{ color: scoreColor(modalCo.to) }">{{ modalCo.to }}%</div></div>
            </div>
            <div class="ph-trail-head">Лента изменений<span>что менялось</span></div>
            <div class="ph-trail">
              <div v-if="trailLoading" class="ph-trail-state">Загрузка ленты…</div>
              <div v-else-if="trailError" class="ph-trail-state">{{ trailError }}</div>
              <div v-else-if="!trail.length" class="ph-trail-state">Изменений за период нет.</div>
              <div v-for="(it,i) in trail" :key="i" class="ph-tr-item">
                <div class="ph-tr-rail"><div class="ph-tr-dot" :style="{ background: it.is_critical ? '#E24B4A' : '#7C6FF7' }" /></div>
                <div class="ph-tr-body">
                  <div class="ph-tr-line"><b>{{ it.actor }}</b> {{ actionRu(it.action) }}<template v-if="it.field"> <span class="ph-tr-field">{{ it.field }}</span></template></div>
                  <div v-if="it.old_value || it.new_value" class="ph-tr-change"><span class="old">{{ it.old_value || '—' }}</span><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 12h14M13 6l6 6-6 6"/></svg><span class="new">{{ it.new_value || '—' }}</span></div>
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
.ph { --p:#7C6FF7; --p-deep:#534AB7; --navy:#0C1230; --navy2:#141C42; --t3:#64748B; --t4:#94A3B8; --bd:#EAEBF2; --line:#F0F1F6; --ease:cubic-bezier(.34,1.2,.64,1); --ease-out:cubic-bezier(.22,1,.36,1); --sh-sm:0 1px 2px rgba(15,23,60,.05); --sh:0 1px 2px rgba(15,23,60,.05),0 12px 32px rgba(15,23,60,.06); --sh-lg:0 24px 64px rgba(15,23,60,.2),0 8px 24px rgba(15,23,60,.08); color:#0F172A; }
.ph-top { height: 62px; background: linear-gradient(120deg,var(--navy),var(--navy2) 70%,#1C2550); display: flex; align-items: center; padding: 0 24px; }
.ph-brand { display: flex; align-items: center; gap: 12px; }
.ph-logo { width: 34px; height: 34px; border-radius: 10px; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; font-weight: 700; font-size: 13px; display: grid; place-items: center; box-shadow: 0 4px 14px rgba(108,92,231,.4); }
.ph-eyebrow { font-size: 9px; font-weight: 600; letter-spacing: .12em; color: #9A8FFF; }
.ph-tt { color: #fff; font-size: 15px; font-weight: 600; margin-top: 2px; }
.ph-top-r { margin-left: auto; }
.ph-sel { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.09); color: rgba(255,255,255,.82); font: 600 12px inherit; padding: 8px 13px; border-radius: 10px; cursor: pointer; outline: none; }
.ph-sel option { color: #1E2A4A; }

.ph-page { padding: 22px 24px 80px; max-width: 1080px; margin: 0 auto; }
.ph-state { padding: 60px; text-align: center; color: var(--t3); }
.ph-state.err { color: #E24B4A; }

/* EMPTY */
.ph-empty { text-align: center; padding: 60px 24px; background: linear-gradient(180deg,#fff,#FBFAFF); border: 1px solid var(--bd); border-radius: 18px; box-shadow: var(--sh); max-width: 540px; margin: 24px auto; }
.ph-empty-ic { width: 60px; height: 60px; border-radius: 16px; background: linear-gradient(135deg,#F0EEFF,#E7E3FF); color: var(--p-deep); display: grid; place-items: center; margin: 0 auto 18px; }
.ph-empty-t { font-size: 18px; font-weight: 600; color: #1E2A4A; letter-spacing: -.01em; }
.ph-empty-s { font-size: 13px; color: var(--t3); line-height: 1.6; margin: 10px auto 22px; max-width: 420px; }

.ph-freeze { display: inline-flex; align-items: center; gap: 7px; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border: none; font: 600 12px inherit; padding: 9px 15px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 16px rgba(108,92,231,.3); transition: transform .16s var(--ease),box-shadow .16s; }
.ph-freeze.big { font-size: 13px; padding: 12px 22px; }
.ph-freeze:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 8px 22px rgba(108,92,231,.4); }
.ph-freeze:disabled { opacity: .6; cursor: default; }

/* HEAD */
.ph-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.ph-eyebrow2 { font-size: 10px; font-weight: 600; letter-spacing: .08em; color: var(--p-deep); }
.ph-period { font-size: 18px; font-weight: 600; color: #1E2A4A; margin-top: 3px; letter-spacing: -.01em; }
.ph-head-r { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ph-pick-wrap { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--t4); }
.ph-sel2 { border: 1px solid var(--bd); background: #fff; border-radius: 8px; padding: 7px 10px; font: 600 11.5px inherit; color: #1E2A4A; cursor: pointer; outline: none; max-width: 150px; }

/* VERDICT */
.ph-verdict { background: linear-gradient(135deg,#fff,#FBFAFF); border: 1px solid var(--bd); border-radius: 18px; padding: 22px 26px; box-shadow: var(--sh); margin-bottom: 18px; }
.ph-vd-label { font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3); }
.ph-vd-label span { text-transform: none; letter-spacing: 0; font-weight: 500; color: var(--t4); margin-left: 6px; }
.ph-vd-row { display: flex; align-items: center; gap: 16px; margin-top: 12px; flex-wrap: wrap; }
.ph-vd-from { font-size: 38px; font-weight: 700; color: var(--t4); letter-spacing: -.04em; font-variant-numeric: tabular-nums; line-height: 1; }
.ph-vd-from small { font-size: 18px; }
.ph-vd-arr { flex-shrink: 0; }
.ph-vd-to { font-size: 54px; font-weight: 700; letter-spacing: -.045em; font-variant-numeric: tabular-nums; line-height: 1; }
.ph-vd-to small { font-size: 24px; }
.ph-vd-delta { font-size: 15px; font-weight: 700; padding: 7px 13px; border-radius: 11px; font-variant-numeric: tabular-nums; }
.ph-vd-delta.up { background: #E3F8EE; color: #0F6E56; } .ph-vd-delta.dn { background: #FCE7E7; color: #B23434; } .ph-vd-delta.fl { background: #F1F2F6; color: var(--t3); }
.ph-vd-status { margin-left: auto; font-size: 13px; font-weight: 600; padding: 8px 16px; border-radius: 11px; }
.ph-vd-meta { display: flex; align-items: center; gap: 10px; margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line); font-size: 12.5px; color: var(--t3); }
.ph-vd-meta b { font-weight: 700; font-variant-numeric: tabular-nums; } .ph-vd-meta .dot { color: var(--t4); }

/* COLS */
.ph-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.ph-col { background: #fff; border: 1px solid var(--bd); border-radius: 16px; box-shadow: var(--sh); overflow: hidden; }
.ph-col-head { display: flex; align-items: center; gap: 8px; padding: 14px 18px; font-size: 12.5px; font-weight: 600; border-bottom: 1px solid var(--line); }
.ph-col-head.up { color: #0F6E56; } .ph-col-head.dn { color: #B23434; }
.ph-col-n { margin-left: auto; font-size: 12px; background: #F1F2F6; color: var(--t3); padding: 2px 9px; border-radius: 8px; }
.ph-col-list { padding: 4px 0; }
.ph-co { display: grid; grid-template-columns: 30px 1fr auto auto; align-items: center; gap: 11px; padding: 10px 18px; cursor: pointer; transition: background .12s; }
.ph-co:hover { background: #FAFAFF; }
.av { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; font-size: 9px; font-weight: 700; color: #fff; box-shadow: inset 0 1px 1px rgba(255,255,255,.25),0 2px 6px rgba(15,23,60,.12); }
.av.lg { width: 44px; height: 44px; border-radius: 13px; font-size: 13px; }
.ph-co-meta { min-width: 0; }
.ph-co-nm { font-size: 12.5px; font-weight: 500; color: #1E2A4A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ph-co-sec { font-size: 10px; color: var(--t4); margin-top: 1px; }
.ph-co-prog { display: flex; align-items: baseline; gap: 7px; font-variant-numeric: tabular-nums; }
.ph-co-prog .from { font-size: 11px; color: var(--t4); text-decoration: line-through; }
.ph-co-prog .to { font-size: 14px; font-weight: 700; }
.ph-co-d { font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; min-width: 36px; text-align: right; }
.ph-co-d.up { color: #0F6E56; } .ph-co-d.dn { color: #B23434; }
.ph-col-empty { padding: 28px; text-align: center; color: var(--t4); font-size: 12px; }

.ph-hint { display: flex; align-items: center; gap: 9px; margin-top: 16px; padding: 13px 16px; background: rgba(124,111,247,.05); border: 1px solid rgba(124,111,247,.16); border-radius: 12px; font-size: 12px; color: var(--t3); }
.ph-hint svg { color: var(--p); flex-shrink: 0; }
.ph-actions { display: flex; gap: 10px; margin-top: 18px; justify-content: flex-end; }
.ph-act { display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--bd); background: #fff; color: var(--t3); font: 600 12px inherit; padding: 9px 16px; border-radius: 10px; cursor: default; }
.ph-act .soon { font-size: 9px; font-weight: 600; color: var(--p-deep); background: #F0EEFF; padding: 2px 7px; border-radius: 6px; text-transform: uppercase; letter-spacing: .03em; }

/* MODAL */
.ph-back { position: fixed; inset: 0; background: rgba(15,18,40,.5); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); z-index: 9999; display: grid; place-items: center; padding: 24px; }
.ph-mod { width: min(580px,100%); max-height: calc(100vh - 48px); background: #fff; border-radius: 18px; box-shadow: var(--sh-lg); display: flex; flex-direction: column; overflow: hidden; }
.ph-mod-head { display: flex; align-items: center; justify-content: space-between; padding: 20px 22px; border-bottom: 1px solid var(--line); background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 9%, #fff), #fff 70%); }
.cmpcell { display: flex; align-items: center; gap: 12px; }
.ph-mod-name { font-size: 16px; font-weight: 600; color: #1E2A4A; }
.ph-mod-sec { font-size: 11px; color: var(--t3); margin-top: 2px; }
.ph-x { border: 0; background: rgba(15,23,60,.04); cursor: pointer; color: #64748B; width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center; transition: all .15s; }
.ph-x:hover { background: rgba(127,119,221,.12); color: var(--p-deep); }
.ph-mod-ab { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; padding: 18px 22px; margin: 16px 22px 0; background: #FAFAFD; border: 1px solid var(--line); border-radius: 13px; }
.ph-ab-cell { text-align: center; }
.ph-ab-lbl { font-size: 9.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--t4); }
.ph-ab-val { font-size: 34px; font-weight: 700; letter-spacing: -.035em; margin-top: 5px; font-variant-numeric: tabular-nums; line-height: 1; }
.ph-ab-delta { text-align: center; font-size: 19px; font-weight: 700; padding: 8px 14px; border-radius: 11px; font-variant-numeric: tabular-nums; }
.ph-ab-delta.up { background: #E3F8EE; color: #0F6E56; } .ph-ab-delta.dn { background: #FCE7E7; color: #B23434; } .ph-ab-delta.fl { background: #F1F2F6; color: var(--t3); }
.ph-ab-delta small { display: block; font-size: 8.5px; font-weight: 600; text-transform: uppercase; opacity: .7; }
.ph-trail-head { display: flex; align-items: baseline; justify-content: space-between; padding: 18px 22px 10px; font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3); }
.ph-trail-head span { font-size: 10px; font-weight: 500; color: var(--t4); text-transform: none; letter-spacing: 0; }
.ph-trail { overflow-y: auto; padding: 0 22px 20px; }
.ph-trail-state { padding: 28px; text-align: center; color: var(--t4); font-size: 12px; }
.ph-tr-item { display: flex; gap: 12px; padding: 12px 0; }
.ph-tr-rail { position: relative; display: flex; justify-content: center; width: 8px; flex-shrink: 0; }
.ph-tr-rail::before { content: ""; position: absolute; top: 14px; bottom: -12px; width: 1.5px; background: var(--line); }
.ph-tr-item:last-child .ph-tr-rail::before { display: none; }
.ph-tr-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 4px; box-shadow: 0 0 0 3px #fff; }
.ph-tr-body { flex: 1; min-width: 0; }
.ph-tr-line { font-size: 12.5px; color: #334155; } .ph-tr-line b { font-weight: 600; color: #1E2A4A; }
.ph-tr-field { color: var(--p-deep); font-weight: 600; }
.ph-tr-change { display: inline-flex; align-items: center; gap: 8px; margin-top: 5px; font-size: 11.5px; }
.ph-tr-change .old { color: var(--t4); text-decoration: line-through; } .ph-tr-change .new { color: #0F6E56; font-weight: 600; } .ph-tr-change svg { color: var(--t4); }
.ph-tr-meta { font-size: 10.5px; color: var(--t4); margin-top: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ph-tr-time { font-size: 10.5px; color: var(--t4); white-space: nowrap; }
.ph-modal-enter-active,.ph-modal-leave-active { transition: opacity .22s ease; }
.ph-modal-enter-from,.ph-modal-leave-to { opacity: 0; }
.ph-modal-enter-active .ph-mod { transition: transform .4s var(--ease); }
.ph-modal-enter-from .ph-mod { transform: scale(.94) translateY(12px); }

@media (max-width: 820px) { .ph-cols { grid-template-columns: 1fr; } }
</style>
