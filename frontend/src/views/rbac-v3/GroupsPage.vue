<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import ModalShell from '@/components/ModalShell.vue';
import { groupsApi, rbacV3Api, rolesApi, permissionsApi, permissionsToLevels, levelsToPermissions, isGridManagedPermission } from '@/api/rbacV3';
import type { RbacV3Group, RbacV3GroupDetail, RbacV3UserBrief, RbacV3Role, RbacV3GroupGrant, RbacV3Permission } from '@/api/rbacV3';
import type { AccessLevel } from '@/composables/usePermissions';
import { companiesApi } from '@/api/companies';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import ModuleSelectGrid from '@/components/rbac-v3/ModuleSelectGrid.vue';
import { useToast } from '@/composables/useToast';
import { useConfirm } from '@/composables/useConfirm';

const toast = useToast();
const { confirmDialog } = useConfirm();

// ─── Точечные правила (deny / срок / scope по компаниям) ────────
interface AdvGrant { permission_code: string; grant_type: 'grant' | 'deny'; expires_at: string | null; scope_companies: string[]; }
const allPerms = ref<RbacV3Permission[]>([]);
const allCompanies = ref<{ code: string; name: string }[]>([]);
const advGrants = ref<AdvGrant[]>([]);

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
    // Базовые grant (без типа deny / срока / scope) → grid; остальные → точечные правила.
    const isAdv = (p: any) => p.grant_type === 'deny' || p.expires_at || (p.scope_companies && p.scope_companies.length);
    const basePerms = detail.value.permissions.filter(p => !isAdv(p));
    advGrants.value = detail.value.permissions.filter(isAdv).map(p => ({
      permission_code: p.code,
      grant_type: (p.grant_type === 'deny' ? 'deny' : 'grant') as 'grant' | 'deny',
      expires_at: p.expires_at ? p.expires_at.slice(0, 10) : null,
      scope_companies: p.scope_companies || [],
    }));
    levels.value = permissionsToLevels(basePerms.map(p => p.code));
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
  try { allPerms.value = await permissionsApi.list(); } catch { /* best-effort */ }
  try {
    const r = await companiesApi.list({ per_page: 500 } as any);
    const items = (r as any).items || (r as any).companies || (Array.isArray(r) ? r : []);
    allCompanies.value = items.map((c: any) => ({ code: c.code, name: c.name_ru || c.name || c.code }));
  } catch { /* scope picker degrades to manual codes */ }
});

// ─── Точечные правила: add / remove / save-сборка ────────────────
function addAdvGrant() {
  advGrants.value.push({ permission_code: allPerms.value[0]?.code || '', grant_type: 'deny', expires_at: null, scope_companies: [] });
  dirty.value = true;
}
function removeAdvGrant(i: number) { advGrants.value.splice(i, 1); dirty.value = true; }
function toggleScopeCompany(g: AdvGrant, code: string) {
  const i = g.scope_companies.indexOf(code);
  if (i >= 0) g.scope_companies.splice(i, 1); else g.scope_companies.push(code);
  dirty.value = true;
}
watch(selectedId, loadDetail);

