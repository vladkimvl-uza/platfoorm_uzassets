<script setup lang="ts">
/**
 * ESGMaturityMatrix — операционное ядро ESG Maturity Cockpit.
 * Строки = компании (по секторам), колонки = 6 измерений зрелости.
 * ISO/Отчётность/Климат/Риски редактируются inline (клик по чипу/степперу).
 * Рейтинги (D3) — клик открывает профиль (правка через единый источник AgencyRating). EMS — вычисляемый.
 */
import { computed, ref, watch } from "vue";
import { useToast } from "@/composables/useToast";
import { esgApi, type ESGMaturityHeatmap, type ESGMaturityCompany, type ESGRatingMini } from "@/api/esg";
import { ratingsApi } from "@/api/ratings";
import { isModerationQueued } from "@/api/client";
import ESGReportRatingModal from "@/components/ESG/ESGReportRatingModal.vue";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";
import { resolveCompanyDisplayName, resolveSectorDisplayName } from "@/utils/displayNames";

const { t } = useI18n();


const props = defineProps<{
  heatmap: ESGMaturityHeatmap | null;
  canEdit: boolean;
  search?: string;
}>();
const emit = defineEmits<{ (e: "saved"): void; (e: "open-company", id: string): void }>();

const toast = useToast();
const errorText = (err: any) => err?.response?.data?.detail || err?.message || t("ошибка");
const rows = ref<ESGMaturityCompany[]>([]);
const companyName = (company: ESGMaturityCompany) =>
  resolveCompanyDisplayName(
    company.company_name || company.company_code,
    company.company_id || company.company_code,
  ) || "—";
const sectorName = (company: ESGMaturityCompany) =>
  resolveSectorDisplayName(
    company.sector_name || company.sector_code,
    company.sector_code,
  ) || t("Прочее");

// Единое окно «внешней валидации» (отчётность + заверение + рейтинг) по компании.
const unifiedFor = ref<ESGMaturityCompany | null>(null);
function openUnified(c: ESGMaturityCompany) { if (props.canEdit) unifiedFor.value = c; }
watch(() => props.heatmap, (h) => { rows.value = h ? h.companies.map((c) => ({ ...c, cells: [...c.cells] })) : []; }, { immediate: true });

const filtered = computed(() => {
  const q = (props.search || "").trim().toLowerCase();
  const list = q
    ? rows.value.filter((c) => `${companyName(c)} ${c.company_name || ""} ${c.company_code}`.toLowerCase().includes(q))
    : rows.value;
  return list;
});
// группировка по секторам с сохранением порядка
const grouped = computed(() => {
  const out: { key: string; name: string; color: string; companies: ESGMaturityCompany[] }[] = [];
  const idx = new Map<string, number>();
  for (const c of filtered.value) {
    const key = c.sector_code || "—";
    let i = idx.get(key);
    if (i === undefined) {
      i = out.length;
      idx.set(key, i);
      out.push({ key, name: sectorName(c), color: c.sector_color || "#94A3B8", companies: [] });
    }
    out[i].companies.push(c);
  }
  return out;
});

// ── helpers ───────────────────────────────────────────────────────────
function cellStage(c: ESGMaturityCompany, dim: string, sub = ""): number {
  const cell = c.cells.find((x) => x.dimension === dim && (x.sub_key || "") === sub);
  if (cell) return cell.stage || 0;
  return c.dim_stage?.[dim] ?? 0;
}
function emsColor(e: number): string {
  // Мягкая пастель (единый стиль баров портфеля). Используется только для
  // заливки бара EMS (.mm-co-bar i), не для текста.
  if (e >= 70) return "#5DC093";
  if (e >= 40) return "#D9A05A";
  return "#E2807F";
}
const ISO = [
  { sub: "iso14001", label: "14001", tip: i18nKey("ISO 14001 · Экологический менеджмент") },
  { sub: "iso45001", label: "45001", tip: i18nKey("ISO 45001 · Охрана труда и пром. безопасность") },
  { sub: "iso50001", label: "50001", tip: i18nKey("ISO 50001 · Энергоменеджмент") },
];
// D2 «Подготовка ESG-отчётности» — 0..3 (заверение вынесено в отдельную колонку D2A)
const REP_LABELS = [i18nKey("нет"), i18nKey("разовый"), i18nKey("регулярный"), "IFRS SDS"];
const REP_COLORS = ["#94A3B8", "#378ADD", "#378ADD", "#7C6FF7"];
// D2A «Прохождение независимого заверения» — нет / запланировано / пройдено
const ASSUR_LABELS = [i18nKey("нет"), i18nKey("запланировано"), i18nKey("пройдено")];
const ASSUR_COLORS = ["#94A3B8", "#D9A05A", "#1D9E75"];
// Клампим отображаемую стадию отчётности: legacy-данные могли иметь D2=4
// («+ assurance»); теперь заверение — отдельное измерение, D2 ≤ 3.
function repStage(c: ESGMaturityCompany): number { return Math.min(3, dStage(c, "D2", "")); }

// Короткое имя агентства для компактной ячейки рейтинга.
function agencyAbbr(a: string): string {
  const s = (a || "").toLowerCase();
  if (s.includes("fitch")) return "Fitch";
  if (s.includes("s&p") || s.includes("standard & poor") || s.includes("sp ")) return "S&P";
  if (s.includes("cdp")) return "CDP";
  if (s.includes("msci")) return "MSCI";
  if (s.includes("moody")) return "Moody’s";
  if (s.includes("sustainalytics")) return "Sustainalytics";
  if (s.includes("iss")) return "ISS";
  return a.length > 12 ? a.slice(0, 11) + "…" : a;
}

