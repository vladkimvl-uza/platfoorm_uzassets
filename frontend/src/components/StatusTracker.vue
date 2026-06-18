<script setup lang="ts">
/**
 * StatusTracker — «Текущий статус проекта» (Вариант C: месячный трекер).
 *
 *  • Полоса месяцев с цветными точками-индикаторами (health) — тренд с
 *    первого взгляда. Клик по месяцу → его записи в таймлайне.
 *  • Панель выбранного месяца + композер (текст + светофор) → новая запись.
 *  • Динамичный таймлайн истории под трекером (анимированные точки,
 *    «рисующаяся» линия, slide-in записей).
 *
 * Append-only: каждое сохранение — новая запись. В режиме создания
 * (entityId=null) бэкенда ещё нет → черновик уходит наверх через v-model,
 * родитель POST-ит первую запись после создания сущности.
 */
import { ref, computed, onMounted, watch, nextTick } from "vue";
import {
  statusUpdatesApi,
  HEALTH_META,
  HEALTH_ORDER,
  type StatusUpdate,
  type StatusHealth,
} from "@/api/statusUpdates";

const props = defineProps<{
  entityType: "project" | "task";
  entityId: string | null;
  canEdit: boolean;
  draftBody?: string;
  draftHealth?: StatusHealth | null;
}>();
const emit = defineEmits<{
  (e: "update:draftBody", v: string): void;
  (e: "update:draftHealth", v: StatusHealth | null): void;
}>();

const MONTHS_RU = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];
const MONTHS_FULL = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];

const entries = ref<StatusUpdate[]>([]);
const loading = ref(false);
const composing = ref(false);
const draftText = ref("");
const draftH = ref<StatusHealth | null>(null);
const saving = ref(false);
const justAddedId = ref<string | null>(null);

const now = new Date();
const STRIP_MONTHS = 9;

function monthKey(d: Date) { return `${d.getFullYear()}-${d.getMonth()}`; }
const selectedKey = ref(monthKey(now));

// ─── Загрузка истории ───
async function load() {
  if (!props.entityId) return;
  loading.value = true;
  try {
    entries.value = await statusUpdatesApi.list(props.entityType, props.entityId);
  } catch { /* тихо */ } finally { loading.value = false; }
}
onMounted(() => {
  load();
  // создание: подхватить уже введённый черновик
  if (!props.entityId) {
    draftText.value = props.draftBody || "";
    draftH.value = props.draftHealth ?? null;
    composing.value = true;
  }
});
watch(() => props.entityId, (v) => { if (v) load(); });

// в режиме создания синхронизируем черновик наверх
watch([draftText, draftH], () => {
  if (!props.entityId) {
    emit("update:draftBody", draftText.value);
    emit("update:draftHealth", draftH.value);
  }
});

// ─── Полоса месяцев ───
interface MonthCell { key: string; y: number; m: number; short: string; full: string; health: StatusHealth | null; has: boolean; isCurrent: boolean; }

const monthCells = computed<MonthCell[]>(() => {
  const cells: MonthCell[] = [];
  const base = new Date(now.getFullYear(), now.getMonth(), 1);
  for (let i = STRIP_MONTHS - 1; i >= 0; i--) {
    const d = new Date(base.getFullYear(), base.getMonth() - i, 1);
    const key = monthKey(d);
    // последняя запись этого месяца (entries отсортированы desc)
    const latest = entries.value.find((e) => monthKey(new Date(e.created_at)) === key);
    cells.push({
      key, y: d.getFullYear(), m: d.getMonth(),
      short: MONTHS_RU[d.getMonth()], full: MONTHS_FULL[d.getMonth()],
      health: latest?.health ?? null, has: !!latest,
      isCurrent: key === monthKey(now),
    });
  }
  return cells;
});

