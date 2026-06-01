<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { groupsApi, rbacV3Api, rolesApi, permissionsToLevels, levelsToPermissions } from '@/api/rbacV3';
import type { RbacV3Group, RbacV3GroupDetail, RbacV3UserBrief, RbacV3Role } from '@/api/rbacV3';
import type { AccessLevel } from '@/composables/usePermissions';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';

const groups = ref<RbacV3Group[]>([]);
const selectedId = ref<string | null>(null);
const detail = ref<RbacV3GroupDetail | null>(null);
const levels = ref<Record<string, AccessLevel>>({});
const loading = ref(false);
const error = ref<string | null>(null);
const saving = ref(false);
const dirty = ref(false);

const editName = ref('');
const editDescription = ref('');
const editDepartment = ref('');

const showCreate = ref(false);
const newGroup = ref({ code: '', name: '', description: '', department: '' });

const showMemberPicker = ref(false);
const allUsers = ref<RbacV3UserBrief[]>([]);
const memberSearch = ref('');
const allRoles = ref<RbacV3Role[]>([]);
// Default role for newly-added members (chosen in the picker modal).
const pickerRoleCode = ref<string>('viewer');

async function loadGroups() {
  try {
    groups.value = (await groupsApi.list()).sort((a, b) => a.name.localeCompare(b.name));
    if (!selectedId.value && groups.value.length > 0) selectedId.value = groups.value[0].id;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось загрузить группы';
  }
}
async function loadDetail() {
  if (!selectedId.value) { detail.value = null; return; }
  loading.value = true; error.value = null; dirty.value = false;
  try {
    detail.value = await groupsApi.get(selectedId.value);
    editName.value = detail.value.name;
    editDescription.value = detail.value.description || '';
    editDepartment.value = detail.value.department || '';
    levels.value = permissionsToLevels(detail.value.permissions.map(p => p.code));
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка загрузки группы';
  } finally {
    loading.value = false;
  }
}
onMounted(async () => {
  await loadGroups();
  try {
    allRoles.value = await rolesApi.list();
  } catch { /* role list is best-effort — picker falls back to 'viewer' */ }
});
watch(selectedId, loadDetail);

function selectGroup(id: string) {
  if (dirty.value && !confirm('Есть несохранённые изменения. Перейти к другой группе?')) return;
  selectedId.value = id;
}
function onLevelChange(newLevels: Record<string, AccessLevel>) {
  levels.value = newLevels;
  dirty.value = true;
}

async function save() {
  if (!detail.value || !selectedId.value) return;
  saving.value = true; error.value = null;
  try {
    if (editName.value !== detail.value.name ||
        editDescription.value !== (detail.value.description || '') ||
        editDepartment.value !== (detail.value.department || '')) {
      await groupsApi.update(selectedId.value, {
        name: editName.value,
        description: editDescription.value || undefined,
        department: editDepartment.value || undefined,
      });
    }
    const newCodes = levelsToPermissions(levels.value);
    const oldCodes = detail.value.permissions.map(p => p.code).sort().join(',');
    if (newCodes.sort().join(',') !== oldCodes) {
      await groupsApi.setPermissions(selectedId.value, newCodes);
    }
    await loadGroups();
    await loadDetail();
    dirty.value = false;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка сохранения';
  } finally {
    saving.value = false;
  }
}

