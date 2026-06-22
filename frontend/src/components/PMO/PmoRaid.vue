<script setup lang="ts">
/**
 * PmoRaid — реестр RAID (Риски/Допущения/Проблемы/Зависимости) (P2).
 * Матрица вероятность×влияние (5×5) + таблица + форма создания/правки.
 */
import { ref, computed, watch, onMounted } from "vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { pmoApi, type RaidItem, type RaidPayload, type RaidKind, type RaidSeverity, type RaidStatus } from "@/api/pmo";

const props = defineProps<{ companyCode: string; canEdit?: boolean }>();

const KINDS: { v: RaidKind; l: string }[] = [
  { v: "risk", l: "Риск" }, { v: "assumption", l: "Допущение" },
  { v: "issue", l: "Проблема" }, { v: "dependency", l: "Зависимость" },
];
const KIND_L: Record<string, string> = Object.fromEntries(KINDS.map(k => [k.v, k.l]));
const SEVERITIES: { v: RaidSeverity; l: string; c: string }[] = [
  { v: "low", l: "Низкая", c: "#5F5E5A" }, { v: "medium", l: "Средняя", c: "#D97706" },
  { v: "high", l: "Высокая", c: "#E24B4A" }, { v: "critical", l: "Критич.", c: "#7F1D1D" },
];
const SEV_M = Object.fromEntries(SEVERITIES.map(s => [s.v, s]));
const STATUSES: { v: RaidStatus; l: string; c: string }[] = [
  { v: "open", l: "Открыт", c: "#E24B4A" }, { v: "mitigating", l: "В работе", c: "#D97706" }, { v: "closed", l: "Закрыт", c: "#1D9E75" },
];
const STAT_M = Object.fromEntries(STATUSES.map(s => [s.v, s]));

// PMBOK 7 — полярность (угроза/возможность) + стратегии реагирования
const POLARITIES = [
  { v: "threat", l: "Угроза", c: "#E24B4A" },
  { v: "opportunity", l: "Возможность", c: "#1D9E75" },
];
const POL_M = Object.fromEntries(POLARITIES.map(p => [p.v, p]));
const RESPONSES: Record<string, { v: string; l: string }[]> = {
  threat: [
    { v: "avoid", l: "Избегать" }, { v: "transfer", l: "Передать" },
    { v: "mitigate", l: "Снизить" }, { v: "accept", l: "Принять" }, { v: "escalate", l: "Эскалировать" },
  ],
  opportunity: [
    { v: "exploit", l: "Использовать" }, { v: "share", l: "Разделить" },
    { v: "enhance", l: "Усилить" }, { v: "accept", l: "Принять" }, { v: "escalate", l: "Эскалировать" },
  ],
};
const RESP_L: Record<string, string> = {};
for (const arr of Object.values(RESPONSES)) for (const r of arr) RESP_L[r.v] = r.l;

const loading = ref(true);
const error = ref<string | null>(null);
const items = ref<RaidItem[]>([]);
const kindFilter = ref<string>("");
const polarityFilter = ref<string>("");
const matrixCell = ref<{ p: number; i: number } | null>(null);

