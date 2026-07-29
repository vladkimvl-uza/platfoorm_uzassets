<script setup lang="ts">
/**
 * ESGReportRatingModal — единое окно редактирования «внешней валидации» ESG по
 * компании: Подготовка отчётности (D2 + ссылка) · Независимое заверение (D2A) ·
 * ESG-рейтинги (список агентств/значений/ссылок + «запланировано»).
 *
 * Заменяет тесное inline-редактирование в ячейках матрицы. Пакетное сохранение
 * с dirty-guard (ModalShell) и тостами (никаких тихих провалов). «Запланировано
 * получение рейтинга» хранится служебной ячейкой rp (stage 1) — питает донат
 * покрытия (planned_count).
 */
import { computed, ref, watch } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { esgApi, type ESGMaturityCompany } from "@/api/esg";
import { ratingsApi } from "@/api/ratings";
import { useToast } from "@/composables/useToast";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const props = defineProps<{
  open: boolean;
  company: ESGMaturityCompany | null;
  year: number;
  canEdit: boolean;
}>();
const emit = defineEmits<{ (e: "close"): void; (e: "saved"): void }>();

const toast = useToast();

const ESG_AGENCIES = ["Sustainable Fitch", "S&P ESG", "CDP", "MSCI", "Sustainalytics", "ISS"];
const REP_OPTS = [
  { v: 0, label: "нет" }, { v: 1, label: "разовый" },
  { v: 2, label: "регулярный" }, { v: 3, label: "IFRS SDS" },
];
const ASSUR_OPTS = [
  { v: 0, label: "нет" }, { v: 1, label: "запланировано" }, { v: 2, label: "пройдено" },
];

interface RatingRow { id?: string; agency: string; value: string; report_url: string; _new?: boolean }

// ── редактируемое состояние ──
const repStage = ref(0);
const repNr = ref(false);
const repLink = ref("");
const assurStage = ref(0);
const assurNr = ref(false);
const planned = ref(false);
const rows = ref<RatingRow[]>([]);
const removedIds = ref<string[]>([]);
const saving = ref(false);

let initial = "";
function snap(): string {
  return JSON.stringify({
    repStage: repStage.value, repNr: repNr.value, repLink: repLink.value.trim(),
    assurStage: assurStage.value, assurNr: assurNr.value, planned: planned.value,
    rows: rows.value.map((r) => ({ id: r.id || null, agency: r.agency, value: r.value.trim(), url: r.report_url.trim() })),
    removed: [...removedIds.value].sort(),
  });
}
const dirty = computed(() => snap() !== initial);

function cellStage(dim: string, sub = ""): number {
  const c = props.company?.cells.find((x) => x.dimension === dim && (x.sub_key || "") === sub);
  return c?.stage || 0;
}
function cellEvidence(dim: string, sub = ""): string {
  const c = props.company?.cells.find((x) => x.dimension === dim && (x.sub_key || "") === sub);
  return c?.evidence_url || "";
}

function init() {
  const c = props.company;
  if (!c) return;
  repStage.value = Math.min(3, cellStage("D2"));
  repNr.value = cellStage("nr", "D2") >= 1;
  repLink.value = cellEvidence("D2");
  assurStage.value = cellStage("D2A");
  assurNr.value = cellStage("nr", "D2A") >= 1;
  planned.value = cellStage("rp") >= 1;
  rows.value = (c.ratings || []).map((r) => ({
    id: r.id || undefined, agency: r.agency,
    value: r.score || r.rating || "", report_url: r.report_url || "",
  }));
  removedIds.value = [];
  initial = snap();
}
watch(() => [props.open, props.company?.company_id], () => { if (props.open) init(); }, { immediate: true });

const title = computed(() => props.company?.company_name || props.company?.company_code || "Компания");