const selectedCell = computed(() => monthCells.value.find((c) => c.key === selectedKey.value) || monthCells.value[monthCells.value.length - 1]);
const selectedEntries = computed(() => entries.value.filter((e) => monthKey(new Date(e.created_at)) === selectedKey.value));
const selectedLatest = computed<StatusUpdate | null>(() => selectedEntries.value[0] || null);

// «текущий» = самая свежая запись вообще
const currentEntry = computed<StatusUpdate | null>(() => entries.value[0] || null);
const staleDays = computed(() => {
  if (!currentEntry.value) return null;
  return Math.floor((Date.now() - new Date(currentEntry.value.created_at).getTime()) / 86400000);
});
const isStale = computed(() => props.entityId && (staleDays.value === null || (staleDays.value ?? 0) > 30));

function selectMonth(c: MonthCell) {
  selectedKey.value = c.key;
  composing.value = false;
}

// ─── Композер ───
function openComposer() {
  draftText.value = selectedLatest.value?.body || "";
  draftH.value = selectedLatest.value?.health ?? currentEntry.value?.health ?? null;
  composing.value = true;
  nextTick(() => { document.getElementById("st-textarea")?.focus(); });
}
function cancelComposer() {
  composing.value = false;
  draftText.value = "";
}
function pickHealth(h: StatusHealth) {
  draftH.value = draftH.value === h ? null : h;
}

async function save() {
  const body = draftText.value.trim();
  if (!body) return;
  if (!props.entityId) {            // create-mode: только синхронизация наверх
    emit("update:draftBody", body);
    emit("update:draftHealth", draftH.value);
    return;
  }
  saving.value = true;
  // editor-safety: бэкап до отправки
  try { localStorage.setItem(`uz_status_draft_${props.entityType}_${props.entityId}`, JSON.stringify({ body, health: draftH.value })); } catch { /* ignore */ }
  try {
    const created = await statusUpdatesApi.create(props.entityType, props.entityId, body, draftH.value);
    entries.value = [created, ...entries.value];
    justAddedId.value = created.id;
    selectedKey.value = monthKey(new Date(created.created_at));
    composing.value = false;
    draftText.value = "";
    try { localStorage.removeItem(`uz_status_draft_${props.entityType}_${props.entityId}`); } catch { /* ignore */ }
    setTimeout(() => { justAddedId.value = null; }, 1600);
  } catch (e) {
    /* оставляем композер открытым, бэкап цел */
  } finally { saving.value = false; }
}

function canModify(_e: StatusUpdate): boolean {
  return props.canEdit;   // backend дополнительно гейтит автора/owner
}
async function removeEntry(e: StatusUpdate) {
  if (!confirm("Удалить эту запись статуса?")) return;
  try {
    await statusUpdatesApi.remove(e.id);
    entries.value = entries.value.filter((x) => x.id !== e.id);
  } catch { /* ignore */ }
}