async function load() {
  loading.value = true; error.value = null;
  try {
    items.value = await pmoApi.listRaid(props.companyCode);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить RAID";
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch(() => props.companyCode, load);

const polFiltered = computed(() => polarityFilter.value
  ? items.value.filter(i => (i.polarity || "threat") === polarityFilter.value) : items.value);
const openItems = computed(() => polFiltered.value.filter(i => i.status !== "closed"));
const filtered = computed(() =>
  polFiltered.value.filter(i =>
    (!kindFilter.value || i.kind === kindFilter.value) &&
    (!matrixCell.value || (i.probability === matrixCell.value.p && i.impact === matrixCell.value.i)),
  ),
);

// Матрица: impact 5..1 (строки), probability 1..5 (столбцы)
function cellCount(p: number, i: number): number {
  return openItems.value.filter(x => x.probability === p && x.impact === i).length;
}
function scoreColor(score: number): string {
  if (score >= 20) return "#E24B4A";
  if (score >= 13) return "#EF7C44";
  if (score >= 8) return "#D97706";
  if (score >= 4) return "#C6A700";
  return "#1D9E75";
}
function toggleCell(p: number, i: number) {
  matrixCell.value = (matrixCell.value && matrixCell.value.p === p && matrixCell.value.i === i) ? null : { p, i };
}

// ── Форма ──
const blank = (): RaidPayload => ({
  kind: "risk", title: "", description: "", owner_name: "", severity: "medium",
  probability: 3, impact: 3, polarity: "threat", response_strategy: null,
  status: "open", mitigation: "", due_date: null,
});
const form = ref<RaidPayload>(blank());
const editingId = ref<string | null>(null);
const formOpen = ref(false);
const saving = ref(false);

// Сброс стратегии при смене полярности, если она невалидна для новой
const respOptions = computed(() => RESPONSES[form.value.polarity || "threat"]);
function onPolarityChange() {
  if (form.value.response_strategy && !respOptions.value.some(r => r.v === form.value.response_strategy)) {
    form.value.response_strategy = null;
  }
}

function openCreate() { form.value = blank(); editingId.value = null; formOpen.value = true; }
function openEdit(it: RaidItem) {
  form.value = {
    kind: it.kind, title: it.title, description: it.description || "", owner_name: it.owner_name || "",
    severity: it.severity, probability: it.probability, impact: it.impact,
    polarity: it.polarity || "threat", response_strategy: it.response_strategy || null,
    status: it.status, mitigation: it.mitigation || "", due_date: it.due_date,
  };
  editingId.value = it.id; formOpen.value = true;
}
async function save() {
  if (!form.value.title?.trim()) { error.value = "Название обязательно"; return; }
  saving.value = true; error.value = null;
  try {
    if (editingId.value) await pmoApi.updateRaid(editingId.value, form.value);
    else await pmoApi.createRaid(props.companyCode, form.value);
    formOpen.value = false;
    await load();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось сохранить";
  } finally { saving.value = false; }
}
async function removeItem(it: RaidItem) {
  if (!confirm(`Удалить «${it.title}»?`)) return;
  try { await pmoApi.deleteRaid(it.id); await load(); }
  catch (e: any) { error.value = e?.response?.data?.detail || "Не удалось удалить"; }
}

const fmtDue = (s: string | null) => s ? new Date(s + "T00:00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) : "—";
</script>

<template>
  <div class="pr">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />

    <!-- Тулбар -->
    <div class="pr-bar">
      <div class="pr-chips">
        <button class="pr-chip" :class="{ on: kindFilter === '' }" @click="kindFilter = ''">Все типы</button>
        <button v-for="k in KINDS" :key="k.v" class="pr-chip" :class="{ on: kindFilter === k.v }" @click="kindFilter = k.v">{{ k.l }}</button>
      </div>
      <div class="pr-pol-seg">
        <button class="pr-pol" :class="{ on: polarityFilter === '' }" @click="polarityFilter = ''">Все</button>
        <button class="pr-pol pol-threat" :class="{ on: polarityFilter === 'threat' }" @click="polarityFilter = 'threat'">Угрозы</button>
        <button class="pr-pol pol-opp" :class="{ on: polarityFilter === 'opportunity' }" @click="polarityFilter = 'opportunity'">Возможности</button>
      </div>
      <button v-if="canEdit" class="pr-add" @click="openCreate">+ Запись RAID</button>
    </div>

    <UzaStateBlock v-if="loading" state="loading" text="Загрузка реестра…" />

    <template v-else>
      <div class="pr-cols">
        <!-- Матрица P×I -->
        <div class="pr-matrix">
          <div class="pr-matrix-t">Вероятность × Влияние</div>
          <table class="pr-mx">
            <tbody>
              <tr v-for="i in [5,4,3,2,1]" :key="'i'+i">
                <th class="pr-mx-yl">{{ i }}</th>
                <td
                  v-for="p in [1,2,3,4,5]"
                  :key="'c'+p+i"
                  class="pr-mx-c"
                  :class="{ on: matrixCell && matrixCell.p === p && matrixCell.i === i, dim: cellCount(p,i) === 0 }"
                  :style="{ background: scoreColor(p*i) }"
                  :title="`P${p} × I${i} = ${p*i}` + (cellCount(p,i) ? ` · ${cellCount(p,i)} откр.` : '')"
                  @click="toggleCell(p, i)"
                >{{ cellCount(p,i) || "" }}</td>
              </tr>
              <tr><th class="pr-mx-corner"></th><th v-for="p in [1,2,3,4,5]" :key="'x'+p" class="pr-mx-xl">{{ p }}</th></tr>
            </tbody>
          </table>
          <div class="pr-mx-axis"><span>← влияние</span><span>вероятность →</span></div>
        </div>

        <!-- Таблица -->
        <div class="pr-table-wrap">
          <div v-if="matrixCell" class="pr-filterhint">
            Фильтр: P{{ matrixCell.p }}×I{{ matrixCell.i }}
            <button @click="matrixCell = null">сбросить ×</button>
          </div>
          <UzaStateBlock v-if="!filtered.length" state="empty" variant="block" title="Записей нет" text="Добавьте риск/проблему/допущение/зависимость." />
          <table v-else class="uza-table pr-tbl">
            <thead>
              <tr>
                <th>Тип</th><th>Название</th><th>Владелец</th><th>Серьёзн.</th>
                <th style="text-align:center">P×I</th><th style="text-align:center">Score</th>
                <th>Статус</th><th>Срок</th><th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(it, idx) in filtered" :key="it.id" class="pr-row" :style="{ animationDelay: Math.min(idx * 0.03, 0.4) + 's' }">
                <td>
                  <span class="pr-pol-dot" :title="POL_M[it.polarity || 'threat']?.l" :style="{ background: POL_M[it.polarity || 'threat']?.c }"></span>
                  <span class="pr-kind">{{ KIND_L[it.kind] }}</span>
                </td>
                <td>
                  <div class="pr-title">{{ it.title }}</div>
                  <div v-if="it.response_strategy" class="pr-resp">Реакция: {{ RESP_L[it.response_strategy] || it.response_strategy }}</div>
                  <div v-if="it.mitigation" class="pr-mit">↳ {{ it.mitigation }}</div>
                </td>
                <td>{{ it.owner_name || "—" }}</td>
                <td><span class="pr-sev" :style="{ color: SEV_M[it.severity]?.c }">{{ SEV_M[it.severity]?.l }}</span></td>
                <td style="text-align:center" class="is-mono">{{ it.probability }}×{{ it.impact }}</td>
                <td style="text-align:center"><span class="pr-score" :style="{ background: scoreColor(it.score) }">{{ it.score }}</span></td>
                <td><span class="pr-stat" :style="{ color: STAT_M[it.status]?.c }">{{ STAT_M[it.status]?.l }}</span></td>
                <td class="is-mono">{{ fmtDue(it.due_date) }}</td>
                <td style="text-align:right">
                  <button v-if="canEdit" class="pr-ia" title="Править" @click="openEdit(it)">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                  </button>
                  <button v-if="canEdit" class="pr-ia pr-ia-del" title="Удалить" @click="removeItem(it)">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- Форма создания/правки -->
    <div v-if="formOpen" class="pr-modal-ov" @click.self="formOpen = false">
      <div class="pr-modal">
        <div class="pr-modal-h">{{ editingId ? "Правка записи" : "Новая запись RAID" }}</div>
        <div class="pr-modal-b">
          <div class="pr-f2">
            <div class="pr-f"><label>Тип</label>
              <select v-model="form.kind"><option v-for="k in KINDS" :key="k.v" :value="k.v">{{ k.l }}</option></select>
            </div>
            <div class="pr-f"><label>Полярность</label>
              <div class="pr-pol-toggle">
                <button type="button" class="pol-threat" :class="{ on: form.polarity === 'threat' }" @click="form.polarity = 'threat'; onPolarityChange()">Угроза</button>
                <button type="button" class="pol-opp" :class="{ on: form.polarity === 'opportunity' }" @click="form.polarity = 'opportunity'; onPolarityChange()">Возможность</button>
              </div>
            </div>
          </div>
          <div class="pr-f"><label>Название</label><input v-model="form.title" placeholder="Кратко суть" /></div>
          <div class="pr-f"><label>Описание</label><textarea v-model="form.description" rows="2"></textarea></div>
          <div class="pr-f2">
            <div class="pr-f"><label>Владелец</label><input v-model="form.owner_name" placeholder="Имя" /></div>
            <div class="pr-f"><label>Серьёзность</label>
              <select v-model="form.severity"><option v-for="s in SEVERITIES" :key="s.v" :value="s.v">{{ s.l }}</option></select>
            </div>
          </div>
          <div class="pr-f2">
            <div class="pr-f"><label>Вероятность (1–5)</label><input type="number" min="1" max="5" v-model.number="form.probability" /></div>
            <div class="pr-f"><label>Влияние (1–5)</label><input type="number" min="1" max="5" v-model.number="form.impact" /></div>
          </div>
          <div class="pr-f2">
            <div class="pr-f"><label>Статус</label>
              <select v-model="form.status"><option v-for="s in STATUSES" :key="s.v" :value="s.v">{{ s.l }}</option></select>
            </div>
            <div class="pr-f"><label>Срок</label><input type="date" v-model="form.due_date" /></div>
          </div>
          <div class="pr-f"><label>Стратегия реагирования ({{ form.polarity === 'opportunity' ? 'возможность' : 'угроза' }})</label>
            <select v-model="form.response_strategy">
              <option :value="null">— Не выбрана</option>
              <option v-for="r in respOptions" :key="r.v" :value="r.v">{{ r.l }}</option>
            </select>
          </div>
          <div class="pr-f"><label>{{ form.polarity === 'opportunity' ? 'План реализации' : 'Митигировка / план' }}</label><textarea v-model="form.mitigation" rows="2"></textarea></div>
        </div>
        <div class="pr-modal-f">
          <button class="pr-btn-ghost" @click="formOpen = false">Отмена</button>
          <button class="pr-btn" :disabled="saving" @click="save">{{ saving ? "Сохраняю…" : "Сохранить" }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pr { padding: 4px 2px 24px; }
.pr-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.pr-chips { display: flex; gap: 4px; flex-wrap: wrap; }
.pr-chip { padding: 5px 11px; border-radius: 8px; border: 1px solid var(--border, rgba(99,102,180,.14)); background: var(--bg1, #fff); color: var(--t2, #475569); font-size: var(--fs-sm, 11px); font-weight: 500; cursor: pointer; font-family: inherit; }
.pr-chip.on { background: var(--p, #7c6ff7); border-color: var(--p); color: #fff; }
.pr-add { margin-left: auto; padding: 7px 14px; border-radius: 9px; border: 1px solid var(--p, #7c6ff7); background: var(--p, #7c6ff7); color: #fff; font-size: var(--fs-sm, 11.5px); font-weight: 500; cursor: pointer; font-family: inherit; flex-shrink: 0; }
/* Полярность (угроза/возможность) */
.pr-pol-seg { display: inline-flex; gap: 2px; background: var(--bg2, #fafafc); border-radius: 9px; padding: 2px; border: 1px solid var(--border, rgba(99,102,180,.12)); }
.pr-pol { padding: 5px 10px; border: none; background: transparent; border-radius: 7px; font-size: var(--fs-sm, 11px); font-weight: 500; color: var(--t3, #94a3b8); cursor: pointer; font-family: inherit; transition: all .14s var(--ease-standard); }
.pr-pol.on { background: #fff; box-shadow: 0 1px 3px rgba(15,23,60,.1); }
.pr-pol.pol-threat.on { color: #E24B4A; }
.pr-pol.pol-opp.on { color: #1D9E75; }
.pr-pol:not(.on):hover { color: var(--t1, #1e2a4a); }
.pr-pol-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 6px; vertical-align: middle; flex-shrink: 0; }
.pr-resp { font-size: var(--fs-xs, 10px); color: var(--p-deep, #534ab7); font-weight: 600; margin-top: 2px; }
.pr-pol-toggle { display: flex; gap: 4px; }
.pr-pol-toggle button { flex: 1; padding: 7px 8px; border: 1px solid var(--border, rgba(99,102,180,.16)); background: var(--bg1, #fff); border-radius: 8px; font-size: var(--fs-sm, 11px); font-weight: 500; color: var(--t3, #94a3b8); cursor: pointer; font-family: inherit; transition: all .14s; }
.pr-pol-toggle .pol-threat.on { background: rgba(226,75,74,.1); border-color: #E24B4A; color: #E24B4A; }
.pr-pol-toggle .pol-opp.on { background: rgba(29,158,117,.1); border-color: #1D9E75; color: #1D9E75; }

.pr-cols { display: grid; grid-template-columns: 340px 1fr; gap: 18px; align-items: start; }
/* ≤14″: матрица встаёт над таблицей, таблице — вся ширина */
@media (max-width: 1200px) { .pr-cols { grid-template-columns: 1fr; } .pr-matrix { max-width: 440px; } }
.pr-table-wrap { overflow-x: auto; }

.pr-matrix { border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: var(--r, 10px); padding: 12px; background: var(--bg1, #fff); }
.pr-matrix-t { font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94a3b8); font-weight: 600; margin-bottom: 8px; }
.pr-mx { border-collapse: collapse; width: 100%; table-layout: fixed; }
.pr-mx-c { height: 50px; text-align: center; color: #fff; font-weight: 700; font-size: var(--fs-md, 13px); cursor: pointer; border: 2px solid #fff; border-radius: 6px; transition: transform .1s; font-variant-numeric: tabular-nums; }
.pr-mx-c.dim { opacity: .32; }
.pr-mx-c:hover { transform: scale(1.1); box-shadow: 0 3px 10px rgba(15,23,60,.28); }
.pr-mx-c.on { outline: 2px solid #1e2a4a; outline-offset: 1px; transform: scale(1.06); opacity: 1; }
.pr-mx-yl, .pr-mx-xl { font-size: var(--fs-2xs, 9px); color: var(--t3, #94a3b8); font-weight: 600; text-align: center; padding: 2px; }
.pr-mx-yl, .pr-mx-corner { width: 22px; }
.pr-mx-corner { width: 16px; }
.pr-mx-axis { display: flex; justify-content: space-between; font-size: 8px; color: var(--t3, #94a3b8); margin-top: 4px; }

.pr-filterhint { font-size: var(--fs-sm, 11px); color: var(--p-deep, #534ab7); margin-bottom: 8px; }
.pr-filterhint button { background: none; border: none; color: var(--t3, #94a3b8); cursor: pointer; font-family: inherit; text-decoration: underline; }
.pr-tbl { font-size: var(--fs-sm, 11.5px); min-width: 680px; }
.pr-row { animation: prRowIn .4s var(--ease-out) both; }
.pr-row:hover { background: rgba(124,111,247,.04); }
@keyframes prRowIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
/* Премиум-вход модалки RAID */
.pr-modal { animation: prModalIn .34s var(--ease-standard) both; }
@keyframes prModalIn { from { opacity: 0; transform: scale(.96) translateY(12px); } to { opacity: 1; transform: scale(1) translateY(0); } }
.pr-kind { font-size: var(--fs-2xs, 9px); padding: 2px 6px; border-radius: 5px; background: rgba(124,111,247,.1); color: var(--p-deep, #534ab7); font-weight: 600; white-space: nowrap; }
.pr-title { font-weight: 500; color: var(--t1, #1e2a4a); }
.pr-mit { font-size: var(--fs-xs, 10px); color: var(--t3, #94a3b8); margin-top: 2px; }
.pr-sev, .pr-stat { font-weight: 600; white-space: nowrap; }
.pr-score { display: inline-block; min-width: 22px; padding: 1px 5px; border-radius: 5px; color: #fff; font-weight: 700; font-variant-numeric: tabular-nums; }
.pr-ia { background: none; border: none; cursor: pointer; color: var(--t3, #94a3b8); padding: 4px; border-radius: 6px; }
.pr-ia:hover { background: rgba(124,111,247,.08); color: var(--p-deep, #534ab7); }
.pr-ia-del:hover { background: rgba(226,75,74,.08); color: #E24B4A; }

/* Модалка формы */
.pr-modal-ov { position: fixed; inset: 0; z-index: var(--z-modal, 9100); background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(7px); backdrop-filter: blur(7px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.pr-modal { background: var(--bg1, #fff); border-radius: 14px; width: min(540px, 96vw); max-height: 92vh; overflow: hidden; display: flex; flex-direction: column; box-shadow: var(--shl); }
.pr-modal-h { padding: 14px 18px; font-size: var(--fs-md, 13px); font-weight: 600; color: var(--t1, #1e2a4a); border-bottom: 1px solid var(--border, rgba(99,102,180,.12)); }
.pr-modal-b { padding: 14px 18px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.pr-f { display: flex; flex-direction: column; gap: 4px; }
.pr-f2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.pr-f label { font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); font-weight: 600; }
.pr-f input, .pr-f select, .pr-f textarea { padding: 7px 10px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 8px; font-size: var(--fs-base, 12px); font-family: inherit; outline: none; background: var(--bg1, #fff); color: var(--t1, #1e2a4a); }
.pr-f textarea { resize: vertical; }
.pr-modal-f { padding: 12px 18px; border-top: 1px solid var(--border, rgba(99,102,180,.12)); display: flex; justify-content: flex-end; gap: 8px; background: var(--bg2, #fafafc); }
.pr-btn { padding: 8px 16px; border-radius: 9px; border: 1px solid var(--p, #7c6ff7); background: var(--p, #7c6ff7); color: #fff; font-size: var(--fs-sm, 11.5px); font-weight: 500; cursor: pointer; font-family: inherit; }
.pr-btn:disabled { opacity: .5; }
.pr-btn-ghost { padding: 8px 16px; border-radius: 9px; border: 1px solid var(--border, rgba(99,102,180,.18)); background: transparent; color: var(--t2, #475569); font-size: var(--fs-sm, 11.5px); cursor: pointer; font-family: inherit; }
</style>
