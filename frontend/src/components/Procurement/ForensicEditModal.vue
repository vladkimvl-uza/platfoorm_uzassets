<script setup lang="ts">
/**
 * ForensicEditModal — bulk edit plan/fact данных по компаниям.
 * 1:1 legacy showProcDataEditModal (упрощённая версия — single year per session).
 *
 * Список 22 компаний (expandable rows). Внутри expanded — поля:
 *   План, Факт (annual)
 *   9 мес план/факт
 *   Q1-Q4 план/факт
 *   Статус плана, Форензик, Аудитор, Период
 *
 * Save → PUT /forensic/companies/{k} (Phase 3 backend); пока — stub-alert.
 */
import { ref, computed, watch } from "vue";
import { useConfirm } from "@/composables/useConfirm";
import { useToast } from "@/composables/useToast";
import { execCol } from "@/utils/execBand";

interface YearRow {
  y: number;
  plan?: number | null;
  fact?: number | null;
  n9p?: number | null;
  n9f?: number | null;
  q1p?: number | null; q1f?: number | null;
  q2p?: number | null; q2f?: number | null;
  q3p?: number | null; q3f?: number | null;
  q4p?: number | null; q4f?: number | null;
}

interface ProcCompany {
  n: string;
  k: string;
  s: string;
  sector_color?: string;
  // 7 флагманов держат в поле plan ЧИСЛОВУЮ сумму плана (а не статус-строку) —
  // тип должен это отражать, иначе TS прячет число и <select> его затирает.
  plan?: string | number | null;
  forensic?: string;
  auditor?: string;
  aYears?: string;
  years?: YearRow[];
  yP24?: number | null; yF24?: number | null; nP24?: number | null; nF24?: number | null;
  yP25?: number | null; yF25?: number | null; nP25?: number | null; nF25?: number | null;
  yP26?: number | null;
}

const props = defineProps<{
  companies: ProcCompany[];
  year: number;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved", patches: { company: ProcCompany; year: number }[]): void;
}>();

const { confirmDialog } = useConfirm();
const toast = useToast();

// Local working copy (deep clone)
const working = ref<ProcCompany[]>(JSON.parse(JSON.stringify(props.companies)));
const expandedIdx = ref<number>(-1);

// Снимок исходных данных на момент последней синхронизации с props. Нужен, чтобы
// (а) закрытие при наличии правок шло с подтверждением (M-10) и (б) фоновое
// обновление props (перезагрузка списка) НЕ затирало несохранённые правки.
const snapshot = ref<string>(JSON.stringify(props.companies));
const dirty = computed(() => JSON.stringify(working.value) !== snapshot.value);

watch(() => props.companies, (next) => {
  // Пере-синхронизируемся только если пользователь ничего не менял — иначе
  // сохраняем его правки (не клоббим ввод внезапным refetch'ем).
  if (dirty.value) return;
  working.value = JSON.parse(JSON.stringify(next));
  snapshot.value = JSON.stringify(next);
}, { deep: false });

// M-10: единая точка закрытия — при несохранённых правках спрашиваем подтверждение
// (раньше клик по фону / крестик / «Отмена» молча теряли все изменения).
async function requestClose() {
  if (dirty.value) {
    const ok = await confirmDialog({
      message: "Есть несохранённые изменения. Закрыть без сохранения?",
      danger: true,
    });
    if (!ok) return;
  }
  emit("close");
}

function getYr(c: ProcCompany, y: number): YearRow {
  if (!c.years) c.years = [];
  let yr = c.years.find(yy => yy.y === y);
  if (!yr) {
    yr = { y };
    c.years.push(yr);
  }
  return yr;
}

const SECTOR_LABELS_RU: Record<string, string> = {
  mining: "Горнодобывающий", oilgas: "Нефтегазовый",
  energy: "Энергетика", transport: "Транспорт", other: "Прочие",
};

function toggleCompany(i: number) {
  expandedIdx.value = expandedIdx.value === i ? -1 : i;
}

// Diff counter — how many fields changed vs original (props.companies[i])
function changedCount(idx: number): number {
  const orig = props.companies[idx];
  const cur = working.value[idx];
  if (!orig || !cur) return 0;
  let n = 0;
  for (const f of ["plan", "forensic", "auditor", "aYears"] as const) {
    if ((orig[f] || "") !== (cur[f] || "")) n++;
  }
  const origYr = orig.years?.find(y => y.y === props.year) || {} as YearRow;
  const curYr = cur.years?.find(y => y.y === props.year) || {} as YearRow;
  const fields: (keyof YearRow)[] = ["plan", "fact", "n9p", "n9f", "q1p", "q1f", "q2p", "q2f", "q3p", "q3f", "q4p", "q4f"];
  for (const f of fields) {
    if ((origYr[f] ?? null) !== (curYr[f] ?? null)) n++;
  }
  return n;
}