function addRow() {
  if (!props.canEdit) return;
  const have = new Set(rows.value.map((r) => r.agency));
  const agency = ESG_AGENCIES.find((a) => !have.has(a)) || ESG_AGENCIES[0];
  rows.value.push({ agency, value: "", report_url: "", _new: true });
}
function removeRow(i: number) {
  const r = rows.value[i];
  if (r.id) removedIds.value.push(r.id);
  rows.value.splice(i, 1);
}

function requestClose() { emit("close"); }

async function save() {
  if (!props.company || saving.value || !props.canEdit) return;
  const cid = props.company.company_id;
  const year = props.year;
  const before = JSON.parse(initial);
  saving.value = true;
  let queued = false;
  const flag = (r: unknown) => { if ((r as { queued?: boolean })?.queued) queued = true; };
  try {
    const calls: Promise<unknown>[] = [];
    const cell = (dimension: string, sub_key: string, extra: Record<string, unknown>) =>
      esgApi.upsertMaturityCell({ company_id: cid, year, dimension, sub_key, ...extra }).then(flag);

    // Отчётность (D2) + «не требуется»
    if (repNr.value !== before.repNr) calls.push(cell("nr", "D2", { stage: repNr.value ? 1 : 0 }));
    if (!repNr.value && repStage.value !== before.repStage) calls.push(cell("D2", "", { stage: repStage.value }));
    if (repLink.value.trim() !== before.repLink) calls.push(cell("D2", "", { evidence_url: repLink.value.trim() }));

    // Заверение (D2A) + «не требуется»
    if (assurNr.value !== before.assurNr) calls.push(cell("nr", "D2A", { stage: assurNr.value ? 1 : 0 }));
    if (!assurNr.value && assurStage.value !== before.assurStage) calls.push(cell("D2A", "", { stage: assurStage.value }));

    // Запланировано получение рейтинга
    if (planned.value !== before.planned) calls.push(cell("rp", "", { stage: planned.value ? 1 : 0 }));

    // Рейтинги: удаления
    for (const id of removedIds.value) calls.push(ratingsApi.remove(id).then(flag));
    // Рейтинги: новые + правки существующих
    const beforeRows: { id: string | null; value: string; url: string }[] = before.rows;
    for (const r of rows.value) {
      const value = r.value.trim();
      const url = r.report_url.trim();
      if (r._new || !r.id) {
        if (value) calls.push(ratingsApi.create({ company_id: cid, agency: r.agency, score: value, report_url: url || undefined }).then(flag));
      } else {
        const prev = beforeRows.find((b) => b.id === r.id);
        if (prev && (prev.value !== value || prev.url !== url)) {
          const payload: Record<string, unknown> = { score: value };
          if (prev.url !== url) payload.report_url = url;
          calls.push(ratingsApi.update(r.id, payload as never).then(flag));
        }
      }
    }

    if (!calls.length) { requestClose(); return; }
    await Promise.all(calls);
    if (queued) toast.info("Часть изменений отправлена на согласование");
    else toast.success("Сохранено");
    emit("saved");
    initial = snap();
    requestClose();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не сохранено: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <ModalShell :open="open" size="md" :dirty="dirty" @close="requestClose">
    <template #header>
      <div class="erm-head">
        <span class="erm-eyebrow">{{ t('ESG · внешняя валидация') }}</span>
        <h2 class="erm-title">{{ title }}</h2>
        <span class="erm-yr">FY {{ year }}</span>
      </div>
    </template>

    <div v-if="company" class="erm-body">
      <!-- 1. Подготовка ESG-отчётности -->
      <section class="erm-sec">
        <div class="erm-sec-h">
          <span>{{ t('Подготовка ESG-отчётности') }}</span>
          <label class="erm-nr"><input type="checkbox" v-model="repNr" :disabled="!canEdit" /> {{ t('не требуется') }}</label>
        </div>
        <template v-if="!repNr">
          <div class="erm-seg">
            <button v-for="o in REP_OPTS" :key="o.v" type="button" class="erm-seg-btn"
                    :class="{ on: repStage === o.v }" :disabled="!canEdit" @click="repStage = o.v">{{ o.label }}</button>
          </div>
          <input v-model="repLink" type="url" class="erm-inp" :placeholder="t('https://… ссылка на отчёт')" :disabled="!canEdit" />
        </template>
        <div v-else class="erm-nr-note">{{ t('Подготовка отчётности исключена из статистики') }}</div>
      </section>

      <!-- 2. Прохождение независимого заверения -->
      <section class="erm-sec">
        <div class="erm-sec-h">
          <span>{{ t('Прохождение независимого заверения') }}</span>
          <label class="erm-nr"><input type="checkbox" v-model="assurNr" :disabled="!canEdit" /> {{ t('не требуется') }}</label>
        </div>
        <div v-if="!assurNr" class="erm-seg">
          <button v-for="o in ASSUR_OPTS" :key="o.v" type="button" class="erm-seg-btn"
                  :class="{ on: assurStage === o.v }" :disabled="!canEdit" @click="assurStage = o.v">{{ o.label }}</button>
        </div>
        <div v-else class="erm-nr-note">{{ t('Заверение исключено из статистики') }}</div>
      </section>

      <!-- 3. ESG-рейтинги -->
      <section class="erm-sec">
        <div class="erm-sec-h"><span>{{ t('Получение ESG-рейтинга') }}</span></div>
        <div class="erm-rates">
          <div v-for="(r, i) in rows" :key="r.id || 'new' + i" class="erm-rate">
            <select v-model="r.agency" class="erm-rate-ag" :disabled="!canEdit">
              <option v-for="a in ESG_AGENCIES" :key="a" :value="a">{{ a }}</option>
            </select>
            <input v-model="r.value" type="text" class="erm-rate-v" :placeholder="t('значение')" :disabled="!canEdit" />
            <input v-model="r.report_url" type="url" class="erm-rate-url" :placeholder="t('ссылка (опц.)')" :disabled="!canEdit" />
            <button v-if="canEdit" type="button" class="erm-rate-del" :title="t('Удалить рейтинг')" @click="removeRow(i)">✕</button>
          </div>
          <div v-if="!rows.length" class="erm-empty">{{ t('Рейтингов пока нет') }}</div>
        </div>
        <div class="erm-rate-foot">
          <button v-if="canEdit" type="button" class="erm-add" @click="addRow">{{ t('+ рейтинг') }}</button>
          <label class="erm-planned" :class="{ dis: rows.some((r) => r.value.trim()) }"
                 :title="rows.some((r) => r.value.trim()) ? 'Есть полученный рейтинг' : 'Отметить как запланированный'">
            <input type="checkbox" v-model="planned" :disabled="!canEdit" /> {{ t('запланировано получение рейтинга') }}
          </label>
        </div>
      </section>
    </div>

    <template #footer>
      <button class="erm-cancel" type="button" @click="requestClose">{{ t('Отмена') }}</button>
      <button v-if="canEdit" class="erm-save" type="button" :disabled="!dirty || saving" @click="save">
        {{ saving ? "Сохранение…" : "Сохранить" }}
      </button>
    </template>
  </ModalShell>
</template>

<style scoped>
.erm-head { display: flex; flex-direction: column; gap: 2px; }
.erm-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--t3, #94A3B8); }
.erm-title { font-size: 16px; font-weight: 600; margin: 2px 0 0; color: var(--t1, #1E2A4A); line-height: 1.25; }
.erm-yr { font-size: 11px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }

.erm-body { display: flex; flex-direction: column; gap: 18px; }
.erm-sec { display: flex; flex-direction: column; gap: 9px; }
.erm-sec-h { display: flex; align-items: center; justify-content: space-between; font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--p-deep, #534AB7); }
.erm-nr { display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; font-weight: 500; text-transform: none; letter-spacing: 0; color: var(--t3, #94A3B8); cursor: pointer; }
.erm-nr input { accent-color: #94A3B8; }
.erm-nr-note { font-size: 11.5px; font-style: italic; color: #A8AEC0; padding: 4px 2px; }

.erm-seg { display: inline-flex; flex-wrap: wrap; gap: 5px; }
.erm-seg-btn {
  font-size: 12px; font-weight: 600; font-family: inherit; color: var(--t2, #4B5468);
  background: var(--bg2, #F6F5FB); border: 1px solid var(--border, #ECEAF5); border-radius: 8px;
  padding: 6px 13px; cursor: pointer; transition: all .14s ease;
}
.erm-seg-btn:hover:not(:disabled) { border-color: color-mix(in srgb, var(--brand, #6C5CE7) 40%, #fff); }
.erm-seg-btn.on { color: #fff; background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); border-color: transparent; box-shadow: 0 2px 8px rgba(108,92,231,.28); }
.erm-seg-btn:disabled { opacity: .6; cursor: default; }

.erm-inp {
  width: 100%; box-sizing: border-box; font-size: 12.5px; font-family: inherit; color: var(--t1, #1E2A4A);
  padding: 8px 11px; border: 1px solid var(--border, #ECEAF5); border-radius: 9px; outline: none; background: var(--bg1, #fff);
  transition: border-color .14s, box-shadow .14s;
}
.erm-inp:focus { border-color: var(--brand, #6C5CE7); box-shadow: 0 0 0 3px rgba(124,111,247,.14); }

.erm-rates { display: flex; flex-direction: column; gap: 7px; }
.erm-rate { display: grid; grid-template-columns: minmax(0,1.4fr) minmax(0,.8fr) minmax(0,1.6fr) auto; gap: 6px; align-items: center; }
.erm-rate-ag, .erm-rate-v, .erm-rate-url {
  font-size: 12px; font-family: inherit; color: var(--t1, #1E2A4A);
  padding: 6px 9px; border: 1px solid var(--border, #ECEAF5); border-radius: 8px; outline: none; background: var(--bg1, #fff); min-width: 0;
  transition: border-color .14s, box-shadow .14s;
}
.erm-rate-ag:focus, .erm-rate-v:focus, .erm-rate-url:focus { border-color: var(--brand, #6C5CE7); box-shadow: 0 0 0 2px rgba(124,111,247,.12); }
.erm-rate-del { width: 28px; height: 28px; flex-shrink: 0; border: none; border-radius: 8px; background: #FEF2F2; color: #E24B4A; font-size: 13px; font-weight: 700; cursor: pointer; transition: all .12s ease; }
.erm-rate-del:hover { background: #E24B4A; color: #fff; }
.erm-empty { font-size: 11.5px; font-style: italic; color: #A8AEC0; padding: 4px 2px; }

.erm-rate-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-top: 2px; }
.erm-add {
  font-size: 11.5px; font-weight: 600; color: var(--brand, #6C5CE7); background: transparent;
  border: 1px dashed var(--border-strong, #D9D7E8); border-radius: 8px; padding: 5px 12px; cursor: pointer; transition: all .14s ease;
}
.erm-add:hover { border-color: var(--brand, #6C5CE7); background: color-mix(in srgb, var(--brand, #6C5CE7) 6%, #fff); }
.erm-planned { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 500; color: var(--t2, #4B5468); cursor: pointer; }
.erm-planned input { accent-color: #F0C67A; }
.erm-planned.dis { opacity: .5; }

.erm-cancel { font-size: 12.5px; font-weight: 600; font-family: inherit; color: var(--t2, #4B5468); background: transparent; border: 1px solid var(--border-hard, #E5E7EB); border-radius: 10px; padding: 9px 18px; cursor: pointer; margin-right: auto; }
.erm-cancel:hover { background: var(--bg2, #F6F5FB); }
.erm-save {
  font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); border: none; border-radius: 10px; padding: 9px 22px; cursor: pointer;
  box-shadow: 0 3px 12px rgba(108,92,231,.34); transition: transform .14s, box-shadow .14s, opacity .14s;
}
.erm-save:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108,92,231,.45); }
.erm-save:disabled { opacity: .5; cursor: default; box-shadow: none; }
</style>
