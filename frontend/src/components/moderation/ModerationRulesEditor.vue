<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  moderationApi,
  type ActionInfo, type ModuleInfo, type Rule, type RulePayload,
} from "@/api/moderation";

const emit = defineEmits<{ change: [] }>();

const rules = ref<Rule[]>([]);
const selected = ref<Rule | null>(null);
const modules = ref<ModuleInfo[]>([]);
const actions = ref<ActionInfo[]>([]);

const loading = ref(false);
const saving = ref(false);
const error = ref<string | null>(null);

const draft = ref<Partial<RulePayload>>({});
const dirty = ref(false);

async function loadAll() {
  loading.value = true;
  try {
    const [r, cat] = await Promise.all([
      moderationApi.listRules(),
      moderationApi.catalog(),
    ]);
    rules.value = r.items;
    modules.value = cat.modules;
    actions.value = cat.actions;
    if (!selected.value && r.items.length > 0) selectRule(r.items[0]);
  } catch (e: any) { error.value = e?.message; }
  finally { loading.value = false; }
}

onMounted(loadAll);

function selectRule(r: Rule) {
  if (dirty.value && !confirm("Несохранённые изменения будут потеряны. Продолжить?")) return;
  selected.value = r;
  draft.value = JSON.parse(JSON.stringify(r));
  dirty.value = false;
}

async function createNew() {
  if (dirty.value && !confirm("Несохранённые изменения будут потеряны. Продолжить?")) return;
  const payload: RulePayload = {
    name: "Новое правило",
    description: null, icon: null, is_active: false, sort_order: 100,
    trigger_user_ids: null, trigger_group_codes: null, trigger_role_codes: null,
    trigger_is_external: true,
    trigger_modules: null,
    trigger_company_ids: null, trigger_sector_ids: null,
    trigger_year_from: null, trigger_year_to: null,
    trigger_actions: ["edit"],
    trigger_conditions: null,
    moderator_primary_id: null,
    moderator_coapprover_id: null,
    moderator_fallback_group_code: null,
    approval_mode: "any",
    escalate_after_hours: 24,
    auto_approve_after_hours: null,
    expire_after_days: 30,
    notify_proposer_assigned: true,
    notify_proposer_resolved: true,
    notify_coapprovers_cc: true,
    notify_owner_on_reject: false,
    log_to_audit: true,
  };
  try {
    const r = await moderationApi.createRule(payload);
    await loadAll();
    selectRule(r);
  } catch (e: any) { error.value = e?.message; }
}

async function toggleActive(r: Rule, ev?: Event) {
  ev?.stopPropagation();
  try {
    const updated = await moderationApi.toggleRule(r.id);
    const i = rules.value.findIndex((x) => x.id === r.id);
    if (i >= 0) rules.value[i] = updated;
    if (selected.value?.id === r.id) { selected.value = updated; draft.value = JSON.parse(JSON.stringify(updated)); }
    emit("change");
  } catch (e: any) { error.value = e?.message; }
}