const totalChanges = computed(() =>
  working.value.reduce((s, _, i) => s + changedCount(i), 0),
);

// H-4: единый tri-state (как gPct/gPctState в таблице). 9-мес приоритетнее, если
// план 9-мес заведён; иначе годовой. Факт=0 при плане>0 → 0% (провал, красным),
// а не «—» (нет данных). Прежний `yr.plan && yr.fact` ронял записанный факт=0 в null.
function execBasis(c: ProcCompany): { p: number | null; f: number | null } {
  const yr = c.years?.find(y => y.y === props.year);
  if (!yr) return { p: null, f: null };
  const has9 = yr.n9p != null;
  return has9
    ? { p: yr.n9p ?? null, f: yr.n9f ?? null }
    : { p: yr.plan ?? null, f: yr.fact ?? null };
}
function executionPct(c: ProcCompany): number | null {
  const { p, f } = execBasis(c);
  if (p == null || p === 0 || f == null) return null;
  return Math.round((f / p) * 1000) / 10;
}
function execState(c: ProcCompany): "pct" | "nofact" | "noplan" {
  const { p, f } = execBasis(c);
  if (p == null || p === 0) return "noplan";
  if (f == null) return "nofact";
  return "pct";
}

function numInput(yr: YearRow, key: keyof YearRow) {
  return yr[key] ?? "";
}
function setNum(yr: YearRow, key: keyof YearRow, val: string) {
  // M-11: план/факт закупок — суммы в млрд, не бывают отрицательными.
  // Пустое → null; нечисло/Infinity → null; отрицательное → 0 (clamp).
  let n: number | null = val === "" ? null : Number(val);
  if (n != null && !Number.isFinite(n)) n = null;
  if (n != null && n < 0) n = 0;
  (yr as unknown as Record<string, number | null>)[key as string] = n;
}

// M-11: жёсткая валидация — только заведомо невалидный ввод (отрицательные/
// не-числа). Переисполнение (факт>план) НЕ ошибка: это отдельная красная зона
// >110% (H-5), реальный сигнал форензика, а не невалидные данные.
const _NUM_FIELDS: (keyof YearRow)[] = [
  "plan", "fact", "n9p", "n9f", "q1p", "q1f", "q2p", "q2f", "q3p", "q3f", "q4p", "q4f",
];
function validate(): string | null {
  for (const c of working.value) {
    const yr = c.years?.find(y => y.y === props.year);
    if (!yr) continue;
    for (const f of _NUM_FIELDS) {
      const v = yr[f];
      if (v != null && (!Number.isFinite(v as number) || (v as number) < 0)) {
        return `${c.n}: недопустимое значение в поле «${f}» (год ${props.year}) — суммы не бывают отрицательными.`;
      }
    }
  }
  return null;
}

async function save() {
  // Anti-wipe: не эмитим сохранение поверх непрогруженного списка.
  if (!props.companies.length) {
    toast.error("Список компаний не загружен — сохранение отменено.");
    return;
  }
  const err = validate();
  if (err) { toast.error(err); return; }
  // Мягкая проверка ТОЛЬКО по ИЗМЕНЁННЫМ компаниям: собираем все расхождения
  // «сумма кварталов ≠ годовой план (>5%)» в ОДНО подтверждение (не дёргаем по
  // одной за компанию и не теряем весь батч из-за отмены по строке, которую юзер
  // даже не открывал; квартальная разбивка может законно вестись отдельно от года).
  const offenders: string[] = [];
  working.value.forEach((c, i) => {
    if (changedCount(i) === 0) return;
    const yr = c.years?.find(y => y.y === props.year);
    if (!yr || yr.plan == null || yr.plan === 0) return;
    const qs = [yr.q1p, yr.q2p, yr.q3p, yr.q4p];
    if (!qs.every(x => x != null)) return;
    const sum = qs.reduce((s: number, x) => s + (x || 0), 0);
    if (Math.abs(sum - yr.plan) / yr.plan > 0.05) {
      offenders.push(`${c.n}: кварталы ${Math.round(sum)} ≠ год ${Math.round(yr.plan)}`);
    }
  });
  if (offenders.length) {
    const ok = await confirmDialog({
      message: `Сумма квартальных планов ≠ годовому плану (>5%):\n\n${offenders.join("\n")}\n\nСохранить всё равно?`,
      danger: true,
    });
    if (!ok) return;
  }
  const patches: { company: ProcCompany; year: number }[] = [];
  working.value.forEach((c, i) => {
    if (changedCount(i) > 0) patches.push({ company: c, year: props.year });
  });
  emit("saved", patches);
}
</script>

