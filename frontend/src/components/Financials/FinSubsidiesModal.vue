<script setup lang="ts">
/**
 * FinSubsidiesModal — реестр субсидий по компаниям портфеля.
 *
 * Открывается из метрики «Субсидии» в модуле финансы. Полный реестр с
 * фильтрами по году / сектору / компании / статусу / поиску, итогами и
 * CRUD (если есть право financials.edit). Премиум UX, top-accent, без эмодзи.
 */
import { computed, onMounted, ref } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import Odometer from "@/components/Odometer.vue";
import { useToast } from "@/composables/useToast";
import type { CompanyListItem, SectorBrief } from "@/api/companies";
import {
  subsidiesApi,
  fmtSubsidySum,
  SUBSIDY_STATUSES,
  subsidyStatusLabel,
  type SubsidyRow,
} from "@/api/subsidies";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();

const props = defineProps<{
  year: number;
  sectorCode: string;
  companies: CompanyListItem[];
  sectors: SectorBrief[];
  canEdit?: boolean;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "changed"): void;  // запись добавлена/изменена/удалена → родитель обновляет метрику
}>();

const toast = useToast();

const rows = ref<SubsidyRow[]>([]);
const loading = ref(true);
const loadError = ref<string | null>(null);

// ─── Фильтры (инициализируются контекстом страницы) ────────────────
const fYear = ref<number | "">(props.year ?? "");
const fSector = ref<string>(props.sectorCode || "");
const fCompany = ref<string>("");
const fStatus = ref<string>("");
const fSearch = ref<string>("");

async function load() {
  loading.value = true;
  loadError.value = null;
  try {
    rows.value = await subsidiesApi.list();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    loadError.value = err?.response?.data?.detail || err?.message || t("Не удалось загрузить реестр");
  } finally {
    loading.value = false;
  }
}
onMounted(load);

const years = computed<number[]>(() => {
  const set = new Set<number>();
  for (const r of rows.value) if (r.year != null) set.add(r.year);
  return Array.from(set).sort((a, b) => b - a);
});

const sortedSectors = computed(() =>
  [...props.sectors].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)),
);