async function removeMember(userId: string) {
  if (!detail.value || !selectedId.value) return;
  if (!confirm('Убрать пользователя из группы?')) return;
  try {
    // Pack 147: preserve each remaining member's role_code (default 'viewer')
    const remaining = detail.value.members
      .filter(m => m.id !== userId)
      .map(m => ({ user_id: m.id, role_code: m.role_code || 'viewer' }));
    await groupsApi.setMembers(selectedId.value, remaining);
    await loadDetail();
    await loadGroups();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка';
  }
}
async function addMember(userId: string) {
  if (!detail.value || !selectedId.value) return;
  if (detail.value.members.some(m => m.id === userId)) return;
  try {
    // Pack 147: keep existing roles; new user gets pickerRoleCode (default 'viewer').
    const all = [
      ...detail.value.members.map(m => ({ user_id: m.id, role_code: m.role_code || 'viewer' })),
      { user_id: userId, role_code: pickerRoleCode.value || 'viewer' },
    ];
    await groupsApi.setMembers(selectedId.value, all);
    await loadDetail();
    await loadGroups();
    showMemberPicker.value = false;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Ошибка';
  }
}

async function changeMemberRole(userId: string, newRoleCode: string) {
  if (!detail.value || !selectedId.value) return;
  try {
    const updated = detail.value.members.map(m => ({
      user_id: m.id,
      role_code: m.id === userId ? newRoleCode : (m.role_code || 'viewer'),
    }));
    await groupsApi.setMembers(selectedId.value, updated);
    await loadDetail();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось сменить роль';
  }
}
async function openMemberPicker() {
  showMemberPicker.value = true;
  if (allUsers.value.length === 0) {
    try {
      const resp = await rbacV3Api.listUsers({ limit: 200, is_active: true });
      allUsers.value = resp.items;
    } catch (e: any) {
      error.value = e?.response?.data?.detail || 'Ошибка загрузки пользователей';
    }
  }
}

async function onCreate() {
  if (!newGroup.value.code.trim() || !newGroup.value.name.trim()) {
    error.value = 'Код и название обязательны';
    return;
  }
  saving.value = true;
  try {
    const created = await groupsApi.create({
      code: newGroup.value.code.trim(),
      name: newGroup.value.name.trim(),
      description: newGroup.value.description.trim() || undefined,
      department: newGroup.value.department.trim() || undefined,
    });
    showCreate.value = false;
    newGroup.value = { code: '', name: '', description: '', department: '' };
    await loadGroups();
    selectedId.value = created.id;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось создать группу';
  } finally {
    saving.value = false;
  }
}

async function onDelete() {
  if (!detail.value || !selectedId.value) return;
  if (detail.value.member_count > 0) {
    alert(`Нельзя удалить группу с участниками (${detail.value.member_count} чел). Сначала уберите всех.`);
    return;
  }
  if (!confirm(`Удалить группу "${detail.value.name}"?`)) return;
  try {
    await groupsApi.remove(selectedId.value);
    selectedId.value = null;
    detail.value = null;
    await loadGroups();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось удалить группу';
  }
}

const availableMembers = computed(() => {
  if (!detail.value) return [];
  const existing = new Set(detail.value.members.map(m => m.id));
  return allUsers.value.filter(u =>
    !existing.has(u.id) &&
    (!memberSearch.value.trim() ||
      (u.full_name + ' ' + u.email).toLowerCase().includes(memberSearch.value.trim().toLowerCase()))
  );
});

const byDept = computed(() => {
  const map = new Map<string, RbacV3Group[]>();
  for (const g of groups.value) {
    const key = g.department || 'Без отдела';
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(g);
  }
  return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
});
</script>