<template>
  <Transition name="pe" appear>
    <div class="pe-bg" @click.self="requestClose">
      <div class="pe-card">
        <div class="pe-h">
          <div>
            <h3>Редактирование данных закупок</h3>
            <div class="pe-h-sub">
              {{ companies.length }} компаний · год {{ year }} · все суммы в млрд сум
              <span v-if="totalChanges > 0" class="pe-h-changes"> · <b>{{ totalChanges }}</b> изменений</span>
            </div>
          </div>
          <button class="pe-x" @click="requestClose" title="Закрыть">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
              <path d="M3 3l10 10M13 3L3 13"/>
            </svg>
          </button>
        </div>

        <div class="pe-co-list">
          <div
            v-for="(c, i) in working"
            :key="c.k"
            class="pe-co"
            :class="{ expanded: expandedIdx === i }"
          >
            <div class="pe-co-h" @click="toggleCompany(i)">
              <svg class="pe-co-chev" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
                <polyline points="4 6 8 10 12 6"/>
              </svg>
              <span class="pe-sec-strip" :style="{ background: c.sector_color || '#888' }"></span>
              <span class="pe-co-name">{{ c.n }}</span>
              <span class="pe-co-sec">{{ SECTOR_LABELS_RU[c.s] || c.s }}</span>
              <span v-if="changedCount(i) > 0" class="pe-co-changed">{{ changedCount(i) }} изм.</span>
              <span class="pe-co-pct" :style="{ color: execCol(executionPct(c)) }">
                <template v-if="execState(c) === 'pct'">{{ executionPct(c) }}%</template>
                <span v-else-if="execState(c) === 'nofact'" title="План есть, факт не заведён">факт —</span>
                <span v-else style="color:var(--t3)">—</span>
              </span>
            </div>

            <div v-if="expandedIdx === i" class="pe-body">
              <!-- Year fields -->
              <div class="pe-tab-cnt">
                <div class="pe-section-t">Год {{ year }}</div>
                <div class="pe-grid cols-2">
                  <div class="pe-fld">
                    <div class="pe-fld-l">План год</div>
                    <input class="pe-fld-i num" type="number" step="0.01" min="0"
                      :value="numInput(getYr(c, year), 'plan')"
                      @input="setNum(getYr(c, year), 'plan', ($event.target as HTMLInputElement).value)" />
                  </div>
                  <div class="pe-fld">
                    <div class="pe-fld-l">Факт год</div>
                    <input class="pe-fld-i num" type="number" step="0.01" min="0"
                      :value="numInput(getYr(c, year), 'fact')"
                      @input="setNum(getYr(c, year), 'fact', ($event.target as HTMLInputElement).value)" />
                  </div>
                  <div class="pe-fld">
                    <div class="pe-fld-l">План 9 мес</div>
                    <input class="pe-fld-i num" type="number" step="0.01" min="0"
                      :value="numInput(getYr(c, year), 'n9p')"
                      @input="setNum(getYr(c, year), 'n9p', ($event.target as HTMLInputElement).value)" />
                  </div>
                  <div class="pe-fld">
                    <div class="pe-fld-l">Факт 9 мес</div>
                    <input class="pe-fld-i num" type="number" step="0.01" min="0"
                      :value="numInput(getYr(c, year), 'n9f')"
                      @input="setNum(getYr(c, year), 'n9f', ($event.target as HTMLInputElement).value)" />
                  </div>
                </div>

                <div class="pe-section-t" style="margin-top:14px">Поквартально</div>
                <div class="pe-grid cols-4">
                  <template v-for="q in (['q1','q2','q3','q4'] as const)" :key="q">
                    <div class="pe-fld">
                      <div class="pe-fld-l">{{ q.toUpperCase() }} план</div>
                      <input class="pe-fld-i num" type="number" step="0.01" min="0"
                        :value="numInput(getYr(c, year), `${q}p` as keyof YearRow)"
                        @input="setNum(getYr(c, year), `${q}p` as keyof YearRow, ($event.target as HTMLInputElement).value)" />
                    </div>
                    <div class="pe-fld">
                      <div class="pe-fld-l">{{ q.toUpperCase() }} факт</div>
                      <input class="pe-fld-i num" type="number" step="0.01" min="0"
                        :value="numInput(getYr(c, year), `${q}f` as keyof YearRow)"
                        @input="setNum(getYr(c, year), `${q}f` as keyof YearRow, ($event.target as HTMLInputElement).value)" />
                    </div>
                  </template>
                </div>

                <div class="pe-section-t" style="margin-top:14px">Метаданные</div>
                <div class="pe-grid cols-2">
                  <div class="pe-fld">
                    <div class="pe-fld-l">Статус плана</div>
                    <!-- Флагман (числовая сумма плана): показываем read-only, чтобы
                         <select> не превратил число в статус-строку и не затёр сумму. -->
                    <select v-if="typeof c.plan !== 'number'" class="pe-fld-i text" v-model="c.plan">
                      <option value="">—</option>
                      <option value="Утверждён">Утверждён</option>
                      <option value="Не утверждён">Не утверждён</option>
                    </select>
                    <div v-else class="pe-fld-i text" style="opacity:.7"
                         title="Числовой план (флагман) — план утверждён на эту сумму; редактируется как «План год», не как статус">
                      Утверждён · {{ c.plan }}
                    </div>
                  </div>
                  <div class="pe-fld">
                    <div class="pe-fld-l">Статус форензика</div>
                    <select class="pe-fld-i text" v-model="c.forensic">
                      <option value="">—</option>
                      <option value="Завершён">Завершён</option>
                      <option value="В процессе">В процессе</option>
                      <option :value="`Тендер в ${year}`">Тендер</option>
                      <option value="Не начат">Не начат</option>
                    </select>
                  </div>
                  <div class="pe-fld">
                    <div class="pe-fld-l">Аудитор</div>
                    <select class="pe-fld-i text" v-model="c.auditor">
                      <option value="">—</option>
                      <option value="KPMG">KPMG</option>
                      <option value="PwC">PwC</option>
                      <option value="Deloitte">Deloitte</option>
                      <option value="E&Y">E&amp;Y</option>
                    </select>
                  </div>
                  <div class="pe-fld">
                    <div class="pe-fld-l">Период аудита</div>
                    <input class="pe-fld-i text" type="text" placeholder="2024-2025"
                      v-model="c.aYears" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="pe-foot">
          <div class="pe-foot-l">
            <span v-if="totalChanges === 0">Нет изменений</span>
            <span v-else><b>{{ totalChanges }}</b> {{ totalChanges === 1 ? 'изменение' : 'изменений' }} в {{ working.filter((_, i) => changedCount(i) > 0).length }} компаниях</span>
          </div>
          <div class="pe-foot-r">
            <button class="pe-btn pe-btn-cancel" @click="requestClose">Отмена</button>
            <button class="pe-btn pe-btn-save" :disabled="totalChanges === 0" @click="save">
              Сохранить изменения
            </button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.pe-bg {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  z-index: 9000;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.pe-card {
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  width: 880px; max-width: 100%;
  max-height: 92dvh;
  display: flex; flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18);
  overflow: hidden;
}

