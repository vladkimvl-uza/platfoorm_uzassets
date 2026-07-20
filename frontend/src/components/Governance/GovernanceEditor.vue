<script setup lang="ts">
/**
 * GovernanceEditor — редактор корп. управления компании (модалка).
 *
 * Две секции:
 *   • «Показатели» — GovernanceData за год (состав совета, комитеты,
 *     заседания, посещаемость, заметки) → governanceApi.upsertData
 *   • «Совет директоров» — CRUD членов совета → create/update/deleteMember
 *
 * Бэкенд гейтит governance.edit и пишет историю/модерацию (202 → на
 * модерацию). Данные общие с /governance → правки синхронизируются (оба
 * читают из одного источника; после сейва эмитим saved → родитель рефетчит).
 */
import { reactive, ref, computed } from "vue";
import {
  governanceApi,
  ROLE_TYPE_META,
  type GovernanceDataBrief,
  type BoardMemberBrief,
  type RoleType,
} from "@/api/governance";
import { isModerationQueued } from "@/api/client";
import { useConfirm } from "@/composables/useConfirm";
import { useToast } from "@/composables/useToast";
import ModalShell from "@/components/ModalShell.vue";

const { confirmDialog } = useConfirm();
const toast = useToast();

const props = defineProps<{
  companyId: string;
  companyName: string;
  year: number;
  data: GovernanceDataBrief | null;
  members: BoardMemberBrief[];
}>();

const emit = defineEmits<{ close: []; saved: [] }>();

const section = ref<"data" | "board">("data");
const saving = ref(false);
const err = ref<string | null>(null);
const queued = ref(false);

// ─── Секция «Показатели» ──────────────────────────────────────────
const form = reactive({
  board_size: props.data?.board_size ?? null as number | null,
  independent_directors_count: props.data?.independent_directors_count ?? null as number | null,
  women_directors_count: props.data?.women_directors_count ?? null as number | null,
  foreign_directors_count: props.data?.foreign_directors_count ?? null as number | null,
  avg_age: props.data?.avg_age ?? null as number | null,
  has_audit_committee: props.data?.has_audit_committee ?? false,
  has_strategy_committee: props.data?.has_strategy_committee ?? false,
  has_anticorr_committee: props.data?.has_anticorr_committee ?? false,
  has_induction_program: props.data?.has_induction_program ?? false,
  // «Комитет по назначениям и вознаграждениям» — ОДИН комитет (в БД два флага по
  // историческим причинам); UI ведёт одну галочку, на сохранении пишем оба разом.
  has_nomrem_committee: (props.data?.has_nomination_committee || props.data?.has_remuneration_committee) ?? false,
  // больше не показываются в редакторе/чипах, но сохраняем, чтобы не терять данные
  has_procurement_committee: props.data?.has_procurement_committee ?? false,
  has_esg_committee: props.data?.has_esg_committee ?? false,
  has_dno_insurance: props.data?.has_dno_insurance ?? false,
  meetings_per_year: props.data?.meetings_per_year ?? null as number | null,
  avg_attendance_pct: props.data?.avg_attendance_pct ?? null as number | null,
  notes: props.data?.notes ?? "",
});
// A4: dirty-guard — снимок исходного состояния для предупреждения при закрытии.
const _initialForm = JSON.stringify({ ...form });
async function requestClose(): Promise<void> {
  const dataChanged = JSON.stringify({ ...form }) !== _initialForm;
  const memberInProgress = showMemberForm.value && !!mForm.full_name.trim();
  if ((dataChanged || memberInProgress) &&
      !(await confirmDialog({ message: "Есть несохранённые изменения. Закрыть без сохранения?", danger: true }))) {
    return;
  }
  emit("close");
}

const numFields: { key: keyof typeof form; label: string; max?: number }[] = [
  { key: "board_size", label: "Размер совета" },
  { key: "independent_directors_count", label: "Независимых" },
  { key: "women_directors_count", label: "Женщин" },
  { key: "foreign_directors_count", label: "Иностранцев" },
  { key: "avg_age", label: "Средний возраст" },
  { key: "meetings_per_year", label: "Заседаний в год" },
  { key: "avg_attendance_pct", label: "Посещаемость, %", max: 100 },
];
// Единый набор «как на дашборде» (Состав НС → Комитеты).
const committees: { key: keyof typeof form; label: string }[] = [
  { key: "has_audit_committee", label: "Аудита" },
  { key: "has_strategy_committee", label: "Стратегии" },
  { key: "has_nomrem_committee", label: "По назначениям и вознаграждениям" },
  { key: "has_anticorr_committee", label: "Антикоррупционный" },
  { key: "has_induction_program", label: "Программа введения" },
];