const filtered = computed<SubsidyRow[]>(() => {
  const q = fSearch.value.trim().toLowerCase();
  return rows.value.filter(r => {
    if (fYear.value !== "" && r.year !== fYear.value) return false;
    if (fSector.value && String(r.sector_code || "").toLowerCase() !== fSector.value.toLowerCase()) return false;
    if (fCompany.value && r.company_id !== fCompany.value) return false;
    if (fStatus.value && r.status !== fStatus.value) return false;
    if (q) {
      const hay = [r.company_name, r.program, r.source, r.kind, r.note].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
});

const filteredTotal = computed(() =>
  filtered.value.reduce((s, r) => s + Number(r.amount || 0), 0),
);
const totalFmt = computed(() => fmtSubsidySum(filteredTotal.value));

const distinctCompanies = computed(() => new Set(filtered.value.map(r => r.company_id)).size);
const topSector = computed(() => {
  const m = new Map<string, { name: string; color: string; total: number }>();
  for (const r of filtered.value) {
    const k = r.sector_code || "—";
    const e = m.get(k) || { name: r.sector_name || t("Без сектора"), color: r.sector_color || "#94A3B8", total: 0 };
    e.total += Number(r.amount || 0);
    m.set(k, e);
  }
  let best: { name: string; color: string; total: number } | null = null;
  for (const e of m.values()) if (!best || e.total > best.total) best = e;
  return best;
});

interface SummaryStat { key: string; label: string; value: string; unit?: string; accent: string; animate: boolean; }
const summaryStats = computed<SummaryStat[]>(() => [
  { key: "total", label: t("Сумма субсидий"), value: totalFmt.value.value, unit: t(totalFmt.value.unit), accent: "#1D9E75", animate: true },
  { key: "count", label: t("Записей"), value: String(filtered.value.length), accent: "#7F77DD", animate: true },
  { key: "co", label: t("Компаний"), value: String(distinctCompanies.value), accent: "#378ADD", animate: true },
  { key: "sector", label: t("Топ-сектор"), value: topSector.value ? topSector.value.name : "—", accent: topSector.value?.color || "#EF9F27", animate: false },
]);

function resetFilters() {
  fYear.value = "";
  fSector.value = "";
  fCompany.value = "";
  fStatus.value = "";
  fSearch.value = "";
}

function fmtAmount(v: number | null): string {
  const f = fmtSubsidySum(v);
  return f.value === "—" ? "—" : `${f.value} ${t(f.unit)}`;
}
function fmtDate(d: string | null): string {
  if (!d) return "—";
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : d;
}

// ─── CRUD форма ────────────────────────────────────────────────────
interface FormState {
  company_id: string;
  year: number | "";
  amountMln: number | "";   // ввод в млн сум → хранится raw сум (×1e6)
  program: string;
  source: string;
  kind: string;
  status: string;
  allocation_date: string;
  note: string;
}
function emptyForm(): FormState {
  return {
    company_id: "",
    year: props.year ?? "",
    amountMln: "",
    program: "",
    source: "",
    kind: "",
    status: "",
    allocation_date: "",
    note: "",
  };
}
const formOpen = ref(false);
const editingId = ref<string | null>(null);
const form = ref<FormState>(emptyForm());
const saving = ref(false);

function openCreate() {
  editingId.value = null;
  form.value = emptyForm();
  // если выбран фильтр-компания/сектор-год — предзаполняем
  if (fCompany.value) form.value.company_id = fCompany.value;
  if (fYear.value !== "") form.value.year = fYear.value;
  formOpen.value = true;
}
function openEdit(r: SubsidyRow) {
  editingId.value = r.id;
  form.value = {
    company_id: r.company_id,
    year: r.year ?? "",
    amountMln: r.amount != null ? Math.round((r.amount / 1e6) * 100) / 100 : "",
    program: r.program || "",
    source: r.source || "",
    kind: r.kind || "",
    status: r.status || "",
    allocation_date: r.allocation_date ? r.allocation_date.slice(0, 10) : "",
    note: r.note || "",
  };
  formOpen.value = true;
}
function cancelForm() {
  formOpen.value = false;
  editingId.value = null;
}

async function saveForm() {
  if (saving.value) return;
  if (!form.value.company_id) {
    toast.error(t("Выберите компанию"));
    return;
  }
  saving.value = true;
  const payload = {
    company_id: form.value.company_id,
    year: form.value.year === "" ? null : Number(form.value.year),
    amount: form.value.amountMln === "" ? null : Number(form.value.amountMln) * 1e6,
    program: form.value.program.trim() || null,
    source: form.value.source.trim() || null,
    kind: form.value.kind.trim() || null,
    status: form.value.status || null,
    allocation_date: form.value.allocation_date || null,
    note: form.value.note.trim() || null,
  };
  try {
    if (editingId.value) {
      const updated = await subsidiesApi.update(editingId.value, {
        year: payload.year,
        amount: payload.amount,
        program: payload.program,
        source: payload.source,
        kind: payload.kind,
        status: payload.status,
        allocation_date: payload.allocation_date,
        note: payload.note,
      });
      const i = rows.value.findIndex(r => r.id === editingId.value);
      if (i >= 0) rows.value[i] = updated;
      toast.success(t("Субсидия обновлена"));
    } else {
      const created = await subsidiesApi.create(payload);
      rows.value.unshift(created);
      toast.success(t("Субсидия добавлена"));
    }
    formOpen.value = false;
    editingId.value = null;
    emit("changed");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t("Не удалось сохранить: {err}", { err: err?.response?.data?.detail || err?.message || t("ошибка") }));
  } finally {
    saving.value = false;
  }
}

const confirmDeleteId = ref<string | null>(null);
const deleting = ref(false);
async function doDelete(r: SubsidyRow) {
  if (deleting.value) return;
  deleting.value = true;
  try {
    await subsidiesApi.remove(r.id);
    rows.value = rows.value.filter(x => x.id !== r.id);
    confirmDeleteId.value = null;
    toast.success(t("Субсидия удалена"));
    emit("changed");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t("Не удалось удалить: {err}", { err: err?.response?.data?.detail || err?.message || t("ошибка") }));
  } finally {
    deleting.value = false;
  }
}

const sortedCompanies = computed(() =>
  [...props.companies].sort((a, b) => (a.name_ru || "").localeCompare(b.name_ru || "", "ru")),
);
</script>

<template>
  <ModalShell :open="true" size="full" @close="emit('close')">
    <template #header>
      <div class="sub-head">
        <div class="sub-head-t">{{ t("Реестр субсидий") }}</div>
        <div class="sub-head-s">
          {{ t("{n} из {m} записей · итог", { n: filtered.length, m: rows.length }) }}
          <b>{{ totalFmt.value }}</b> <span v-if="totalFmt.unit">{{ t(totalFmt.unit) }}</span>
        </div>
      </div>
    </template>

    <div class="sub">
      <!-- Сводка -->
      <div class="sub-stats">
        <div
          v-for="(s, si) in summaryStats"
          :key="s.key"
          class="sub-stat"
          :style="{ '--accent': s.accent, '--d': (si * 60) + 'ms' }"
        >
          <div class="sub-stat-lbl">{{ t(s.label) }}</div>
          <div class="sub-stat-val">
            <Odometer v-if="s.animate" :value="s.value" /><span v-else class="sub-stat-txt">{{ s.value }}</span><span v-if="s.unit" class="sub-stat-unit">{{ s.unit }}</span>
          </div>
        </div>
      </div>

      <!-- Тулбар: фильтры + добавить -->
      <div class="sub-tools">
        <div class="sub-filters">
          <select v-model="fYear" class="sub-sel">
            <option value="">{{ t("Все годы") }}</option>
            <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
          </select>
          <select v-model="fSector" class="sub-sel">
            <option value="">{{ t("Все секторы") }}</option>
            <option v-for="s in sortedSectors" :key="s.code" :value="String(s.code).toLowerCase()">{{ s.name_ru }}</option>
          </select>
          <select v-model="fCompany" class="sub-sel">
            <option value="">{{ t("Все компании") }}</option>
            <option v-for="c in sortedCompanies" :key="c.id" :value="c.id">{{ c.name_ru }}</option>
          </select>
          <select v-model="fStatus" class="sub-sel">
            <option value="">{{ t("Все статусы") }}</option>
            <option v-for="s in SUBSIDY_STATUSES" :key="s.key" :value="s.key">{{ t(s.label) }}</option>
          </select>
          <input v-model="fSearch" class="sub-search" type="text" :placeholder="t('Поиск по назначению, источнику…')" />
          <button class="sub-reset" type="button" @click="resetFilters">{{ t("Сбросить") }}</button>
        </div>
        <button v-if="canEdit" class="sub-add" type="button" @click="openCreate">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          {{ t("Добавить субсидию") }}
        </button>
      </div>

      <!-- Форма создания/редактирования -->
      <Transition name="sub-form-fade">
        <div v-if="formOpen" class="sub-form">
          <div class="sub-form-h">{{ editingId ? t('Редактирование субсидии') : t('Новая субсидия') }}</div>
          <div class="sub-form-grid">
            <label class="sub-fld">
              <span class="sub-fld-l">{{ t("Компания") }} *</span>
              <select v-model="form.company_id" class="sub-inp">
                <option value="">{{ t("— выберите —") }}</option>
                <option v-for="c in sortedCompanies" :key="c.id" :value="c.id">{{ c.name_ru }}</option>
              </select>
            </label>
            <label class="sub-fld sub-fld-sm">
              <span class="sub-fld-l">{{ t("Год") }}</span>
              <input v-model.number="form.year" class="sub-inp" type="number" min="2000" max="2100" />
            </label>
            <label class="sub-fld sub-fld-sm">
              <span class="sub-fld-l">{{ t("Сумма, млн сум") }}</span>
              <input v-model.number="form.amountMln" class="sub-inp" type="number" min="0" step="0.01" />
            </label>
            <label class="sub-fld">
              <span class="sub-fld-l">{{ t("Назначение / программа") }}</span>
              <input v-model="form.program" class="sub-inp" type="text" :placeholder="t('Напр. субсидирование процентной ставки')" />
            </label>
            <label class="sub-fld">
              <span class="sub-fld-l">{{ t("Источник") }}</span>
              <input v-model="form.source" class="sub-inp" type="text" :placeholder="t('Республиканский бюджет / Фонд…')" />
            </label>
            <label class="sub-fld">
              <span class="sub-fld-l">{{ t("Вид") }}</span>
              <input v-model="form.kind" class="sub-inp" type="text" :placeholder="t('Прямая / % ставка / грант…')" />
            </label>
            <label class="sub-fld sub-fld-sm">
              <span class="sub-fld-l">{{ t("Статус") }}</span>
              <select v-model="form.status" class="sub-inp">
                <option value="">—</option>
                <option v-for="s in SUBSIDY_STATUSES" :key="s.key" :value="s.key">{{ t(s.label) }}</option>
              </select>
            </label>
            <label class="sub-fld sub-fld-sm">
              <span class="sub-fld-l">{{ t("Дата выделения") }}</span>
              <input v-model="form.allocation_date" class="sub-inp" type="date" />
            </label>
            <label class="sub-fld sub-fld-wide">
              <span class="sub-fld-l">{{ t("Примечание") }}</span>
              <textarea v-model="form.note" class="sub-inp sub-ta" rows="2"></textarea>
            </label>
          </div>
          <div class="sub-form-btns">
            <button class="sub-btn-cancel" type="button" :disabled="saving" @click="cancelForm">{{ t("Отмена") }}</button>
            <button class="sub-btn-save" type="button" :disabled="saving" @click="saveForm">
              {{ saving ? t('Сохранение…') : (editingId ? t('Сохранить') : t('Добавить')) }}
            </button>
          </div>
        </div>
      </Transition>

      <!-- Состояния -->
      <div v-if="loading" class="sub-skel">
        <div v-for="n in 7" :key="n" class="sub-skel-row" :style="{ '--d': (n * 70) + 'ms' }"></div>
      </div>
      <div v-else-if="loadError" class="sub-state sub-state-err">{{ loadError }}</div>
      <div v-else-if="!rows.length" class="sub-state">
        {{ t("Реестр субсидий пуст.") }}<template v-if="canEdit"> {{ t("Нажмите «Добавить субсидию», чтобы внести первую запись.") }}</template>
      </div>
      <div v-else-if="!filtered.length" class="sub-state">{{ t("Нет записей под текущие фильтры.") }}</div>

      <!-- Таблица -->
      <div v-else class="sub-tbl-wrap">
        <table class="sub-tbl">
          <thead>
            <tr>
              <th class="l">{{ t("Компания") }}</th>
              <th class="l">{{ t("Сектор") }}</th>
              <th class="c">{{ t("Год") }}</th>
              <th class="l">{{ t("Назначение") }}</th>
              <th class="l">{{ t("Источник") }}</th>
              <th class="l">{{ t("Вид") }}</th>
              <th class="r">{{ t("Сумма") }}</th>
              <th class="c">{{ t("Дата") }}</th>
              <th class="l">{{ t("Статус") }}</th>
              <th v-if="canEdit" class="c"></th>
            </tr>
          </thead>
          <transition-group tag="tbody" name="sub-row" appear>
            <tr v-for="(r, ri) in filtered" :key="r.id" :style="{ '--ri': ri }">
              <td class="l sub-co">
                <span class="sub-co-dot" :style="{ background: r.sector_color || '#94A3B8' }"></span>
                {{ r.company_name || '—' }}
              </td>
              <td class="l sub-muted">{{ r.sector_name || '—' }}</td>
              <td class="c">{{ r.year ?? '—' }}</td>
              <td class="l">{{ r.program || '—' }}</td>
              <td class="l sub-muted">{{ r.source || '—' }}</td>
              <td class="l sub-muted">{{ r.kind || '—' }}</td>
              <td class="r sub-amt">{{ fmtAmount(r.amount) }}</td>
              <td class="c sub-muted">{{ fmtDate(r.allocation_date) }}</td>
              <td class="l">
                <span v-if="r.status" class="sub-badge" :class="'st-' + r.status">{{ t(subsidyStatusLabel(r.status)) }}</span>
                <span v-else class="sub-muted">—</span>
              </td>
              <td v-if="canEdit" class="c sub-actions">
                <template v-if="confirmDeleteId === r.id">
                  <span class="sub-confirm">{{ t("Удалить?") }}</span>
                  <button class="sub-ic sub-ic-yes" :disabled="deleting" :title="t('Подтвердить')" @click="doDelete(r)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
                  </button>
                  <button class="sub-ic" :title="t('Отмена')" @click="confirmDeleteId = null">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
                  </button>
                </template>
                <template v-else>
                  <button class="sub-ic" :title="t('Редактировать')" @click="openEdit(r)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
                  </button>
                  <button class="sub-ic sub-ic-del" :title="t('Удалить')" @click="confirmDeleteId = r.id">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
                  </button>
                </template>
              </td>
            </tr>
          </transition-group>
          <tfoot>
            <tr>
              <td :colspan="6" class="r sub-foot-l">{{ t("Итого по фильтру") }}</td>
              <td class="r sub-foot-v">{{ totalFmt.value }}<span class="sub-foot-u"> {{ t(totalFmt.unit) }}</span></td>
              <td :colspan="canEdit ? 3 : 2"></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
.sub-head-t { font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); letter-spacing: -.01em; }
.sub-head-s { font-size: 11.5px; color: var(--t3, var(--t-muted)); margin-top: 2px; }
.sub-head-s b { color: var(--t1, #1E2A4A); font-weight: 600; font-feature-settings: "tnum"; }

.sub { display: flex; flex-direction: column; gap: 14px; }

/* ─── Сводка (стат-полоса) ─── */
.sub-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.sub-stat {
  position: relative; overflow: hidden;
  background: var(--bg2, #FAFBFC);
  border: 1px solid var(--border1, rgba(0, 0, 0, .05));
  border-radius: 11px; padding: 12px 14px 11px;
  animation: subStatIn .5s cubic-bezier(.22, .61, .36, 1) var(--d, 0ms) both;
  transition: box-shadow .2s, transform .2s;
}
.sub-stat:hover { box-shadow: 0 4px 14px rgba(15, 23, 60, .07); transform: translateY(-1px); }
.sub-stat::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, #7F77DD); transform-origin: left;
  animation: subStripe .7s cubic-bezier(.22, .61, .36, 1) var(--d, 0ms) both;
}
.sub-stat-lbl { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, var(--t-muted)); font-weight: 500; margin-bottom: 7px; }
.sub-stat-val { font-size: 23px; font-weight: 400; letter-spacing: -.02em; color: var(--t1, #1E2A4A); line-height: 1; font-feature-settings: "tnum"; display: flex; align-items: baseline; gap: 5px; min-width: 0; }
.sub-stat-txt { display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 15px; font-weight: 500; }
.sub-stat-unit { font-size: 12px; color: var(--t3, var(--t-muted)); font-weight: 500; flex-shrink: 0; }
@keyframes subStatIn { 0% { opacity: 0; transform: translateY(10px) scale(.98); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes subStripe { 0% { transform: scaleX(0); } 100% { transform: scaleX(1); } }

/* ─── Skeleton ─── */
.sub-skel { display: flex; flex-direction: column; gap: 8px; padding: 6px 0; }
.sub-skel-row {
  height: 42px; border-radius: 8px;
  background: linear-gradient(90deg, rgba(0,0,0,.04) 25%, rgba(0,0,0,.075) 37%, rgba(0,0,0,.04) 63%);
  background-size: 400% 100%;
  animation: subSkel 1.3s ease-in-out infinite, subFadeIn .4s ease var(--d, 0ms) both;
}
@keyframes subSkel { 0% { background-position: 100% 0; } 100% { background-position: 0 0; } }
@keyframes subFadeIn { from { opacity: 0; } to { opacity: 1; } }

/* ─── Анимация строк (TransitionGroup) ─── */
.sub-row-enter-active { transition: opacity .4s ease, transform .4s cubic-bezier(.22, .61, .36, 1); transition-delay: calc(var(--ri, 0) * 22ms); }
.sub-row-enter-from { opacity: 0; transform: translateY(9px); }
.sub-row-leave-active { transition: opacity .28s ease; }
.sub-row-leave-to { opacity: 0; }
.sub-row-move { transition: transform .38s cubic-bezier(.22, .61, .36, 1); }

.sub-tools { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.sub-filters { display: flex; flex-wrap: wrap; gap: 8px; flex: 1; }
.sub-sel, .sub-search {
  padding: 7px 10px; border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, .12);
  font-size: 12px; font-family: inherit; color: var(--t1, #1E2A4A);
  background: var(--bg1, #fff); outline: none; max-width: 230px;
}
.sub-sel { cursor: pointer; }
.sub-search { min-width: 220px; flex: 1; }
.sub-sel:focus, .sub-search:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .15); }
.sub-reset {
  padding: 7px 12px; border-radius: 8px; font-size: 12px; font-family: inherit;
  background: var(--bg2, #FAFBFC); border: 1px solid rgba(0, 0, 0, .1);
  color: var(--t3, var(--t-muted)); cursor: pointer; transition: all .15s;
}
.sub-reset:hover { color: var(--t1, #1E2A4A); border-color: rgba(0, 0, 0, .2); }
.sub-add {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: 8px; border: none;
  background: #7F77DD; color: #fff; font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit; transition: background .15s; white-space: nowrap;
}
.sub-add:hover { background: #6B63D4; }

/* Форма */
.sub-form {
  border: 1px solid rgba(127, 119, 221, .25);
  border-radius: 12px; padding: 16px; position: relative; overflow: hidden;
  background: var(--bg2, #FAFBFC);
}
.sub-form::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: #7F77DD; }
.sub-form-h { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--p-deep, #5B53B8); margin-bottom: 12px; }
.sub-form-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.sub-fld { display: flex; flex-direction: column; gap: 5px; }
.sub-fld-sm { grid-column: span 1; }
.sub-fld-wide { grid-column: 1 / -1; }
.sub-fld-l { font-size: 10px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: var(--t3, var(--t-muted)); }
.sub-inp {
  padding: 7px 10px; border-radius: 7px; border: 1px solid rgba(0, 0, 0, .12);
  font-size: 12.5px; font-family: inherit; color: var(--t1, #1E2A4A);
  background: var(--bg1, #fff); outline: none; width: 100%; box-sizing: border-box;
}
.sub-inp:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .15); }
.sub-ta { resize: vertical; min-height: 44px; }
.sub-form-btns { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.sub-btn-cancel, .sub-btn-save { padding: 7px 16px; font-size: 12px; font-weight: 500; border-radius: 7px; cursor: pointer; font-family: inherit; transition: all .15s; }
.sub-btn-cancel { background: var(--bg1, #fff); color: var(--t3, var(--t-muted)); border: 1px solid rgba(0, 0, 0, .1); }
.sub-btn-cancel:hover:not(:disabled) { background: #fff; color: var(--t1, #1E2A4A); }
.sub-btn-save { background: #7F77DD; color: #fff; border: none; }
.sub-btn-save:hover:not(:disabled) { background: #6B63D4; }
.sub-btn-cancel:disabled, .sub-btn-save:disabled { opacity: .6; cursor: not-allowed; }

.sub-form-fade-enter-active, .sub-form-fade-leave-active { transition: opacity .2s, transform .2s; }
.sub-form-fade-enter-from, .sub-form-fade-leave-to { opacity: 0; transform: translateY(-6px); }

/* Состояния */
.sub-state { text-align: center; padding: 40px 20px; color: var(--t3, var(--t-muted)); font-size: 13px; line-height: 1.6; }
.sub-state-err { color: #933632; }

/* Таблица */
.sub-tbl-wrap { overflow-x: auto; border: 1px solid var(--border1, rgba(0, 0, 0, .06)); border-radius: 12px; }
.sub-tbl { width: 100%; border-collapse: collapse; font-size: 12px; font-variant-numeric: tabular-nums; }
.sub-tbl thead th {
  position: sticky; top: 0; z-index: 1;
  padding: 10px 12px; font-size: 9.5px; font-weight: 600; letter-spacing: .05em;
  text-transform: uppercase; color: var(--t3, var(--t-muted));
  background: var(--bg2, #FAFBFC); border-bottom: 1.5px solid rgba(0, 0, 0, .08);
  white-space: nowrap;
}
.sub-tbl th.l, .sub-tbl td.l { text-align: left; }
.sub-tbl th.r, .sub-tbl td.r { text-align: right; }
.sub-tbl th.c, .sub-tbl td.c { text-align: center; }
.sub-tbl tbody td { padding: 9px 12px; border-bottom: 1px solid rgba(0, 0, 0, .04); color: var(--t1, #1E2A4A); vertical-align: middle; }
.sub-tbl tbody tr:hover { background: rgba(127, 119, 221, .035); }
.sub-co { font-weight: 500; white-space: nowrap; }
.sub-co-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 7px; vertical-align: middle; }
.sub-muted { color: var(--t3, #6B6A66); }
.sub-amt { font-weight: 600; white-space: nowrap; }

.sub-badge {
  display: inline-block; font-size: 10px; font-weight: 600; letter-spacing: .02em;
  padding: 2px 8px; border-radius: 999px; white-space: nowrap;
  background: rgba(0, 0, 0, .06); color: var(--t3, #5F5E5A);
}
.sub-badge.st-planned   { background: rgba(127, 119, 221, .14); color: var(--p-deep, #5B53B8); }
.sub-badge.st-allocated { background: rgba(55, 138, 221, .14); color: #2C6CA8; }
.sub-badge.st-received  { background: rgba(29, 158, 117, .14); color: #0F6E56; }
.sub-badge.st-used      { background: rgba(29, 158, 117, .20); color: #0B5A46; }
.sub-badge.st-cancelled { background: rgba(226, 75, 74, .12); color: #933632; }

.sub-actions { white-space: nowrap; display: flex; gap: 4px; align-items: center; justify-content: center; }
.sub-ic {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 6px; cursor: pointer;
  background: transparent; border: 1px solid transparent; color: var(--t3, var(--t-muted));
  transition: all .15s;
}
.sub-ic:hover { background: rgba(127, 119, 221, .1); color: var(--p-deep, #5B53B8); border-color: rgba(127, 119, 221, .25); }
.sub-ic-del:hover { background: rgba(226, 75, 74, .1); color: #C53030; border-color: rgba(226, 75, 74, .25); }
.sub-ic-yes { color: #0F6E56; }
.sub-ic-yes:hover { background: rgba(29, 158, 117, .12); color: #0F6E56; border-color: rgba(29, 158, 117, .3); }
.sub-confirm { font-size: 11px; color: #933632; font-weight: 600; margin-right: 2px; }

.sub-tbl tfoot td { padding: 11px 12px; border-top: 1.5px solid rgba(0, 0, 0, .1); font-weight: 600; }
.sub-foot-l { color: var(--t3, var(--t-muted)); text-transform: uppercase; font-size: 10px; letter-spacing: .05em; }
.sub-foot-v { color: var(--t1, #1E2A4A); font-size: 14px; font-feature-settings: "tnum"; }
.sub-foot-u { font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; }

@media (max-width: 900px) {
  .sub-form-grid { grid-template-columns: repeat(2, 1fr); }
  .sub-stats { grid-template-columns: repeat(2, 1fr); }
}
</style>