<template>
  <div class="rv3-groups-shell">
    <!-- LEFT -->
    <div class="rv3-gr-list">
      <div class="rv3-gr-list-hd">
        <span class="rv3-rl-section-hd">Группы · {{ groups.length }}</span>
        <button class="rv3-gr-plus" @click="showCreate = true" aria-label="add">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="3" x2="8" y2="13"/><line x1="3" y1="8" x2="13" y2="8"/></svg>
        </button>
      </div>

      <template v-for="[dept, list] in byDept" :key="dept">
        <div class="rv3-rl-section-hd" style="padding-top:14px">{{ dept }} · {{ list.length }}</div>
        <div
          v-for="g in list"
          :key="g.id"
          :class="['rv3-rl-item', { on: selectedId === g.id }]"
          @click="selectGroup(g.id)"
        >
          <div class="rv3-gr-name">{{ g.name }}</div>
          <div class="rv3-gr-meta">{{ g.member_count }} чел · {{ g.permission_count }} разреш.</div>
        </div>
      </template>

      <div v-if="groups.length === 0" class="rv3-state">Групп пока нет</div>
    </div>

    <!-- RIGHT -->
    <div class="rv3-gr-edit">
      <div v-if="loading" class="rv3-state">Загрузка...</div>
      <div v-else-if="error" class="rv3-state rv3-err">{{ error }}</div>
      <template v-else-if="detail">
        <div class="rv3-gr-edit-hd">
          <div class="rv3-gr-edit-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#534AB7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
          </div>
          <div style="flex:1;">
            <input v-model="editName" class="rv3-gr-title-input" @input="dirty = true" />
            <div class="rv3-gr-meta-row">
              <span>code: <code>{{ detail.code }}</code></span>
              <span>·</span>
              <span>{{ detail.member_count }} участников</span>
            </div>
          </div>
          <button class="rv3-save" :disabled="!dirty || saving" @click="save">
            {{ saving ? 'Сохранение...' : (dirty ? 'Сохранить' : 'Сохранено') }}
          </button>
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label">Описание</div>
          <textarea
            v-model="editDescription"
            class="rv3-textarea"
            @input="dirty = true"
            placeholder="Назначение группы"
          ></textarea>
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label">Отдел</div>
          <input
            v-model="editDepartment"
            class="rv3-input"
            @input="dirty = true"
            placeholder="Финансовый блок / Юр.управление / ..."
          />
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label rv3-edit-label-row">
            <span>Участники · {{ detail.members.length }}</span>
            <button class="rv3-link-btn" @click="openMemberPicker">+ добавить</button>
          </div>
          <div class="rv3-members">
            <div v-for="m in detail.members" :key="m.id" class="rv3-member">
              <UserAvatar :email="m.email" :full-name="m.full_name" :size="22" />
              <span class="rv3-member-name">{{ m.full_name }}</span>
              <select
                class="rv3-member-role"
                :value="m.role_code || 'viewer'"
                @change="changeMemberRole(m.id, ($event.target as HTMLSelectElement).value)"
                :title="`Роль в группе: ${m.role_name || m.role_code || 'viewer'}`"
              >
                <option v-for="r in allRoles" :key="r.code" :value="r.code">{{ r.name_ru }}</option>
              </select>
              <span class="rv3-member-x" @click="removeMember(m.id)">×</span>
            </div>
            <span v-if="detail.members.length === 0" class="rv3-empty">никого нет — добавьте через кнопку справа</span>
          </div>
        </div>

        <div class="rv3-edit-section">
          <div class="rv3-edit-label">Групповые разрешения · выдаются всем участникам</div>
          <ModuleSelectGrid
            :model-value="levels"
            :editable="true"
            :columns="4"
            @update:model-value="onLevelChange"
          />
        </div>

        <div class="rv3-edit-foot">
          <div style="flex:1"></div>
          <button class="rv3-btn rv3-btn-red" @click="onDelete">Удалить группу</button>
        </div>
      </template>
      <div v-else-if="groups.length > 0" class="rv3-state">Выберите группу слева</div>
    </div>

    <!-- Member picker modal -->
    <div v-if="showMemberPicker" class="rv3-modal-bd" @click.self="showMemberPicker = false">
      <div class="rv3-modal">
        <div class="rv3-modal-hd">Добавить участника</div>
        <div class="rv3-edit-label" style="margin-top:4px">Роль в этой группе</div>
        <select v-model="pickerRoleCode" class="rv3-input" style="margin-bottom:10px">
          <option v-for="r in allRoles" :key="r.code" :value="r.code">{{ r.name_ru }}</option>
        </select>
        <input v-model="memberSearch" class="rv3-input" placeholder="Поиск по имени/email..." style="margin-bottom:10px" autofocus />
        <div class="rv3-picker-list">
          <div v-for="u in availableMembers" :key="u.id" class="rv3-picker-item" @click="addMember(u.id)">
            <UserAvatar :email="u.email" :full-name="u.full_name" :size="26" />
            <div style="flex:1;min-width:0">
              <div class="rv3-picker-name">{{ u.full_name }}</div>
              <div class="rv3-picker-email">{{ u.email }}</div>
            </div>
          </div>
          <div v-if="availableMembers.length === 0" class="rv3-empty">никого не найдено</div>
        </div>
        <div style="display:flex;justify-content:flex-end;margin-top:14px;">
          <button class="rv3-btn rv3-btn-ghost" @click="showMemberPicker = false">Закрыть</button>
        </div>
      </div>
    </div>

    <!-- Create group modal -->
    <div v-if="showCreate" class="rv3-modal-bd" @click.self="showCreate = false">
      <div class="rv3-modal">
        <div class="rv3-modal-hd">Новая группа</div>
        <div class="rv3-edit-label" style="margin-top:8px">Код (slug)</div>
        <input v-model="newGroup.code" class="rv3-input" placeholder="legal / finance / mining_team" />
        <div class="rv3-edit-label" style="margin-top:8px">Название</div>
        <input v-model="newGroup.name" class="rv3-input" placeholder="Юридический блок" />
        <div class="rv3-edit-label" style="margin-top:8px">Отдел (опционально)</div>
        <input v-model="newGroup.department" class="rv3-input" placeholder="Юр.управление" />
        <div class="rv3-edit-label" style="margin-top:8px">Описание (опционально)</div>
        <textarea v-model="newGroup.description" class="rv3-textarea" />
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px;">
          <button class="rv3-btn rv3-btn-ghost" @click="showCreate = false">Отмена</button>
          <button class="rv3-save" :disabled="saving" @click="onCreate">
            {{ saving ? 'Создание...' : 'Создать' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rv3-groups-shell {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 1px;
  background: var(--border-hard);
  min-height: calc(100vh - 56px);
  position: relative;
}
.rv3-gr-list { background: var(--bg1, #fff); padding: 16px 0; overflow-y: auto; }
.rv3-gr-list-hd { padding: 0 18px 12px; display: flex; align-items: center; justify-content: space-between; }
.rv3-rl-section-hd {
  padding: 0 18px 8px;
  font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase;
}
.rv3-gr-plus {
  background: transparent; border: none; color: var(--p-deep);
  cursor: pointer; padding: 2px; display: flex; align-items: center;
}
.rv3-rl-item {
  padding: 10px 18px;
  cursor: pointer;
  position: relative; overflow: hidden;
}
.rv3-rl-item:hover { background: var(--bg2, #FAFAFC); }
.rv3-rl-item.on { background: rgba(127,119,221,.06); }
.rv3-rl-item.on::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.rv3-gr-name { font-size: 13px; font-weight: 500; margin-bottom: 2px; }
.rv3-gr-meta { font-size: 10.5px; color: var(--t3, var(--t-muted)); }

.rv3-gr-edit { background: var(--bg1, #fff); padding: 24px 28px; overflow-y: auto; }
.rv3-gr-edit-hd { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 18px; }
.rv3-gr-edit-icon {
  width: 42px; height: 42px;
  background: rgba(127,119,221,.12);
  border: 1px solid rgba(127,119,221,.3);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.rv3-gr-title-input {
  font-size: 16px; font-weight: 500; letter-spacing: -.01em;
  border: none; outline: none; background: transparent;
  padding: 0; width: 100%; color: var(--t1, #1E2A4A);
  font-family: inherit;
}
.rv3-gr-meta-row {
  font-size: 11px; color: var(--t3, var(--t-muted)); margin-top: 3px;
  display: flex; align-items: center; gap: 8px;
}
.rv3-gr-meta-row code {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace; color: var(--t1, #1E2A4A);
}
.rv3-save {
  padding: 7px 14px;
  background: var(--green); color: #fff;
  border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-save:disabled { background: var(--border-hard); color: var(--t3, var(--t-muted)); cursor: not-allowed; }
.rv3-edit-section { margin-bottom: 18px; }
.rv3-edit-label {
  font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 6px;
}
.rv3-edit-label-row { display: flex; align-items: center; justify-content: space-between; }
.rv3-input {
  width: 100%; padding: 8px 12px;
  border: 0.5px solid var(--border-hard); border-radius: 8px;
  font-size: 12px; color: var(--t1, #1E2A4A); outline: none;
  font-family: inherit;
}
.rv3-textarea {
  width: 100%; padding: 9px 12px;
  border: 0.5px solid var(--border-hard); border-radius: 8px;
  font-size: 12px; color: var(--t1, #1E2A4A); outline: none;
  resize: vertical; min-height: 48px;
  font-family: inherit;
}
.rv3-link-btn {
  background: transparent; border: none; color: var(--p-deep);
  font-size: 11px; font-weight: 500; cursor: pointer;
  font-family: inherit;
}
.rv3-members { display: flex; flex-wrap: wrap; gap: 8px; }
.rv3-member {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px 4px 4px;
  background: var(--bg2, #F9FAFB); border: 0.5px solid var(--border-hard);
  border-radius: 14px; font-size: 11px;
}
.rv3-member-name { font-weight: 500; }
.rv3-member-role {
  margin-left: 6px;
  padding: 1px 4px 1px 6px;
  font-size: 10.5px;
  border: 0.5px solid #D1D5DB;
  border-radius: 4px;
  background: var(--bg1, #fff);
  color: var(--p-deep);
  cursor: pointer;
  font-weight: 500;
}
.rv3-member-role:hover { background: var(--bg2, #FAFAFC); border-color: #7F77DD; }
.rv3-member-x {
  color: var(--t3, var(--t-muted)); cursor: pointer; padding: 0 3px;
}
.rv3-member-x:hover { color: var(--sev-high); }
.rv3-empty { font-size: 11.5px; color: var(--t3, var(--t-muted)); font-style: italic; }
.rv3-edit-foot {
  margin-top: 24px;
  padding-top: 18px;
  border-top: 0.5px solid var(--border-hard);
  display: flex; gap: 8px; align-items: center;
}
.rv3-btn {
  padding: 7px 14px; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-btn-ghost { background: transparent; border: 1px solid var(--border-hard); color: var(--t1, #1E2A4A); }
.rv3-btn-red { background: var(--bg1, #fff); border: 1px solid var(--sev-high); color: var(--sev-high); }
.rv3-btn-red:hover { background: rgba(226,75,74,.06); }
.rv3-state { padding: 60px; text-align: center; font-size: 13px; color: var(--t3, var(--t-muted)); }
.rv3-err { color: var(--sev-high); }

.rv3-modal-bd {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(15,18,40,.45); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  padding: 36px;
}
.rv3-modal {
  width: 480px; max-width: 100%;
  background: var(--bg1, #fff); border-radius: 14px;
  padding: 20px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18);
}
.rv3-modal-hd {
  font-size: 15px; font-weight: 500; letter-spacing: -.01em;
  margin-bottom: 14px;
}
.rv3-picker-list {
  max-height: 360px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 2px;
}
.rv3-picker-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 11px; border-radius: 7px;
  cursor: pointer;
}
.rv3-picker-item:hover { background: var(--bg2, #FAFAFC); }
.rv3-picker-name { font-size: 12.5px; font-weight: 500; }
.rv3-picker-email { font-size: 10.5px; color: var(--t3, var(--t-muted)); }
</style>