// ── Inline-правка / добавление ESG-рейтинга прямо из матрицы ───────────
const ESG_AGENCIES = ["Sustainable Fitch", "S&P ESG", "CDP", "MSCI", "Sustainalytics", "ISS"];
const ratingEdit = ref<string | null>(null);   // id редактируемого рейтинга
const ratingDraft = ref("");
const ratingSaving = ref(false);
function rfocus(el: unknown) { const i = el as HTMLInputElement | null; if (i) { i.focus(); i.select(); } }
function isRatingEdit(r: ESGRatingMini): boolean { return !!r.id && ratingEdit.value === r.id; }
function startRatingEdit(r: ESGRatingMini) {
  if (!props.canEdit || !r.id || ratingSaving.value) return;
  addRatingFor.value = null;
  ratingDraft.value = r.score || r.rating || "";
  ratingEdit.value = r.id;
}
function cancelRatingEdit() { ratingEdit.value = null; ratingDraft.value = ""; }
async function commitRatingEdit(r: ESGRatingMini) {
  if (ratingEdit.value !== r.id) return;
  const val = ratingDraft.value.trim();
  const prev = (r.score || r.rating || "").trim();
  ratingEdit.value = null;
  if (!r.id || val === prev) return;
  ratingSaving.value = true;
  try {
    const payload = r.score ? { score: val } : { rating: val };
    await ratingsApi.update(r.id, payload as never);
    toast.success(t('Рейтинг обновлён')); emit("saved");
  } catch (e: unknown) {
    if (isModerationQueued(e)) return;
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t('Не сохранено: {value0}', { value0: errorText(err) }));
  } finally { ratingSaving.value = false; }
}

// удаление рейтинга (с подтверждением у чипа — защита от случайного)
const ratingDel = ref<string | null>(null);
function askDeleteRating(r: ESGRatingMini) {
  if (!props.canEdit || !r.id) return;
  ratingEdit.value = null;
  ratingDel.value = r.id;
}
function cancelDeleteRating() { ratingDel.value = null; }
async function confirmDeleteRating(r: ESGRatingMini) {
  if (!r.id || ratingSaving.value) return;
  ratingDel.value = null;
  ratingSaving.value = true;
  try {
    await ratingsApi.remove(r.id);
    toast.success(t('Рейтинг удалён')); emit("saved");
  } catch (e: unknown) {
    if (isModerationQueued(e)) return;
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t('Не удалено: {value0}', { value0: errorText(err) }));
  } finally { ratingSaving.value = false; }
}

const addRatingFor = ref<string | null>(null);   // company_id, куда добавляем
const addAgency = ref(ESG_AGENCIES[0]);
const addValue = ref("");
function isAddRating(c: ESGMaturityCompany): boolean { return addRatingFor.value === c.company_id; }
function startAddRating(c: ESGMaturityCompany) {
  if (!props.canEdit) return;
  ratingEdit.value = null;
  const have = new Set((c.ratings || []).map((r) => r.agency));
  addAgency.value = ESG_AGENCIES.find((a) => !have.has(a)) || ESG_AGENCIES[0];
  addValue.value = "";
  addRatingFor.value = c.company_id;
}
function cancelAddRating() { addRatingFor.value = null; addValue.value = ""; }
async function commitAddRating(c: ESGMaturityCompany) {
  if (addRatingFor.value !== c.company_id || ratingSaving.value) return;
  const val = addValue.value.trim();
  if (!val || !addAgency.value) { cancelAddRating(); return; }
  ratingSaving.value = true;
  try {
    await ratingsApi.create({ company_id: c.company_id, agency: addAgency.value, score: val });
    toast.success(t('Рейтинг добавлен')); emit("saved");
    cancelAddRating();
  } catch (e: unknown) {
    if (isModerationQueued(e)) { cancelAddRating(); return; }
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t('Не добавлено: {value0}', { value0: errorText(err) }));
  } finally { ratingSaving.value = false; }
}

// ── inline-edit с подтверждением у ячейки (защита от случайной правки) ──
const saving = ref<string | null>(null);   // ключ редактируемой ячейки
function ckey(cid: string, dim: string, sub: string) { return `${cid}:${dim}:${sub}`; }

// Ожидающее подтверждения изменение (одна ячейка за раз). Клик НЕ применяет
// значение сразу — только формирует превью; применяется по ✓.
const pending = ref<{ c: ESGMaturityCompany; dim: string; sub: string; stage: number } | null>(null);
function isPending(c: ESGMaturityCompany, dim: string, sub = ""): boolean {
  const p = pending.value;
  return !!p && p.c.company_id === c.company_id && p.dim === dim && p.sub === sub;
}
// Стадия с учётом ожидающего изменения (превью в ячейке).
function dStage(c: ESGMaturityCompany, dim: string, sub = ""): number {
  return isPending(c, dim, sub) ? pending.value!.stage : cellStage(c, dim, sub);
}
function setPending(c: ESGMaturityCompany, dim: string, sub: string, stage: number) {
  if (!props.canEdit || saving.value) return;
  pending.value = { c, dim, sub, stage };
}
function cancelPending() { pending.value = null; }
async function confirmPending() {
  const p = pending.value;
  if (!p) return;
  pending.value = null;
  await setStage(p.c, p.dim, p.sub, p.stage);
}

