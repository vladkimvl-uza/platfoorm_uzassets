<script setup lang="ts">
/**
 * PaPurchaseDrillModal — drill 2-го уровня по отдельной закупке.
 * v2 rewrite 2026-05-26: built on PaModalShell.
 *
 *   • Stats strip: цена SOE · median рынка · Δ сум/ед · Δ % · объём · потенциал
 *   • Banner: AI recommendation (с эталон-компанией если есть)
 *   • Banner: ⚠ если закупка is_dirty — данные подозрительные, не для аудита
 *   • Table: related closures этой компании в той же категории (max 8)
 */
import { computed, ref, watch } from "vue";
import {
  paFmtMoney,
  paFmtMoneyShort,
  paSameCat,
  procurementAnalysisApi,
  type ClosureRow,
  type ProcurementAggregate,
} from "@/api/procurement_analysis";
import { useToast } from "@/composables/useToast";
import PaModalShell from "./PaModalShell.vue";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";


const { t } = useI18n();

const props = defineProps<{
  purchase: ClosureRow;
  data: ProcurementAggregate;
  canEdit?: boolean;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "select-co", companyId: string): void;
  (e: "updated", payload: {
    id: string;
    conclusion_text: string | null;
    conclusion_status: string | null;
    conclusion_date: string | null;
    conclusion_author_name: string | null;
  }): void;
}>();

const toast = useToast();

// ─── Заключение центра экспертизы ───────────────────────────────────
const CONCLUSION_STATUSES: { key: string; label: string }[] = [
  { key: "", label: i18nKey("Не задан") },
  { key: "pending", label: i18nKey("На рассмотрении") },
  { key: "approved", label: i18nKey("Согласовано") },
  { key: "conditional", label: i18nKey("Условно согласовано") },
  { key: "rejected", label: i18nKey("Отклонено") },
];

const editingConcl = ref(false);
const conclDraft = ref("");
const conclStatusDraft = ref("");
const savingConcl = ref(false);

watch(
  () => props.purchase.id,
  () => {
    editingConcl.value = false;
    conclDraft.value = props.purchase.conclusion_text || "";
    conclStatusDraft.value = props.purchase.conclusion_status || "";
  },
  { immediate: true },
);

const conclStatusMeta = computed(() =>
  CONCLUSION_STATUSES.find(s => s.key === (props.purchase.conclusion_status || "")) || CONCLUSION_STATUSES[0],
);

function startEditConcl() {
  conclDraft.value = props.purchase.conclusion_text || "";
  conclStatusDraft.value = props.purchase.conclusion_status || "";
  editingConcl.value = true;
}
function cancelConcl() {
  editingConcl.value = false;
}

async function saveConcl() {
  if (savingConcl.value) return;
  savingConcl.value = true;
  try {
    const res = await procurementAnalysisApi.updateClosure(props.purchase.id, {
      conclusion_text: conclDraft.value.trim() || null,
      conclusion_status: conclStatusDraft.value || null,
    });
    emit("updated", {
      id: props.purchase.id,
      conclusion_text: res.conclusion_text ?? (conclDraft.value.trim() || null),
      conclusion_status: res.conclusion_status ?? (conclStatusDraft.value || null),
      conclusion_date: res.conclusion_date ?? null,
      conclusion_author_name: res.conclusion_author_name ?? null,
    });
    editingConcl.value = false;
    toast.success(t("Заключение сохранено"));
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t("Не удалось сохранить заключение") + ": " + (err?.response?.data?.detail || err?.message || t("ошибка")));
  } finally {
    savingConcl.value = false;
  }
}

