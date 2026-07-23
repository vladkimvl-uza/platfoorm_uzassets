<script setup lang="ts">
/**
 * ValueOpportunities — «Реестр возможностей ценности».
 * Единый реестр выявленной экономии / роста / предотвращённого риска по
 * компаниям портфеля, с суммами, ответственными и трекингом реализации
 * (выявлено → в работе → реализовано). Доступ по умолчанию только у владельца,
 * настраивается через право value.view/value.edit в RBAC.
 */
import { computed, inject, onMounted, ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useToast } from "@/composables/useToast";
import { bpApi, type AvailableCompany } from "@/api/bpKpi";
import {
  valueApi, VALUE_SOURCE_LABEL, VALUE_KIND_LABEL, VALUE_STATUS_LABEL,
  type ValueOpportunity, type ValueSummary, type ValueOpportunityInput,
  type ValueStatus, type ValueSource, type ValueKind,
} from "@/api/valueOpportunities";

const auth = useAuthStore();
const toast = useToast();
const canEdit = computed(() => auth.hasPermission("value.edit"));

const toggleSidebar = inject<() => void>("toggleSidebar", () => {});
const openMobileSidebar = inject<() => void>("openMobileSidebar", () => {});
function onBurger() {
  if (typeof window !== "undefined" && window.innerWidth <= 1023) openMobileSidebar();
  else toggleSidebar();
}

const rows = ref<ValueOpportunity[]>([]);
const summary = ref<ValueSummary | null>(null);
const companies = ref<AvailableCompany[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

const fStatus = ref<string>("");
const fSource = ref<string>("");
let seq = 0;

const STATUSES: { v: ValueStatus; l: string }[] = [
  { v: "identified", l: "Выявлено" }, { v: "in_progress", l: "В работе" },
  { v: "realized", l: "Реализовано" }, { v: "dismissed", l: "Отклонено" },
];
const SOURCES: ValueSource[] = ["unit_cost", "procurement", "business_plan", "kpi", "manual"];
const KINDS: ValueKind[] = ["economy", "uplift", "risk"];

function fmt(v: string | number | null | undefined): string {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  const a = Math.abs(n);
  const s = a >= 1000 ? Math.round(n).toLocaleString("ru-RU").replace(/,/g, " ")
    : a >= 10 ? n.toFixed(0) : n.toFixed(1).replace(/\.0$/, "");
  return s;
}
function statusColor(s: string): string {
  return s === "realized" ? "#1D9E75" : s === "in_progress" ? "#D97706"
    : s === "dismissed" ? "#9AA3B2" : "#6355E0";
}
function kindColor(k: string): string {
  return k === "economy" ? "#1D9E75" : k === "uplift" ? "#6355E0" : "#E24B4A";
}

async function load() {
  const my = ++seq;
  loading.value = true; error.value = null;
  try {
    const [list, sum] = await Promise.all([
      valueApi.list({ status: fStatus.value || undefined, source: fSource.value || undefined }),
      valueApi.summary(),
    ]);
    if (my !== seq) return;
    rows.value = list; summary.value = sum;
  } catch (e: unknown) {
    if (my !== seq) return;
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить реестр";
  } finally { if (my === seq) loading.value = false; }
}
onMounted(async () => {
  load();
  try { companies.value = await bpApi.availableCompanies(); } catch { /* ignore */ }
});

// ─── Create / Edit modal ───
const modalOpen = ref(false);
const editing = ref<ValueOpportunity | null>(null);
const form = ref<ValueOpportunityInput>({ title: "", source: "manual", kind: "economy", status: "identified" });
const saving = ref(false);

function openCreate() {
  editing.value = null;
  form.value = { title: "", source: "manual", kind: "economy", status: "identified", year: new Date().getFullYear() };
  modalOpen.value = true;
}
function openEdit(r: ValueOpportunity) {
  editing.value = r;
  form.value = {
    company_id: r.company_id, year: r.year, source: r.source, kind: r.kind, status: r.status,
    title: r.title, description: r.description,
    value_amount: r.value_amount == null ? null : Number(r.value_amount),
    realized_amount: r.realized_amount == null ? null : Number(r.realized_amount),
    owner: r.owner, target_date: r.target_date,
  };
  modalOpen.value = true;
}
async function save() {
  if (!form.value.title.trim()) { toast.error("Укажите название возможности"); return; }
  saving.value = true;
  try {
    if (editing.value) await valueApi.update(editing.value.id, form.value);
    else await valueApi.create(form.value);
    toast.success(editing.value ? "Возможность обновлена" : "Возможность добавлена");
    modalOpen.value = false;
    await load();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } };
    toast.error(err?.response?.data?.detail || "Не удалось сохранить");
  } finally { saving.value = false; }
}