function fmtDateFull(iso: string): string {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS_FULL[d.getMonth()].toLowerCase()} ${d.getFullYear()}`;
}
function relTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 3600) return "только что";
  if (diff < 86400) return Math.floor(diff / 3600) + " ч назад";
  const days = Math.floor(diff / 86400);
  if (days === 1) return "вчера";
  if (days < 30) return days + " дн назад";
  return Math.floor(days / 30) + " мес назад";
}
// «Нет оценки» больше не серый — фирменный фиолетовый, чтобы трекер жил цветом.
function healthColor(h: StatusHealth | null): string { return h ? HEALTH_META[h].color : "#7F77DD"; }
function healthLabel(h: StatusHealth | null): string { return h ? HEALTH_META[h].label : "Нет оценки"; }
</script>

<template>
  <div class="st-root">
    <div class="st-head">
      <span class="st-label">Текущий статус проекта</span>
      <span v-if="isStale && entityId" class="st-stale">
        <span class="st-stale-dot"></span>{{ staleDays === null ? "Нет статуса" : "Обновить" }}
      </span>
    </div>

    <!-- ═══ Полоса месяцев ═══ -->
    <div v-if="entityId" class="st-strip">
      <button
        v-for="(c, i) in monthCells"
        :key="c.key"
        class="st-mcell"
        :class="{ 'st-mcell-on': c.key === selectedKey, 'st-mcell-now': c.isCurrent, 'st-mcell-empty': !c.has }"
        :style="{ '--mc': healthColor(c.health), '--d': i * 0.04 + 's' }"
        :title="`${c.full} ${c.y} · ${healthLabel(c.health)}`"
        @click="selectMonth(c)"
      >
        <span class="st-mdot"></span>
        <span class="st-mname">{{ c.short }}</span>
      </button>
    </div>

    <!-- ═══ Панель выбранного месяца ═══ -->
    <div class="st-panel" :style="{ '--ph': healthColor(selectedLatest?.health ?? null) }">
      <div class="st-panel-head">
        <div class="st-panel-title">
          {{ selectedCell?.full }} {{ selectedCell?.y }}
          <span v-if="selectedLatest" class="st-hpill" :style="{ '--hc': healthColor(selectedLatest.health) }">
            <span class="st-hpill-dot"></span>{{ healthLabel(selectedLatest.health) }}
          </span>
        </div>
        <button v-if="canEdit && !composing" class="st-fill-btn" @click="openComposer">
          {{ selectedLatest ? "Обновить" : "Заполнить" }}
        </button>
      </div>

      <!-- Текст выбранного месяца -->
      <transition name="st-fade">
        <div v-if="!composing && selectedLatest" class="st-current-body">
          {{ selectedLatest.body }}
          <div class="st-current-meta">
            {{ selectedLatest.author_name || "—" }} · {{ relTime(selectedLatest.created_at) }}
          </div>
        </div>
        <div v-else-if="!composing && !selectedLatest" class="st-empty">
          Обновления за этот месяц ещё нет.
        </div>
      </transition>

      <!-- Композер -->
      <transition name="st-slide">
        <div v-if="composing" class="st-composer">
          <div class="st-health-row">
            <button
              v-for="h in HEALTH_ORDER" :key="h"
              class="st-hbtn" :class="{ 'st-hbtn-on': draftH === h }"
              :style="{ '--hc': HEALTH_META[h].color }"
              @click="pickHealth(h)"
            >
              <span class="st-hbtn-dot"></span>{{ HEALTH_META[h].label }}
            </button>
          </div>
          <textarea
            id="st-textarea"
            v-model="draftText"
            class="st-textarea"
            rows="3"
            placeholder="Опишите текущий ход проекта словами…"
          ></textarea>
          <div v-if="entityId" class="st-composer-actions">
            <button class="st-btn-ghost" @click="cancelComposer">Отмена</button>
            <button class="st-btn-save" :disabled="saving || !draftText.trim()" @click="save">
              {{ saving ? "Сохранение…" : "Сохранить статус" }}
            </button>
          </div>
          <div v-else class="st-create-hint">Будет сохранено как первый статус после создания.</div>
        </div>
      </transition>
    </div>

    <!-- ═══ Динамичный таймлайн истории ═══ -->
    <div v-if="entityId && entries.length" class="st-history">
      <div class="st-history-label">История статусов · {{ entries.length }}</div>
      <transition-group tag="div" class="st-timeline" name="st-tl">
        <div
          v-for="e in entries"
          :key="e.id"
          class="st-tl-item"
          :class="{ 'st-tl-new': e.id === justAddedId, 'st-tl-sel': monthKey(new Date(e.created_at)) === selectedKey }"
          :style="{ '--hc': healthColor(e.health) }"
        >
          <span class="st-tl-dot"></span>
          <div class="st-tl-card">
            <div class="st-tl-top">
              <span class="st-tl-date">{{ fmtDateFull(e.created_at) }}</span>
              <span class="st-hpill st-hpill-sm" :style="{ '--hc': healthColor(e.health) }">
                <span class="st-hpill-dot"></span>{{ healthLabel(e.health) }}
              </span>
              <button v-if="canModify(e)" class="st-tl-del" title="Удалить" @click="removeEntry(e)">×</button>
            </div>
            <div class="st-tl-body">{{ e.body }}</div>
            <div class="st-tl-author">{{ e.author_name || "—" }}</div>
          </div>
        </div>
      </transition-group>
    </div>
  </div>
</template>

<style scoped>
.st-root { display: flex; flex-direction: column; gap: 12px; }
.st-head { display: flex; align-items: center; gap: 10px; }
.st-label {
  font-size: 10px; font-weight: 500; text-transform: uppercase;
  letter-spacing: .07em; color: var(--t3, #94A3B8);
}
.st-stale {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 10px; font-weight: 600; color: #B87600;
  background: rgba(239,159,39,.12); border: .5px solid rgba(239,159,39,.32);
  padding: 2px 9px; border-radius: 999px;
}
.st-stale-dot {
  width: 6px; height: 6px; border-radius: 50%; background: #EF9F27;
  animation: st-pulse 1.8s ease-in-out infinite;
}
@keyframes st-pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: .4; transform: scale(1.5); } }

/* ── Полоса месяцев ── */
.st-strip {
  display: flex; gap: 4px; padding: 4px 2px;
  overflow-x: auto;
}
.st-mcell {
  flex: 1 0 auto; min-width: 46px;
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 8px 4px 6px; border-radius: 11px;
  background: transparent; border: 1px solid transparent;
  cursor: pointer; font-family: inherit;
  transition: background .16s, border-color .16s, transform .16s var(--ease-standard, cubic-bezier(.34,1.2,.64,1));
  animation: st-cell-in .4s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both;
  animation-delay: var(--d);
}
@keyframes st-cell-in { from { opacity: 0; transform: translateY(6px) scale(.9); } to { opacity: 1; transform: none; } }
.st-mcell:hover { background: rgba(127,119,221,.06); transform: translateY(-2px); }
.st-mcell-on { background: rgba(127,119,221,.10); border-color: rgba(127,119,221,.28); }
.st-mdot {
  width: 13px; height: 13px; border-radius: 50%;
  background: var(--mc, #C7CCD9);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--mc, #C7CCD9) 18%, transparent);
  transition: transform .16s, box-shadow .16s;
}
.st-mcell-empty .st-mdot {
  background: transparent; border: 2px dashed #C7CCD9; box-shadow: none;
}
.st-mcell-now .st-mdot {
  transform: scale(1.18);
  animation: st-now-glow 2.2s ease-in-out infinite;
}
@keyframes st-now-glow {
  0%, 100% { box-shadow: 0 0 0 3px color-mix(in srgb, var(--mc, #7F77DD) 22%, transparent); }
  50%      { box-shadow: 0 0 0 6px color-mix(in srgb, var(--mc, #7F77DD) 10%, transparent),
                         0 0 10px color-mix(in srgb, var(--mc, #7F77DD) 45%, transparent); }
}
.st-mcell-on .st-mdot {
  background: radial-gradient(circle at 32% 30%,
    color-mix(in srgb, var(--mc, #7F77DD) 65%, #fff), var(--mc, #7F77DD));
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--mc, #7F77DD) 26%, transparent);
}
.st-mname {
  font-size: 10.5px; font-weight: 500; color: var(--t3, #94A3B8);
  font-variant-numeric: tabular-nums;
}
.st-mcell-on .st-mname, .st-mcell-now .st-mname { color: var(--t1, #1E2A4A); font-weight: 600; }

/* ── Панель месяца ── */
.st-panel {
  position: relative; border-radius: 13px;
  background: var(--bg-soft, #FAFAFC);
  border: 1px solid rgba(15,23,60,.06);
  padding: 13px 15px 14px 17px;
  box-shadow: 0 1px 4px rgba(15,23,60,.04);
}
.st-panel::before {
  content: ""; position: absolute; left: 0; top: 12px; bottom: 12px; width: 3px;
  border-radius: 0 3px 3px 0;
  background: linear-gradient(180deg,
    var(--ph, #7F77DD), color-mix(in srgb, var(--ph, #7F77DD) 45%, transparent));
  transition: background .3s;
}
.st-panel {
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--ph, #7F77DD) 5%, transparent), transparent 60%),
    var(--bg-soft, #FAFAFC);
}
.st-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.st-panel-title {
  display: flex; align-items: center; gap: 9px; flex-wrap: wrap;
  font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A);
}
.st-hpill {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 10.5px; font-weight: 600; color: var(--hc, #94A3B8);
  background: color-mix(in srgb, var(--hc, #94A3B8) 12%, transparent);
  padding: 2px 9px; border-radius: 999px;
}
.st-hpill-sm { font-size: 10px; padding: 1.5px 8px; }
.st-hpill-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--hc, #94A3B8); }
.st-fill-btn {
  font-size: 11.5px; font-weight: 600; color: #fff; background: var(--p-deep, #534AB7);
  border: none; border-radius: 8px; padding: 6px 13px; cursor: pointer; font-family: inherit;
  transition: background .14s, transform .14s;
}
.st-fill-btn:hover { background: #463E9F; transform: translateY(-1px); }
.st-current-body {
  margin-top: 10px; font-size: 13px; line-height: 1.5; color: var(--t1, #1E2A4A);
  white-space: pre-wrap;
}
.st-current-meta { margin-top: 7px; font-size: 11px; color: var(--t3, #94A3B8); }
.st-empty { margin-top: 9px; font-size: 12.5px; color: var(--t3, #94A3B8); font-style: italic; }

/* ── Композер ── */
.st-composer { margin-top: 11px; }
.st-health-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 9px; }
.st-hbtn {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; font-weight: 500; color: var(--t2, #475569);
  background: #fff; border: 1px solid rgba(15,23,60,.10);
  padding: 4px 10px; border-radius: 999px; cursor: pointer; font-family: inherit;
  transition: all .14s var(--ease-standard, cubic-bezier(.34,1.2,.64,1));
}
.st-hbtn-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--hc); transition: transform .14s; }
.st-hbtn:hover { border-color: var(--hc); }
.st-hbtn-on {
  color: var(--hc); border-color: var(--hc);
  background: color-mix(in srgb, var(--hc) 10%, #fff);
  transform: translateY(-1px);
}
.st-hbtn-on .st-hbtn-dot { transform: scale(1.3); }
.st-textarea {
  width: 100%; box-sizing: border-box; resize: vertical;
  font-family: inherit; font-size: 13px; line-height: 1.5; color: var(--t1, #1E2A4A);
  padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border-input, #E5E7EB);
  background: #fff; transition: border-color .14s, box-shadow .14s;
}
.st-textarea:focus { outline: none; border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127,119,221,.14); }
.st-composer-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 9px; }
.st-btn-ghost {
  font-size: 12px; font-weight: 500; color: var(--t2, #475569);
  background: transparent; border: 1px solid var(--border-hard, #E5E7EB);
  border-radius: 8px; padding: 6px 13px; cursor: pointer; font-family: inherit;
}
.st-btn-ghost:hover { background: #F3F4F8; }
.st-btn-save {
  font-size: 12px; font-weight: 600; color: #fff; background: #1D9E75;
  border: none; border-radius: 8px; padding: 6px 15px; cursor: pointer; font-family: inherit;
  transition: background .14s, transform .14s;
}
.st-btn-save:hover:not(:disabled) { background: #178B66; transform: translateY(-1px); }
.st-btn-save:disabled { opacity: .5; cursor: not-allowed; }
.st-create-hint { margin-top: 8px; font-size: 11px; color: var(--t3, #94A3B8); font-style: italic; }

/* ── Таймлайн истории (динамичный) ── */
.st-history { margin-top: 4px; }
.st-history-label {
  font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: .07em;
  color: var(--t3, #94A3B8); margin-bottom: 10px;
}
.st-timeline { position: relative; padding-left: 6px; }
.st-tl-item {
  position: relative; padding: 0 0 14px 22px;
}
/* «Рисующаяся» вертикальная линия */
.st-tl-item::before {
  content: ""; position: absolute; left: 5px; top: 13px; bottom: -1px; width: 2px;
  background: linear-gradient(var(--hc, #C7CCD9), rgba(15,23,60,.08));
  transform-origin: top; animation: st-line .5s ease both;
}
.st-tl-item:last-child::before { display: none; }
@keyframes st-line { from { transform: scaleY(0); } to { transform: scaleY(1); } }
.st-tl-dot {
  position: absolute; left: 0; top: 7px; width: 12px; height: 12px; border-radius: 50%;
  background: var(--hc, #C7CCD9); border: 2px solid var(--bg1, #fff);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--hc, #C7CCD9) 16%, transparent);
  animation: st-dot-pop .4s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both;
  z-index: 1;
}
@keyframes st-dot-pop { from { transform: scale(0); } to { transform: scale(1); } }
.st-tl-card {
  background: #fff; border: 1px solid rgba(15,23,60,.06); border-radius: 11px;
  padding: 9px 12px 10px; box-shadow: 0 1px 3px rgba(15,23,60,.04);
  transition: box-shadow .16s, border-color .16s, transform .16s;
}
.st-tl-item:hover .st-tl-card { box-shadow: 0 4px 14px rgba(15,23,60,.08); transform: translateY(-1px); }
.st-tl-sel .st-tl-card { border-color: color-mix(in srgb, var(--hc, #7F77DD) 40%, transparent); }
.st-tl-new .st-tl-card { animation: st-flash 1.5s ease; }
@keyframes st-flash {
  0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--hc, #1D9E75) 55%, transparent); }
  100% { box-shadow: 0 0 0 14px transparent; }
}
.st-tl-top { display: flex; align-items: center; gap: 8px; }
.st-tl-date { font-size: 11px; font-weight: 600; color: var(--t1, #1E2A4A); }
.st-tl-del {
  margin-left: auto; width: 18px; height: 18px; border-radius: 5px; border: none;
  background: transparent; color: var(--t3, #94A3B8); cursor: pointer; font-size: 15px;
  line-height: 1; opacity: 0; transition: opacity .14s, background .14s, color .14s;
}
.st-tl-item:hover .st-tl-del { opacity: 1; }
.st-tl-del:hover { background: rgba(226,75,74,.10); color: #E24B4A; }
.st-tl-body { margin-top: 5px; font-size: 12.5px; line-height: 1.5; color: var(--t2, #475569); white-space: pre-wrap; }
.st-tl-author { margin-top: 6px; font-size: 10.5px; color: var(--t3, #94A3B8); }

/* ── Transitions ── */
.st-fade-enter-active, .st-fade-leave-active { transition: opacity .2s; }
.st-fade-enter-from, .st-fade-leave-to { opacity: 0; }
.st-slide-enter-active { transition: max-height .35s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)), opacity .3s; max-height: 320px; overflow: hidden; }
.st-slide-leave-active { transition: max-height .25s ease, opacity .2s; max-height: 320px; overflow: hidden; }
.st-slide-enter-from, .st-slide-leave-to { max-height: 0; opacity: 0; }
.st-tl-enter-active { transition: all .4s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)); }
.st-tl-enter-from { opacity: 0; transform: translateY(-12px); }
.st-tl-move { transition: transform .4s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)); }
</style>
