<template>
  <div class="kpe-backdrop" @click.self="$emit('close')">
    <div class="kpe-modal">
      <div class="kpe-header">
        <div>
          <div class="kpe-eyebrow">UzAssets · KPI редактор</div>
          <h2 class="kpe-title">{{ companyName }} · FY {{ year }}</h2>
        </div>
        <button class="kpe-close" @click="$emit('close')">×</button>
      </div>

      <!-- Validation banner -->
      <div v-if="weightTotal !== 100" class="kpe-banner" :class="weightTotal === 100 ? 'ok' : 'warn'">
        Сумма годовых весов {{ weightTotal }}% (должна быть 100%)
      </div>

      <div class="kpe-body" :data-readonly="!perm.canEdit">
        <div v-if="!managers.length" class="kpe-empty">
          Нет руководителей.
          <button v-if="perm.canEdit" class="kpe-btn kpe-btn-primary" @click="addManager" style="margin-top: 14px">
            + Добавить руководителя
          </button>
          <div v-else style="margin-top: 14px; font-size: 12px; color: var(--t3, #888780);">
            У вас нет прав на редактирование KPI.
          </div>
        </div>

        <!-- Tabs for managers -->
        <div v-else class="kpe-tabs">
          <button
            v-for="(m, i) in managers"
            :key="i"
            class="kpe-tab"
            :class="{ on: activeIdx === i }"
            @click="activeIdx = i"
          >
            {{ m.short_title || m.title || `№${i + 1}` }}
            <span v-if="perm.canDelete" class="kpe-tab-rm" @click.stop="removeManager(i)" title="Удалить">×</span>
          </button>
          <button class="kpe-tab-add" @click="addManager" title="Добавить руководителя">+</button>
        </div>

        <div v-if="activeManager" class="kpe-mgr">
          <!-- Manager fields -->
          <div class="kpe-mgr-fields">
            <div class="kpe-fld">
              <label>Должность (полное название)</label>
              <input v-model="activeManager.title" type="text" class="kpe-in" />
            </div>
            <div class="kpe-fld">
              <label>Краткое название</label>
              <input v-model="activeManager.short_title" type="text" class="kpe-in" />
            </div>
            <div class="kpe-fld">
              <label>Ответственность (роль)</label>
              <input v-model="activeManager.role" type="text" class="kpe-in" />
            </div>
          </div>

          <!-- Indicators table -->
          <div class="kpe-ind-h">
            <span>Индикаторы ({{ activeManager.indicators.length }})</span>
            <button class="kpe-mini-btn" @click="addIndicator">+ Добавить индикатор</button>
          </div>

          <table v-if="activeManager.indicators.length" class="kpe-tbl">
            <thead>
              <tr>
                <th class="lbl">Название</th>
                <th>Ед.</th>
                <th title="Направление метрики: больше=лучше или меньше=лучше">Напр.</th>
                <th>Вес год</th>
                <th>План год</th>
                <th>Факт год</th>
                <th>Q1 W</th>
                <th>Q1 P</th>
                <th>Q1 F</th>
                <th>Q2 W</th>
                <th>Q2 P</th>
                <th>Q2 F</th>
                <th>Q3 W</th>
                <th>Q3 P</th>
                <th>Q3 F</th>
                <th>Q4 W</th>
                <th>Q4 P</th>
                <th>Q4 F</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(ind, i) in activeManager.indicators" :key="i">
                <td class="lbl"><input v-model="ind.name" class="kpe-in" type="text" placeholder="Название KPI" /></td>
                <td><input v-model="ind.unit" class="kpe-in kpe-in-s" type="text" placeholder="ед" /></td>
                <td>
                  <select v-model="ind.direction" class="kpe-in kpe-in-dir" title="↑ больше=лучше · ↓ меньше=лучше (себестоимость, просрочка)">
                    <option value="up">↑ больше</option>
                    <option value="down">↓ меньше</option>
                  </select>
                </td>
                <td><input v-model.number="ind.weight" class="kpe-in kpe-in-n" type="number" step="0.5" min="0" max="100" /></td>
                <td><input v-model.number="ind.plan_year" class="kpe-in kpe-in-m" type="number" step="0.001" /></td>
                <td><input v-model.number="ind.fact_year" class="kpe-in kpe-in-m" type="number" step="0.001" /></td>
                <td><input v-model.number="ind.q1_weight" class="kpe-in kpe-in-n" type="number" step="0.5" /></td>
                <td><input v-model.number="ind.q1_plan" class="kpe-in kpe-in-m" type="number" step="0.001" /></td>
                <td><input v-model.number="ind.q1_fact" class="kpe-in kpe-in-m" type="number" step="0.001" /></td>
                <td><input v-model.number="ind.q2_weight" class="kpe-in kpe-in-n" type="number" step="0.5" /></td>
                <td><input v-model.number="ind.q2_plan" class="kpe-in kpe-in-m" type="number" step="0.001" /></td>
                <td><input v-model.number="ind.q2_fact" class="kpe-in kpe-in-m" type="number" step="0.001" /></td>
                <td><input v-model.number="ind.q3_weight" class="kpe-in kpe-in-n" type="number" step="0.5" /></td>
                <td><input v-model.number="ind.q3_plan" class="kpe-in kpe-in-m" type="number" step="0.001" /></td>
                <td><input v-model.number="ind.q3_fact" class="kpe-in kpe-in-m" type="number" step="0.001" /></td>
                <td><input v-model.number="ind.q4_weight" class="kpe-in kpe-in-n" type="number" step="0.5" /></td>
                <td><input v-model.number="ind.q4_plan" class="kpe-in kpe-in-m" type="number" step="0.001" /></td>
                <td><input v-model.number="ind.q4_fact" class="kpe-in kpe-in-m" type="number" step="0.001" /></td>
                <td>
                  <button v-if="perm.canDelete" class="kpe-rm" @click="removeIndicator(i)" title="Удалить">×</button>
                </td>
              </tr>
            </tbody>
          </table>

          <div v-else class="kpe-empty-ind">
            Нет индикаторов. Добавьте через кнопку выше.
          </div>
        </div>
      </div>

      <div class="kpe-footer">
        <span class="kpe-status">
          {{ managers.length }} руководителей · {{ totalIndicators }} индикаторов · сумма весов {{ weightTotal }}%
        </span>
        <div class="kpe-actions">
          <button class="kpe-btn kpe-btn-ghost" @click="$emit('close')">{{ perm.canEdit ? "Отмена" : "Закрыть" }}</button>
          <button
            v-if="perm.canEdit"
            class="kpe-btn kpe-btn-primary"
            @click="save"
            :disabled="saving"
          >
            {{ saving ? "Сохранение..." : "Сохранить всё" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  kpiApi,
  num,
  type KpiCompanyYearUpsert,
  type KpiManagerUpsert,
} from "@/api/bpKpi";
import { isModerationQueued } from "@/api/client";
import { usePermissions } from "@/composables/usePermissions";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";

const { confirmDialog } = useConfirm();

const perm = usePermissions("kpi");

const props = defineProps<{
  companyId: string;
  companyName: string;
  year: number;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved"): void;
}>();

type EditorManager = KpiManagerUpsert;

const managers = ref<EditorManager[]>([]);
const activeIdx = ref(0);
const saving = ref(false);
// Optimistic-lock token from the most recent server snapshot. Echoed back
// on save as If-Match so backend can detect concurrent edits (Pack 153).
const editorToken = ref<string | null>(null);

const activeManager = computed<EditorManager | null>(() => managers.value[activeIdx.value] || null);

const totalIndicators = computed(() => managers.value.reduce((s, m) => s + m.indicators.length, 0));

const weightTotal = computed(() => {
  let s = 0;
  for (const m of managers.value) {
    for (const ind of m.indicators) {
      s += num(ind.weight ?? 0);
    }
  }
  return Math.round(s * 100) / 100;
});

function addManager() {
  managers.value.push({
    title: "Новый руководитель",
    short_title: "",
    role: "",
    sort_order: managers.value.length,
    indicators: [],
  });
  activeIdx.value = managers.value.length - 1;
}

async function removeManager(idx: number) {
  if (!(await confirmDialog({ message: `Удалить руководителя «${managers.value[idx].short_title || managers.value[idx].title}»?`, danger: true }))) return;
  managers.value.splice(idx, 1);
  if (activeIdx.value >= managers.value.length) activeIdx.value = Math.max(0, managers.value.length - 1);
}

function addIndicator() {
  if (!activeManager.value) return;
  activeManager.value.indicators.push({
    name: "Новый KPI",
    unit: "",
    direction: "up",
    weight: 0,
    plan_year: null,
    fact_year: null,
    q1_weight: 0, q2_weight: 0, q3_weight: 0, q4_weight: 0,
    q1_plan: null, q1_fact: null,
    q2_plan: null, q2_fact: null,
    q3_plan: null, q3_fact: null,
    q4_plan: null, q4_fact: null,
    sort_order: activeManager.value.indicators.length,
  });
}

function removeIndicator(idx: number) {
  if (!activeManager.value) return;
  activeManager.value.indicators.splice(idx, 1);
}

/** Жёсткие ошибки данных (блокируют сохранение). Возвращает текст или null. */
function hardValidate(): string | null {
  for (const m of managers.value) {
    for (const ind of m.indicators) {
      const nm = String(ind.name || "").trim();
      if (!nm) return `У руководителя «${m.short_title || m.title}» есть KPI без названия`;
      const w = num(ind.weight ?? 0);
      if (w < 0 || w > 100) return `Вес «${nm}» вне диапазона 0–100`;
      for (const qw of [ind.q1_weight, ind.q2_weight, ind.q3_weight, ind.q4_weight]) {
        const x = num(qw ?? 0);
        if (x < 0 || x > 100) return `Квартальный вес «${nm}» вне диапазона 0–100`;
      }
      for (const v of [ind.plan_year, ind.fact_year, ind.q1_plan, ind.q1_fact,
                       ind.q2_plan, ind.q2_fact, ind.q3_plan, ind.q3_fact, ind.q4_plan, ind.q4_fact]) {
        if (v != null && num(v) < 0) return `Отрицательное значение план/факт в «${nm}»`;
      }
    }
  }
  return null;
}

async function save() {
  if (saving.value) return;
  // P1: жёсткая валидация диапазонов → блок с тостом.
  const verr = hardValidate();
  if (verr) { useToast().error(verr); return; }
  // Сумма весов ≠ 100 — мягкий гейт (подтверждение), чтобы не блокировать
  // правку легаси-данных, но явно предупредить.
  if (weightTotal.value !== 100) {
    const ok = await confirmDialog({
      message: `Сумма годовых весов = ${weightTotal.value}% (рекомендуется 100%). Сохранить всё равно?`,
    });
    if (!ok) return;
  }
  saving.value = true;
  try {
    // Reassign sort_order
    managers.value.forEach((m, i) => {
      m.sort_order = i;
      m.indicators.forEach((ind, j) => { ind.sort_order = j; });
    });
    const payload: KpiCompanyYearUpsert = {
      company_id: props.companyId,
      year: props.year,
      managers: managers.value,
    };
    const resp = await kpiApi.replaceCompanyYear(payload, editorToken.value);
    editorToken.value = resp.editorToken;  // re-arm for next save
    // If gated, the interceptor already toasted the user; close the editor.
    // Otherwise emit 'saved' so the parent refreshes.
    if (isModerationQueued(resp.result)) {
      emit("close");
    } else {
      // Успех = бэкенд закоммитил (API 2xx). Подтверждаем визуально.
      useToast().success("KPI сохранён");
      emit("saved");
    }
  } catch (e: any) {
    // 409 Conflict = another editor saved while we were working.
    // Show a clear reload prompt instead of generic failure.
    const status = e?.response?.status;
    const errCode = e?.response?.data?.error;
    if (status === 409 && errCode === "EditorConflict") {
      const detail = e?.response?.data?.detail
        ?? "Другой пользователь сохранил KPI пока вы редактировали. Перезагрузить?";
      if (await confirmDialog({ message: detail + "\n\nOK — перезагрузить и потерять текущие правки.\nОтмена — остаться, чтобы скопировать значения.", danger: true })) {
        emit("close");
      }
    } else {
      console.error("[KPI editor] save failed:", e);
      const reason = e?.response?.data?.detail || e?.message || "неизвестная ошибка";
      useToast().error(`KPI не сохранён: ${reason}`);
    }
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  try {
    const loaded = await kpiApi.getCompanyYear(props.companyId, props.year);
    editorToken.value = loaded.editorToken;
    managers.value = loaded.managers.map((m) => ({
      sort_order: m.sort_order,
      title: m.title,
      short_title: m.short_title ?? "",
      role: m.role ?? "",
      indicators: m.indicators.map((ind) => ({
        sort_order: ind.sort_order,
        name: ind.name,
        unit: ind.unit ?? "",
        direction: ind.direction === "down" ? "down" : "up",
        weight: num(ind.weight),
        plan_year: ind.plan_year != null ? num(ind.plan_year) : null,
        fact_year: ind.fact_year != null ? num(ind.fact_year) : null,
        q1_weight: num(ind.q1_weight),
        q2_weight: num(ind.q2_weight),
        q3_weight: num(ind.q3_weight),
        q4_weight: num(ind.q4_weight),
        q1_plan: ind.q1_plan != null ? num(ind.q1_plan) : null,
        q1_fact: ind.q1_fact != null ? num(ind.q1_fact) : null,
        q2_plan: ind.q2_plan != null ? num(ind.q2_plan) : null,
        q2_fact: ind.q2_fact != null ? num(ind.q2_fact) : null,
        q3_plan: ind.q3_plan != null ? num(ind.q3_plan) : null,
        q3_fact: ind.q3_fact != null ? num(ind.q3_fact) : null,
        q4_plan: ind.q4_plan != null ? num(ind.q4_plan) : null,
        q4_fact: ind.q4_fact != null ? num(ind.q4_fact) : null,
        notes: ind.notes ?? null,
      })),
    }));
  } catch (e) {
    console.error("[KPI editor] load failed:", e);
    managers.value = [];
  }
});
</script>

<style scoped>
.kpe-backdrop {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}
.kpe-modal {
  background: var(--bg1, #fff);
  border-radius: 14px;
  width: min(1300px, 96vw);
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18);
}

.kpe-header {
  padding: 18px 22px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
}
.kpe-eyebrow {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
}
.kpe-title { font-size: 16px; font-weight: 600; margin: 4px 0 0; color: var(--t1, #1e2a4a); }
.kpe-close {
  background: transparent;
  border: none;
  font-size: 24px;
  color: rgba(15, 23, 60, .45);
  cursor: pointer;
  padding: 0 8px;
}

.kpe-banner {
  margin: 8px 22px 0;
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 500;
}
.kpe-banner.ok { background: rgba(29, 158, 117, .08); color: var(--green); }
.kpe-banner.warn { background: rgba(239, 159, 39, .08); color: #B45309; }

.kpe-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 22px 18px;
}

.kpe-empty {
  text-align: center;
  padding: 80px 20px;
  color: rgba(15, 23, 60, .55);
  font-size: 14px;
}

.kpe-tabs {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  margin-bottom: 14px;
}
.kpe-tab {
  background: transparent;
  border: none;
  padding: 8px 14px;
  font-size: 11.5px;
  font-weight: 500;
  color: rgba(15, 23, 60, .55);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.kpe-tab.on {
  color: #7F77DD;
  font-weight: 600;
  border-bottom-color: #7F77DD;
}
.kpe-tab-rm {
  color: rgba(15, 23, 60, .35);
  font-size: 14px;
  font-weight: 700;
  padding: 0 4px;
  border-radius: 3px;
}
.kpe-tab-rm:hover { color: var(--sev-high); background: rgba(226, 75, 74, .1); }

.kpe-tab-add {
  background: rgba(127, 119, 221, .1);
  border: none;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 13px;
  font-weight: 600;
  color: #7F77DD;
  cursor: pointer;
  margin-left: 4px;
  align-self: center;
}
.kpe-tab-add:hover { background: rgba(127, 119, 221, .18); }

.kpe-mgr-fields {
  display: grid;
  grid-template-columns: 2fr 1fr 2fr;
  gap: 10px;
  margin-bottom: 14px;
}
@media (max-width: 900px) { .kpe-mgr-fields { grid-template-columns: 1fr; } }

.kpe-fld { display: flex; flex-direction: column; gap: 4px; }
.kpe-fld label {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
}

.kpe-in {
  font: inherit;
  font-size: 12px;
  padding: 6px 10px;
  border: 1px solid rgba(15, 23, 60, .12);
  border-radius: 5px;
  background: var(--bg1, #fff);
  outline: none;
  transition: border-color .15s, background .15s;
  width: 100%;
}
.kpe-in:focus { border-color: #7F77DD; background: rgba(127, 119, 221, .04); }

.kpe-ind-h {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
}
.kpe-mini-btn {
  background: rgba(127, 119, 221, .1);
  border: none;
  border-radius: 5px;
  padding: 5px 12px;
  font-size: 11px;
  font-weight: 600;
  color: #7F77DD;
  cursor: pointer;
  text-transform: none;
  letter-spacing: 0;
}
.kpe-mini-btn:hover { background: rgba(127, 119, 221, .18); }

.kpe-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.kpe-tbl th {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .5);
  text-align: right;
  padding: 5px 4px;
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  position: sticky;
  top: 0;
  background: var(--bg1, #fff);
}
.kpe-tbl th.lbl { text-align: left; min-width: 220px; }

.kpe-tbl td {
  padding: 3px 4px;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  text-align: right;
}
.kpe-tbl td.lbl { text-align: left; min-width: 220px; }

.kpe-tbl .kpe-in { padding: 4px 6px; font-size: 11px; min-width: 60px; }
.kpe-tbl .kpe-in-s { width: 60px; min-width: 50px; }
.kpe-tbl .kpe-in-dir { width: 84px; min-width: 78px; padding: 4px 4px; font-size: 11px; cursor: pointer; }
.kpe-tbl .kpe-in-n { width: 60px; min-width: 50px; text-align: right; }
.kpe-tbl .kpe-in-m { width: 80px; min-width: 70px; text-align: right; }

.kpe-rm {
  background: transparent;
  border: none;
  color: rgba(15, 23, 60, .35);
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 3px;
}
.kpe-rm:hover { color: var(--sev-high); background: rgba(226, 75, 74, .1); }

.kpe-empty-ind {
  text-align: center;
  padding: 32px 20px;
  color: rgba(15, 23, 60, .55);
  font-size: 12px;
  background: var(--bg2, #FAFAFD);
  border-radius: 8px;
}

.kpe-footer {
  padding: 12px 22px 16px;
  border-top: 1px solid rgba(15, 23, 60, .06);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: var(--bg2, #FAFAFD);
}
.kpe-status { font-size: 11px; color: rgba(15, 23, 60, .55); }
.kpe-actions { display: flex; gap: 8px; }

.kpe-btn {
  padding: 7px 16px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  font-family: inherit;
}
.kpe-btn-ghost {
  background: transparent;
  border: 1px solid rgba(15, 23, 60, .15);
  color: rgba(15, 23, 60, .65);
}
.kpe-btn-primary { background: #7F77DD; color: #fff; }
.kpe-btn-primary:hover:not(:disabled) { background: #6B62D6; }
.kpe-btn-primary:disabled { opacity: .5; cursor: not-allowed; }

/* Read-only mode for users without kpi.edit permission */
.kpe-body[data-readonly="true"] input,
.kpe-body[data-readonly="true"] textarea,
.kpe-body[data-readonly="true"] select {
  pointer-events: none;
  background: var(--bg2, #FAFAFC) !important;
  color: rgba(15, 23, 60, .55);
  cursor: not-allowed;
}
</style>