function fmtDateTime(d: string | null): string {
  if (!d) return "";
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[3]}.${m[2]}.${m[1]}`;
  return d;
}

const cat = computed(() => {
  const found = props.data.categories.find(c => paSameCat(c.id, props.purchase.category_id));
  return found || { id: 0, name: "—", short: t("ед"), icon: null };
});

const related = computed<ClosureRow[]>(() =>
  props.data.purchases
    .filter(r =>
      r.company_id === props.purchase.company_id &&
      paSameCat(r.category_id, props.purchase.category_id),
    )
    .sort((a, b) => (b.contract_date || "").localeCompare(a.contract_date || ""))
    .slice(0, 12),
);

// 2026-05-26: Number-coerce — volume/unit_price приходят строками
// (Postgres numeric → JSON). `0 + "200000"` = string concat → "0200000".
const totalVol = computed(() =>
  related.value.reduce((s, r) => s + Number(r.volume), 0),
);

const devPct = computed(() => Number(props.purchase.deviation_pct ?? 0));
const devAbs = computed(() =>
  (Number(props.purchase.unit_price) - Number(props.purchase.market_avg)) * Number(props.purchase.volume),
);

const bestCo = computed<ClosureRow | null>(() => {
  let best: ClosureRow | null = null;
  let bestPrice = Infinity;
  for (const r of props.data.purchases) {
    if (r.is_dirty) continue;
    if (!paSameCat(r.category_id, props.purchase.category_id)) continue;
    if (r.unit_price < bestPrice) { bestPrice = r.unit_price; best = r; }
  }
  return best;
});

// Security (audit M-12): экранируем свободный текст из БД (company_name/supplier)
// перед вставкой в v-html — иначе stored XSS из импортированных/AI-ingest закупок.
function _escHtml(s: unknown): string {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
}
const recommendation = computed<string>(() => {
  const best = bestCo.value;
  if (best && best.company_id !== props.purchase.company_id && best.unit_price < props.purchase.unit_price) {
    const saveTotal = (props.purchase.unit_price - best.unit_price) * totalVol.value;
    const vars = {
      co: `<b>${_escHtml(best.company_name)}</b>`,
      price: `<b>${paFmtMoney(best.unit_price)}</b>`,
      sup: _escHtml(best.supplier || ""),
      save: `<b>${paFmtMoneyShort(saveTotal)} ${t("сум/год")}</b>`,
    };
    return best.supplier
      ? t("{co} закупает по {price} у поставщика «{sup}». Рассмотреть смену поставщика — потенциальная экономия {save} при сохранении объёмов.", vars)
      : t("{co} закупает по {price}. Рассмотреть смену поставщика — потенциальная экономия {save} при сохранении объёмов.", vars);
  }
  if (devPct.value < -5) {
    const dev = `<b>${t("ниже рынка на {pct}%", { pct: Math.abs(devPct.value).toFixed(1) })}</b>`;
    return t("Закупка {dev} — хороший результат. Поделиться методикой с другими компаниями портфеля.", { dev });
  }
  return t("Цена в пределах рыночной. Продолжать мониторинг.");
});

const isRecGood = computed(() => devPct.value < -5);

function fmtDate(d: string | null): string {
  if (!d) return "—";
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[3]}.${m[2]}.${m[1]}`;
  return d;
}

const accentColor = computed(() => {
  if (props.purchase.is_dirty) return "#888780";
  if (devPct.value >= 50) return "#E24B4A";
  if (devPct.value >= 10) return "#EF9F27";
  if (devPct.value < -5) return "#1D9E75";
  return "#7F77DD";
});

const headerTitle = computed(() => {
  const company = props.purchase.company_name || props.purchase.company_id;
  return `${company} · ${cat.value.name}`;
});
</script>