// быстрая смена статуса из таблицы
async function setStatus(r: ValueOpportunity, s: ValueStatus) {
  try { await valueApi.update(r.id, { status: s }); await load(); toast.success("Статус обновлён"); }
  catch { toast.error("Не удалось изменить статус"); }
}

// ─── Delete ───
const deleting = ref<ValueOpportunity | null>(null);
async function confirmDelete() {
  if (!deleting.value) return;
  try { await valueApi.remove(deleting.value.id); toast.success("Удалено"); deleting.value = null; await load(); }
  catch { toast.error("Не удалось удалить"); }
}
</script>

<template>
  <div class="vo-view">
    <div class="vo-topbar">
      <button class="vo-burger" @click="onBurger" aria-label="Меню">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <div class="vo-tb-left">
        <div class="vo-eyebrow">UzAssets · Ценность</div>
        <div class="vo-title">Реестр возможностей ценности</div>
        <div class="vo-sub">Экономия, рост и предотвращённые риски по компаниям — от выявления до реализации</div>
      </div>
      <button v-if="canEdit" class="vo-add" @click="openCreate">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        Добавить
      </button>
    </div>

    <div class="vo-body">
      <!-- KPI strip -->
      <div class="vo-kpis">
        <div class="vo-kpi" style="--a:#6355E0">
          <div class="vo-kpi-lbl">Выявленный потенциал</div>
          <div class="vo-kpi-val">{{ fmt(summary?.identified_amount) }}<span class="vo-kpi-u">млрд сум</span></div>
          <div class="vo-kpi-sub">в работе {{ fmt(summary?.in_progress_amount) }}</div>
        </div>
        <div class="vo-kpi" style="--a:#1D9E75">
          <div class="vo-kpi-lbl">Реализовано</div>
          <div class="vo-kpi-val">{{ fmt(summary?.realized_amount) }}<span class="vo-kpi-u">млрд сум</span></div>
          <div class="vo-kpi-sub">подтверждённый эффект</div>
        </div>
        <div class="vo-kpi" style="--a:#D97706">
          <div class="vo-kpi-lbl">Записей в реестре</div>
          <div class="vo-kpi-val">{{ summary?.total_count ?? 0 }}</div>
          <div class="vo-kpi-sub">по {{ (summary?.by_company?.length ?? 0) }} компаниям</div>
        </div>
        <div class="vo-kpi" style="--a:#378ADD">
          <div class="vo-kpi-lbl">Источники</div>
          <div class="vo-kpi-chips">
            <span v-for="s in (summary?.by_source || [])" :key="s.status" class="vo-src-chip">
              {{ VALUE_SOURCE_LABEL[s.status as ValueSource] || s.status }}: <b>{{ s.count }}</b>
            </span>
            <span v-if="!(summary?.by_source?.length)" class="vo-kpi-sub">нет данных</span>
          </div>
        </div>
      </div>

      <!-- Filters -->
      <div class="vo-filters">
        <div class="vo-seg">
          <button :class="{ on: fStatus === '' }" @click="fStatus = ''; load()">Все</button>
          <button v-for="s in STATUSES" :key="s.v" :class="{ on: fStatus === s.v }" @click="fStatus = s.v; load()">{{ s.l }}</button>
        </div>
        <select v-model="fSource" @change="load" class="vo-sel">
          <option value="">Все источники</option>
          <option v-for="s in SOURCES" :key="s" :value="s">{{ VALUE_SOURCE_LABEL[s] }}</option>
        </select>
      </div>

      <div v-if="error" class="vo-err">{{ error }}</div>
      <div v-else-if="loading" class="vo-loading">Загрузка…</div>
      <div v-else-if="!rows.length" class="vo-empty">
        <b>Реестр пуст</b>
        <span>Добавьте возможность вручную. Позже подключим авто-выявление из модулей «Удельная себестоимость», «Закупки» и «Бизнес-план».</span>
      </div>

      <!-- Table -->
      <div v-else class="vo-tbl-wrap">
        <table class="vo-tbl">
          <thead><tr>
            <th>Компания</th><th>Источник</th><th>Возможность</th><th>Тип</th>
            <th class="r">Потенциал</th><th class="r">Реализовано</th><th>Статус</th><th>Ответственный</th>
            <th v-if="canEdit"></th>
          </tr></thead>
          <tbody>
            <tr v-for="r in rows" :key="r.id">
              <td>
                <span class="vo-co"><i :style="{ background: r.sector_color || '#9AA3B2' }"></i>{{ r.company_name || '— портфель —' }}</span>
              </td>
              <td><span class="vo-src">{{ VALUE_SOURCE_LABEL[r.source] }}</span></td>
              <td class="vo-ttl">
                <div class="vo-ttl-t">{{ r.title }}</div>
                <div v-if="r.description" class="vo-ttl-d">{{ r.description }}</div>
              </td>
              <td><span class="vo-kind" :style="{ color: kindColor(r.kind), background: kindColor(r.kind) + '18' }">{{ VALUE_KIND_LABEL[r.kind] }}</span></td>
              <td class="r vo-amt">{{ fmt(r.value_amount) }}</td>
              <td class="r vo-amt">{{ fmt(r.realized_amount) }}</td>
              <td>
                <select v-if="canEdit" :value="r.status" @change="setStatus(r, ($event.target as HTMLSelectElement).value as ValueStatus)"
                        class="vo-status-sel" :style="{ color: statusColor(r.status), borderColor: statusColor(r.status) + '55' }">
                  <option v-for="s in STATUSES" :key="s.v" :value="s.v">{{ s.l }}</option>
                </select>
                <span v-else class="vo-status" :style="{ color: statusColor(r.status), background: statusColor(r.status) + '18' }">{{ VALUE_STATUS_LABEL[r.status] }}</span>
              </td>
              <td class="vo-owner">{{ r.owner || '—' }}</td>
              <td v-if="canEdit" class="vo-actions">
                <button class="vo-ico" @click="openEdit(r)" title="Редактировать">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>
                </button>
                <button class="vo-ico vo-ico-del" @click="deleting = r" title="Удалить">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create/Edit modal -->
    <Teleport to="body">
      <div v-if="modalOpen" class="vo-back" @click.self="modalOpen = false" role="dialog" aria-modal="true">
        <div class="vo-modal">
          <header class="vo-m-hd">
            <h3>{{ editing ? "Редактировать возможность" : "Новая возможность ценности" }}</h3>
            <button class="vo-x" @click="modalOpen = false">×</button>
          </header>
          <div class="vo-m-body">
            <label class="vo-fld"><span>Название *</span>
              <input v-model="form.title" type="text" maxlength="300" placeholder="Напр. Снижение перерасхода дизтоплива на 8%" />
            </label>
            <label class="vo-fld"><span>Описание</span>
              <textarea v-model="form.description" rows="2" placeholder="Как создаётся ценность, обоснование"></textarea>
            </label>
            <div class="vo-fld-row">
              <label class="vo-fld"><span>Компания</span>
                <select v-model="form.company_id">
                  <option :value="null">— портфель (все) —</option>
                  <option v-for="c in companies" :key="c.company_id" :value="c.company_id">{{ c.company_name_ru }}</option>
                </select>
              </label>
              <label class="vo-fld vo-fld-sm"><span>Год</span>
                <input v-model.number="form.year" type="number" />
              </label>
            </div>
            <div class="vo-fld-row">
              <label class="vo-fld"><span>Источник</span>
                <select v-model="form.source"><option v-for="s in SOURCES" :key="s" :value="s">{{ VALUE_SOURCE_LABEL[s] }}</option></select>
              </label>
              <label class="vo-fld"><span>Тип</span>
                <select v-model="form.kind"><option v-for="k in KINDS" :key="k" :value="k">{{ VALUE_KIND_LABEL[k] }}</option></select>
              </label>
              <label class="vo-fld"><span>Статус</span>
                <select v-model="form.status"><option v-for="s in STATUSES" :key="s.v" :value="s.v">{{ s.l }}</option></select>
              </label>
            </div>
            <div class="vo-fld-row">
              <label class="vo-fld"><span>Потенциал, млрд сум</span>
                <input v-model.number="form.value_amount" type="number" step="0.001" />
              </label>
              <label class="vo-fld"><span>Реализовано, млрд сум</span>
                <input v-model.number="form.realized_amount" type="number" step="0.001" />
              </label>
            </div>
            <div class="vo-fld-row">
              <label class="vo-fld"><span>Ответственный</span>
                <input v-model="form.owner" type="text" placeholder="ФИО / подразделение" />
              </label>
              <label class="vo-fld vo-fld-sm"><span>Срок</span>
                <input v-model="form.target_date" type="date" />
              </label>
            </div>
          </div>
          <footer class="vo-m-ft">
            <button class="vo-btn-ghost" @click="modalOpen = false">Отмена</button>
            <button class="vo-btn" :disabled="saving" @click="save">{{ saving ? "Сохранение…" : "Сохранить" }}</button>
          </footer>
        </div>
      </div>
    </Teleport>

    <!-- Delete confirm -->
    <Teleport to="body">
      <div v-if="deleting" class="vo-back" @click.self="deleting = null" role="dialog" aria-modal="true">
        <div class="vo-modal vo-modal-sm">
          <header class="vo-m-hd"><h3>Удалить возможность?</h3><button class="vo-x" @click="deleting = null">×</button></header>
          <div class="vo-m-body"><p class="vo-del-txt">«{{ deleting.title }}» будет удалена из реестра. Действие необратимо.</p></div>
          <footer class="vo-m-ft">
            <button class="vo-btn-ghost" @click="deleting = null">Отмена</button>
            <button class="vo-btn vo-btn-danger" @click="confirmDelete">Удалить</button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.vo-view { min-height: 100dvh; background: var(--bg2, #F6F6FA); }
.vo-topbar { display: flex; align-items: center; gap: 14px; padding: 16px 26px; background: linear-gradient(120deg, #2A2550, #4B3F9E); color: #fff; }
.vo-burger { display: none; border: none; background: rgba(255,255,255,.14); color: #fff; width: 36px; height: 36px; border-radius: 9px; cursor: pointer; align-items: center; justify-content: center; }
.vo-tb-left { flex: 1; min-width: 0; }
.vo-eyebrow { font-size: 11px; letter-spacing: .14em; opacity: .7; font-weight: 600; }
.vo-title { font-size: 21px; font-weight: 650; margin-top: 2px; }
.vo-sub { font-size: 12.5px; opacity: .75; margin-top: 3px; }
.vo-add { display: inline-flex; align-items: center; gap: 6px; height: 38px; padding: 0 16px; border: none; border-radius: 10px; background: #fff; color: #4B3F9E; font-weight: 650; font-size: 13.5px; cursor: pointer; }
.vo-add:hover { background: #F0EEFF; }

.vo-body { padding: 22px 26px 40px; max-width: 1400px; margin: 0 auto; }

.vo-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }
.vo-kpi { position: relative; background: #fff; border-radius: 14px; padding: 16px 18px 14px; box-shadow: 0 2px 12px rgba(15,23,60,.06); overflow: hidden; min-height: 96px; }
.vo-kpi::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--a, #6355E0); }
.vo-kpi-lbl { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: #8A90A0; font-weight: 600; }
.vo-kpi-val { font-size: 27px; font-weight: 400; letter-spacing: -.03em; color: #1E2A4A; margin: 6px 0 3px; display: flex; align-items: baseline; gap: 6px; font-variant-numeric: tabular-nums; }
.vo-kpi-u { font-size: 11px; color: #9AA3B2; font-weight: 500; }
.vo-kpi-sub { font-size: 11.5px; color: #9AA3B2; }
.vo-kpi-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.vo-src-chip { font-size: 10.5px; color: #5A6172; background: #F2F2F8; padding: 2px 7px; border-radius: 6px; }
.vo-src-chip b { color: #1E2A4A; }

.vo-filters { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.vo-seg { display: inline-flex; background: #EDEDF3; border-radius: 10px; padding: 3px; }
.vo-seg button { border: none; background: transparent; padding: 6px 13px; border-radius: 8px; cursor: pointer; font-size: 12.5px; font-weight: 600; color: #5A6172; }
.vo-seg button.on { background: #fff; color: #4B3F9E; box-shadow: 0 1px 4px -1px rgba(20,20,34,.18); }
.vo-sel, .vo-status-sel { height: 34px; padding: 0 10px; border: 1px solid #E4E4EC; border-radius: 9px; background: #fff; font-size: 13px; color: #1E2A4A; cursor: pointer; }

.vo-err { color: #E24B4A; padding: 16px; background: #FCE9E8; border-radius: 10px; }
.vo-loading { color: #8A90A0; padding: 40px; text-align: center; }
.vo-empty { display: flex; flex-direction: column; gap: 8px; align-items: center; text-align: center; padding: 60px 20px; color: #8A90A0; }
.vo-empty b { color: #1E2A4A; font-size: 16px; }
.vo-empty span { max-width: 56ch; font-size: 13px; line-height: 1.6; }

.vo-tbl-wrap { background: #fff; border-radius: 14px; box-shadow: 0 2px 12px rgba(15,23,60,.06); overflow-x: auto; }
.vo-tbl { border-collapse: collapse; width: 100%; font-size: 13px; }
.vo-tbl th, .vo-tbl td { padding: 11px 14px; text-align: left; border-bottom: 1px solid #F0F0F5; white-space: nowrap; }
.vo-tbl th { background: #FAFAFD; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #8A90A0; font-weight: 650; position: sticky; top: 0; }
.vo-tbl th.r, .vo-tbl td.r { text-align: right; }
.vo-tbl tbody tr:hover td { background: #FAFAFD; }
.vo-tbl tbody tr:last-child td { border-bottom: none; }
.vo-co { display: inline-flex; align-items: center; gap: 8px; font-weight: 500; color: #1E2A4A; }
.vo-co i { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.vo-src { font-size: 12px; color: #5A6172; }
.vo-ttl { white-space: normal; max-width: 340px; }
.vo-ttl-t { color: #1E2A4A; font-weight: 500; }
.vo-ttl-d { color: #9AA3B2; font-size: 11.5px; margin-top: 2px; }
.vo-kind { display: inline-block; padding: 2px 9px; border-radius: 20px; font-size: 11.5px; font-weight: 600; }
.vo-amt { font-variant-numeric: tabular-nums; font-weight: 600; color: #1E2A4A; }
.vo-status { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 11.5px; font-weight: 600; }
.vo-status-sel { height: 30px; font-size: 12px; font-weight: 600; border-width: 1px; }
.vo-owner { color: #5A6172; font-size: 12.5px; }
.vo-actions { text-align: right; white-space: nowrap; }
.vo-ico { border: none; background: transparent; color: #9AA3B2; cursor: pointer; padding: 5px; border-radius: 7px; }
.vo-ico:hover { background: #F0EEFF; color: #4B3F9E; }
.vo-ico-del:hover { background: #FCE9E8; color: #E24B4A; }

.vo-back { position: fixed; inset: 0; z-index: var(--z-modal, 9100); display: flex; align-items: flex-start; justify-content: center; padding: 6vh 16px 40px; background: rgba(20,20,34,.5); backdrop-filter: blur(3px); }
.vo-modal { width: min(640px, 100%); background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 24px 64px -20px rgba(20,20,34,.5); max-height: 88vh; display: flex; flex-direction: column; }
.vo-modal-sm { width: min(440px, 100%); }
.vo-m-hd { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px 14px; border-bottom: 1px solid #F0F0F5; }
.vo-m-hd h3 { margin: 0; font-size: 17px; font-weight: 650; color: #1E2A4A; }
.vo-x { border: none; background: transparent; font-size: 24px; color: #9AA3B2; cursor: pointer; }
.vo-m-body { padding: 18px 22px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
.vo-fld { display: flex; flex-direction: column; gap: 5px; flex: 1; }
.vo-fld > span { font-size: 11.5px; color: #8A90A0; font-weight: 600; }
.vo-fld input, .vo-fld select, .vo-fld textarea { border: 1px solid #E4E4EC; border-radius: 9px; padding: 8px 10px; font-size: 13.5px; font-family: inherit; color: #1E2A4A; background: #fff; }
.vo-fld input:focus, .vo-fld select:focus, .vo-fld textarea:focus { outline: none; border-color: #6355E0; box-shadow: 0 0 0 3px rgba(99,85,224,.15); }
.vo-fld-row { display: flex; gap: 12px; flex-wrap: wrap; }
.vo-fld-sm { max-width: 130px; }
.vo-del-txt { color: #5A6172; font-size: 13.5px; line-height: 1.5; margin: 0; }
.vo-m-ft { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 22px 18px; border-top: 1px solid #F0F0F5; }
.vo-btn { height: 38px; padding: 0 18px; border: none; border-radius: 10px; background: linear-gradient(135deg, #7C6FF7, #6355E0); color: #fff; font-weight: 650; font-size: 13.5px; cursor: pointer; }
.vo-btn:disabled { opacity: .6; cursor: default; }
.vo-btn-danger { background: #E24B4A; }
.vo-btn-ghost { height: 38px; padding: 0 16px; border: 1px solid #E4E4EC; border-radius: 10px; background: #fff; color: #5A6172; font-weight: 600; font-size: 13.5px; cursor: pointer; }

@media (max-width: 1023px) { .vo-burger { display: inline-flex; } }
@media (max-width: 1100px) { .vo-kpis { grid-template-columns: 1fr 1fr; } }
@media (max-width: 620px) { .vo-kpis { grid-template-columns: 1fr; } .vo-body { padding: 16px; } }
</style>