async function setStage(c: ESGMaturityCompany, dim: string, sub: string, stage: number) {
  if (!props.canEdit || saving.value) return;
  const key = ckey(c.company_id, dim, sub);
  const cell = c.cells.find((x) => x.dimension === dim && (x.sub_key || "") === sub);
  const prev = cell ? cell.stage : null;
  // optimistic
  if (cell) cell.stage = stage;
  else c.cells.push({ dimension: dim, sub_key: sub, stage } as never);
  saving.value = key;
  try {
    await esgApi.upsertMaturityCell({ company_id: c.company_id, year: props.heatmap!.year, dimension: dim, sub_key: sub, stage });
    toast.success(t('Сохранено')); emit("saved");
  } catch (e: unknown) {
    if (isModerationQueued(e)) return;
    if (cell) cell.stage = prev ?? 0;
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t('Не сохранено: {value0}', { value0: errorText(err) }));
  } finally { saving.value = null; }
}
// ISO chip: клик циклит превью 0→1→2→0 (применяется по ✓)
function cycleIso(c: ESGMaturityCompany, sub: string) {
  const s = dStage(c, "D1", sub);
  setPending(c, "D1", sub, s >= 2 ? 0 : s + 1);
}
// степпер: клик по сегменту i → превью стадии i+1 (повторный клик по вершине → −1)
function clickStep(c: ESGMaturityCompany, dim: string, i: number) {
  const cur = dStage(c, dim, "");
  setPending(c, dim, "", cur === i + 1 ? i : i + 1);
}
function cycleRep(c: ESGMaturityCompany) {
  // клик по пилюле циклит статусы 0..3 (нет→разовый→регулярный→IFRS SDS),
  // затем «не требуется», затем обратно к статусу
  if (dStage(c, "nr", "D2") >= 1) { setPending(c, "nr", "D2", 0); return; }   // не требуется → вернуть статус
  const s = repStage(c);
  if (s >= 3) { setPending(c, "nr", "D2", 1); return; }                       // после «IFRS SDS» → не требуется
  setPending(c, "D2", "", s + 1);
}
// D2A «Прохождение независимого заверения»: клик циклит нет→запланировано→пройдено→нет
function cycleAssur(c: ESGMaturityCompany) {
  if (dStage(c, "nr", "D2A") >= 1) { setPending(c, "nr", "D2A", 0); return; }
  const s = dStage(c, "D2A", "");
  setPending(c, "D2A", "", s >= 2 ? 0 : s + 1);
}

// ── «Не нуждается» (исключение компании из метрик/статистики) ───────────
// Хранится служебной ячейкой meta/not_needed (stage 1 = не нуждается).
function isNotNeeded(c: ESGMaturityCompany): boolean {
  return dStage(c, "meta", "not_needed") >= 1;   // учитывает pending-превью
}
function toggleNotNeeded(c: ESGMaturityCompany) {
  if (!props.canEdit || saving.value) return;
  const cur = cellStage(c, "meta", "not_needed") >= 1;   // текущее (без pending)
  setPending(c, "meta", "not_needed", cur ? 0 : 1);
}

// ── «Не требуется» по конкретному измерению (исключение из статистики/EMS) ──
// Хранится служебной ячейкой nr/<dim> (stage 1 = не требуется).
function isDimNr(c: ESGMaturityCompany, dim: string): boolean {
  return dStage(c, "nr", dim) >= 1;   // учитывает pending-превью
}
function toggleDimNr(c: ESGMaturityCompany, dim: string) {
  if (!props.canEdit || saving.value) return;
  const cur = cellStage(c, "nr", dim) >= 1;
  setPending(c, "nr", dim, cur ? 0 : 1);
}

// ── Ссылка на отчёт в колонке «Отчётность» (evidence_url ячейки D2) ─────
function cellEvidence(c: ESGMaturityCompany, dim: string, sub = ""): string | null {
  const cell = c.cells.find((x) => x.dimension === dim && (x.sub_key || "") === sub);
  return cell?.evidence_url || null;
}
const linkEdit = ref<string | null>(null);   // company_id строки с открытым input
const linkDraft = ref("");
function isLinkEdit(c: ESGMaturityCompany): boolean { return linkEdit.value === c.company_id; }
function focusEl(el: unknown) { const i = el as HTMLInputElement | null; if (i) { i.focus(); i.select(); } }
function startLinkEdit(c: ESGMaturityCompany) {
  if (!props.canEdit || saving.value) return;
  linkDraft.value = cellEvidence(c, "D2") || "";
  linkEdit.value = c.company_id;
}
function cancelLink() { linkEdit.value = null; linkDraft.value = ""; }
async function commitLink(c: ESGMaturityCompany) {
  if (linkEdit.value !== c.company_id) return;
  const url = linkDraft.value.trim();
  const prev = cellEvidence(c, "D2") || "";
  linkEdit.value = null;
  if (url === prev) return;
  const cell = c.cells.find((x) => x.dimension === "D2" && (x.sub_key || "") === "");
  const prevUrl = cell ? (cell.evidence_url ?? null) : null;
  if (cell) cell.evidence_url = url || null;        // optimistic
  else c.cells.push({ dimension: "D2", sub_key: "", stage: 0, evidence_url: url || null } as never);
  saving.value = ckey(c.company_id, "D2", "url");
  try {
    await esgApi.upsertMaturityCell({ company_id: c.company_id, year: props.heatmap!.year, dimension: "D2", sub_key: "", evidence_url: url });
    toast.success(t('Ссылка сохранена')); emit("saved");
  } catch (e: unknown) {
    if (isModerationQueued(e)) return;
    if (cell) cell.evidence_url = prevUrl;
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t('Не сохранено: {value0}', { value0: errorText(err) }));
  } finally { saving.value = null; }
}
</script>

