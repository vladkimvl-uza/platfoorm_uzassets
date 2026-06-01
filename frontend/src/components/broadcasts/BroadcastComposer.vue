<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  broadcastsApi,
  type AckMode, type ScheduleMode, type Template, type TemplatePayload,
  type RecipientPreview,
} from "@/api/admin_broadcasts";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();

const props = defineProps<{ templateId: string }>();
const emit = defineEmits<{ saved: []; deleted: [] }>();

const template = ref<Template | null>(null);
const draft = ref<Partial<TemplatePayload>>({});
const preview = ref<RecipientPreview | null>(null);
const previewLoading = ref(false);
const saving = ref(false);
const dirty = ref(false);
const error = ref<string | null>(null);

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

async function loadTemplate() {
  error.value = null;
  try {
    template.value = await broadcastsApi.getTemplate(props.templateId);
    draft.value = JSON.parse(JSON.stringify(template.value));
    dirty.value = false;
    await refreshPreview();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

onMounted(loadTemplate);
watch(() => props.templateId, loadTemplate);

function markDirty() { dirty.value = true; }

async function refreshPreview() {
  previewLoading.value = true;
  try { preview.value = await broadcastsApi.previewRecipients(props.templateId); }
  catch (e: any) { /* silent */ }
  finally { previewLoading.value = false; }
}

async function save() {
  if (!draft.value) return;
  saving.value = true;
  error.value = null;
  try {
    const updated = await broadcastsApi.updateTemplate(props.templateId, draft.value as Partial<TemplatePayload>);
    template.value = updated;
    draft.value = JSON.parse(JSON.stringify(updated));
    dirty.value = false;
    emit("saved");
    await refreshPreview();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { saving.value = false; }
}

async function activate() {
  if (dirty.value) await save();
  if (!template.value) return;
  try {
    await broadcastsApi.updateTemplate(props.templateId, { is_active: true });
    await loadTemplate();
    emit("saved");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function testOnSelf() {
  try {
    if (dirty.value) await save();
    await broadcastsApi.testOnSelf(props.templateId);
    alert("Тестовая рассылка отправлена вам");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function sendNow() {
  if (!confirm("Отправить сейчас всем получателям?")) return;
  try {
    if (dirty.value) await save();
    await broadcastsApi.sendNow(props.templateId);
    alert("Рассылка отправлена");
    emit("saved");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function removeTemplate() {
  if (!confirm(`Удалить рассылку "${draft.value?.name}"?`)) return;
  try {
    await broadcastsApi.deleteTemplate(props.templateId);
    emit("deleted");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

function setScheduleMode(m: ScheduleMode) {
  draft.value.schedule_mode = m;
  if (m === "interval" && !draft.value.schedule_config) {
    draft.value.schedule_config = {
      weekdays: [4], time: "09:00", tz: "Asia/Tashkent",
    };
  }
  markDirty();
}

function toggleWeekday(d: number) {
  const cfg = draft.value.schedule_config || { weekdays: [], time: "09:00", tz: "Asia/Tashkent" };
  const wd = [...(cfg.weekdays || [])];
  const i = wd.indexOf(d);
  if (i >= 0) wd.splice(i, 1); else wd.push(d);
  draft.value.schedule_config = { ...cfg, weekdays: wd };
  markDirty();
}

function setAckMode(mode: AckMode) {
  draft.value.ack_mode = mode;
  if (mode === "select" && !draft.value.ack_options) {
    draft.value.ack_options = ["До конца дня", "Завтра", "Нужна помощь"];
  }
  markDirty();
}

function addAckOption() {
  draft.value.ack_options = [...(draft.value.ack_options || []), "Новый вариант"];
  markDirty();
}
function removeAckOption(i: number) {
  const list = [...(draft.value.ack_options || [])];
  list.splice(i, 1);
  draft.value.ack_options = list;
  markDirty();
}

function setGroupCodesFromText(text: string) {
  const items = text.split(",").map((s) => s.trim()).filter(Boolean);
  draft.value.target_group_codes = items.length ? items : null;
  markDirty();
}
function setRoleCodesFromText(text: string) {
  const items = text.split(",").map((s) => s.trim()).filter(Boolean);
  draft.value.target_role_codes = items.length ? items : null;
  markDirty();
}

const targetCount = computed(() => preview.value?.total ?? 0);
</script>

<template>
  <div v-if="template && draft" class="bc-wrap">

    <div v-if="error" class="bc-err">{{ error }} <button @click="error = null">×</button></div>

    <div class="bc-grid">

      <!-- Section 1: Content -->
      <div class="bc-card">
        <div class="bc-card-hd">
          <span class="bc-num">1</span> Содержание
        </div>
        <div class="bc-card-body">
          <div class="bc-field">
            <label>Имя шаблона</label>
            <input v-model="draft.name" @input="markDirty"/>
          </div>

          <div class="bc-field">
            <label>Тип</label>
            <div class="bc-chips">
              <button v-for="t in ['announcement','policy','training','survey','reminder']" :key="t"
                      class="bc-chip" :class="{ active: draft.type === t }"
                      @click="(e) => { draft.type = t; markDirty(); }">
                {{ ({ announcement: "Объявление", policy: "Политика", training: "Обучение", survey: "Опрос", reminder: "Напоминание" } as Record<string, string>)[t] }}
              </button>
            </div>
          </div>

          <div class="bc-field">
            <label>Приоритет</label>
            <div class="bc-chips">
              <button v-for="p in ['low','normal','high','critical']" :key="p"
                      class="bc-chip" :class="`prio-${p}`" :class-list="{ active: draft.priority === p }"
                      :style="draft.priority === p ? { background: '#7F77DD', color: '#fff', borderColor: '#7F77DD' } : {}"
                      @click="(e) => { draft.priority = p as any; markDirty(); }">
                {{ p }}
              </button>
            </div>
          </div>

          <div class="bc-field">
            <label>Заголовок</label>
            <input v-model="draft.title" @input="markDirty"/>
          </div>

          <div class="bc-field">
            <label>Текст (markdown)</label>
            <textarea v-model="draft.body" rows="4" @input="markDirty"></textarea>
          </div>

          <div class="bc-field">
            <label>Ссылка</label>
            <input v-model="draft.link_url" placeholder="https://..." @input="markDirty"/>
          </div>
        </div>
      </div>

      <!-- Section 2: Targeting -->
      <div class="bc-card">
        <div class="bc-card-hd">
          <span class="bc-num">2</span> Получатели
          <span class="bc-target-cnt" :class="{ loading: previewLoading }">
            {{ previewLoading ? "..." : targetCount }} чел.
          </span>
        </div>
        <div class="bc-card-body">

          <label class="bc-check">
            <input type="checkbox" :checked="draft.target_all"
                   @change="(e) => { draft.target_all = (e.target as HTMLInputElement).checked; markDirty(); refreshPreview(); }"/>
            <b>Все активные пользователи</b>
          </label>

          <div v-if="!draft.target_all" class="bc-target-block">
            <div class="bc-field">
              <label>Группы (codes через запятую)</label>
              <input :value="(draft.target_group_codes || []).join(', ')"
                     placeholder="cfo, head_of_finance, ..."
                     @blur="(e) => { setGroupCodesFromText((e.target as HTMLInputElement).value); refreshPreview(); }"/>
            </div>
            <div class="bc-field">
              <label>Роли (codes через запятую)</label>
              <input :value="(draft.target_role_codes || []).join(', ')"
                     placeholder="financier, department_head, ..."
                     @blur="(e) => { setRoleCodesFromText((e.target as HTMLInputElement).value); refreshPreview(); }"/>
            </div>
            <div class="bc-field">
              <label>Конкретные UserIDs (UUID через запятую)</label>
              <input :value="(draft.target_user_ids || []).join(', ')"
                     placeholder="uuid1, uuid2..."
                     @blur="(e) => { const t = (e.target as HTMLInputElement).value; draft.target_user_ids = t.trim() ? t.split(',').map(s => s.trim()).filter(Boolean) : null; markDirty(); refreshPreview(); }"/>
            </div>
          </div>

          <div v-if="preview && preview.sample.length" class="bc-preview">
            <div class="bc-preview-hd">Образец получателей · показано {{ preview.sample.length }} из {{ preview.total }}</div>
            <div class="bc-preview-list">
              <span v-for="u in preview.sample.slice(0, 12)" :key="u.id" class="bc-preview-chip">
                {{ u.full_name || u.email }}
              </span>
              <span v-if="preview.total > 12" class="bc-preview-chip more">+{{ preview.total - 12 }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Section 3: Schedule -->
      <div class="bc-card">
        <div class="bc-card-hd">
          <span class="bc-num">3</span> Расписание
        </div>
        <div class="bc-card-body">
          <div class="bc-chips">
            <button class="bc-chip" :class="{ active: draft.schedule_mode === 'oneshot' }" @click="setScheduleMode('oneshot')">Однократно</button>
            <button class="bc-chip" :class="{ active: draft.schedule_mode === 'interval' }" @click="setScheduleMode('interval')">Повторяющееся</button>
            <button class="bc-chip" :class="{ active: draft.schedule_mode === 'cron' }" @click="setScheduleMode('cron')">Cron</button>
          </div>

          <div v-if="draft.schedule_mode === 'oneshot'" class="bc-sched-block">
            <div class="bc-field">
              <label>Когда отправить (datetime)</label>
              <input type="datetime-local"
                     :value="draft.schedule_start_at ? draft.schedule_start_at.slice(0, 16) : ''"
                     @change="(e) => { const v = (e.target as HTMLInputElement).value; draft.schedule_start_at = v ? new Date(v).toISOString() : null; markDirty(); }"/>
            </div>
          </div>

          <div v-else-if="draft.schedule_mode === 'interval'" class="bc-sched-block">
            <div class="bc-field">
              <label>Дни недели</label>
              <div class="bc-weekdays">
                <button v-for="(d, i) in WEEKDAYS" :key="i"
                        class="bc-wd"
                        :class="{ active: (draft.schedule_config?.weekdays || []).includes(i) }"
                        @click="toggleWeekday(i)">
                  {{ d }}
                </button>
              </div>
            </div>
            <div class="bc-field bc-field-row">
              <div style="flex: 1">
                <label>Время</label>
                <input type="time"
                       :value="draft.schedule_config?.time || '09:00'"
                       @input="(e) => { draft.schedule_config = { ...(draft.schedule_config || {}), time: (e.target as HTMLInputElement).value }; markDirty(); }"/>
              </div>
              <div style="flex: 1">
                <label>Timezone</label>
                <input :value="draft.schedule_config?.tz || 'Asia/Tashkent'"
                       @input="(e) => { draft.schedule_config = { ...(draft.schedule_config || {}), tz: (e.target as HTMLInputElement).value }; markDirty(); }"/>
              </div>
            </div>
            <div class="bc-field bc-field-row">
              <div style="flex: 1">
                <label>Окно от</label>
                <input type="date"
                       :value="draft.schedule_start_at ? draft.schedule_start_at.slice(0, 10) : ''"
                       @change="(e) => { const v = (e.target as HTMLInputElement).value; draft.schedule_start_at = v ? new Date(v).toISOString() : null; markDirty(); }"/>
              </div>
              <div style="flex: 1">
                <label>до</label>
                <input type="date"
                       :value="draft.schedule_end_at ? draft.schedule_end_at.slice(0, 10) : ''"
                       @change="(e) => { const v = (e.target as HTMLInputElement).value; draft.schedule_end_at = v ? new Date(v).toISOString() : null; markDirty(); }"/>
              </div>
            </div>
            <div v-if="template.next_run_at" class="bc-next-run">
              <i class="ti ti-clock" style="font-size: 12px;" aria-hidden="true"></i>
              Следующая отправка: <b>{{ fmt.fmtDateTime(template.next_run_at) }}</b>
            </div>
          </div>

          <div v-else-if="draft.schedule_mode === 'cron'" class="bc-sched-block">
            <div class="bc-field">
              <label>Cron expression</label>
              <input :value="draft.schedule_config?.cron || ''"
                     placeholder="0 9 * * 5"
                     @input="(e) => { draft.schedule_config = { ...(draft.schedule_config || {}), cron: (e.target as HTMLInputElement).value }; markDirty(); }"/>
            </div>
            <div style="font-size: 10px; color: var(--color-text-tertiary);">
              Cron-режим ещё не реализован в scheduler. Используйте interval с weekdays.
            </div>
          </div>
        </div>
      </div>

      <!-- Section 4: Ack -->
      <div class="bc-card">
        <div class="bc-card-hd">
          <span class="bc-num">4</span> Обратная связь
        </div>
        <div class="bc-card-body">
          <div class="bc-field">
            <label>Режим</label>
            <div class="bc-chips">
              <button v-for="m in (['none','click','text','select','yesno','file'] as AckMode[])" :key="m"
                      class="bc-chip"
                      :class="{ active: draft.ack_mode === m }"
                      @click="setAckMode(m)">
                {{ ({ none: "Не требуется", click: "Click", text: "Текст", select: "Список", yesno: "Yes/No", file: "Файл" } as Record<string,string>)[m] }}
              </button>
            </div>
          </div>

          <div v-if="draft.ack_mode !== 'none'" class="bc-ack-block">
            <div class="bc-field">
              <label>Вопрос для получателя</label>
              <input v-model="draft.ack_question"
                     placeholder="Когда будете готовы?"
                     @input="markDirty"/>
            </div>

            <div v-if="draft.ack_mode === 'select'" class="bc-field">
              <label>Варианты ответа</label>
              <div class="bc-ack-options">
                <div v-for="(opt, i) in (draft.ack_options || [])" :key="i" class="bc-ack-opt">
                  <input :value="opt"
                         @input="(e) => { const list = [...(draft.ack_options || [])]; list[i] = (e.target as HTMLInputElement).value; draft.ack_options = list; markDirty(); }"/>
                  <button class="bc-x" @click="removeAckOption(i)"><i class="ti ti-x" aria-hidden="true"></i></button>
                </div>
                <button class="bc-add" @click="addAckOption">
                  <i class="ti ti-plus" aria-hidden="true"></i> вариант
                </button>
              </div>
            </div>
          </div>

          <div class="bc-toggle-list">
            <label class="bc-toggle">
              <input type="checkbox" :checked="draft.is_sticky"
                     @change="(e) => { draft.is_sticky = (e.target as HTMLInputElement).checked; markDirty(); }"/>
              <span><b>Sticky</b> — модалка блокирует UI пока не подтверждено</span>
              <span v-if="draft.is_sticky" class="bc-warn-pill">ВНИМАНИЕ</span>
            </label>
            <label class="bc-toggle">
              <span>Дедлайн ответа через</span>
              <input type="number" :value="draft.ack_deadline_hours ?? ''" placeholder="—"
                     @input="(e) => { const v = (e.target as HTMLInputElement).valueAsNumber; draft.ack_deadline_hours = Number.isFinite(v) ? v : null; markDirty(); }"
                     style="width: 70px;"/>
              <span>часов</span>
            </label>
            <label class="bc-toggle">
              <span>Авто-resend если не открыто через</span>
              <input type="number" :value="draft.auto_resend_hours ?? ''" placeholder="—"
                     @input="(e) => { const v = (e.target as HTMLInputElement).valueAsNumber; draft.auto_resend_hours = Number.isFinite(v) ? v : null; markDirty(); }"
                     style="width: 70px;"/>
              <span>часов</span>
            </label>
            <label class="bc-toggle">
              <input type="checkbox" :checked="draft.escalate_to_manager"
                     @change="(e) => { draft.escalate_to_manager = (e.target as HTMLInputElement).checked; markDirty(); }"/>
              <span>Эскалировать руководителю после дедлайна</span>
            </label>
            <label class="bc-toggle">
              <input type="checkbox" :checked="draft.show_site_banner_on_overdue"
                     @change="(e) => { draft.show_site_banner_on_overdue = (e.target as HTMLInputElement).checked; markDirty(); }"/>
              <span>Site-wide banner при просрочке (для sticky)</span>
            </label>
          </div>
        </div>
      </div>

    </div>

    <div class="bc-footer">
      <button class="bc-btn bc-btn-danger" @click="removeTemplate">
        <i class="ti ti-trash" aria-hidden="true"></i> Удалить
      </button>
      <div style="flex: 1"></div>
      <span v-if="dirty" class="bc-dirty">несохранённые изменения</span>
      <button class="bc-btn bc-btn-ghost" @click="testOnSelf">
        <i class="ti ti-test-pipe" aria-hidden="true"></i> Test на себя
      </button>
      <button class="bc-btn bc-btn-ghost" @click="save" :disabled="saving || !dirty">
        {{ saving ? "Сохраняем..." : "Сохранить" }}
      </button>
      <button v-if="!template.is_active" class="bc-btn bc-btn-primary" @click="activate">
        <i class="ti ti-power" aria-hidden="true"></i> Активировать
      </button>
      <button v-else class="bc-btn bc-btn-primary" @click="sendNow">
        <i class="ti ti-send" aria-hidden="true"></i> Отправить сейчас
      </button>
    </div>
  </div>
  <div v-else class="bc-loading">Загрузка…</div>
</template>

<style scoped>
.bc-wrap { display: flex; flex-direction: column; flex: 1; }
.bc-loading { padding: 60px; text-align: center; color: var(--color-text-tertiary); font-size: 13px; }

.bc-err {
  margin: 8px 18px;
  background: rgba(226,75,74,.08);
  border: 0.5px solid rgba(226,75,74,.3);
  color: #A32D2D;
  padding: 7px 12px;
  border-radius: 7px;
  font-size: 11.5px;
  display: flex; justify-content: space-between; align-items: center;
}
.bc-err button { background: transparent; border: 0; color: #A32D2D; cursor: pointer; font-size: 16px; }

.bc-grid {
  padding: 14px 18px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  flex: 1;
  overflow-y: auto;
}

.bc-card {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 10px;
  overflow: hidden;
}
.bc-card-hd {
  padding: 10px 14px;
  background: linear-gradient(90deg, rgba(127,119,221,.05), transparent);
  border-bottom: 0.5px solid var(--color-border-tertiary);
  font-size: 11px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 500;
  display: flex; align-items: center; gap: 8px;
}
.bc-num {
  width: 19px; height: 19px;
  border-radius: 50%;
  background: rgba(127,119,221,.15);
  color: #534AB7;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 600;
}
.bc-target-cnt {
  background: rgba(29,158,117,.1);
  color: #0F6E56;
  padding: 1px 8px;
  border-radius: 9px;
  font-size: 10px;
  font-weight: 600;
  margin-left: auto;
  text-transform: lowercase;
}
.bc-target-cnt.loading { background: rgba(0,0,0,.05); color: var(--color-text-tertiary); }

.bc-card-body { padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }

.bc-field { display: flex; flex-direction: column; gap: 3px; }
.bc-field label {
  font-size: 9.5px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .05em;
}
.bc-field input, .bc-field textarea {
  padding: 6px 10px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 6px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
  background: var(--color-background-primary);
}
.bc-field-row { flex-direction: row; gap: 8px; align-items: flex-start; }
.bc-field textarea { resize: vertical; line-height: 1.45; }

.bc-chips { display: flex; flex-wrap: wrap; gap: 4px; }
.bc-chip {
  background: var(--color-background-secondary);
  border: 0.5px solid rgba(0,0,0,.06);
  color: var(--color-text-secondary);
  padding: 4px 10px;
  border-radius: 5px;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
}
.bc-chip.active {
  background: #7F77DD;
  color: #fff;
  border-color: #7F77DD;
}

.bc-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  cursor: pointer;
  color: var(--color-text-primary);
}

.bc-target-block {
  padding: 9px 11px;
  background: var(--color-background-secondary);
  border-radius: 7px;
  display: flex; flex-direction: column; gap: 8px;
}

.bc-preview { margin-top: 4px; }
.bc-preview-hd { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 5px; }
.bc-preview-list { display: flex; flex-wrap: wrap; gap: 4px; }
.bc-preview-chip {
  background: var(--color-background-secondary);
  padding: 2px 8px;
  border-radius: 9px;
  font-size: 10.5px;
  color: var(--color-text-secondary);
}
.bc-preview-chip.more { background: rgba(127,119,221,.08); color: #534AB7; font-weight: 500; }

.bc-sched-block {
  padding: 10px 12px;
  background: var(--color-background-secondary);
  border-radius: 7px;
  display: flex; flex-direction: column; gap: 8px;
}

.bc-weekdays { display: flex; gap: 4px; flex-wrap: wrap; }
.bc-wd {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  color: var(--color-text-secondary);
  width: 32px; height: 26px;
  border-radius: 5px;
  font-size: 10.5px;
  cursor: pointer;
  font-family: inherit;
}
.bc-wd.active { background: #7F77DD; color: #fff; border-color: #7F77DD; font-weight: 500; }

.bc-next-run::before { content:""; position:absolute; left:6px; top:8px; bottom:8px; width:4px; border-radius:4px; background:#7F77DD; }
.bc-next-run {
  position: relative; overflow: hidden;
  padding: 7px 10px 7px 18px;
  background: rgba(127,119,221,.06);
  border-radius: 5px;
  font-size: 10.5px;
  color: #534AB7;
  display: flex; align-items: center; gap: 5px;
}

.bc-ack-block {
  padding: 10px 12px;
  background: var(--color-background-secondary);
  border-radius: 7px;
  display: flex; flex-direction: column; gap: 8px;
}
.bc-ack-options { display: flex; flex-direction: column; gap: 4px; }
.bc-ack-opt { display: flex; gap: 4px; align-items: center; }
.bc-ack-opt input { flex: 1; }
.bc-x {
  background: transparent; border: 0; color: var(--color-text-tertiary);
  cursor: pointer; padding: 4px;
}
.bc-x:hover { color: #A32D2D; }
.bc-add {
  background: transparent;
  border: 0.5px dashed rgba(127,119,221,.4);
  color: #534AB7;
  padding: 4px 8px;
  border-radius: 5px;
  font-size: 10.5px;
  cursor: pointer;
  font-family: inherit;
  align-self: flex-start;
  display: inline-flex; align-items: center; gap: 3px;
}

.bc-toggle-list { display: flex; flex-direction: column; gap: 7px; padding-top: 5px; border-top: 0.5px solid var(--color-border-tertiary); margin-top: 5px; }
.bc-toggle {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11.5px;
  color: var(--color-text-secondary);
  cursor: pointer;
}
.bc-toggle input[type="checkbox"] { accent-color: #7F77DD; }
.bc-toggle input[type="number"] {
  width: 60px;
  padding: 2px 7px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 4px;
  font-size: 11px;
  font-family: inherit;
  text-align: center;
}
.bc-warn-pill {
  background: rgba(239,159,39,.15);
  color: #854F0B;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: .04em;
  margin-left: 4px;
}

.bc-footer {
  padding: 11px 18px;
  background: #FAFAFC;
  border-top: 0.5px solid var(--color-border-tertiary);
  display: flex; align-items: center; gap: 6px;
}
.bc-dirty {
  font-size: 10.5px;
  color: #854F0B;
  background: rgba(239,159,39,.1);
  padding: 2px 8px;
  border-radius: 4px;
}
.bc-btn {
  border: 0;
  padding: 7px 14px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
}
.bc-btn:disabled { opacity: .5; cursor: not-allowed; }
.bc-btn-ghost { background: transparent; border: 0.5px solid var(--color-border-tertiary); color: var(--color-text-secondary); }
.bc-btn-ghost:hover:not(:disabled) { background: rgba(0,0,0,.03); }
.bc-btn-primary { background: #7F77DD; color: #fff; }
.bc-btn-danger { background: rgba(226,75,74,.1); color: #A32D2D; }
</style>
