<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { rolesApi, createUser, generatePassword } from '@/api/rbacV3';
import type { RbacV3Role } from '@/api/rbacV3';
import RoleChip from './RoleChip.vue';

const props = defineProps<{
  prefill?: { full_name?: string; department?: string; role_codes?: string[] };
}>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'created', userId: string): void;
}>();

const email = ref('');
const fullName = ref(props.prefill?.full_name || '');
const department = ref(props.prefill?.department || '');
const password = ref(generatePassword());
const mustChangePassword = ref(true);
const selectedRoles = ref<string[]>(props.prefill?.role_codes || []);

const allRoles = ref<RbacV3Role[]>([]);
const saving = ref(false);
const error = ref<string | null>(null);
const copied = ref(false);

onMounted(async () => {
  try { allRoles.value = await rolesApi.list(); }
  catch (e: any) { error.value = e?.response?.data?.detail || 'Не удалось загрузить роли'; }
});

function regenPassword() { password.value = generatePassword(); copied.value = false; }
function copyPassword() {
  navigator.clipboard.writeText(password.value).then(() => {
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  });
}
function toggleRole(code: string) {
  const i = selectedRoles.value.indexOf(code);
  if (i >= 0) selectedRoles.value.splice(i, 1);
  else selectedRoles.value.push(code);
}

