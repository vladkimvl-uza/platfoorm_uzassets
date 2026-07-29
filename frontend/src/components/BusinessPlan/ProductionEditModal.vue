<script setup lang="ts">
/** ProductionEditModal — редактор производственных данных одной компании.
 *  Правка/добавление/удаление строк продукции (натура+деньги: база/план/ожид),
 *  вложенность «в т.ч.», live-пересчёт темпа/исполнения. Конвенции аудитов:
 *  dirty-guard (ModalShell :dirty + подтверждение), валидация (min 0),
 *  тосты, никаких тихих провалов. */
import { computed, ref } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { productionApi, type ProdCompany, type ProdLine } from "@/api/production";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";


const { t } = useI18n();

const props = defineProps<{ company: ProdCompany; year: number; period: string }>();
const emit = defineEmits<{ (e: "close"): void; (e: "saved"): void }>();

const toast = useToast();
const { confirmDialog } = useConfirm();

type ELine = {
  name: string; unit: string; total: boolean; parent: number | null;
  baseN: number | null; baseM: number | null;
  planN: number | null; planM: number | null;
  expN: number | null; expM: number | null;
  factN: number | null; factM: number | null;
};

function blank(total = false): ELine {
  return { name: total ? props.company.n : "", unit: total ? (props.company.unit || t("млрд сум")) : "",
    total, parent: null, baseN: null, baseM: null, planN: null, planM: null,
    expN: null, expM: null, factN: null, factM: null };
}

// working copy from company.lines (ensure a total row exists)
const working = ref<ELine[]>((() => {
  const src = (props.company.lines || []).map((l: ProdLine) => ({
    name: l.name || "", unit: l.unit || "", total: !!l.total, parent: l.parent ?? null,
    baseN: l.baseN ?? null, baseM: l.baseM ?? null, planN: l.planN ?? null, planM: l.planM ?? null,
    expN: l.expN ?? null, expM: l.expM ?? null, factN: l.factN ?? null, factM: l.factM ?? null,
  }));
  if (!src.some((l) => l.total)) src.unshift(blank(true));
  return src;
})());

const snapshot = ref(JSON.stringify(working.value));
const dirty = computed(() => JSON.stringify(working.value) !== snapshot.value);
const saving = ref(false);

// ─── live compute (зеркалит бэкенд) ───────────────────────────
function _growth(base: number | null, cur: number | null): number | null {
  if (base == null || cur == null || base <= 0) return null;
  return Math.round(cur / base * 1000) / 10;
}
function _exec(plan: number | null, exp: number | null, planN: number | null, expN: number | null): { pct: number | null; state: string } {
  let p = plan, e = exp, ok = true;
  if (p == null || p <= 0) { p = planN; e = expN; ok = false; }
  if (p == null || p <= 0) return { pct: null, state: "noplan" };
  if (e == null) return { pct: null, state: "nofact" };
  return { pct: Math.round(e / p * 1000) / 10, state: "pct" };
}
function pctCol(p: number | null): string {
  if (p == null) return "var(--t3, #94A3B8)";
  if (p > 110) return "#7C3AED"; if (p >= 90) return "#1D9E75"; if (p >= 75) return "#D97706"; return "#993D3D";
}
// результат периода = факт (если введён) иначе ожидаемое
function rowExec(l: ELine) {
  const rM = l.factM != null ? l.factM : l.expM;
  const rN = l.factN != null ? l.factN : l.expN;
  return _exec(l.planM, rM, l.planN, rN);
}
function rowGrowth(l: ELine) {
  const rM = l.factM != null ? l.factM : l.expM;
  const rN = l.factN != null ? l.factN : l.expN;
  const g = _growth(l.baseM, rM); return g != null ? g : _growth(l.baseN, rN);
}

function setNum(l: ELine, key: keyof ELine, v: string) {
  let n: number | null = v === "" ? null : Number(v);
  if (n != null && !Number.isFinite(n)) n = null;
  if (n != null && n < 0) n = 0;                 // M-11: неотрицательные объёмы
  (l as unknown as Record<string, number | null>)[key as string] = n;
}