async function selectGroup(id: string) {
  if (dirty.value && !(await confirmDialog('Есть несохранённые изменения. Перейти к другой группе?'))) return;
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
    // Собираем итоговые гранты: базовые (из grid, исключая коды точечных правил) +
    // точечные правила (deny/срок/scope). Точечное правило приоритетнее базового.
    const advCodes = new Set(advGrants.value.map(g => g.permission_code));
    // Права вне сетки (tasks.create, bp.approve, admin.*, procurement.request.*)
    // сетка не показывает и выдать не может — переносим их как есть, иначе
    // сохранение сетки молча отберёт у группы то, чего в ней не было видно.
    const kept = (detail.value?.permissions || [])
      .map(p => p.code)
      .filter(c => !isGridManagedPermission(c) && !advCodes.has(c));
    const baseGrants: RbacV3GroupGrant[] = Array.from(
      new Set([...levelsToPermissions(levels.value), ...kept]),
    )
      .filter(c => !advCodes.has(c))
      .map(c => ({ permission_code: c, grant_type: 'grant' as const }));
    const adv: RbacV3GroupGrant[] = advGrants.value
      .filter(g => g.permission_code)
      .map(g => ({
        permission_code: g.permission_code,
        grant_type: g.grant_type,
        expires_at: g.expires_at ? new Date(g.expires_at + 'T23:59:59').toISOString() : null,
        scope_companies: g.scope_companies.length ? g.scope_companies : null,
      }));
    await groupsApi.setGrants(selectedId.value, [...baseGrants, ...adv]);
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
  if (!(await confirmDialog({ message: 'Убрать пользователя из группы?', danger: true }))) return;
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
    toast.error(`Нельзя удалить группу с участниками (${detail.value.member_count} чел). Сначала уберите всех.`);
    return;
  }
  if (!(await confirmDialog({ message: `Удалить группу "${detail.value.name}"?`, danger: true }))) return;
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

        <!-- Точечные правила: deny / срок действия / scope по компаниям -->
        <div class="rv3-edit-section">
          <div class="rv3-edit-label rv3-adv-hd">
            <span>Точечные правила · запрет, срок действия, ограничение по компаниям</span>
            <button class="rv3-adv-add" @click="addAdvGrant">+ Правило</button>
          </div>
          <div v-if="!advGrants.length" class="rv3-adv-empty">
            Нет точечных правил. Используйте, чтобы <b>запретить</b> конкретное право, выдать его <b>на срок</b> или только для <b>выбранных компаний</b>.
          </div>
          <div v-for="(g, i) in advGrants" :key="i" class="rv3-adv-row" :class="{ deny: g.grant_type === 'deny' }">
            <div class="rv3-adv-main">
              <select v-model="g.grant_type" class="rv3-adv-type" :class="g.grant_type" @change="dirty = true">
                <option value="grant">Разрешить</option>
                <option value="deny">Запретить</option>
              </select>
              <select v-model="g.permission_code" class="rv3-adv-perm" @change="dirty = true">
                <option v-for="p in allPerms" :key="p.code" :value="p.code">{{ p.name || p.code }} ({{ p.code }})</option>
              </select>
              <label class="rv3-adv-exp" title="Срок действия (необязательно)">
                до <input type="date" v-model="g.expires_at" @change="dirty = true" />
              </label>
              <button class="rv3-adv-del" @click="removeAdvGrant(i)" title="Удалить правило">×</button>
            </div>
            <div class="rv3-adv-scope">
              <span class="rv3-adv-scope-l">Компании (пусто = все):</span>
              <div class="rv3-adv-chips">
                <button
                  v-for="c in allCompanies" :key="c.code"
                  class="rv3-adv-chip" :class="{ on: g.scope_companies.includes(c.code) }"
                  @click="toggleScopeCompany(g, c.code)"
                >{{ c.name }}</button>
                <span v-if="!allCompanies.length" class="rv3-adv-scope-empty">список компаний недоступен</span>
              </div>
            </div>
          </div>
        </div>

        <div class="rv3-edit-foot">
          <div style="flex:1"></div>
          <button class="rv3-btn rv3-btn-red" @click="onDelete">Удалить группу</button>
        </div>
      </template>
      <div v-else-if="groups.length > 0" class="rv3-state">Выберите группу слева</div>
    </div>

    <!-- Member picker modal -->
    <ModalShell :open="showMemberPicker" size="md" title="Добавить участника" @close="showMemberPicker = false">
        <div class="rv3-edit-label" style="margin-top:4px">Роль в этой группе</div>
        <select v-model="pickerRoleCode" class="rv3-input" style="margin-bottom:10px">
          <option v-for="r in allRoles" :key="r.code" :value="r.code">{{ r.name_ru }}</option>
        </select>
        <input v-model="memberSearch" class="rv3-input" placeholder="Поиск по имени/email..." style="margin-bottom:10px" autofocus />
        <div class="rv3-picker-list">
          <div v-for="u in availableMembers" :key="u.id" class="rv3-picker-item" @click="addMember(u.id)">
            <UserAvatar :email="u.email" :full-name="u.full_name" :avatar-url="(u as any).avatar_url" :size="26" />
            <div style="flex:1;min-width:0">
              <div class="rv3-picker-name">{{ u.full_name }}</div>
              <div class="rv3-picker-email">{{ u.email }}</div>
            </div>
          </div>
          <div v-if="availableMembers.length === 0" class="rv3-empty">никого не найдено</div>
        </div>
      <template #footer>
        <button class="rv3-btn rv3-btn-ghost" @click="showMemberPicker = false">Закрыть</button>
      </template>
    </ModalShell>

    <!-- Create group modal -->
    <ModalShell :open="showCreate" size="md" title="Новая группа" @close="showCreate = false">
        <div class="rv3-edit-label" style="margin-top:8px">Код (slug)</div>
        <input v-model="newGroup.code" class="rv3-input" placeholder="legal / finance / mining_team" />
        <div class="rv3-edit-label" style="margin-top:8px">Название</div>
        <input v-model="newGroup.name" class="rv3-input" placeholder="Юридический блок" />
        <div class="rv3-edit-label" style="margin-top:8px">Отдел (опционально)</div>
        <input v-model="newGroup.department" class="rv3-input" placeholder="Юр.управление" />
        <div class="rv3-edit-label" style="margin-top:8px">Описание (опционально)</div>
        <textarea v-model="newGroup.description" class="rv3-textarea" />
      <template #footer>
        <button class="rv3-btn rv3-btn-ghost" @click="showCreate = false">Отмена</button>
        <button class="rv3-save" :disabled="saving" @click="onCreate">
          {{ saving ? 'Создание...' : 'Создать' }}
        </button>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.rv3-groups-shell {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 1px;
  background: var(--border-hard);
  min-height: calc(100dvh - 56px);
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
  background: linear-gradient(135deg, #7C6FF7, #534AB7); border: none; color: #fff;
  cursor: pointer; width: 26px; height: 26px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(124,111,247,.3); transition: transform .15s, box-shadow .15s;
}
.rv3-gr-plus:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(124,111,247,.4); }
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
/* Точечные правила */
.rv3-adv-hd { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.rv3-adv-add { padding: 4px 12px; border: none; border-radius: 999px; background: rgba(124,111,247,.12); color: #534AB7; font-size: 11px; font-weight: 600; cursor: pointer; font-family: var(--font); transition: background .14s; }
.rv3-adv-add:hover { background: rgba(124,111,247,.22); }
.rv3-adv-empty { font-size: 12px; color: var(--t3, #94A3B8); padding: 10px 12px; background: #F7F6FD; border-radius: 10px; line-height: 1.5; }
.rv3-adv-empty b { color: var(--t2, #334155); }
.rv3-adv-row { border: 1px solid rgba(99,102,180,.12); border-radius: 12px; padding: 11px 12px; margin-top: 9px; background: #fff; }
.rv3-adv-row.deny { border-color: rgba(239,68,68,.25); background: rgba(239,68,68,.03); }
.rv3-adv-main { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rv3-adv-type { border: 1px solid rgba(99,102,180,.18); border-radius: 8px; padding: 5px 8px; font-size: 12px; font-weight: 600; font-family: var(--font); cursor: pointer; }
.rv3-adv-type.grant { color: #1D9E75; } .rv3-adv-type.deny { color: #EF4444; }
.rv3-adv-perm { flex: 1; min-width: 180px; border: 1px solid rgba(99,102,180,.18); border-radius: 8px; padding: 5px 8px; font-size: 12px; font-family: var(--font); cursor: pointer; }
.rv3-adv-exp { display: flex; align-items: center; gap: 5px; font-size: 11.5px; color: var(--t3, #94A3B8); }
.rv3-adv-exp input { border: 1px solid rgba(99,102,180,.18); border-radius: 7px; padding: 4px 7px; font-size: 12px; font-family: var(--font); }
.rv3-adv-del { width: 26px; height: 26px; border: none; border-radius: 7px; background: #F1F0FB; color: #64748B; font-size: 17px; cursor: pointer; flex-shrink: 0; }
.rv3-adv-del:hover { background: rgba(239,68,68,.12); color: #EF4444; }
.rv3-adv-scope { margin-top: 9px; }
.rv3-adv-scope-l { font-size: 10.5px; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94A3B8); display: block; margin-bottom: 5px; }
.rv3-adv-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.rv3-adv-chip { padding: 3px 10px; border: 1px solid rgba(99,102,180,.16); border-radius: 999px; background: #fff; font-size: 11px; color: var(--t2, #334155); cursor: pointer; font-family: var(--font); transition: all .13s; }
.rv3-adv-chip.on { background: #7C6FF7; border-color: #7C6FF7; color: #fff; font-weight: 600; }
.rv3-adv-scope-empty { font-size: 11px; color: #94A3B8; }
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
  background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px);
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

@media (max-width: 768px) {
  .rv3-groups-shell { grid-template-columns: 1fr; min-height: auto; }
  .rv3-gr-list { max-height: 40dvh; border-bottom: 1px solid var(--border-hard); }
}
@media (max-width: 480px) {
  .rv3-members { flex-direction: column; gap: 4px; }
  .rv3-member { width: 100%; }
  .rv3-modal { max-width: calc(100% - 24px); padding: 16px; }
  .rv3-picker-list { max-height: 50dvh; }
}
</style>
