<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { rolesApi, permissionsToLevels, levelsToPermissions } from '@/api/rbacV3';
import type { RbacV3Role, RbacV3RoleDetail } from '@/api/rbacV3';
import type { AccessLevel } from '@/composables/usePermissions';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';
import CreateRoleModal from '@/components/rbac-v3/CreateRoleModal.vue';
import { rolesApiExt } from '@/api/rbacV3';

const roles = ref<RbacV3Role[]>([]);
const selectedCode = ref<string | null>(null);
const detail = ref<RbacV3RoleDetail | null>(null);
const levels = ref<Record<string, AccessLevel>>({});
const loading = ref(false);
const error = ref<string | null>(null);
const saving = ref(false);
const dirty = ref(false);
const description = ref('');

async function loadRoles() {
  try {
    roles.value = (await rolesApi.list()).sort((a, b) => a.sort_order - b.sort_order);
    if (!selectedCode.value && roles.value.length > 0) {
      selectedCode.value = roles.value[0].code;
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось загрузить роли';
  }
}

async function loadDetail() {
  if (!selectedCode.value) { detail.value = null; return; }
  loading.value = true; error.value = null; dirty.value = false;
  try {
    detail.value = await rolesApi.get(selectedCode.value);
    description.value = detail.value.description_ru || '';
    levels.value = permissionsToLevels(detail.value.permissions.map(p => p.code));
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка загрузки роли';
  } finally {
    loading.value = false;
  }
}

onMounted(loadRoles);
watch(selectedCode, loadDetail);

function selectRole(code: string) {
  if (dirty.value && !confirm('Есть несохранённые изменения. Перейти к другой роли?')) return;
  selectedCode.value = code;
}

function onLevelChange(newLevels: Record<string, AccessLevel>) {
  levels.value = newLevels;
  dirty.value = true;
}

function setAllLevels(level: AccessLevel) {
  const next: Record<string, AccessLevel> = {};
  for (const code of Object.keys(levels.value)) next[code] = level;
  levels.value = next;
  dirty.value = true;
}

const showCreate = ref(false);
const createPrefill = ref<{ name?: string; description?: string; levels?: Record<string, AccessLevel>; from?: string } | null>(null);

function openCreate() { createPrefill.value = null; showCreate.value = true; }
function openDuplicate() {
  if (!detail.value) return;
  createPrefill.value = {
    from: detail.value.code,
    name: detail.value.name_ru + ' (копия)',
    description: detail.value.description_ru || '',
    levels: { ...levels.value },
  };
  showCreate.value = true;
}
async function onRoleCreated(code: string) {
  showCreate.value = false;
  createPrefill.value = null;
  await loadRoles();
  selectedCode.value = code;
}

async function saveDescription() {
  if (!detail.value || !selectedCode.value) return;
  if ((detail.value.description_ru || '') === description.value) return;
  try {
    await rolesApiExt.update(selectedCode.value, { description_ru: description.value });
    await loadRoles();
    await loadDetail();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось сохранить описание';
  }
}

async function removeRole() {
  if (!detail.value || !selectedCode.value) return;
  if (detail.value.is_system) return;
  const input = prompt(`Удалить роль "${detail.value.code}"?\nВведите code для подтверждения: ${detail.value.code}`);
  if (!input || input.trim() !== detail.value.code) {
    if (input !== null) alert('Code не совпадает');
    return;
  }
  try {
    await rolesApiExt.remove(selectedCode.value);
    selectedCode.value = null;
    detail.value = null;
    await loadRoles();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось удалить роль';
  }
}

async function save() {
  if (!detail.value || !selectedCode.value) return;
  saving.value = true; error.value = null;
  try {
    const codes = levelsToPermissions(levels.value);
    detail.value = await rolesApi.updatePermissions(selectedCode.value, codes);
    levels.value = permissionsToLevels(detail.value.permissions.map(p => p.code));
    dirty.value = false;
    await loadRoles();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка сохранения';
  } finally {
    saving.value = false;
  }
}

const ROLE_COLOR: Record<string, string> = {
  admin:'#E24B4A', ceo:'#EF9F27', debt:'#1D9E75',
  readonly:'#888780', imv_admin:'#378ADD',
};
function roleColor(code: string) { return ROLE_COLOR[code] || '#7F77DD'; }

const sysRoles = computed(() => roles.value.filter(r => r.is_system));
const customRoles = computed(() => roles.value.filter(r => !r.is_system));
</script>

<template>
  <div class="rv3-roles-shell">
    <!-- LEFT: list -->
    <div class="rv3-roles-list">
      <div class="rv3-rl-section">
        <div class="rv3-rl-section-hd">Системные · {{ sysRoles.length }}</div>
        <div
          v-for="r in sysRoles"
          :key="r.code"
          :class="['rv3-rl-item', { on: selectedCode === r.code }]"
          @click="selectRole(r.code)"
        >
          <div class="rv3-rl-row">
            <span class="rv3-rl-dot" :style="{ background: roleColor(r.code) }"></span>
            <span class="rv3-rl-name">{{ r.code }}</span>
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="#888780" stroke-width="1.5" style="margin-left:auto;flex-shrink:0;">
              <rect x="3" y="5" width="6" height="5" rx="1"/>
              <path d="M5 5V3a1 1 0 0 1 2 0v2"/>
            </svg>
          </div>
          <div class="rv3-rl-meta">{{ r.name_ru }} · {{ r.permission_count }} разреш.</div>
        </div>
      </div>

      <div class="rv3-rl-section" v-if="customRoles.length > 0">
        <div class="rv3-rl-section-hd">Пользовательские · {{ customRoles.length }}</div>
        <div
          v-for="r in customRoles"
          :key="r.code"
          :class="['rv3-rl-item', { on: selectedCode === r.code }]"
          @click="selectRole(r.code)"
        >
          <div class="rv3-rl-row">
            <span class="rv3-rl-dot" :style="{ background: roleColor(r.code) }"></span>
            <span class="rv3-rl-name">{{ r.code }}</span>
          </div>
          <div class="rv3-rl-meta">{{ r.name_ru }} · {{ r.permission_count }} разреш.</div>
        </div>
      </div>

      <button class="rv3-rl-add" @click="openCreate">
        + Новая роль
      </button>
    </div>

    <!-- RIGHT: editor -->
    <div class="rv3-roles-edit">
      <div v-if="loading" class="rv3-state">Загрузка...</div>
      <div v-else-if="error" class="rv3-state rv3-err">{{ error }}</div>
      <template v-else-if="detail">
        <div class="rv3-edit-hd">
          <div class="rv3-edit-icon" :style="{ background: roleColor(detail.code) + '20', borderColor: roleColor(detail.code) + '50' }">
            <span class="rv3-rl-dot" :style="{ background: roleColor(detail.code), width: '14px', height: '14px' }"></span>
          </div>
          <div style="flex:1;">
            <div class="rv3-edit-title">
              {{ detail.name_ru }}
              <RoleChip :code="detail.code" size="sm" />
            </div>
            <div class="rv3-edit-meta">
              <span>code: <code>{{ detail.code }}</code></span>
              <span v-if="detail.is_system" class="rv3-sys">
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="5" width="6" height="5" rx="1"/><path d="M5 5V3a1 1 0 0 1 2 0v2"/></svg>
                системная
              </span>
              <span>· {{ detail.permission_count }} разрешений</span>
            </div>
          </div>
          <button
            class="rv3-save"
            :disabled="!dirty || saving"
            @click="save"
          >
            {{ saving ? 'Сохранение...' : (dirty ? 'Сохранить' : 'Сохранено') }}
          </button>
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label">Описание</div>
          <textarea
            v-model="description"
            class="rv3-textarea"
            placeholder="Описание роли — для чего используется"
            @blur="saveDescription"
          ></textarea>
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label rv3-edit-label-row">
            <span>Доступ к модулям</span>
            <div class="rv3-quick">
              <button class="rv3-quick-btn rv3-quick-admin" @click="setAllLevels('admin')">ВСЕ ADMIN</button>
              <button class="rv3-quick-btn" @click="setAllLevels('read')">ВСЕ READ</button>
              <button class="rv3-quick-btn" @click="setAllLevels('none')">СБРОС</button>
            </div>
          </div>
          <ModuleSelectGrid
            :model-value="levels"
            :editable="true"
            :columns="4"
            @update:model-value="onLevelChange"
          />
        </div>

        <div class="rv3-edit-foot">
          <button class="rv3-btn rv3-btn-ghost" @click="openDuplicate">Дублировать роль</button>
          <div style="flex:1"></div>
          <button
            v-if="!detail.is_system"
            class="rv3-btn rv3-btn-red"
            @click="removeRole"
          >Удалить роль</button>
        </div>
      </template>
    </div>

    <CreateRoleModal
      v-if="showCreate"
      :prefill-from-code="createPrefill?.from"
      :prefill-name="createPrefill?.name"
      :prefill-description="createPrefill?.description"
      :prefill-levels="createPrefill?.levels"
      @close="showCreate = false; createPrefill = null"
      @created="onRoleCreated"
    />
  </div>
</template>

<style scoped>
.rv3-roles-shell {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 1px;
  background: #E5E7EB;
  min-height: calc(100vh - 56px);
}
.rv3-roles-list {
  background: var(--bg1, #fff);
  padding: 16px 0;
  overflow-y: auto;
}
.rv3-rl-section + .rv3-rl-section { margin-top: 18px; }
.rv3-rl-section-hd {
  padding: 0 18px 8px;
  font-size: 10px; font-weight: 500; color: var(--t3, #888780);
  letter-spacing: .06em; text-transform: uppercase;
}
.rv3-rl-item {
  padding: 10px 18px;
  cursor: pointer;
  position: relative; overflow: hidden;
}
.rv3-rl-item:hover { background: var(--bg2, #FAFAFC); }
.rv3-rl-item.on {
  background: rgba(127,119,221,.06);
}
.rv3-rl-item.on::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transform-origin: left center;
  pointer-events: none;
}
.rv3-rl-row { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
.rv3-rl-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.rv3-rl-name { font-size: 13px; font-weight: 500; font-family: ui-monospace, 'SF Mono', Menlo, monospace; }
.rv3-rl-meta { font-size: 10.5px; color: var(--t3, #888780); }
.rv3-rl-add {
  margin: 14px 18px 0;
  padding: 9px 12px;
  background: transparent;
  border: 1px dashed #D1D5DB;
  border-radius: 8px;
  color: var(--t3, #888780);
  font-size: 12px; font-weight: 500;
  cursor: not-allowed;
  width: calc(100% - 36px);
  font-family: inherit;
}

.rv3-roles-edit { background: var(--bg1, #fff); padding: 24px 28px; overflow-y: auto; }
.rv3-edit-hd {
  display: flex; align-items: flex-start; gap: 14px; margin-bottom: 18px;
}
.rv3-edit-icon {
  width: 42px; height: 42px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; border: 1px solid;
}
.rv3-edit-title {
  font-size: 16px; font-weight: 500; letter-spacing: -.01em;
  display: flex; align-items: center; gap: 10px;
}
.rv3-edit-meta {
  font-size: 11px; color: var(--t3, #888780); margin-top: 3px;
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.rv3-edit-meta code {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  color: var(--t1, #1E2A4A);
}
.rv3-sys {
  display: inline-flex; align-items: center; gap: 4px;
  color: #E24B4A;
}
.rv3-save {
  padding: 7px 14px;
  background: #1D9E75; color: #fff;
  border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-save:disabled {
  background: #E5E7EB; color: var(--t3, #888780); cursor: not-allowed;
}
.rv3-edit-section { margin-bottom: 18px; }
.rv3-edit-label {
  font-size: 10px; font-weight: 500; color: var(--t3, #888780);
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 6px;
}
.rv3-edit-label-row {
  display: flex; align-items: center; justify-content: space-between;
}
.rv3-textarea {
  width: 100%; padding: 9px 12px;
  border: 0.5px solid #E5E7EB; border-radius: 8px;
  font-size: 12px; color: var(--t1, #1E2A4A); outline: none;
  resize: vertical; min-height: 48px;
  font-family: inherit;
  background: var(--bg2, #FAFAFC);
}
.rv3-quick { display: flex; gap: 4px; }
.rv3-quick-btn {
  padding: 3px 9px;
  background: #F3F4F8; color: var(--t3, #888780);
  border: none; border-radius: 10px;
  font-size: 9.5px; font-weight: 500;
  letter-spacing: .04em; cursor: pointer; font-family: inherit;
}
.rv3-quick-btn:hover { background: #E5E7EB; }
.rv3-quick-admin {
  background: rgba(29,158,117,.12) !important;
  color: #1D9E75 !important;
}
.rv3-edit-foot {
  margin-top: 24px;
  padding-top: 18px;
  border-top: 0.5px solid #E5E7EB;
  display: flex; gap: 8px; align-items: center;
}
.rv3-btn {
  padding: 7px 14px; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-btn:disabled { opacity: .55; cursor: not-allowed; }
.rv3-btn-ghost { background: transparent; border: 1px solid #E5E7EB; color: var(--t1, #1E2A4A); }
.rv3-btn-red { background: var(--bg1, #fff); border: 1px solid #E24B4A; color: #E24B4A; }
.rv3-state { padding: 60px; text-align: center; font-size: 13px; color: var(--t3, #888780); }
.rv3-err { color: #E24B4A; }
</style>