// ─── row ops ──────────────────────────────────────────────────
function addProduct() { working.value.push(blank(false)); }
function addChild(idx: number) {
  const child = blank(false); child.parent = idx;
  working.value.splice(idx + 1, 0, child);
  reindexParents();
}
function delRow(idx: number) {
  if (working.value[idx].total) { toast.info(t("Строку-итог удалить нельзя")); return; }
  working.value.splice(idx, 1);
  reindexParents();
}
function move(idx: number, dir: -1 | 1) {
  const j = idx + dir;
  if (j < 1 || j >= working.value.length) return;   // не двигаем total (idx 0)
  const t = working.value[idx]; working.value[idx] = working.value[j]; working.value[j] = t;
  reindexParents();
}
// после вставок/удалений parent-индексы «в т.ч.» могут поехать — упрощаем:
// сбрасываем parent, если он указывает на несуществующую/не-предшествующую строку.
function reindexParents() {
  working.value.forEach((l, i) => {
    if (l.parent != null && (l.parent >= i || l.parent < 0 || !working.value[l.parent])) l.parent = null;
  });
}

async function requestClose() {
  if (dirty.value) {
    const ok = await confirmDialog({ message: t("Есть несохранённые изменения. Закрыть без сохранения?"), danger: true });
    if (!ok) return;
  }
  emit("close");
}

async function save() {
  if (saving.value) return;
  const lines = working.value.filter((l) => l.total || l.name.trim() !== "");
  if (!lines.length) { toast.error(t("Нет строк для сохранения")); return; }
  saving.value = true;
  try {
    const payloadLines: ProdLine[] = lines.map((l) => ({
      name: l.name.trim() || "—", unit: l.unit.trim() || null, total: l.total, parent: l.parent,
      baseN: l.baseN, baseM: l.baseM, planN: l.planN, planM: l.planM,
      expN: l.expN, expM: l.expM, factN: l.factN, factM: l.factM,
    }));
    const r: unknown = await productionApi.upsertCompany(props.company.k, {
      year: props.year, period: props.period, lines: payloadLines,
    });
    if ((r as { queued?: boolean })?.queued) toast.info(t("Отправлено на модерацию"));
    else toast.success(t("Производственные данные сохранены"));
    snapshot.value = JSON.stringify(working.value);
    emit("saved");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t("Не сохранено: {e}", { e: err?.response?.data?.detail || err?.message || t("ошибка") }));
  } finally {
    saving.value = false;
  }
}

const periodLabel = computed(() => ({ h1: i18nKey("1 полугодие"), h2: i18nKey("2 полугодие"), annual: i18nKey("год") }[props.period] || props.period));
</script>

