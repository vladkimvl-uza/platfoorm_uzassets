<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { emailRulesApi, rolesApi } from '@/api/rbacV3';
import type { RbacV3EmailRule, RbacV3Role } from '@/api/rbacV3';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';

const rules = ref<RbacV3EmailRule[]>([]);
const roles = ref<RbacV3Role[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const showCreate = ref(false);
const saving = ref(false);

const newRule = ref({
  email: '',
  role_codes: [] as string[],
  department: '',
  notes: '',
});

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [rs, ru] = await Promise.all([emailRulesApi.list(), rolesApi.list()]);
    rules.value = rs.sort((a, b) => a.email.localeCompare(b.email));
    roles.value = ru;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось загрузить правила';
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function toggleRoleInNew(code: string) {
  const i = newRule.value.role_codes.indexOf(code);
  if (i >= 0) newRule.value.role_codes.splice(i, 1);
  else newRule.value.role_codes.push(code);
}

async function createRule() {
  if (!newRule.value.email.trim()) {
    error.value = 'Email обязателен';
    return;
  }
  if (newRule.value.role_codes.length === 0) {
    error.value = 'Выберите хотя бы одну роль';
    return;
  }
  saving.value = true; error.value = null;
  try {
    await emailRulesApi.create({
      email: newRule.value.email.trim(),
      role_codes: newRule.value.role_codes,
      department: newRule.value.department.trim() || undefined,
      notes: newRule.value.notes.trim() || undefined,
    });
    showCreate.value = false;
    newRule.value = { email: '', role_codes: [], department: '', notes: '' };
    await load();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось создать правило';
  } finally {
    saving.value = false;
  }
}

async function deleteRule(id: string, email: string) {
  if (!confirm(`Удалить правило для ${email}?`)) return;
  try {
    await emailRulesApi.remove(id);
    await load();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось удалить';
  }
}

const isPattern = (email: string) => email.includes('*');

function fmtDate(s: string) {
  const d = new Date(s);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' });
}
</script>

<template>
  <div class="rv3-er-shell">
    <!-- Header / intro -->
    <div class="rv3-er-hd">
      <div>
        <div class="rv3-er-title">Правила автоназначения ролей по email</div>
        <div class="rv3-er-sub">
          Когда новый пользователь регистрируется и его email совпадает с правилом —
          ему автоматически выдаются указанные роли и scope.
          Поддерживаются точные адреса (<code>ivan@uz-assets.uz</code>)
          и wildcard-шаблоны (<code>*@uz-assets.uz</code>).
        </div>
      </div>
      <button class="rv3-er-add" @click="showCreate = true">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="3" x2="8" y2="13"/><line x1="3" y1="8" x2="13" y2="8"/></svg>
        Новое правило
      </button>
    </div>

    <div v-if="error && !showCreate" class="rv3-er-err">{{ error }}</div>

    <!-- List -->
    <div v-if="loading" class="rv3-state">Загрузка...</div>
    <div v-else-if="rules.length === 0" class="rv3-empty-card">
      <div class="rv3-empty-icon">
        <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#D1D5DB" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
          <polyline points="22,6 12,13 2,6"/>
        </svg>
      </div>
      <div class="rv3-empty-title">Правил автоназначения пока нет</div>
      <div class="rv3-empty-text">
        Создайте первое правило — например, выдать всем сотрудникам <br/>
        <code>*@uz-assets.uz</code> роль <strong>readonly</strong>
      </div>
    </div>
    <div v-else class="rv3-er-list">
      <div class="rv3-er-row rv3-er-row-hd">
        <div>Email / шаблон</div>
        <div>Роли</div>
        <div>Отдел</div>
        <div>Создано</div>
        <div></div>
      </div>
      <div v-for="r in rules" :key="r.id" class="rv3-er-row">
        <div class="rv3-er-email">
          <span v-if="isPattern(r.email)" class="rv3-er-pattern-badge">PATTERN</span>
          <code>{{ r.email }}</code>
        </div>
        <div class="rv3-er-roles">
          <RoleChip v-for="rc in r.role_codes" :key="rc" :code="rc" size="sm" />
        </div>
        <div class="rv3-er-dept">{{ r.department || '—' }}</div>
        <div class="rv3-er-created">{{ fmtDate(r.created_at) }}</div>
        <div class="rv3-er-actions">
          <button class="rv3-er-del" @click="deleteRule(r.id, r.email)" :title="'Удалить правило для ' + r.email">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 5h10M6 5V3h4v2M5 5l1 9h4l1-9"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Create modal -->
    <div v-if="showCreate" class="rv3-modal-bd" @click.self="showCreate = false">
      <div class="rv3-modal">
        <div class="rv3-modal-hd">Новое правило автоназначения</div>

        <div class="rv3-edit-label">Email или шаблон</div>
        <input
          v-model="newRule.email"
          class="rv3-input"
          placeholder="ivan@uz-assets.uz   или   *@uz-assets.uz"
          autofocus
        />
        <div class="rv3-input-hint">
          <code>*@domain</code> — все с этим доменом · <code>name@example.com</code> — конкретный адрес
        </div>

        <div class="rv3-edit-label" style="margin-top:14px">Роли для автоназначения</div>
        <div class="rv3-role-picker">
          <button
            v-for="r in roles"
            :key="r.code"
            type="button"
            :class="['rv3-role-toggle', { on: newRule.role_codes.includes(r.code) }]"
            @click="toggleRoleInNew(r.code)"
          >
            <RoleChip :code="r.code" size="sm" />
            <span class="rv3-role-toggle-name">{{ r.name_ru }}</span>
          </button>
        </div>

        <div class="rv3-edit-label" style="margin-top:14px">Отдел (опционально)</div>
        <input v-model="newRule.department" class="rv3-input" placeholder="Финансовый блок" />

        <div class="rv3-edit-label" style="margin-top:14px">Заметка (опционально)</div>
        <textarea
          v-model="newRule.notes"
          class="rv3-textarea"
          placeholder="Контекст: для кого это правило, когда удалить, и т.д."
        ></textarea>

        <div v-if="error" class="rv3-form-err">{{ error }}</div>

        <div class="rv3-modal-foot">
          <button class="rv3-btn rv3-btn-ghost" @click="showCreate = false" :disabled="saving">Отмена</button>
          <button class="rv3-save" :disabled="saving" @click="createRule">
            {{ saving ? 'Создание...' : 'Создать правило' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rv3-er-shell {
  padding: 28px;
  min-height: calc(100vh - 56px);
  max-width: 1100px;
  margin: 0 auto;
}
.rv3-er-hd {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 24px;
  margin-bottom: 24px;
}
.rv3-er-title {
  font-size: 15px; font-weight: 500; letter-spacing: -.01em;
  margin-bottom: 6px;
}
.rv3-er-sub {
  font-size: 12px; color: var(--t3, #888780); line-height: 1.6;
  max-width: 640px;
}
.rv3-er-sub code {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 11px; color: var(--t1, #1E2A4A);
  background: #F3F4F8; padding: 1px 5px; border-radius: 4px;
}
.rv3-er-add {
  flex-shrink: 0;
  display: flex; align-items: center; gap: 6px;
  height: 32px; padding: 0 14px;
  background: #1D9E75; border: none; border-radius: 8px;
  color: #fff; font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  transition: background .12s;
}
.rv3-er-add:hover { background: #178760; }
.rv3-er-err {
  margin-bottom: 14px;
  padding: 10px 14px;
  background: rgba(226,75,74,.08);
  border: 0.5px solid rgba(226,75,74,.3);
  border-radius: 8px;
  color: #A82C2B; font-size: 12px;
}
.rv3-state {
  padding: 60px; text-align: center;
  font-size: 13px; color: var(--t3, #888780);
}
.rv3-empty-card {
  background: var(--bg1, #fff); border: 0.5px solid #E5E7EB; border-radius: 14px;
  padding: 48px;
  text-align: center;
  box-shadow: 0 4px 16px rgba(15,23,60,.04);
}
.rv3-empty-icon { margin-bottom: 14px; }
.rv3-empty-title {
  font-size: 14px; font-weight: 500; letter-spacing: -.01em;
  margin-bottom: 8px;
}
.rv3-empty-text {
  font-size: 12px; color: var(--t3, #888780); line-height: 1.6;
}
.rv3-empty-text code {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 11px; color: var(--t1, #1E2A4A);
  background: #F3F4F8; padding: 1px 5px; border-radius: 4px;
}
.rv3-er-list {
  background: var(--bg1, #fff); border: 0.5px solid #E5E7EB; border-radius: 12px;
  overflow: hidden;
}
.rv3-er-row {
  display: grid;
  grid-template-columns: 2fr 2fr 1fr 1fr 50px;
  gap: 14px; align-items: center;
  padding: 12px 18px;
  border-bottom: 0.5px solid #F3F4F8;
}
.rv3-er-row:last-child { border-bottom: none; }
.rv3-er-row-hd {
  background: var(--bg2, #FAFAFC);
  font-size: 9.5px; font-weight: 500; color: var(--t3, #888780);
  letter-spacing: .06em; text-transform: uppercase;
}
.rv3-er-email { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.rv3-er-email code {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-weight: 500; color: var(--t1, #1E2A4A);
}
.rv3-er-pattern-badge {
  padding: 1px 6px;
  background: rgba(239,159,39,.12); color: #B27015;
  border-radius: 7px;
  font-size: 9px; font-weight: 500; letter-spacing: .04em;
}
.rv3-er-roles { display: flex; gap: 4px; flex-wrap: wrap; }
.rv3-er-dept { font-size: 11.5px; color: var(--t1, #1E2A4A); }
.rv3-er-created { font-size: 11px; color: var(--t3, #888780); }
.rv3-er-actions { display: flex; justify-content: flex-end; }
.rv3-er-del {
  width: 28px; height: 28px;
  background: transparent; border: 1px solid transparent;
  color: var(--t3, #888780); border-radius: 6px;
  cursor: pointer; font-family: inherit;
  display: flex; align-items: center; justify-content: center;
  transition: all .12s;
}
.rv3-er-del:hover { background: rgba(226,75,74,.08); color: #E24B4A; border-color: rgba(226,75,74,.3); }

/* Modal styles — same as Groups create */
.rv3-modal-bd {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(15,18,40,.45); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  padding: 36px;
}
.rv3-modal {
  width: 520px; max-width: 100%;
  background: var(--bg1, #fff); border-radius: 14px;
  padding: 22px 24px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18);
  max-height: 90vh; overflow-y: auto;
}
.rv3-modal-hd {
  font-size: 15px; font-weight: 500; letter-spacing: -.01em;
  margin-bottom: 14px;
}
.rv3-edit-label {
  font-size: 10px; font-weight: 500; color: var(--t3, #888780);
  letter-spacing: .06em; text-transform: uppercase; margin-bottom: 5px;
}
.rv3-input {
  width: 100%; padding: 8px 12px;
  border: 0.5px solid #E5E7EB; border-radius: 8px;
  font-size: 12px; color: var(--t1, #1E2A4A); outline: none;
  font-family: inherit;
}
.rv3-input-hint {
  margin-top: 5px; font-size: 10.5px; color: var(--t3, #888780);
}
.rv3-input-hint code {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 10px; color: var(--t1, #1E2A4A);
  background: #F3F4F8; padding: 1px 4px; border-radius: 3px;
}
.rv3-textarea {
  width: 100%; padding: 9px 12px;
  border: 0.5px solid #E5E7EB; border-radius: 8px;
  font-size: 12px; color: var(--t1, #1E2A4A); outline: none;
  resize: vertical; min-height: 48px;
  font-family: inherit;
}
.rv3-role-picker { display: flex; flex-wrap: wrap; gap: 6px; }
.rv3-role-toggle {
  display: flex; align-items: center; gap: 7px;
  padding: 5px 10px;
  background: var(--bg2, #F9FAFB); border: 1px solid #E5E7EB; border-radius: 14px;
  cursor: pointer; font-family: inherit; font-size: 11px;
}
.rv3-role-toggle:hover { background: var(--bg1, #fff); border-color: #D1D5DB; }
.rv3-role-toggle.on { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.4); }
.rv3-role-toggle-name { color: var(--t1, #1E2A4A); }
.rv3-form-err {
  margin-top: 12px;
  padding: 8px 11px;
  background: rgba(226,75,74,.08); border: 0.5px solid rgba(226,75,74,.3);
  border-radius: 7px;
  font-size: 11.5px; color: #A82C2B;
}
.rv3-modal-foot {
  display: flex; gap: 8px; justify-content: flex-end;
  margin-top: 16px;
}
.rv3-btn {
  padding: 7px 14px; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-btn-ghost {
  background: transparent; border: 1px solid #E5E7EB; color: var(--t1, #1E2A4A);
}
.rv3-save {
  padding: 7px 14px;
  background: #1D9E75; color: #fff; border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit;
}
.rv3-save:disabled { background: #E5E7EB; color: var(--t3, #888780); cursor: not-allowed; }
</style>