async function save() {
  if (!selected.value || !draft.value) return;
  saving.value = true;
  error.value = null;
  try {
    const updated = await moderationApi.updateRule(selected.value.id, draft.value);
    const i = rules.value.findIndex((x) => x.id === updated.id);
    if (i >= 0) rules.value[i] = updated;
    selected.value = updated;
    draft.value = JSON.parse(JSON.stringify(updated));
    dirty.value = false;
    emit("change");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { saving.value = false; }
}

async function removeRule() {
  if (!selected.value) return;
  if (!confirm(`Удалить правило "${selected.value.name}"?`)) return;
  try {
    await moderationApi.deleteRule(selected.value.id);
    selected.value = null; draft.value = {}; dirty.value = false;
    await loadAll();
  } catch (e: any) { error.value = e?.message; }
}

function markDirty() { dirty.value = true; }

function toggleArr<T>(arr: T[] | null | undefined, value: T): T[] {
  const list = arr ? [...arr] : [];
  const i = list.indexOf(value);
  if (i >= 0) list.splice(i, 1);
  else list.push(value);
  return list;
}

function moduleToggle(code: string) {
  draft.value.trigger_modules = toggleArr(draft.value.trigger_modules ?? null, code);
  markDirty();
}
function actionToggle(code: string) {
  draft.value.trigger_actions = toggleArr(draft.value.trigger_actions ?? null, code as any);
  markDirty();
}

function addCondition() {
  const list = draft.value.trigger_conditions ? [...draft.value.trigger_conditions] : [];
  list.push({ field: "amount", op: ">", value: 0, unit: "USD" });
  draft.value.trigger_conditions = list;
  markDirty();
}
function removeCondition(idx: number) {
  if (!draft.value.trigger_conditions) return;
  const list = [...draft.value.trigger_conditions];
  list.splice(idx, 1);
  draft.value.trigger_conditions = list;
  markDirty();
}

const moderatorSummary = computed(() => {
  const d = draft.value;
  const parts: string[] = [];
  if (d.moderator_primary_id) parts.push("primary");
  if (d.moderator_coapprover_id) parts.push("co-approver");
  if (d.moderator_fallback_group_code) parts.push(`fallback: ${d.moderator_fallback_group_code}`);
  if (!parts.length) return "не назначены";
  return parts.join(" · ");
});
</script>

<template>
  <div class="mre-wrap">
    <div v-if="error" class="mre-err">{{ error }}</div>

    <div class="mre-grid">

      <div class="mre-list">
        <div class="mre-list-hd">
          <span>{{ rules.length }} правил</span>
          <button class="mre-new-btn" @click="createNew">
            <i class="ti ti-plus" aria-hidden="true"></i> Новое
          </button>
        </div>

        <div v-if="loading" class="mre-empty">Загрузка…</div>
        <div v-else-if="!rules.length" class="mre-empty">
          Правил пока нет. Создайте первое.
        </div>

        <div v-for="r in rules" :key="r.id" class="mre-list-row"
             :class="{ active: selected?.id === r.id, off: !r.is_active }"
             @click="selectRule(r)">
          <i :class="`ti ti-${r.icon || 'route'} mre-row-icn`" aria-hidden="true"></i>
          <div class="mre-row-body">
            <div class="mre-row-name">{{ r.name }}</div>
            <div class="mre-row-meta">
              <span v-if="r.total_matches > 0">{{ r.total_matches }} срабатываний</span>
              <span v-else>не срабатывало</span>
            </div>
          </div>
          <button class="mre-row-toggle" :class="{ on: r.is_active }" @click="toggleActive(r, $event)">
            {{ r.is_active ? "ON" : "OFF" }}
          </button>
        </div>
      </div>

      <div class="mre-editor" v-if="selected && draft">
        <div class="mre-ed-hd">
          <i :class="`ti ti-${draft.icon || 'route'}`" style="font-size: 18px; color: #534AB7;" aria-hidden="true"></i>
          <input v-model="draft.name" class="mre-ed-name" @input="markDirty"/>
          <div class="mre-ed-meta">
            v.{{ selected.version }} · обновлено {{ new Date(selected.updated_at).toLocaleDateString("ru-RU") }} ·
            применено {{ selected.total_matches }} раз
          </div>
          <label class="mre-active-toggle">
            <span style="font-size: 11px;">{{ draft.is_active ? "Активно" : "Неактивно" }}</span>
            <input type="checkbox" :checked="draft.is_active" @change="draft.is_active = ($event.target as HTMLInputElement).checked; markDirty()"/>
          </label>
        </div>

        <div class="mre-section">
          <div class="mre-section-hd">
            <span class="mre-section-num">1</span>
            КОГДА (триггер)
          </div>
          <div class="mre-section-body">

            <div class="mre-criterion">
              <span class="mre-cri-label">WHO</span>
              <label class="mre-cri-check">
                <input type="checkbox" :checked="draft.trigger_is_external" @change="draft.trigger_is_external = ($event.target as HTMLInputElement).checked; markDirty()"/>
                все external
              </label>
              <span style="color: var(--color-text-tertiary); font-size: 10px;">+ users/groups/roles вручную (API)</span>
            </div>

            <div class="mre-criterion">
              <span class="mre-cri-label">WHAT</span>
              <span class="mre-modules">
                <button v-for="m in modules" :key="m.code"
                        class="mre-mod-chip"
                        :class="{ active: (draft.trigger_modules || []).includes(m.code) }"
                        @click="moduleToggle(m.code)">
                  <i :class="`ti ti-${m.icon}`" style="font-size: 11px;" aria-hidden="true"></i>
                  {{ m.label }}
                </button>
              </span>
            </div>

            <div class="mre-criterion">
              <span class="mre-cri-label">ACTION</span>
              <span class="mre-modules">
                <button v-for="a in actions" :key="a.code"
                        class="mre-mod-chip"
                        :class="{ active: (draft.trigger_actions || []).includes(a.code as any) }"
                        @click="actionToggle(a.code)">
                  {{ a.label }}
                </button>
              </span>
            </div>

            <div class="mre-criterion mre-cri-cols">
              <span class="mre-cri-label">YEAR</span>
              <span class="mre-year-inputs">
                от <input type="number" v-model.number="draft.trigger_year_from" @input="markDirty" placeholder="—"/>
                до <input type="number" v-model.number="draft.trigger_year_to" @input="markDirty" placeholder="—"/>
              </span>
            </div>

            <div class="mre-criterion mre-cri-block">
              <span class="mre-cri-label">ТРЕШХОЛД</span>
              <div class="mre-conditions">
                <div v-for="(c, idx) in (draft.trigger_conditions || [])" :key="idx" class="mre-cond">
                  <input class="mre-cond-field" :value="c.field" @input="(e) => { c.field = (e.target as HTMLInputElement).value; markDirty(); }" placeholder="field"/>
                  <select class="mre-cond-op" :value="c.op" @change="(e) => { c.op = (e.target as HTMLSelectElement).value as any; markDirty(); }">
                    <option value="=">=</option>
                    <option value="!=">≠</option>
                    <option value=">">&gt;</option>
                    <option value=">=">≥</option>
                    <option value="<">&lt;</option>
                    <option value="<=">≤</option>
                    <option value="abs>">|x| &gt;</option>
                    <option value="delta>">Δ% &gt;</option>
                  </select>
                  <input class="mre-cond-val" :value="String(c.value ?? '')" @input="(e) => { c.value = (e.target as HTMLInputElement).value; markDirty(); }" placeholder="value"/>
                  <input class="mre-cond-unit" :value="c.unit ?? ''" @input="(e) => { c.unit = (e.target as HTMLInputElement).value; markDirty(); }" placeholder="unit"/>
                  <button class="mre-cond-rm" @click="removeCondition(idx)"><i class="ti ti-x" style="font-size: 11px;" aria-hidden="true"></i></button>
                </div>
                <button class="mre-cond-add" @click="addCondition">
                  <i class="ti ti-plus" aria-hidden="true"></i> условие
                </button>
              </div>
            </div>

          </div>
        </div>

        <div class="mre-section">
          <div class="mre-section-hd">
            <span class="mre-section-num">2</span>
            КТО МОДЕРИРУЕТ (chain)
          </div>
          <div class="mre-section-body">
            <div class="mre-mod-row">
              <span class="mre-mod-num">1</span>
              <span class="mre-mod-lbl">Primary →</span>
              <input class="mre-mod-input" :value="draft.moderator_primary_id ?? ''" placeholder="user UUID"
                     @input="(e) => { draft.moderator_primary_id = (e.target as HTMLInputElement).value || null; markDirty(); }"/>
            </div>
            <div class="mre-mod-row">
              <span class="mre-mod-num">2</span>
              <span class="mre-mod-lbl">Co-approver →</span>
              <input class="mre-mod-input" :value="draft.moderator_coapprover_id ?? ''" placeholder="user UUID (опц)"
                     @input="(e) => { draft.moderator_coapprover_id = (e.target as HTMLInputElement).value || null; markDirty(); }"/>
            </div>
            <div class="mre-mod-row">
              <span class="mre-mod-num">3</span>
              <span class="mre-mod-lbl">Fallback group →</span>
              <input class="mre-mod-input" :value="draft.moderator_fallback_group_code ?? ''" placeholder="group code"
                     @input="(e) => { draft.moderator_fallback_group_code = (e.target as HTMLInputElement).value || null; markDirty(); }"/>
            </div>

            <div class="mre-approval">
              <span class="mre-cri-label">Approval mode</span>
              <label class="mre-radio"><input type="radio" :checked="draft.approval_mode === 'any'" @change="draft.approval_mode = 'any'; markDirty()"/> Любой</label>
              <label class="mre-radio"><input type="radio" :checked="draft.approval_mode === 'dual'" @change="draft.approval_mode = 'dual'; markDirty()"/> Dual (оба)</label>
              <label class="mre-radio"><input type="radio" :checked="draft.approval_mode === 'sequential'" @change="draft.approval_mode = 'sequential'; markDirty()"/> Sequential</label>
            </div>
          </div>
        </div>

        <div class="mre-section">
          <div class="mre-section-hd">
            <span class="mre-section-num">3</span>
            АВТО-ДЕЙСТВИЯ И УВЕДОМЛЕНИЯ
          </div>
          <div class="mre-section-body mre-auto-grid">
            <div class="mre-card">
              <div class="mre-card-hd">Тайминги</div>
              <div class="mre-card-body">
                <div class="mre-time-row">
                  <span>Эскалация после</span>
                  <input type="number" v-model.number="draft.escalate_after_hours" @input="markDirty" placeholder="—"/>
                  <span style="color: var(--color-text-tertiary);">ч</span>
                </div>
                <div class="mre-time-row">
                  <span>Авто-approve через</span>
                  <input type="number" v-model.number="draft.auto_approve_after_hours" @input="markDirty" placeholder="никогда"/>
                  <span style="color: var(--color-text-tertiary);">ч</span>
                </div>
                <div class="mre-time-row">
                  <span>Expire</span>
                  <input type="number" v-model.number="draft.expire_after_days" @input="markDirty"/>
                  <span style="color: var(--color-text-tertiary);">дней</span>
                </div>
              </div>
            </div>

            <div class="mre-card">
              <div class="mre-card-hd">Уведомления</div>
              <div class="mre-card-body">
                <label class="mre-notif"><input type="checkbox" :checked="draft.notify_proposer_assigned" @change="draft.notify_proposer_assigned = ($event.target as HTMLInputElement).checked; markDirty()"/> Proposer'у — при назначении</label>
                <label class="mre-notif"><input type="checkbox" :checked="draft.notify_proposer_resolved" @change="draft.notify_proposer_resolved = ($event.target as HTMLInputElement).checked; markDirty()"/> Proposer'у — при решении</label>
                <label class="mre-notif"><input type="checkbox" :checked="draft.notify_coapprovers_cc" @change="draft.notify_coapprovers_cc = ($event.target as HTMLInputElement).checked; markDirty()"/> Co-approver'ам CC</label>
                <label class="mre-notif"><input type="checkbox" :checked="draft.notify_owner_on_reject" @change="draft.notify_owner_on_reject = ($event.target as HTMLInputElement).checked; markDirty()"/> Owner — при rejection</label>
                <label class="mre-notif"><input type="checkbox" :checked="draft.log_to_audit" @change="draft.log_to_audit = ($event.target as HTMLInputElement).checked; markDirty()"/> Audit log entry</label>
              </div>
            </div>
          </div>
        </div>

        <div class="mre-foot">
          <button class="mre-btn mre-btn-danger" @click="removeRule">
            <i class="ti ti-trash" aria-hidden="true"></i> Удалить
          </button>
          <div style="flex: 1"></div>
          <span v-if="dirty" class="mre-dirty">несохранённые изменения</span>
          <button class="mre-btn mre-btn-primary" :disabled="!dirty || saving" @click="save">
            {{ saving ? "Сохраняем..." : `Сохранить v.${selected.version + 1}` }}
          </button>
        </div>
      </div>

      <div v-else class="mre-no-selection">
        Выберите правило слева или создайте новое
      </div>
    </div>
  </div>
</template>

<style scoped>
.mre-wrap { display: flex; flex-direction: column; gap: 8px; }
.mre-err { background: rgba(226,75,74,.08); color: #A32D2D; padding: 8px 12px; border-radius: 7px; font-size: 11.5px; }

.mre-grid { display: grid; grid-template-columns: 240px 1fr; gap: 12px; align-items: flex-start; }

.mre-list {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 10px;
  overflow: hidden;
}
.mre-list-hd {
  padding: 9px 12px;
  font-size: 9.5px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 500;
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 0.5px solid var(--color-border-tertiary);
}
.mre-new-btn {
  background: #7F77DD; color: #fff;
  border: 0;
  padding: 3px 9px;
  border-radius: 5px;
  font-size: 10.5px;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 3px;
}
.mre-list-row {
  padding: 8px 12px;
  display: flex; align-items: center; gap: 7px;
  border-bottom: 0.5px solid rgba(0,0,0,.04);
  cursor: pointer;
  transition: background .12s;
}
.mre-list-row:hover { background: rgba(127,119,221,.03); }
.mre-list-row.active { background: rgba(127,119,221,.08); border-left: 3px solid #7F77DD; padding-left: 9px; }
.mre-list-row.off { opacity: .55; }
.mre-row-icn { font-size: 13px; color: var(--color-text-secondary); flex-shrink: 0; }
.mre-row-body { flex: 1; min-width: 0; }
.mre-row-name { font-size: 11.5px; color: var(--color-text-primary); font-weight: 500; }
.mre-row-meta { font-size: 9.5px; color: var(--color-text-tertiary); }
.mre-row-toggle {
  background: rgba(0,0,0,.06);
  color: var(--color-text-tertiary);
  border: 0;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 8.5px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}
.mre-row-toggle.on { background: #1D9E75; color: #fff; }

.mre-editor {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 10px;
  overflow: hidden;
}
.mre-no-selection { padding: 60px; text-align: center; color: var(--color-text-tertiary); font-size: 13px; }

.mre-ed-hd {
  padding: 11px 14px;
  background: linear-gradient(90deg, rgba(127,119,221,.06), transparent);
  border-bottom: 0.5px solid var(--color-border-tertiary);
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.mre-ed-name {
  border: 0; background: transparent;
  flex: 1; min-width: 200px;
  font-size: 14px; font-weight: 500;
  color: var(--color-text-primary);
  outline: none;
  padding: 2px 0;
}
.mre-ed-name:focus { border-bottom: 0.5px solid #7F77DD; }
.mre-ed-meta { font-size: 10px; color: var(--color-text-tertiary); width: 100%; order: 5; margin-top: -4px; }
.mre-active-toggle {
  display: inline-flex; align-items: center; gap: 6px;
  cursor: pointer;
}

.mre-section { padding: 14px 16px; border-top: 0.5px solid rgba(0,0,0,.05); }
.mre-section-hd {
  display: flex; align-items: center; gap: 8px;
  font-size: 9.5px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 500;
  margin-bottom: 9px;
}
.mre-section-num {
  width: 18px; height: 18px;
  border-radius: 50%;
  background: rgba(127,119,221,.15);
  color: #534AB7;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 9.5px; font-weight: 600;
}
.mre-section-body {
  background: var(--color-background-secondary);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex; flex-direction: column; gap: 8px;
}

.mre-criterion { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11.5px; }
.mre-criterion.mre-cri-block { align-items: flex-start; flex-direction: column; }
.mre-cri-label {
  min-width: 70px;
  color: var(--color-text-tertiary);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .05em;
}
.mre-cri-check { display: inline-flex; align-items: center; gap: 4px; color: var(--color-text-primary); cursor: pointer; }

.mre-modules { display: flex; flex-wrap: wrap; gap: 4px; flex: 1; }
.mre-mod-chip {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  color: var(--color-text-secondary);
  padding: 3px 8px;
  border-radius: 5px;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
  transition: all .12s;
}
.mre-mod-chip.active {
  background: #7F77DD;
  color: #fff;
  border-color: #7F77DD;
}

.mre-year-inputs { display: inline-flex; align-items: center; gap: 5px; color: var(--color-text-secondary); }
.mre-year-inputs input {
  width: 60px;
  padding: 3px 7px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 4px;
  font-size: 11px;
  font-family: inherit;
  background: #fff;
}

.mre-conditions { display: flex; flex-direction: column; gap: 5px; width: 100%; }
.mre-cond { display: flex; align-items: center; gap: 4px; }
.mre-cond input, .mre-cond select {
  padding: 3px 7px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 4px;
  font-size: 11px;
  font-family: inherit;
  background: #fff;
}
.mre-cond-field { flex: 1; max-width: 160px; font-family: monospace; }
.mre-cond-op    { width: 70px; }
.mre-cond-val   { width: 110px; }
.mre-cond-unit  { width: 60px; }
.mre-cond-rm {
  background: transparent; border: 0;
  color: var(--color-text-tertiary);
  cursor: pointer;
  padding: 2px;
}
.mre-cond-rm:hover { color: #A32D2D; }
.mre-cond-add {
  background: transparent;
  border: 0.5px dashed rgba(127,119,221,.4);
  color: #534AB7;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 10.5px;
  cursor: pointer;
  font-family: inherit;
  align-self: flex-start;
  display: inline-flex; align-items: center; gap: 3px;
}

.mre-mod-row { display: flex; align-items: center; gap: 6px; padding: 5px 0; border-bottom: 0.5px dashed rgba(0,0,0,.04); }
.mre-mod-num {
  width: 20px; height: 20px;
  border-radius: 50%;
  background: rgba(127,119,221,.15); color: #534AB7;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 9.5px; font-weight: 600;
}
.mre-mod-lbl { font-size: 11px; color: var(--color-text-tertiary); min-width: 110px; }
.mre-mod-input {
  flex: 1;
  padding: 4px 8px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 5px;
  font-size: 11px;
  font-family: monospace;
  background: #fff;
}

.mre-approval { display: flex; align-items: center; gap: 12px; padding-top: 7px; border-top: 0.5px solid var(--color-border-tertiary); margin-top: 5px; flex-wrap: wrap; }
.mre-radio { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--color-text-secondary); cursor: pointer; }

.mre-auto-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 0; background: transparent; }
.mre-card {
  background: var(--color-background-secondary);
  border-radius: 8px;
  padding: 10px 12px;
}
.mre-card-hd { font-size: 10px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
.mre-card-body { display: flex; flex-direction: column; gap: 6px; font-size: 11px; }
.mre-time-row { display: flex; align-items: center; gap: 6px; }
.mre-time-row > span:first-child { flex: 1; color: var(--color-text-secondary); }
.mre-time-row input {
  width: 70px;
  padding: 3px 8px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 4px;
  font-size: 11px;
  font-family: inherit;
  background: #fff;
}
.mre-notif { display: inline-flex; align-items: center; gap: 5px; color: var(--color-text-primary); cursor: pointer; font-size: 11px; }

.mre-foot {
  padding: 11px 14px;
  border-top: 0.5px solid var(--color-border-tertiary);
  display: flex; align-items: center; gap: 6px;
}
.mre-dirty {
  font-size: 10.5px; color: #854F0B;
  background: rgba(239,159,39,.1);
  padding: 2px 8px; border-radius: 4px;
}
.mre-btn {
  border: 0;
  padding: 7px 14px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
}
.mre-btn:disabled { opacity: .5; cursor: not-allowed; }
.mre-btn-danger { background: rgba(226,75,74,.1); color: #A32D2D; }
.mre-btn-primary { background: #7F77DD; color: #fff; }
.mre-empty { padding: 30px 14px; text-align: center; color: var(--color-text-tertiary); font-size: 11.5px; }
</style>