<template>
  <ModalShell :open="true" size="xl" :dirty="dirty" @close="requestClose">
    <template #header>
      <div class="pe-hd">
        <div>
          <div class="pe-eyebrow">{{ t("Редактирование производства") }} · FY{{ year }} · {{ t(periodLabel) }}</div>
          <div class="pe-title">{{ company.n }}</div>
        </div>
        <span v-if="dirty" class="pe-dirty">● {{ t("не сохранено") }}</span>
      </div>
    </template>

    <div class="pe-hint">
      {{ t("Темп роста и исполнение считаются автоматически (по деньгам, при отсутствии — по натуре). Введите «Факт» для реального исполнения (факт / план); без факта показывается прогнозное (ожид. / план). Объёмы — неотрицательные.") }}
    </div>

    <div class="pe-tbl-wrap">
      <table class="pe-tbl">
        <thead>
          <tr>
            <th class="lt">{{ t("Наименование") }}</th><th>{{ t("Ед.") }}</th>
            <th colspan="2">{{ t("База (2025 факт)") }}</th>
            <th colspan="2">{{ t("План") }}</th>
            <th colspan="2">{{ t("Ожидаемое") }}</th>
            <th colspan="2" class="pe-fact-h">{{ t("Факт") }}</th>
            <th class="rt">{{ t("Исп.") }}</th><th></th>
          </tr>
          <tr class="pe-sub">
            <th></th><th></th>
            <th>{{ t("натура") }}</th><th>{{ t("млрд") }}</th><th>{{ t("натура") }}</th><th>{{ t("млрд") }}</th><th>{{ t("натура") }}</th><th>{{ t("млрд") }}</th>
            <th class="pe-fact-h">{{ t("натура") }}</th><th class="pe-fact-h">{{ t("млрд") }}</th><th></th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(l, i) in working" :key="i" :class="{ total: l.total, child: l.parent != null }">
            <td class="lt">
              <input class="pe-in name" :class="{ 'is-child': l.parent != null }" v-model="l.name"
                     :placeholder="l.total ? t('Итог компании') : t('Продукт')" />
            </td>
            <td><input class="pe-in unit" v-model="l.unit" :placeholder="t('ед.')" /></td>
            <td><input class="pe-in num" type="number" min="0" step="any" :value="l.baseN ?? ''" @input="setNum(l,'baseN',($event.target as HTMLInputElement).value)" /></td>
            <td><input class="pe-in num" type="number" min="0" step="any" :value="l.baseM ?? ''" @input="setNum(l,'baseM',($event.target as HTMLInputElement).value)" /></td>
            <td><input class="pe-in num" type="number" min="0" step="any" :value="l.planN ?? ''" @input="setNum(l,'planN',($event.target as HTMLInputElement).value)" /></td>
            <td><input class="pe-in num" type="number" min="0" step="any" :value="l.planM ?? ''" @input="setNum(l,'planM',($event.target as HTMLInputElement).value)" /></td>
            <td><input class="pe-in num" type="number" min="0" step="any" :value="l.expN ?? ''" @input="setNum(l,'expN',($event.target as HTMLInputElement).value)" /></td>
            <td><input class="pe-in num" type="number" min="0" step="any" :value="l.expM ?? ''" @input="setNum(l,'expM',($event.target as HTMLInputElement).value)" /></td>
            <td><input class="pe-in num pe-fact" type="number" min="0" step="any" :value="l.factN ?? ''" @input="setNum(l,'factN',($event.target as HTMLInputElement).value)" /></td>
            <td><input class="pe-in num pe-fact" type="number" min="0" step="any" :value="l.factM ?? ''" @input="setNum(l,'factM',($event.target as HTMLInputElement).value)" /></td>
            <td class="rt pe-exec" :style="{ color: pctCol(rowExec(l).pct) }">
              {{ rowExec(l).pct != null ? rowExec(l).pct + '%' : (rowExec(l).state === 'nofact' ? t('факт —') : '—') }}
            </td>
            <td class="pe-acts">
              <button class="pe-act" :title="t('Добавить «в т.ч.»')" @click="addChild(i)">﹢</button>
              <button class="pe-act" :title="t('Вверх')" :disabled="i <= 1" @click="move(i,-1)">↑</button>
              <button class="pe-act" :title="t('Вниз')" :disabled="i >= working.length - 1" @click="move(i,1)">↓</button>
              <button v-if="!l.total" class="pe-act del" :title="t('Удалить')" @click="delRow(i)">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pe-foot">
      <button class="pe-add" @click="addProduct">＋ {{ t("Добавить продукт") }}</button>
      <div class="pe-foot-sp" />
      <button class="pe-btn ghost" @click="requestClose">{{ t("Отмена") }}</button>
      <button class="pe-btn save" :disabled="saving || !dirty" @click="save">
        {{ saving ? t("Сохранение…") : t("Сохранить") }}
      </button>
    </div>
  </ModalShell>
</template>