async function submit() {
  if (!email.value.trim() || !fullName.value.trim()) {
    error.value = 'Email и ФИО обязательны';
    return;
  }
  saving.value = true; error.value = null;
  try {
    const u = await createUser({
      email: email.value.trim(),
      full_name: fullName.value.trim(),
      department: department.value.trim() || undefined,
      password: password.value,
      must_change_password: mustChangePassword.value,
      role_codes: selectedRoles.value,
    });
    emit('created', u.id);
    emit('close');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось создать пользователя';
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="rv3-modal-bd" @click.self="emit('close')">
    <div class="rv3-modal">
      <div class="rv3-modal-hd">{{ prefill ? 'Создать аналогичного пользователя' : 'Пригласить пользователя' }}</div>

      <div class="rv3-edit-label">Email</div>
      <input v-model="email" class="rv3-input" placeholder="user@uz-assets.uz" autofocus />

      <div class="rv3-edit-label" style="margin-top:10px">ФИО</div>
      <input v-model="fullName" class="rv3-input" placeholder="Иванов Иван Иванович" />

      <div class="rv3-edit-label" style="margin-top:10px">Отдел (опционально)</div>
      <input v-model="department" class="rv3-input" placeholder="Финансовый блок" />

      <div class="rv3-edit-label" style="margin-top:10px;display:flex;align-items:center;justify-content:space-between">
        <span>Временный пароль</span>
        <div style="display:flex;gap:6px">
          <button class="rv3-mini-btn" @click="regenPassword" type="button">↻ новый</button>
          <button class="rv3-mini-btn" @click="copyPassword" type="button">
            {{ copied ? '✓ скопировано' : 'копировать' }}
          </button>
        </div>
      </div>
      <div class="rv3-pwd">
        <code>{{ password }}</code>
      </div>
      <label class="rv3-cb-row">
        <input type="checkbox" v-model="mustChangePassword" />
        <span>Требовать смену пароля при первом входе</span>
      </label>

      <div class="rv3-edit-label" style="margin-top:14px">Роли</div>
      <div class="rv3-role-picker">
        <button
          v-for="r in allRoles"
          :key="r.code"
          type="button"
          :class="['rv3-role-toggle', { on: selectedRoles.includes(r.code) }]"
          @click="toggleRole(r.code)"
        >
          <RoleChip :code="r.code" size="sm" />
          <span class="rv3-role-toggle-name">{{ r.name_ru }}</span>
        </button>
        <div v-if="allRoles.length === 0" class="rv3-empty">Загрузка ролей...</div>
      </div>

      <div v-if="error" class="rv3-form-err">{{ error }}</div>

      <div class="rv3-modal-foot">
        <button class="rv3-btn rv3-btn-ghost" @click="emit('close')" :disabled="saving">Отмена</button>
        <button class="rv3-save" :disabled="saving" @click="submit">
          {{ saving ? 'Создание...' : (prefill ? 'Создать клон' : 'Пригласить') }}
        </button>
      </div>

      <div class="rv3-modal-hint" v-if="!prefill">
        Пользователь получит email с этим паролем (или сообщите ему лично).
        Magic-link приглашения по email будут в сессии 4.
      </div>
    </div>
  </div>
</template>

<style scoped>
.rv3-modal-bd {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(15,18,40,.45); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  padding: 36px;
}
.rv3-modal {
  width: 480px; max-width: 100%;
  background: var(--card-bg, rgba(255, 255, 255, 0.86)); backdrop-filter: blur(20px) saturate(1.4); -webkit-backdrop-filter: blur(20px) saturate(1.4); border: 1px solid var(--card-border, transparent); border-radius: 14px;
  padding: 22px 24px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18);
  max-height: 90vh; overflow-y: auto;
}
.rv3-modal-hd { font-size: 15px; font-weight: 500; letter-spacing: -.01em; margin-bottom: 14px; }
.rv3-edit-label {
  font-size: 10px; font-weight: 500; color: var(--t3, #888780);
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 5px;
}
.rv3-input {
  width: 100%; padding: 8px 12px;
  border: 0.5px solid #E5E7EB; border-radius: 8px;
  font-size: 12px; color: var(--t1, #1E2A4A); outline: none;
  font-family: inherit;
}
.rv3-pwd {
  padding: 10px 12px;
  background: var(--bg2, #F9FAFB); border: 0.5px solid #E5E7EB; border-radius: 8px;
}
.rv3-pwd code {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 13px; color: var(--t1, #1E2A4A); letter-spacing: .04em;
  user-select: all;
}
.rv3-mini-btn {
  background: transparent; border: none; color: #534AB7;
  font-size: 10.5px; font-weight: 500; cursor: pointer;
  font-family: inherit; padding: 1px 3px;
  letter-spacing: 0; text-transform: none;
}
.rv3-cb-row {
  display: flex; align-items: center; gap: 7px;
  margin-top: 8px;
  font-size: 11.5px; color: var(--t1, #1E2A4A);
  cursor: pointer;
}
.rv3-cb-row input { accent-color: #7F77DD; }

.rv3-role-picker { display: flex; flex-wrap: wrap; gap: 6px; }
.rv3-role-toggle {
  display: flex; align-items: center; gap: 7px;
  padding: 5px 10px;
  background: var(--bg2, #F9FAFB); border: 1px solid #E5E7EB; border-radius: 14px;
  cursor: pointer; font-family: inherit; font-size: 11px;
}
.rv3-role-toggle:hover { background: var(--bg1, #fff); border-color: #D1D5DB; }
.rv3-role-toggle.on {
  background: rgba(127,119,221,.08);
  border-color: rgba(127,119,221,.4);
}
.rv3-role-toggle-name { color: var(--t1, #1E2A4A); }
.rv3-empty { font-size: 11.5px; color: var(--t3, #888780); font-style: italic; }

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
.rv3-btn-ghost { background: transparent; border: 1px solid #E5E7EB; color: var(--t1, #1E2A4A); }
.rv3-save {
  padding: 7px 14px;
  background: #1D9E75; color: #fff; border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit;
}
.rv3-save:disabled { background: #E5E7EB; color: var(--t3, #888780); cursor: not-allowed; }
.rv3-modal-hint {
  margin-top: 12px;
  padding: 8px 11px;
  background: var(--bg2, #FAFAFC); border-radius: 7px;
  font-size: 10.5px; color: var(--t3, #888780); line-height: 1.5;
}
</style>