<template>
  <div class="mm-wrap">
    <table class="mm">
      <thead>
        <tr>
          <th class="mm-h-co">{{ t('Компания') }}</th>
          <th class="mm-h-grp" colspan="3">{{ t('Внедрение систем менеджмента ИСО') }}</th>
          <th class="mm-h">{{ t('Подготовка ESG-отчётности') }}</th>
          <th class="mm-h">{{ t('Прохождение независимого заверения') }}</th>
          <th class="mm-h">{{ t('Получение ESG-рейтинга') }}</th>
          <th class="mm-h">{{ t('Разработка климатической стратегии') }}</th>
          <th class="mm-h">{{ t('Внедрение ESG-рисков') }}</th>
        </tr>
        <tr class="mm-subh">
          <th class="mm-h-co"></th>
          <th v-for="x in ISO" :key="x.sub" :title="t(x.tip)">{{ t(x.label) }}</th>
          <th>{{ t('разовый · регул. · IFRS SDS') }}</th>
          <th>{{ t('независимая верификация') }}</th>
          <th></th>
          <th :title="t('Scope 1–2 → риски → план декарбонизации → реализация')">{{ t('●●●● 4 этапа') }}</th>
          <th :title="t('Double-materiality → кол. оценка → интеграция в ERM')">{{ t('●●● 3 этапа') }}</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="g in grouped" :key="g.key">
          <tr class="mm-sec"><td :colspan="9"><span class="mm-sec-dot" :style="{ background: g.color }"></span>{{ g.name }} · {{ g.companies.length }}</td></tr>
          <tr v-for="c in g.companies" :key="c.company_id" class="mm-row" :class="{ 'mm-row-nn': isNotNeeded(c) }">
            <td class="mm-co" @click="emit('open-company', c.company_id)">
              <span class="mm-co-dot" :style="{ background: c.sector_color || '#94A3B8' }"></span>
              <span class="mm-co-name" :title="companyName(c)">{{ companyName(c) }}</span>
              <span v-if="!isNotNeeded(c)" class="mm-co-bar"><i :style="{ width: c.ems + '%', backgroundColor: emsColor(c.ems) }"></i></span>
              <span v-else class="mm-nn-badge">{{ t('базовые ESG-практики') }}</span>
              <button v-if="canEdit && !isNotNeeded(c)" type="button" class="mm-uni-btn"
                      @click.stop="openUnified(c)"
                      :title="t('Единое окно: отчётность, заверение и рейтинги')">✎</button>
              <button v-if="canEdit" type="button" class="mm-nn-toggle" :class="{ on: isNotNeeded(c) }"
                      @click.stop="toggleNotNeeded(c)"
                      :title="isNotNeeded(c) ? t('Вернуть компанию в метрики') : t('Базовые ESG-практики — реализация проекта не требуется, исключить из метрик')">⊘</button>
              <span v-if="isPending(c,'meta','not_needed')" class="mm-confirm mm-confirm-inline" @click.stop>
                <button type="button" class="mm-ok" :title="t('Применить')" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" :title="t('Отмена')" @click.stop="cancelPending">✕</button>
              </span>
            </td>

            <!-- «Не нуждается» → строка свёрнута, ячейки измерений не показываем -->
            <td v-if="isNotNeeded(c)" class="mm-nn-cell" colspan="8">
              {{ t('реализация ESG-проекта не требуется · исключена из метрик и статистики') }}
            </td>

            <template v-else>
            <!-- ISO: 3 ячейки, либо свёрнутая «не требуется» на всю группу (colspan=3) -->
            <td v-if="isDimNr(c,'D1')" class="mm-c mm-cedit" colspan="3">
              <span class="mm-nr">{{ t('не требуется') }}</span>
              <button v-if="canEdit" type="button" class="mm-nr-tg on"
                      @click.stop="toggleDimNr(c,'D1')" :title="t('Вернуть ISO в статистику')">{{ t('н/т') }}</button>
              <div v-if="isPending(c,'nr','D1')" class="mm-confirm">
                <button type="button" class="mm-ok" :title="t('Применить')" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" :title="t('Отмена')" @click.stop="cancelPending">✕</button>
              </div>
            </td>
            <template v-else>
            <td v-for="(x, xi) in ISO" :key="x.sub" class="mm-c mm-cedit">
              <button type="button" class="mm-iso" :class="['s'+dStage(c,'D1',x.sub), { ed: canEdit, pend: isPending(c,'D1',x.sub) }]"
                      :disabled="!canEdit" :title="t(x.tip)" @click="cycleIso(c, x.sub)">
                {{ dStage(c,'D1',x.sub) >= 2 ? '✓' : dStage(c,'D1',x.sub) === 1 ? '◐' : '—' }}
              </button>
              <button v-if="canEdit && xi === ISO.length - 1" type="button" class="mm-nr-tg"
                      @click.stop="toggleDimNr(c,'D1')" :title="t('Не требуется — исключить ISO из статистики')">{{ t('н/т') }}</button>
              <div v-if="isPending(c,'D1',x.sub) || (xi === ISO.length - 1 && isPending(c,'nr','D1'))" class="mm-confirm">
                <button type="button" class="mm-ok" :title="t('Применить')" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" :title="t('Отмена')" @click.stop="cancelPending">✕</button>
              </div>
            </td>
            </template>
            <!-- Отчётность + inline-ссылка на отчёт -->
            <td class="mm-c mm-cedit mm-rep-c">
              <div class="mm-rep-row">
                <button type="button" class="mm-pill" :class="{ ed: canEdit, pend: isPending(c,'D2','') || isPending(c,'nr','D2'), nr: isDimNr(c,'D2') }"
                        :style="isDimNr(c,'D2') ? {} : { color: REP_COLORS[repStage(c)], background: REP_COLORS[repStage(c)] + '1E' }"
                        :disabled="!canEdit"
                        :title="isDimNr(c,'D2') ? t('Подготовка отчётности: не требуется · клик → вернуть статус') : t('Подготовка ESG-отчётности: {value0} · клик циклит, после «IFRS SDS» → не требуется', { value0: t(REP_LABELS[repStage(c)]) })"
                        @click="cycleRep(c)">
                  {{ isDimNr(c,'D2') ? t('не требуется') : t(REP_LABELS[repStage(c)]) }}
                </button>
                <template v-if="!isDimNr(c,'D2')">
                  <a v-if="cellEvidence(c,'D2') && !isLinkEdit(c)" class="mm-rchip-lnk" :href="cellEvidence(c,'D2') || undefined"
                     target="_blank" rel="noopener" :title="t('Открыть отчёт')" @click.stop>↗</a>
                  <button v-if="canEdit && !isLinkEdit(c)" type="button" class="mm-rep-lnkbtn"
                          @click.stop="startLinkEdit(c)"
                          :title="cellEvidence(c,'D2') ? t('Изменить ссылку на отчёт') : t('Добавить ссылку на отчёт')">
                    {{ cellEvidence(c,'D2') ? '✎' : '+' }}
                  </button>
                </template>
              </div>
              <input v-if="isLinkEdit(c) && !isDimNr(c,'D2')" :ref="focusEl" v-model="linkDraft" type="url" class="mm-rep-inp"
                     :placeholder="t('https://… ссылка на отчёт')" @click.stop
                     @keydown.enter.prevent="commitLink(c)" @keydown.esc.stop.prevent="cancelLink" @blur="commitLink(c)" />
              <div v-if="isPending(c,'D2','') || isPending(c,'nr','D2')" class="mm-confirm">
                <button type="button" class="mm-ok" :title="t('Применить')" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" :title="t('Отмена')" @click.stop="cancelPending">✕</button>
              </div>
            </td>
            <!-- Прохождение независимого заверения (D2A): нет / запланировано / пройдено -->
            <td class="mm-c mm-cedit">
              <button type="button" class="mm-pill"
                      :class="{ ed: canEdit, pend: isPending(c,'D2A','') || isPending(c,'nr','D2A'), nr: isDimNr(c,'D2A') }"
                      :style="isDimNr(c,'D2A') ? {} : { color: ASSUR_COLORS[dStage(c,'D2A','')], background: ASSUR_COLORS[dStage(c,'D2A','')] + '1E' }"
                      :disabled="!canEdit"
                      :title="isDimNr(c,'D2A') ? t('Независимое заверение: не требуется · клик → вернуть статус') : t('Прохождение независимого заверения: {value0} · клик циклит нет → запланировано → пройдено', { value0: t(ASSUR_LABELS[dStage(c,'D2A','')]) })"
                      @click="cycleAssur(c)">
                {{ isDimNr(c,'D2A') ? t('не требуется') : t(ASSUR_LABELS[dStage(c,'D2A','')]) }}
              </button>
              <button v-if="canEdit" type="button" class="mm-nr-tg" :class="{ on: isDimNr(c,'D2A') }"
                      @click.stop="toggleDimNr(c,'D2A')" :title="isDimNr(c,'D2A') ? t('Вернуть заверение в статистику') : t('Не требуется — исключить заверение из статистики')">{{ t('н/т') }}</button>
              <div v-if="isPending(c,'D2A','') || isPending(c,'nr','D2A')" class="mm-confirm">
                <button type="button" class="mm-ok" :title="t('Применить')" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" :title="t('Отмена')" @click.stop="cancelPending">✕</button>
              </div>
            </td>
            <!-- Рейтинг → значение (inline-правка) + агентство + ссылка + динамика «старый → новый» -->
            <td class="mm-c mm-rate-c mm-cedit">
              <span v-if="isDimNr(c,'D3')" class="mm-nr">{{ t('не требуется') }}</span>
              <div v-else class="mm-rates">
                <span v-for="(r, i) in c.ratings" :key="r.id || i" class="mm-rchip">
                  <span v-if="r.prev" class="mm-rprev" :title="t('было: {value0}', { value0: r.prev })">{{ r.prev }}<span class="mm-rarrow">→</span></span>
                  <input v-if="isRatingEdit(r)" :ref="rfocus" v-model="ratingDraft" type="text" class="mm-rinp" @click.stop
                         @keydown.enter.prevent="commitRatingEdit(r)" @keydown.esc.stop.prevent="cancelRatingEdit" @blur="commitRatingEdit(r)" />
                  <button v-else type="button" class="mm-rchip-v mm-rchip-vbtn" :class="{ ed: canEdit }" :disabled="!canEdit"
                          @click.stop="startRatingEdit(r)" :title="t('Изменить значение рейтинга')">{{ r.score || r.rating || '—' }}</button>
                  <span class="mm-rchip-ag">{{ agencyAbbr(r.agency) }}</span>
                  <a v-if="r.report_url" class="mm-rchip-lnk" :href="r.report_url" target="_blank"
                     rel="noopener" :title="t('Открыть отчёт агентства')" @click.stop>↗</a>
                  <template v-if="canEdit && r.id">
                    <span v-if="ratingDel === r.id" class="mm-rdel-cfm">
                      <button type="button" class="mm-ok" :title="t('Удалить рейтинг')" @click.stop="confirmDeleteRating(r)">✓</button>
                      <button type="button" class="mm-no" :title="t('Отмена')" @click.stop="cancelDeleteRating">✕</button>
                    </span>
                    <button v-else type="button" class="mm-rdel" :title="t('Удалить рейтинг')" @click.stop="askDeleteRating(r)">✕</button>
                  </template>
                </span>
                <span v-if="!(c.ratings && c.ratings.length) && !canEdit" class="mm-rate none">{{ t('нет рейтинга') }}</span>
                <div v-if="isAddRating(c)" class="mm-radd-form" @click.stop>
                  <select v-model="addAgency" class="mm-radd-ag">
                    <option v-for="a in ESG_AGENCIES" :key="a" :value="a">{{ agencyAbbr(a) }}</option>
                  </select>
                  <input :ref="rfocus" v-model="addValue" type="text" class="mm-rinp" :placeholder="t('знач.')"
                         @keydown.enter.prevent="commitAddRating(c)" @keydown.esc.stop.prevent="cancelAddRating" />
                  <button type="button" class="mm-ok" :title="t('Добавить')" @click.stop="commitAddRating(c)">✓</button>
                  <button type="button" class="mm-no" :title="t('Отмена')" @click.stop="cancelAddRating">✕</button>
                </div>
                <button v-else-if="canEdit" type="button" class="mm-radd" @click.stop="startAddRating(c)">{{ t('+ рейтинг') }}</button>
              </div>
              <button v-if="canEdit && !isAddRating(c)" type="button" class="mm-nr-tg" :class="{ on: isDimNr(c,'D3') }"
                      @click.stop="toggleDimNr(c,'D3')" :title="isDimNr(c,'D3') ? t('Вернуть рейтинг в статистику') : t('Не требуется — исключить рейтинг из статистики')">{{ t('н/т') }}</button>
              <div v-if="isPending(c,'nr','D3')" class="mm-confirm">
                <button type="button" class="mm-ok" :title="t('Применить')" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" :title="t('Отмена')" @click.stop="cancelPending">✕</button>
              </div>
            </td>
            <!-- Климатическая стратегия stepper 4 -->
            <td class="mm-c mm-cedit">
              <span v-if="isDimNr(c,'D4')" class="mm-nr">{{ t('не требуется') }}</span>
              <span v-else class="mm-step">
                <i v-for="i in 4" :key="i" class="mm-dot clm" :class="{ on: dStage(c,'D4','') >= i, ed: canEdit, pend: isPending(c,'D4','') }" @click="clickStep(c,'D4',i-1)"></i>
              </span>
              <button v-if="canEdit" type="button" class="mm-nr-tg" :class="{ on: isDimNr(c,'D4') }"
                      @click.stop="toggleDimNr(c,'D4')" :title="isDimNr(c,'D4') ? t('Вернуть в статистику') : t('Не требуется — исключить из статистики')">{{ t('н/т') }}</button>
              <div v-if="isPending(c,'D4','') || isPending(c,'nr','D4')" class="mm-confirm">
                <button type="button" class="mm-ok" :title="t('Применить')" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" :title="t('Отмена')" @click.stop="cancelPending">✕</button>
              </div>
            </td>
            <!-- ESG Риски stepper 3 -->
            <td class="mm-c mm-cedit">
              <span v-if="isDimNr(c,'D5')" class="mm-nr">{{ t('не требуется') }}</span>
              <span v-else class="mm-step">
                <i v-for="i in 3" :key="i" class="mm-dot rsk" :class="{ on: dStage(c,'D5','') >= i, ed: canEdit, pend: isPending(c,'D5','') }" @click="clickStep(c,'D5',i-1)"></i>
              </span>
              <button v-if="canEdit" type="button" class="mm-nr-tg" :class="{ on: isDimNr(c,'D5') }"
                      @click.stop="toggleDimNr(c,'D5')" :title="isDimNr(c,'D5') ? t('Вернуть в статистику') : t('Не требуется — исключить из статистики')">{{ t('н/т') }}</button>
              <div v-if="isPending(c,'D5','') || isPending(c,'nr','D5')" class="mm-confirm">
                <button type="button" class="mm-ok" :title="t('Применить')" @click.stop="confirmPending">✓</button>
                <button type="button" class="mm-no" :title="t('Отмена')" @click.stop="cancelPending">✕</button>
              </div>
            </td>
            </template>
          </tr>
        </template>
        <tr v-if="!filtered.length"><td :colspan="9" class="mm-empty">{{ t('Нет компаний') }}</td></tr>
      </tbody>
    </table>
  </div>

  <ESGReportRatingModal
    :open="!!unifiedFor"
    :company="unifiedFor"
    :year="heatmap?.year ?? 0"
    :can-edit="canEdit"
    @close="unifiedFor = null"
    @saved="emit('saved')"
  />