<template>
  <PaModalShell
    :kind="t('Закупка')"
    :title="headerTitle"
    :accent="accentColor"
    max-width="940px"
    @close="emit('close')"
  >
    <!-- ─── Stats ─── -->
    <template #stats>
      <div class="pms-stat">
        <div class="pms-stat-lbl">{{ t("Цена SOE") }}</div>
        <div class="pms-stat-val">{{ paFmtMoney(purchase.unit_price) }}<small>/{{ cat.short || t('ед') }}</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">{{ t("Median рынка") }}</div>
        <div class="pms-stat-val">{{ paFmtMoney(purchase.market_avg) }}<small>/{{ cat.short || t('ед') }}</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">{{ devAbs >= 0 ? t('Переплата / ед.') : t('Экономия / ед.') }}</div>
        <div class="pms-stat-val" :class="devAbs >= 0 ? 'neg' : 'pos'">
          {{ devAbs >= 0 ? '+' : '−' }}{{ paFmtMoney(Math.abs(purchase.unit_price - purchase.market_avg)) }}
        </div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">{{ 'Δ %' }}</div>
        <div class="pms-stat-val" :class="devPct >= 0 ? 'neg' : 'pos'">
          {{ devPct >= 0 ? '+' : '' }}{{ devPct.toFixed(1) }}<small>%</small>
        </div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">{{ t("Объём") }}</div>
        <div class="pms-stat-val">{{ purchase.volume.toLocaleString('ru-RU') }}<small>{{ cat.short || t('ед') }}</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">{{ devAbs >= 0 ? t('Переплата итого') : t('Экономия итого') }}</div>
        <div class="pms-stat-val" :class="devAbs >= 0 ? 'neg' : 'pos'">
          {{ devAbs >= 0 ? '+' : '−' }}{{ paFmtMoneyShort(Math.abs(devAbs)) }}<small>{{ t("сум") }}</small>
        </div>
      </div>
    </template>

    <!-- ─── Body ─── -->
    <div class="ppd-body">

      <!-- Dirty warning -->
      <div v-if="purchase.is_dirty" class="ppd-warn uza-side-stripe">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 9v4M12 17h.01"/>
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        </svg>
        <span><b>{{ t("Закупка помечена как dirty") }}</b> — extreme deviation, {{ t("цены могут быть искажены (разные единицы, спецификации). Используй данные с осторожностью.") }}</span>
      </div>

      <!-- AI recommendation -->
      <div class="ppd-rec" :class="{ 'ppd-rec-good': isRecGood }">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <span v-html="recommendation"></span>
      </div>

      <!-- Meta line -->
      <div class="ppd-meta">
        <span v-if="purchase.supplier"><span class="ppd-meta-l">{{ t("Поставщик") }}:</span> {{ purchase.supplier }}</span>
        <span v-if="purchase.contract_date"><span class="ppd-meta-l">{{ t("Дата") }}:</span> {{ fmtDate(purchase.contract_date) }}</span>
        <span v-if="data.year"><span class="ppd-meta-l">{{ t("Год") }}:</span> FY {{ data.year }}</span>
        <button
          v-if="bestCo && bestCo.company_id !== purchase.company_id"
          class="ppd-best-btn"
          @click="emit('select-co', bestCo!.company_id); emit('close')"
        >
          {{ t("Профиль эталона") }} ({{ bestCo!.company_name }}) →
        </button>
      </div>

      <!-- Заключение центра экспертизы (по закупке) -->
      <div class="ppd-section ppd-concl">
        <div class="ppd-section-h">
          <span class="ppd-section-t">{{ t("Заключение центра экспертизы") }}</span>
          <span
            v-if="purchase.conclusion_status"
            class="ppd-concl-badge"
            :class="'st-' + purchase.conclusion_status"
          >{{ t(conclStatusMeta.label) }}</span>
        </div>

        <div class="ppd-concl-body">
          <template v-if="!editingConcl">
            <div v-if="purchase.conclusion_text" class="ppd-concl-text">{{ purchase.conclusion_text }}</div>
            <div v-else class="ppd-concl-empty">
              {{ t("Заключение по данной закупке ещё не добавлено.") }}
            </div>
            <div class="ppd-concl-foot">
              <span v-if="purchase.conclusion_author_name || purchase.conclusion_date" class="ppd-concl-meta">
                <template v-if="purchase.conclusion_author_name">{{ purchase.conclusion_author_name }}</template><template v-if="purchase.conclusion_author_name && purchase.conclusion_date"> · </template><template v-if="purchase.conclusion_date">{{ fmtDateTime(purchase.conclusion_date) }}</template>
              </span>
              <button v-if="canEdit" class="ppd-concl-edit" @click="startEditConcl">
                {{ purchase.conclusion_text ? t('Редактировать') : t('Добавить заключение') }}
              </button>
            </div>
          </template>

          <template v-else>
            <div class="ppd-concl-srow">
              <label class="ppd-concl-slbl">{{ t("Статус") }}</label>
              <select v-model="conclStatusDraft" class="ppd-concl-sel">
                <option v-for="s in CONCLUSION_STATUSES" :key="s.key" :value="s.key">{{ t(s.label) }}</option>
              </select>
            </div>
            <textarea
              v-model="conclDraft"
              class="ppd-concl-ta"
              rows="4"
              :placeholder="t('Вывод центра экспертизы по закупке: обоснованность цены, соответствие рынку, выявленные риски, рекомендации…')"
            ></textarea>
            <div class="ppd-concl-btns">
              <button class="ppd-concl-cancel" :disabled="savingConcl" @click="cancelConcl">{{ t("Отмена") }}</button>
              <button class="ppd-concl-save" :disabled="savingConcl" @click="saveConcl">
                {{ savingConcl ? t('Сохранение…') : t('Сохранить') }}
              </button>
            </div>
          </template>
        </div>
      </div>

      <!-- Related purchases -->
      <div v-if="related.length > 1" class="ppd-section">
        <div class="ppd-section-h">
          <span class="ppd-section-t">{{ t("Закупки этой компании в категории") }}</span>
          <span class="ppd-section-s">{{ t("{n} закупок · {vol} {unit} объёма", { n: related.length, vol: totalVol.toLocaleString('ru-RU'), unit: cat.short || t('ед') }) }}</span>
        </div>
        <table class="ppd-tbl pa-stagger">
          <thead>
            <tr>
              <th class="left">{{ t("Дата") }}</th>
              <th class="left">{{ t("Поставщик") }}</th>
              <th class="right">{{ t("Объём") }}</th>
              <th class="right">{{ t("Цена") }}</th>
              <th class="right">{{ 'Δ %' }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in related" :key="r.id" :class="{ 'ppd-row-dirty': r.is_dirty, 'ppd-row-current': r.id === purchase.id }">
              <td class="left">{{ fmtDate(r.contract_date) }}<span v-if="r.id === purchase.id" class="ppd-current-tag">{{ t("текущая") }}</span></td>
              <td class="left supplier">{{ r.supplier || '—' }}</td>
              <td class="right">{{ r.volume.toLocaleString('ru-RU') }}</td>
              <td class="right">{{ paFmtMoney(r.unit_price) }}</td>
              <td class="right" :class="(r.deviation_pct ?? 0) >= 0 ? 'neg' : 'pos'">
                {{ (r.deviation_pct ?? 0) >= 0 ? '+' : '' }}{{ (r.deviation_pct ?? 0).toFixed(1) }}%
                <span v-if="r.is_dirty" class="ppd-dirty-tag" title="Dirty">⚠</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </PaModalShell>
</template>

<style scoped>
.ppd-body {
  padding: 18px 22px 22px;
  display: flex; flex-direction: column; gap: 16px;
  flex: 1; min-height: 0;
  overflow-y: auto;
}

.ppd-warn {
  display: flex; align-items: flex-start; gap: 10px;
  background: rgba(239, 159, 39, .10);
  border: 1px solid rgba(239, 159, 39, .35);
  --stripe-color: var(--amber);
  border-radius: 8px;
  padding: 12px 14px 12px 20px;
  font-size: 12px; color: var(--t1, #1E2A4A);
  line-height: 1.5;
}
.ppd-warn svg { color: #B07415; flex-shrink: 0; margin-top: 1px; }
.ppd-warn :deep(b) { font-weight: 600; color: #B07415; }

.ppd-rec {
  display: flex; align-items: flex-start; gap: 10px;
  background: rgba(127, 119, 221, .06);
  border: 1px solid rgba(127, 119, 221, .15);
  --stripe-color: #7F77DD;
  border-radius: 8px;
  padding: 12px 14px 12px 20px;
  font-size: 12px; color: var(--t1, #1E2A4A);
  line-height: 1.55;
}
.ppd-rec svg { color: #7F77DD; flex-shrink: 0; margin-top: 1px; }
.ppd-rec :deep(b) { font-weight: 600; }
.ppd-rec.ppd-rec-good {
  background: rgba(29, 158, 117, .06);
  border-color: rgba(29, 158, 117, .15);
  --stripe-color: var(--green);
}
.ppd-rec.ppd-rec-good svg { color: var(--green); }

.ppd-meta {
  display: flex; flex-wrap: wrap; align-items: center; gap: 16px;
  font-size: 11.5px; color: var(--t3, #5F5E5A);
  padding: 6px 0 2px;
}
.ppd-meta-l {
  color: var(--t3, var(--t-muted)); text-transform: uppercase;
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.06em;
  margin-right: 4px;
}
.ppd-best-btn {
  margin-left: auto;
  background: rgba(29, 158, 117, .08);
  border: 1px solid rgba(29, 158, 117, .25);
  color: #0F6E56;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 11.5px; font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: all .15s;
}
.ppd-best-btn:hover {
  background: var(--green);
  color: #fff;
  border-color: var(--green);
}

.ppd-section {
  background: var(--bg2, #FAFAFC);
  border: 1px solid rgba(0, 0, 0, .06);
  border-radius: 10px;
  overflow: hidden;
}
.ppd-section-h {
  padding: 11px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 6px;
  background: var(--bg1, #fff);
}
.ppd-section-t {
  font-size: 11px; font-weight: 600; color: var(--t1, #1E2A4A);
  text-transform: uppercase; letter-spacing: 0.06em;
}
.ppd-section-s { font-size: 11px; color: var(--t3, var(--t-muted)); }

.ppd-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.ppd-tbl thead th {
  padding: 8px 14px;
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.06em;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  background: rgba(0, 0, 0, .02);
}
.ppd-tbl thead th.left { text-align: left; }
.ppd-tbl thead th.right { text-align: right; }
.ppd-tbl tbody td {
  padding: 8px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  color: var(--t1, #1E2A4A);
  font-weight: 500;
}
.ppd-tbl tbody td.left { text-align: left; }
.ppd-tbl tbody td.right { text-align: right; }
.ppd-tbl tbody td.supplier {
  color: rgba(15, 23, 60, .65); font-style: italic;
  max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ppd-tbl tbody td.pos { color: var(--green); font-weight: 600; }
.ppd-tbl tbody td.neg { color: #C53030; font-weight: 600; }
.ppd-tbl tbody tr:last-child td { border-bottom: 0; }
/* премиум: мягкая подсветка строк связанных закупок */
.ppd-tbl tbody tr { transition: background .15s ease; }
.ppd-tbl tbody tr:not(.ppd-row-current):hover td { background: rgba(127, 119, 221, .045); }

.ppd-row-current td { background: rgba(127, 119, 221, .06); font-weight: 600; }
.ppd-row-dirty td { opacity: 0.55; }
.ppd-current-tag {
  display: inline-block;
  font-size: 9px; font-weight: 700;
  background: rgba(127, 119, 221, .18);
  color: var(--p-deep);
  padding: 1px 6px; border-radius: 3px;
  margin-left: 6px;
  text-transform: uppercase; letter-spacing: 0.05em;
}
.ppd-dirty-tag {
  font-size: 10px; color: #B07415;
  margin-left: 4px;
}

/* ─── Заключение центра экспертизы ─── */
.ppd-concl-badge {
  font-size: 10px; font-weight: 600; letter-spacing: .03em;
  padding: 2px 9px; border-radius: 999px;
  text-transform: uppercase;
  background: rgba(0, 0, 0, .06); color: var(--t3, #5F5E5A);
}
.ppd-concl-badge.st-approved    { background: rgba(29, 158, 117, .14); color: #0F6E56; }
.ppd-concl-badge.st-conditional { background: rgba(239, 159, 39, .16); color: #8A5F15; }
.ppd-concl-badge.st-rejected    { background: rgba(226, 75, 74, .14); color: #933632; }
.ppd-concl-badge.st-pending     { background: rgba(127, 119, 221, .14); color: var(--p-deep, #5B53B8); }

.ppd-concl-body { padding: 13px 14px; }
.ppd-concl-text {
  font-size: 12.5px; line-height: 1.6; color: var(--t1, #1E2A4A);
  white-space: pre-wrap; word-break: break-word;
}
.ppd-concl-empty {
  font-size: 12px; color: var(--t3, var(--t-muted)); font-style: italic;
}
.ppd-concl-foot {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-top: 10px; flex-wrap: wrap;
}
.ppd-concl-meta { font-size: 11px; color: var(--t3, var(--t-muted)); font-feature-settings: "tnum"; }
.ppd-concl-edit {
  margin-left: auto;
  background: rgba(127, 119, 221, .08);
  border: 1px solid rgba(127, 119, 221, .25);
  color: var(--p-deep, #5B53B8);
  padding: 5px 13px; border-radius: 6px;
  font-size: 11.5px; font-weight: 500; cursor: pointer;
  font-family: inherit; transition: all .15s;
}
.ppd-concl-edit:hover { background: #7F77DD; color: #fff; border-color: #7F77DD; }

.ppd-concl-srow { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.ppd-concl-slbl {
  font-size: 10px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--t3, var(--t-muted));
}
.ppd-concl-sel {
  flex: 1; max-width: 240px;
  padding: 7px 10px; border-radius: 7px;
  border: 1px solid rgba(0, 0, 0, .12);
  font-size: 12px; font-family: inherit; color: var(--t1, #1E2A4A);
  background: var(--bg1, #fff); cursor: pointer; outline: none;
}
.ppd-concl-sel:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .15); }
.ppd-concl-ta {
  width: 100%; box-sizing: border-box;
  padding: 10px 12px; border-radius: 8px;
  border: 1px solid rgba(127, 119, 221, .3);
  font-size: 12.5px; line-height: 1.55; font-family: inherit;
  color: var(--t1, #1E2A4A); resize: vertical; outline: none; min-height: 84px;
}
.ppd-concl-ta:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .15); }
.ppd-concl-btns { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; }
.ppd-concl-btns button {
  padding: 6px 16px; font-size: 11.5px; font-weight: 500;
  border-radius: 6px; cursor: pointer; font-family: inherit; transition: all .15s;
}
.ppd-concl-cancel {
  background: var(--bg1, #fff); color: var(--t3, var(--t-muted));
  border: 1px solid rgba(0, 0, 0, .1);
}
.ppd-concl-cancel:hover:not(:disabled) { background: #fafafa; color: var(--t1, #1E2A4A); }
.ppd-concl-save { background: #7F77DD; color: #fff; border: none; }
.ppd-concl-save:hover:not(:disabled) { background: #6B63D4; }
.ppd-concl-btns button:disabled { opacity: .6; cursor: not-allowed; }

/* премиум: мягкое появление баннеров рекомендации/предупреждения */
.ppd-warn { animation: ppdBannerIn 420ms cubic-bezier(.22, 1, .36, 1) both; animation-delay: 60ms; }
.ppd-rec  { animation: ppdBannerIn 420ms cubic-bezier(.22, 1, .36, 1) both; animation-delay: 110ms; }
@keyframes ppdBannerIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: none; }
}
/* премиум: hover на «эталон»-кнопке — лёгкий лифт */
.ppd-best-btn:hover { transform: translateY(-1px); }
.ppd-best-btn { transition: all .15s, transform .18s cubic-bezier(.22, 1, .36, 1); }

@media (prefers-reduced-motion: reduce) {
  .ppd-warn, .ppd-rec { animation: none !important; }
  .ppd-tbl tbody tr { transition: none; }
  .ppd-best-btn:hover { transform: none; }
}
</style>