.pe-h {
  padding: 14px 18px 12px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; justify-content: space-between;
}
.pe-h h3 { margin: 0; font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); letter-spacing: -.005em; }
.pe-h-sub { font-size: 11px; color: var(--t3, var(--t-muted)); margin-top: 2px; }
.pe-h-changes b { color: var(--green); font-weight: 600; }
.pe-x {
  cursor: pointer; width: 30px; height: 30px;
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  color: var(--t3, var(--t-muted)); background: none; border: none;
  transition: background .12s;
}
.pe-x:hover { background: #F4F3F9; color: var(--t1, #1E2A4A); }

.pe-co-list {
  overflow-y: auto;
  flex: 1;
  padding: 10px 14px;
}

.pe-co {
  margin-bottom: 7px;
  border: 1px solid rgba(0, 0, 0, .06);
  border-radius: 9px;
  background: var(--bg1, #fff);
  transition: border-color .15s, box-shadow .15s;
}
.pe-co:hover { border-color: rgba(127, 119, 221, .25); }
.pe-co.expanded {
  border-color: #7F77DD;
  box-shadow: 0 4px 16px rgba(127, 119, 221, .10);
}

.pe-co-h {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px;
  cursor: pointer; user-select: none;
}
.pe-co-h:hover { background: var(--bg2, #FAFAFC); }
.pe-co.expanded .pe-co-h {
  background: linear-gradient(to right, rgba(127, 119, 221, .05), transparent);
  border-radius: 9px 9px 0 0;
}
.pe-co-chev {
  color: var(--t3, var(--t-muted));
  transition: transform .25s ease;
}
.pe-co.expanded .pe-co-chev { transform: rotate(180deg); color: #7F77DD; }

.pe-sec-strip {
  display: inline-block; width: 3px; height: 16px;
  border-radius: 2px; flex-shrink: 0;
}
.pe-co-name {
  font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A);
  flex: 1;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pe-co-sec {
  font-size: 9.5px; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .04em; font-weight: 500;
  padding: 2px 7px; border-radius: 4px;
  background: #F4F3F9;
  margin-left: 6px;
}
.pe-co-changed {
  font-size: 9.5px; font-weight: 600;
  color: var(--green);
  background: rgba(29, 158, 117, .12);
  padding: 2px 7px; border-radius: 10px;
}
.pe-co-pct {
  font-size: 13px; font-weight: 600;
  font-feature-settings: "tnum";
  min-width: 44px; text-align: right;
}

.pe-body {
  border-top: 1px solid rgba(0, 0, 0, .06);
  background: linear-gradient(180deg, #FCFAFF 0%, #FFFFFF 100%);
  animation: pe-body-in .25s ease;
}
@keyframes pe-body-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: none; }
}
.pe-tab-cnt { padding: 14px; }
.pe-section-t {
  font-size: 10.5px; font-weight: 700;
  color: var(--p-deep);
  text-transform: uppercase; letter-spacing: .06em;
  margin-bottom: 8px;
}

.pe-grid { display: grid; gap: 10px; }
.pe-grid.cols-2 { grid-template-columns: repeat(2, 1fr); }
.pe-grid.cols-4 { grid-template-columns: repeat(4, 1fr); }
@media (max-width: 600px) {
  .pe-grid.cols-2, .pe-grid.cols-4 { grid-template-columns: 1fr; }
}

.pe-fld { display: flex; flex-direction: column; gap: 3px; }
.pe-fld-l {
  font-size: 9.5px; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .04em;
  font-weight: 600;
}
.pe-fld-i {
  font-size: 13px;
  padding: 7px 10px;
  border: 1px solid rgba(0, 0, 0, .08);
  border-radius: 7px;
  font-family: inherit;
  background: var(--bg1, #fff);
  transition: all .15s;
  width: 100%;
  box-sizing: border-box;
  font-feature-settings: "tnum";
  color: var(--t1, #1E2A4A);
}
.pe-fld-i:focus {
  outline: none;
  border-color: #7F77DD;
  box-shadow: 0 0 0 3px rgba(127, 119, 221, .1);
}
.pe-fld-i.text { font-feature-settings: normal; text-align: left; }
.pe-fld-i.num { text-align: right; }

.pe-foot {
  padding: 12px 18px;
  border-top: 1px solid rgba(0, 0, 0, .06);
  background: #FCFAFF;
  display: flex; justify-content: space-between; align-items: center;
}
.pe-foot-l { font-size: 11px; color: var(--t3, var(--t-muted)); }
.pe-foot-l b { color: var(--green); font-weight: 600; }
.pe-foot-r { display: flex; gap: 8px; }
.pe-btn {
  font-size: 12px;
  padding: 8px 16px;
  border-radius: 8px;
  font-family: inherit;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid;
  transition: all .12s;
}
.pe-btn-cancel { background: var(--bg1, #fff); color: var(--t3, var(--t-muted)); border-color: rgba(0, 0, 0, .12); }
.pe-btn-cancel:hover { background: #F4F3F9; color: var(--t1, #1E2A4A); }
.pe-btn-save { background: #7F77DD; color: #fff; border-color: #7F77DD; font-weight: 600; }
.pe-btn-save:hover:not(:disabled) {
  background: #6D62D6;
  box-shadow: 0 4px 12px rgba(127, 119, 221, .30);
}
.pe-btn-save:disabled { background: #CBD5E1; border-color: #CBD5E1; cursor: not-allowed; }

.pe-enter-active, .pe-leave-active { transition: opacity .2s; }
.pe-enter-active .pe-card,
.pe-leave-active .pe-card { transition: transform .25s, opacity .2s; }
.pe-enter-from .pe-card,
.pe-leave-to .pe-card { transform: scale(.97) translateY(8px); opacity: 0; }
.pe-enter-from, .pe-leave-to { opacity: 0; }
</style>