</template>

<style scoped>
.mm-wrap { overflow: auto; border: 1px solid rgba(0,0,0,.06); border-radius: 12px; background: var(--bg1, #fff); max-height: calc(100dvh - 320px); }
.mm { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 12px; }
.mm thead th { position: sticky; top: 0; z-index: 4; background: #F6F5FB; color: var(--p-deep, #534AB7); font-weight: 700; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; padding: 7px 8px; text-align: center; border-bottom: 1px solid #E7E5F2; }
/* Двухрядная шапка: первая строка top:0, вторая (под-заголовки) ниже на высоту первой.
   Селектор специфичнее `.mm thead th`, иначе top перебивался на 0 и строки слипались. */
.mm thead tr.mm-subh th { top: 29px; z-index: 3; font-size: 8.5px; font-weight: 600; color: #8a90a8; text-transform: none; letter-spacing: 0; padding: 3px 6px; }
.mm-h-grp { background: #EFEEF9 !important; }
.mm-h-co, td.mm-co { position: sticky; left: 0; z-index: 2; background: var(--bg1, #fff); text-align: left; min-width: 210px; max-width: 240px; }
.mm thead .mm-h-co { z-index: 4; background: #F6F5FB; }
.mm-h-ems { min-width: 46px; }

.mm-sec td { background: linear-gradient(90deg, rgba(127,119,221,.06), transparent); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--p-deep, #5B53B8); padding: 5px 10px; position: sticky; left: 0; }
.mm-sec-dot { display: inline-block; width: 7px; height: 7px; border-radius: 2px; margin-right: 7px; vertical-align: middle; }

.mm-row { transition: background .12s; }
.mm-row:hover td { background: rgba(127,119,221,.045); }
.mm-row:hover td.mm-co { background: #FBFAFF; }
.mm td { border-bottom: 1px solid #F1F0F7; padding: 5px 6px; vertical-align: middle; text-align: center; }
.mm-co { display: flex; align-items: center; gap: 7px; padding: 6px 10px !important; cursor: pointer; }
.mm-co-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.mm-co-name { flex: 1; min-width: 0; text-align: left; font-size: 11.5px; font-weight: 500; color: var(--t1, #1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mm-co:hover .mm-co-name { color: var(--p-deep, #5B53B8); }
.mm-co-bar { width: 38px; height: 4px; border-radius: 3px; background: #ECEAF5; overflow: hidden; flex-shrink: 0; }
.mm-co-bar i { display: block; height: 100%; border-radius: 3px; background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.30) 0%, rgba(255, 255, 255, 0) 55%); transition: width .5s var(--ease-standard, ease); }

.mm-iso { width: 30px; height: 24px; border-radius: 6px; border: none; font-size: 12px; font-weight: 700; font-family: inherit; cursor: default; transition: transform .12s, box-shadow .12s; }
.mm-iso.s2 { background: #DCFCE7; color: #1D9E75; }
.mm-iso.s1 { background: #FEF9C3; color: #D97706; }
.mm-iso.s0 { background: #F1F5F9; color: #94A3B8; }
.mm-iso.ed { cursor: pointer; }
.mm-iso.ed:hover { transform: scale(1.08); box-shadow: 0 0 0 1px rgba(0,0,0,.08); }

.mm-pill { padding: 3px 9px; border-radius: 6px; border: none; font-size: 10.5px; font-weight: 600; font-family: inherit; cursor: default; white-space: nowrap; transition: transform .12s; }
.mm-pill.ed { cursor: pointer; }
.mm-pill.ed:hover { transform: scale(1.04); }
.mm-pill.nr { background: #F1F2F6 !important; color: #8A90A8 !important; font-style: italic; }

.mm-rate { font-size: 10.5px; font-weight: 600; color: var(--t2, #475569); }
.mm-rate.none { color: #C4C8D4; }
/* Ячейка рейтинга: сами значения + агентство + ссылка (клик по ячейке → профиль) */
.mm-rate-c { min-width: 96px; }
.mm-rates { display: inline-flex; flex-direction: column; gap: 3px; align-items: center; cursor: pointer; padding: 2px 6px; border-radius: 7px; transition: background .15s ease; }
.mm-rates:hover { background: color-mix(in srgb, var(--brand, #6C5CE7) 7%, #fff); }
.mm-rchip { display: inline-flex; align-items: baseline; gap: 4px; line-height: 1.15; white-space: nowrap; }
.mm-rchip-v { font-size: 11px; font-weight: 700; color: var(--p-deep, #534AB7); font-feature-settings: 'tnum'; }
.mm-rchip-ag { font-size: 9px; font-weight: 600; color: var(--t3, #94A3B8); text-transform: uppercase; letter-spacing: .02em; }
.mm-rchip-lnk { font-size: 10px; font-weight: 700; color: var(--brand, #6C5CE7); text-decoration: none; padding: 0 1px; border-radius: 4px; }
.mm-rchip-lnk:hover { background: color-mix(in srgb, var(--brand, #6C5CE7) 16%, #fff); }
/* inline-правка значения рейтинга + динамика «старый → новый» + добавление */
.mm-rchip-vbtn { border: none; background: transparent; font-family: inherit; padding: 0 1px; cursor: default; line-height: 1.1; }
.mm-rchip-vbtn.ed { cursor: text; border-radius: 4px; }
.mm-rchip-vbtn.ed:hover { background: color-mix(in srgb, var(--brand, #6C5CE7) 12%, #fff); }
.mm-rprev { display: inline-flex; align-items: baseline; gap: 1px; font-size: 9.5px; font-weight: 600; color: #B6BBC8; text-decoration: line-through; text-decoration-color: #D6DAE4; }
.mm-rarrow { text-decoration: none; color: #C4C8D4; font-weight: 700; margin: 0 1px; }
.mm-rinp { width: 44px; box-sizing: border-box; font-size: 11px; font-weight: 700; font-family: inherit; color: var(--p-deep, #534AB7); padding: 1px 4px; border: 1px solid var(--brand, #6C5CE7); border-radius: 5px; outline: none; background: #fff; box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand, #6C5CE7) 12%, transparent); text-align: center; }
.mm-radd { font-size: 9.5px; font-weight: 600; color: var(--t3, #94A3B8); background: transparent; border: 1px dashed var(--border-strong, #D9D7E8); border-radius: 6px; padding: 1px 7px; cursor: pointer; transition: all .14s ease; }
.mm-radd:hover { color: var(--brand, #6C5CE7); border-color: var(--brand, #6C5CE7); }
.mm-radd-form { display: inline-flex; align-items: center; gap: 3px; }
.mm-radd-ag { font-size: 9.5px; font-family: inherit; padding: 1px 3px; border: 1px solid var(--border, #ECEAF5); border-radius: 5px; outline: none; max-width: 70px; }
.mm-rdel { font-size: 9px; font-weight: 700; color: #C4C8D4; background: transparent; border: none; cursor: pointer; padding: 0 2px; line-height: 1; border-radius: 4px; transition: all .12s ease; }
.mm-rdel:hover { color: #E24B4A; background: #FEF2F2; }
.mm-rdel-cfm { display: inline-flex; gap: 2px; }
.mm-rdel-cfm .mm-ok, .mm-rdel-cfm .mm-no { width: 16px; height: 16px; font-size: 10px; }
.mm-rdel-cfm .mm-ok { background: #FEE2E2; color: #E24B4A; }
.mm-rdel-cfm .mm-ok:hover { background: #E24B4A; color: #fff; }

/* Единое окно «внешней валидации» — кнопка ✎ рядом с именем компании */
.mm-uni-btn { flex-shrink: 0; width: 19px; height: 19px; border-radius: 6px; border: 1px solid var(--border, #ECEAF5); background: #fff; color: #B6BBC8; font-size: 11px; line-height: 1; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; transition: all .14s ease; }
.mm-uni-btn:hover { color: var(--brand, #6C5CE7); border-color: color-mix(in srgb, var(--brand, #6C5CE7) 40%, #fff); background: color-mix(in srgb, var(--brand, #6C5CE7) 6%, #fff); }

/* «Не нуждается» — тумблер + бейдж + свёрнутая строка */
.mm-nn-toggle { flex-shrink: 0; width: 19px; height: 19px; border-radius: 6px; border: 1px solid var(--border, #ECEAF5); background: #fff; color: #B6BBC8; font-size: 12px; line-height: 1; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; transition: all .14s ease; }
.mm-nn-toggle:hover { color: #E24B4A; border-color: #F3C3C2; background: #FEF3F2; }
.mm-nn-toggle.on { color: #fff; background: #94A3B8; border-color: #94A3B8; }
.mm-nn-badge { flex-shrink: 0; font-size: 10px; font-weight: 500; color: #8A90A8; background: #F1F2F6; border-radius: 5px; padding: 1px 8px; white-space: nowrap; }
.mm-row-nn td { background: #FBFBFC; }
.mm-row-nn:hover td { background: #F6F6F9; }
.mm-row-nn .mm-co-name { color: #9AA0B2; }
.mm-nn-cell { text-align: left !important; padding-left: 14px !important; font-size: 10.5px; font-style: italic; color: #A8AEC0; }
.mm-confirm-inline { margin-top: 0 !important; margin-left: 4px; }

/* Ссылка на отчёт в колонке «Отчётность» */
.mm-rep-row { display: inline-flex; align-items: center; gap: 5px; }
.mm-rep-lnkbtn { flex-shrink: 0; font-size: 10px; font-weight: 700; color: var(--t3, #94A3B8); background: transparent; border: 1px solid var(--border, #ECEAF5); border-radius: 5px; padding: 0 5px; height: 17px; line-height: 1; cursor: pointer; transition: all .14s ease; }
.mm-rep-lnkbtn:hover { color: var(--brand, #6C5CE7); border-color: color-mix(in srgb, var(--brand, #6C5CE7) 40%, #fff); background: color-mix(in srgb, var(--brand, #6C5CE7) 6%, #fff); }
.mm-rep-inp { margin-top: 4px; width: 150px; max-width: 100%; box-sizing: border-box; font-size: 10.5px; font-family: inherit; color: var(--t1, #1E2A4A); padding: 3px 7px; border: 1px solid var(--brand, #6C5CE7); border-radius: 6px; outline: none; background: #fff; box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand, #6C5CE7) 12%, transparent); }

/* «Не требуется» по измерению — бейдж + тумблер */
.mm-nr { font-size: 9.5px; font-weight: 600; color: #A8AEC0; font-style: italic; white-space: nowrap; }
.mm-nr-tg { display: inline-block; margin-top: 4px; font-size: 8.5px; font-weight: 700; color: #B6BBC8; background: transparent; border: 1px solid var(--border, #ECEAF5); border-radius: 5px; padding: 0 5px; height: 15px; line-height: 13px; cursor: pointer; transition: all .14s ease; }
.mm-nr-tg:hover { color: #E24B4A; border-color: #F3C3C2; background: #FEF3F2; }
.mm-nr-tg.on { color: #fff; background: #94A3B8; border-color: #94A3B8; }

.mm-step { display: inline-flex; gap: 4px; align-items: center; }
.mm-dot { width: 11px; height: 11px; border-radius: 50%; background: #E6E4F0; transition: transform .12s, background .15s; }
.mm-dot.clm.on { background: #1D9E75; }
.mm-dot.rsk.on { background: #6C5CE7; }
.mm-dot.ed { cursor: pointer; }
.mm-dot.ed:hover { transform: scale(1.25); }

/* Inline-подтверждение правки (защита от случайной правки) */
.mm-cedit { position: relative; }
.mm-iso.pend, .mm-pill.pend { outline: 2px dashed #7C6FF7; outline-offset: 1px; }
.mm-dot.pend { box-shadow: 0 0 0 2px rgba(124, 111, 247, .45); }
.mm-confirm { display: flex; justify-content: center; gap: 4px; margin-top: 5px; animation: mmConfIn .14s ease; }
@keyframes mmConfIn { from { opacity: 0; transform: translateY(-3px); } to { opacity: 1; transform: translateY(0); } }
.mm-ok, .mm-no { width: 22px; height: 20px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; font-weight: 700; line-height: 1; display: inline-flex; align-items: center; justify-content: center; transition: background .12s, color .12s; }
.mm-ok { background: #DCFCE7; color: #1D9E75; }
.mm-ok:hover { background: #16A34A; color: #fff; }
.mm-no { background: #F1F5F9; color: #94A3B8; }
.mm-no:hover { background: #E2E8F0; color: #475569; }

.mm-ems span { font-size: 13px; font-weight: 700; font-feature-settings: 'tnum'; }
.mm-empty { padding: 28px; text-align: center; color: var(--t3, #94A3B8); font-size: 12px; }

/* ─── Адаптив: от <14" ноутбуков до 60–75" стен-дисплеев ─── */
/* Компактные/малые экраны — матрица скроллится по горизонтали, sticky сохраняется */
@media (max-width: 1366px) {
  .mm-h-co, td.mm-co { min-width: 180px; max-width: 200px; }
}
@media (max-width: 1024px) {
  .mm { font-size: 11px; }
  .mm-h-co, td.mm-co { min-width: 160px; max-width: 180px; }
  .mm-iso { width: 26px; height: 22px; }
  .mm-wrap { max-height: calc(100dvh - 280px); }
}
/* Большие дисплеи (4K, 60–75") — крупнее, читаемо с дистанции */
@media (min-width: 2200px) {
  .mm { font-size: 15px; }
  .mm thead th { font-size: 12px; padding: 10px 12px; }
  .mm-subh th { font-size: 11px; top: 40px; }
  .mm-h-co, td.mm-co { min-width: 300px; max-width: 360px; }
  .mm-co-name { font-size: 14.5px; }
  .mm-co-bar { width: 56px; height: 6px; }
  .mm-iso { width: 40px; height: 32px; font-size: 16px; }
  .mm-pill { font-size: 13px; padding: 5px 13px; }
  .mm-rate { font-size: 13px; }
  .mm-dot { width: 15px; height: 15px; }
  .mm-ems span { font-size: 18px; }
  .mm-wrap { max-height: calc(100dvh - 360px); }
}
@media (min-width: 3400px) {
  .mm { font-size: 19px; }
  .mm thead th { font-size: 15px; }
  .mm-subh th { font-size: 13px; top: 50px; }
  .mm-h-co, td.mm-co { min-width: 400px; max-width: 480px; }
  .mm-co-name { font-size: 18px; }
  .mm-co-bar { width: 76px; height: 8px; }
  .mm-iso { width: 52px; height: 42px; font-size: 21px; border-radius: 9px; }
  .mm-pill { font-size: 16px; padding: 7px 17px; }
  .mm-rate { font-size: 16px; }
  .mm-dot { width: 20px; height: 20px; }
  .mm-ems span { font-size: 24px; }
}
</style>