function _num(v: unknown): number | null {
  if (v === "" || v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

// A5: связность данных — независимых/женщин/иностранцев ≤ размера совета и т.п.
function validateData(): string | null {
  const size = _num(form.board_size);
  const checks: [number | null, string][] = [
    [_num(form.independent_directors_count), "Независимых директоров"],
    [_num(form.women_directors_count), "Женщин"],
    [_num(form.foreign_directors_count), "Иностранцев"],
  ];
  for (const [n, lbl] of checks) {
    if (n != null && n < 0) return `${lbl}: значение не может быть отрицательным`;
    if (n != null && size != null && n > size) return `${lbl} (${n}) больше размера совета (${size})`;
  }
  const att = _num(form.avg_attendance_pct);
  if (att != null && (att < 0 || att > 100)) return "Посещаемость должна быть в диапазоне 0–100%";
  const age = _num(form.avg_age);
  if (age != null && (age < 18 || age > 100)) return "Средний возраст вне диапазона 18–100";
  return null;
}

// A1-lite: агрегаты состава считаются из списка членов совета (один источник).
const boardAgg = computed(() => ({
  board_size: localMembers.value.length,
  independent: localMembers.value.filter(m => m.is_independent).length,
  women: localMembers.value.filter(m => m.is_woman).length,
  foreign: localMembers.value.filter(m => m.is_foreign).length,
}));
function fillFromBoard(): void {
  form.board_size = boardAgg.value.board_size;
  form.independent_directors_count = boardAgg.value.independent;
  form.women_directors_count = boardAgg.value.women;
  form.foreign_directors_count = boardAgg.value.foreign;
  toast.info("Подставлено из состава совета — проверьте и сохраните");
}

async function saveData(): Promise<void> {
  const verr = validateData();
  if (verr) { err.value = verr; toast.error(verr); return; }
  saving.value = true; err.value = null; queued.value = false;
  try {
    const res = await governanceApi.upsertData({
      company_id: props.companyId,
      year: props.year,
      board_size: _num(form.board_size),
      independent_directors_count: _num(form.independent_directors_count),
      women_directors_count: _num(form.women_directors_count),
      foreign_directors_count: _num(form.foreign_directors_count),
      avg_age: _num(form.avg_age),
      has_audit_committee: form.has_audit_committee,
      has_strategy_committee: form.has_strategy_committee,
      has_anticorr_committee: form.has_anticorr_committee,
      has_procurement_committee: form.has_procurement_committee,
      has_esg_committee: form.has_esg_committee,
      has_dno_insurance: form.has_dno_insurance,
      has_induction_program: form.has_induction_program,
      // Один комитет → пишем оба исторических флага одинаково.
      has_remuneration_committee: form.has_nomrem_committee,
      has_nomination_committee: form.has_nomrem_committee,
      meetings_per_year: _num(form.meetings_per_year),
      avg_attendance_pct: _num(form.avg_attendance_pct),
      notes: form.notes.trim() || null,
    });
    if (isModerationQueued(res)) { queued.value = true; toast.info("Отправлено на модерацию"); setTimeout(() => emit("saved"), 1200); }
    else { toast.success("Показатели сохранены"); emit("saved"); }
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || "Не удалось сохранить";
    err.value = msg; toast.error(msg);
  } finally { saving.value = false; }
}

// ─── Секция «Совет директоров» ────────────────────────────────────
const localMembers = ref<BoardMemberBrief[]>([...props.members]);
const editingMember = ref<BoardMemberBrief | null>(null);
const showMemberForm = ref(false);

const mForm = reactive({
  full_name: "", position: "", role_type: "" as RoleType | "",
  is_independent: false, is_woman: false, is_foreign: false,
  appointed_date: "", term_end_date: "", email: "", phone: "", bio: "",
});

function openAddMember(): void {
  editingMember.value = null;
  Object.assign(mForm, {
    full_name: "", position: "", role_type: "", is_independent: false,
    is_woman: false, is_foreign: false, appointed_date: "", term_end_date: "",
    email: "", phone: "", bio: "",
  });
  err.value = null; showMemberForm.value = true;
}
function openEditMember(m: BoardMemberBrief): void {
  editingMember.value = m;
  Object.assign(mForm, {
    full_name: m.full_name || "", position: m.position || "",
    role_type: (m.role_type || "") as RoleType | "",
    is_independent: !!m.is_independent, is_woman: !!m.is_woman, is_foreign: !!m.is_foreign,
    appointed_date: m.appointed_date || "", term_end_date: m.term_end_date || "",
    email: (m as any).email || "", phone: (m as any).phone || "", bio: m.bio || "",
  });
  err.value = null; showMemberForm.value = true;
}

async function saveMember(): Promise<void> {
  if (!mForm.full_name.trim()) { err.value = "Укажите ФИО"; toast.error("Укажите ФИО"); return; }
  if (mForm.appointed_date && mForm.term_end_date && mForm.term_end_date <= mForm.appointed_date) {
    const m = "«Срок до» должен быть позже даты назначения"; err.value = m; toast.error(m); return;
  }
  saving.value = true; err.value = null; queued.value = false;
  const payload = {
    full_name: mForm.full_name.trim(),
    position: mForm.position.trim() || null,
    role_type: (mForm.role_type || null) as RoleType | null,
    is_independent: mForm.is_independent,
    is_woman: mForm.is_woman,
    is_foreign: mForm.is_foreign,
    appointed_date: mForm.appointed_date || null,
    term_end_date: mForm.term_end_date || null,
    email: mForm.email.trim() || null,
    phone: mForm.phone.trim() || null,
    bio: mForm.bio.trim() || null,
  };
  try {
    const res = editingMember.value
      ? await governanceApi.updateMember(editingMember.value.id, payload)
      : await governanceApi.createMember({ company_id: props.companyId, ...payload });
    if (isModerationQueued(res)) {
      queued.value = true; toast.info("Отправлено на модерацию");
      setTimeout(() => { showMemberForm.value = false; emit("saved"); }, 1200);
    } else {
      // Локально обновляем список (редактор остаётся открыт для следующих правок)
      const saved = res as BoardMemberBrief;
      if (editingMember.value) {
        const i = localMembers.value.findIndex(x => x.id === editingMember.value!.id);
        if (i >= 0) localMembers.value[i] = saved;
      } else {
        localMembers.value.push(saved);
      }
      showMemberForm.value = false;
      toast.success(editingMember.value ? "Член совета обновлён" : "Член совета добавлен");
      emit("saved");
    }
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || "Не удалось сохранить члена совета";
    err.value = msg; toast.error(msg);
  } finally { saving.value = false; }
}

async function removeMember(m: BoardMemberBrief): Promise<void> {
  if (!(await confirmDialog({ message: `Удалить «${m.full_name}» из совета?`, danger: true }))) return;
  saving.value = true; err.value = null;
  try {
    await governanceApi.deleteMember(m.id);
    localMembers.value = localMembers.value.filter(x => x.id !== m.id);
    toast.success("Член совета удалён");
    emit("saved");
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || "Не удалось удалить";
    err.value = msg; toast.error(msg);
  } finally { saving.value = false; }
}

function roleMeta(r: RoleType | string | null): { label: string; color: string } {
  const found = ROLE_TYPE_META.find(x => x.key === r);
  return found ? { label: found.label, color: found.color } : { label: "—", color: "#94A3B8" };
}
const ROLE_OPTIONS = computed(() => ROLE_TYPE_META);
</script>

<template>
  <ModalShell :open="true" size="md" @close="requestClose">
    <template #header>
      <div>
        <div class="ge-eyebrow">Корп. управление · FY {{ year }}</div>
        <h2 class="ge-title">{{ companyName }}</h2>
      </div>
    </template>

      <div class="ge-tabs">
        <button :class="{ on: section === 'data' }" @click="section = 'data'">Показатели</button>
        <button :class="{ on: section === 'board' }" @click="section = 'board'">
          Совет директоров <span class="ge-tab-count">{{ localMembers.length }}</span>
        </button>
      </div>

      <div class="ge-body">
        <p v-if="err" class="ge-err">{{ err }}</p>
        <p v-if="queued" class="ge-queued">Отправлено на модерацию</p>

        <!-- ─── ПОКАЗАТЕЛИ ─── -->
        <template v-if="section === 'data'">
          <div v-if="localMembers.length" class="ge-autofill">
            <span class="ge-autofill-hint">Состав совета: {{ boardAgg.board_size }} чел · {{ boardAgg.independent }} незав. · {{ boardAgg.women }} жен. · {{ boardAgg.foreign }} иностр.</span>
            <button type="button" class="ge-autofill-btn" :disabled="saving" @click="fillFromBoard">Подставить из совета</button>
          </div>
          <div class="ge-grid">
            <label v-for="f in numFields" :key="f.key" class="ge-field">
              <span class="ge-label">{{ f.label }}</span>
              <input type="number" class="ge-in" v-model="form[f.key as keyof typeof form]"
                     min="0" :max="f.max" :disabled="saving" />
            </label>
          </div>

          <div class="ge-subsection">
            <div class="ge-sub-label">Комитеты совета</div>
            <div class="ge-checks">
              <label v-for="c in committees" :key="c.key" class="ge-check">
                <input type="checkbox" v-model="form[c.key as keyof typeof form]" :disabled="saving" />
                <span>{{ c.label }}</span>
              </label>
            </div>
          </div>

          <label class="ge-field">
            <span class="ge-label">Заметки</span>
            <textarea class="ge-in ge-textarea" v-model="form.notes" rows="3" :disabled="saving"
                      placeholder="Комментарии по корп. управлению…"></textarea>
          </label>

          <div class="ge-actions">
            <button class="ge-btn ge-btn-ghost" @click="requestClose" :disabled="saving">Отмена</button>
            <button class="ge-btn ge-btn-primary" @click="saveData" :disabled="saving">
              <span v-if="saving" class="ge-spin"></span>{{ saving ? "" : "Сохранить показатели" }}
            </button>
          </div>
        </template>

        <!-- ─── СОВЕТ ДИРЕКТОРОВ ─── -->
        <template v-else>
          <!-- форма члена -->
          <div v-if="showMemberForm" class="ge-member-form">
            <div class="ge-sub-label">{{ editingMember ? "Редактирование члена" : "Новый член совета" }}</div>
            <div class="ge-grid">
              <label class="ge-field ge-field-wide">
                <span class="ge-label">ФИО *</span>
                <input class="ge-in" v-model="mForm.full_name" :disabled="saving" placeholder="Иванов Иван Иванович" />
              </label>
              <label class="ge-field ge-field-wide">
                <span class="ge-label">Должность</span>
                <input class="ge-in" v-model="mForm.position" :disabled="saving" placeholder="Председатель совета" />
              </label>
              <label class="ge-field">
                <span class="ge-label">Роль</span>
                <select class="ge-in" v-model="mForm.role_type" :disabled="saving">
                  <option value="">—</option>
                  <option v-for="r in ROLE_OPTIONS" :key="r.key" :value="r.key">{{ r.label }}</option>
                </select>
              </label>
              <label class="ge-field">
                <span class="ge-label">Назначен</span>
                <input type="date" class="ge-in" v-model="mForm.appointed_date" :disabled="saving" />
              </label>
              <label class="ge-field">
                <span class="ge-label">Срок до</span>
                <input type="date" class="ge-in" v-model="mForm.term_end_date" :disabled="saving" />
              </label>
              <label class="ge-field">
                <span class="ge-label">Email</span>
                <input type="email" class="ge-in" v-model="mForm.email" :disabled="saving" placeholder="name@company.uz" />
              </label>
              <label class="ge-field">
                <span class="ge-label">Телефон</span>
                <input type="tel" class="ge-in" v-model="mForm.phone" :disabled="saving" placeholder="+998 90 123 45 67" />
              </label>
            </div>
            <div class="ge-checks">
              <label class="ge-check"><input type="checkbox" v-model="mForm.is_independent" :disabled="saving" /><span>Независимый</span></label>
              <label class="ge-check"><input type="checkbox" v-model="mForm.is_woman" :disabled="saving" /><span>Женщина</span></label>
              <label class="ge-check"><input type="checkbox" v-model="mForm.is_foreign" :disabled="saving" /><span>Иностранец</span></label>
            </div>
            <label class="ge-field">
              <span class="ge-label">Биография</span>
              <textarea class="ge-in ge-textarea" v-model="mForm.bio" rows="2" :disabled="saving"></textarea>
            </label>
            <div class="ge-actions">
              <button class="ge-btn ge-btn-ghost" @click="showMemberForm = false" :disabled="saving">Отмена</button>
              <button class="ge-btn ge-btn-primary" @click="saveMember" :disabled="saving">
                <span v-if="saving" class="ge-spin"></span>{{ saving ? "" : "Сохранить" }}
              </button>
            </div>
          </div>

          <!-- список -->
          <template v-else>
            <button class="ge-add-btn" @click="openAddMember">＋ Добавить члена совета</button>
            <div v-if="localMembers.length === 0" class="ge-empty">Члены совета не заведены</div>
            <div v-else class="ge-member-list">
              <div v-for="m in localMembers" :key="m.id" class="ge-member-row">
                <div class="ge-member-main">
                  <div class="ge-member-name">{{ m.full_name }}</div>
                  <div class="ge-member-sub">
                    <span v-if="m.position">{{ m.position }}</span>
                    <span class="ge-role-pill" :style="{ background: roleMeta(m.role_type).color + '22', color: roleMeta(m.role_type).color }">
                      {{ roleMeta(m.role_type).label }}
                    </span>
                    <span v-if="m.is_independent" class="ge-mini-badge">Незав.</span>
                    <span v-if="m.is_woman" class="ge-mini-badge">Жен.</span>
                    <span v-if="m.is_foreign" class="ge-mini-badge">Иностр.</span>
                  </div>
                </div>
                <div class="ge-member-acts">
                  <button class="ge-icon-btn" @click="openEditMember(m)" title="Редактировать" aria-label="Редактировать">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>
                  </button>
                  <button class="ge-icon-btn ge-icon-del" @click="removeMember(m)" title="Удалить" aria-label="Удалить">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
                  </button>
                </div>
              </div>
            </div>
          </template>
        </template>
      </div>
  </ModalShell>
</template>

<style scoped>
/* Шелл (backdrop/модалка/шапка/закрытие) — теперь через ModalShell. */
.ge-eyebrow { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.07em; color: var(--t3, #64748B); }
.ge-title { font-size: 17px; font-weight: 600; color: var(--t1, #1E2A4A); margin: 3px 0 0; }
.ge-tabs { display: flex; gap: 4px; padding: 4px 0 0; margin-bottom: 4px; border-bottom: 1px solid var(--border-hard, #E5E7EB); }
.ge-tabs button {
  background: none; border: none; padding: 8px 14px 12px; font-size: 13px; font-weight: 500;
  color: var(--t3, #64748B); cursor: pointer; border-bottom: 2px solid transparent; font-family: inherit;
}
.ge-tabs button.on { color: var(--p-deep, #534AB7); border-bottom-color: var(--p, #7C6FF7); }
.ge-tab-count { font-size: 10.5px; background: rgba(124, 111, 247, 0.12); color: var(--p-deep, #534AB7); padding: 1px 6px; border-radius: 7px; margin-left: 3px; }
.ge-body { padding: 14px 0 0; }
.ge-err { font-size: 12px; color: var(--sev-high, #E24B4A); margin: 0 0 10px; }
.ge-queued { font-size: 12px; color: var(--p-deep, #534AB7); font-weight: 500; margin: 0 0 10px; }
.ge-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.ge-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.ge-field-wide { grid-column: 1 / -1; }
.ge-label { font-size: 11px; font-weight: 500; color: var(--t3, #64748B); }
.ge-in {
  width: 100%; box-sizing: border-box; border: 1.5px solid var(--border-input, #E2E8F0);
  border-radius: 8px; background: var(--bg2, #F8FAFC); padding: 8px 10px;
  font-size: 13px; font-family: inherit; color: var(--t1, #1E2A4A); outline: none;
  transition: border-color 0.14s, box-shadow 0.14s;
}
.ge-in:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124, 111, 247, 0.14); }
.ge-textarea { resize: vertical; }
.ge-subsection { margin-top: 16px; }
.ge-sub-label { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; color: var(--t3, #64748B); margin-bottom: 8px; }
.ge-checks { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 6px; }
.ge-check { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--t2, #334155); cursor: pointer; }
.ge-check input { width: 15px; height: 15px; accent-color: var(--p, #7C6FF7); }
.ge-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
.ge-btn {
  border: none; border-radius: 8px; padding: 9px 18px; font-size: 13px; font-weight: 600;
  cursor: pointer; font-family: inherit; display: inline-flex; align-items: center; gap: 6px; min-height: 36px; transition: all 0.14s;
}
.ge-btn:disabled { opacity: 0.6; cursor: default; }
.ge-btn-ghost { background: transparent; border: 1px solid var(--border-input, #E2E8F0); color: var(--t2, #334155); }
.ge-btn-ghost:hover:not(:disabled) { background: var(--bg3, #F1F5F9); }
.ge-btn-primary { background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); color: #fff; box-shadow: 0 2px 10px rgba(108, 92, 231, 0.32); }
.ge-btn-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(108, 92, 231, 0.45); }
.ge-spin { width: 14px; height: 14px; border: 2px solid rgba(255, 255, 255, 0.4); border-top-color: #fff; border-radius: 50%; animation: geSpin 0.7s linear infinite; }
@keyframes geSpin { to { transform: rotate(360deg); } }
.ge-add-btn {
  width: 100%; padding: 10px; border: 1.5px dashed var(--border-input, #CBD5E1); border-radius: 10px;
  background: transparent; color: var(--p-deep, #534AB7); font-size: 13px; font-weight: 500; cursor: pointer;
  font-family: inherit; transition: all 0.14s; margin-bottom: 12px;
}
.ge-add-btn:hover { border-color: var(--p, #7C6FF7); background: rgba(124, 111, 247, 0.05); }
.ge-empty { text-align: center; color: var(--t3, #94A3B8); font-size: 13px; padding: 20px; }
.ge-member-list { display: flex; flex-direction: column; gap: 8px; }
.ge-member-row {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 10px 12px; border: 1px solid var(--border-hard, #E5E7EB); border-radius: 10px;
}
.ge-member-name { font-size: 13.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.ge-member-sub { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 4px; font-size: 11.5px; color: var(--t3, #64748B); }
.ge-role-pill { font-size: 10.5px; font-weight: 600; padding: 1px 7px; border-radius: 6px; }
.ge-mini-badge { font-size: 10px; font-weight: 500; padding: 1px 6px; border-radius: 5px; background: var(--bg3, #F1F5F9); color: var(--t2, #475569); }
.ge-member-acts { display: flex; gap: 4px; flex-shrink: 0; }
.ge-icon-btn { width: 30px; height: 30px; border-radius: 7px; border: 1px solid var(--border-input, #E2E8F0); background: #fff; cursor: pointer; color: var(--t2, #475569); transition: all 0.14s; display: inline-flex; align-items: center; justify-content: center; }
/* A1-lite: автоподстановка состава из совета */
.ge-autofill { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; padding: 9px 12px; background: rgba(124, 111, 247, 0.06); border: 1px solid rgba(124, 111, 247, 0.16); border-radius: 9px; }
.ge-autofill-hint { font-size: 11px; color: var(--t3, #64748B); }
.ge-autofill-btn { padding: 6px 12px; font-size: 11.5px; font-weight: 600; border: 1px solid rgba(124, 111, 247, 0.35); border-radius: 7px; background: #fff; color: var(--p-deep, #534AB7); cursor: pointer; font-family: inherit; transition: all 0.14s; white-space: nowrap; }
.ge-autofill-btn:hover:not(:disabled) { background: var(--p, #7C6FF7); color: #fff; border-color: var(--p, #7C6FF7); }
.ge-autofill-btn:disabled { opacity: 0.6; cursor: default; }
.ge-icon-btn:hover { border-color: var(--p, #7C6FF7); color: var(--p-deep, #534AB7); }
.ge-icon-del:hover { border-color: var(--sev-high, #E24B4A); color: var(--sev-high, #E24B4A); }
.ge-member-form { display: flex; flex-direction: column; gap: 12px; }

@media (max-width: 480px) {
  .ge-modal { max-width: 100%; margin: 0 8px; max-height: 92dvh; }
  .ge-icon-btn, .ge-icon-del { width: 34px; height: 34px; }
}
</style>