<style scoped>
.pe-hd { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; }
.pe-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--p-deep, #534AB7); }
.pe-title { font-size: 16px; font-weight: 600; color: var(--t1, #1E2A4A); margin-top: 2px; }
.pe-dirty { font-size: 11px; font-weight: 600; color: #D97706; }
.pe-hint { font-size: 11.5px; color: var(--t3, var(--t-muted)); margin-bottom: 10px; line-height: 1.4; }

.pe-tbl-wrap { max-height: 52vh; overflow: auto; scrollbar-width: thin; border: 1px solid rgba(0,0,0,.06); border-radius: 10px; }
.pe-tbl { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 980px; }
.pe-tbl th.pe-fact-h { color: var(--p-deep, #534AB7); background: rgba(127,119,221,.07); }
.pe-in.pe-fact { background: rgba(127,119,221,.08); }
.pe-in.pe-fact:focus { background: #fff; }
.pe-tbl thead th { position: sticky; top: 0; z-index: 1; background: var(--bg2, #FAFAFC); padding: 6px 8px;
  font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em; color: var(--t3, var(--t-muted));
  border-bottom: 0.5px solid rgba(0,0,0,.06); text-align: center; white-space: nowrap; }
.pe-tbl thead tr.pe-sub th { top: 27px; font-size: 9px; text-transform: none; padding: 3px 8px; }
.pe-tbl th.lt { text-align: left; } .pe-tbl th.rt { text-align: right; }
.pe-tbl tbody td { padding: 3px 6px; border-bottom: 0.5px solid rgba(0,0,0,.04); }
.pe-tbl td.lt { text-align: left; } .pe-tbl td.rt { text-align: right; }
.pe-tbl tr.total td { background: rgba(127,119,221,.06); }
.pe-tbl tr.child td { background: rgba(127,119,221,.02); }

.pe-in { width: 100%; box-sizing: border-box; padding: 4px 7px; border: 1px solid transparent; background: rgba(127,119,221,.05);
  border-radius: 6px; font: inherit; font-size: 12px; color: var(--t1, #1E2A4A); outline: none; transition: all .12s; }
.pe-in:focus { background: #fff; border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127,119,221,.15); }
.pe-in.name { min-width: 150px; font-weight: 500; } .pe-in.name.is-child { padding-left: 16px; }
.pe-tbl tr.total .pe-in.name { font-weight: 700; }
.pe-in.unit { width: 78px; text-align: center; }
.pe-in.num { width: 78px; text-align: right; font-feature-settings: 'tnum'; }
.pe-exec { font-weight: 600; font-feature-settings: 'tnum'; white-space: nowrap; }

.pe-acts { display: flex; gap: 2px; white-space: nowrap; }
.pe-act { width: 22px; height: 22px; border: none; background: transparent; border-radius: 5px; cursor: pointer;
  color: var(--t3, #94A3B8); font-size: 13px; line-height: 1; transition: all .12s; }
.pe-act:hover:not(:disabled) { background: rgba(127,119,221,.12); color: var(--p-deep, #534AB7); }
.pe-act.del:hover { background: rgba(226,75,74,.1); color: #E24B4A; }
.pe-act:disabled { opacity: .3; cursor: default; }

.pe-foot { display: flex; align-items: center; gap: 8px; margin-top: 14px; }
.pe-foot-sp { flex: 1; }
.pe-add { padding: 7px 13px; border-radius: 8px; border: 1px dashed rgba(127,119,221,.4); background: transparent;
  color: var(--p-deep, #534AB7); font: 600 12px inherit; cursor: pointer; transition: all .13s; }
.pe-add:hover { background: rgba(127,119,221,.06); border-color: #7F77DD; }
.pe-btn { padding: 8px 18px; border-radius: 8px; font: 600 12.5px inherit; cursor: pointer; border: 1px solid; transition: all .13s; }
.pe-btn.ghost { background: #fff; color: var(--t3, #64748B); border-color: rgba(0,0,0,.12); }
.pe-btn.ghost:hover { background: #F4F3F9; color: var(--t1, #1E2A4A); }
.pe-btn.save { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.pe-btn.save:hover:not(:disabled) { background: #6D62D6; box-shadow: 0 4px 12px rgba(127,119,221,.3); }
.pe-btn.save:disabled { background: #CBD5E1; border-color: #CBD5E1; cursor: not-allowed; }
</style>
