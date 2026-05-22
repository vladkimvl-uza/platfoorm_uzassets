<script setup lang="ts">
import { onMounted, ref } from "vue";
import { moderationApi, type SubmittedUser } from "@/api/moderation";

const emit = defineEmits<{ change: [] }>();

const items = ref<SubmittedUser[]>([]);
const loading = ref(false);
const saving = ref<Record<string, boolean>>({});
const error = ref<string | null>(null);
const query = ref("");

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const r = await moderationApi.submittedUsers();
    items.value = r.items;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  } finally { loading.value = false; }
}
onMounted(load);

async function patchFlag(u: SubmittedUser, key: "is_external" | "bypass_moderation", value: boolean) {
  saving.value[u.id] = true;
  try {
    const updated = await moderationApi.patchUserFlags(u.id, { [key]: value });
    const i = items.value.findIndex((x) => x.id === u.id);
    if (i >= 0) {
      items.value[i] = { ...items.value[i], ...updated };
      // List filter is now is_external only — drop on toggle-off.
      if (!items.value[i].is_external) {
        items.value.splice(i, 1);
      }
    }
    emit("change");
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  } finally { saving.value[u.id] = false; }
}

async function patchOrg(u: SubmittedUser, value: string) {
  saving.value[u.id] = true;
  try {
    await moderationApi.patchUserFlags(u.id, { external_org_name: value });
    const i = items.value.findIndex((x) => x.id === u.id);
    if (i >= 0) items.value[i] = { ...items.value[i], external_org_name: value || null };
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  } finally { saving.value[u.id] = false; }
}

function initials(u: SubmittedUser): string {
  if (!u.full_name) return u.email.slice(0, 2).toUpperCase();
  const parts = u.full_name.split(" ").filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return u.full_name.slice(0, 2).toUpperCase();
}

const filtered = () => {
  const q = query.value.trim().toLowerCase();
  if (!q) return items.value;
  return items.value.filter((u) =>
    (u.full_name || "").toLowerCase().includes(q) ||
    u.email.toLowerCase().includes(q) ||
    (u.external_org_name || "").toLowerCase().includes(q),
  );
};
</script>

<template>
  <div class="su-wrap">
    <div class="su-hd">
      <i class="ti ti-info-circle" aria-hidden="true"></i>
      <span>
        Все пользователи с активным <code>is_external</code>. Их записи матчатся
        правилами с <code>trigger_is_external=true</code> и попадают в очередь модерации.
        <code>bypass_moderation</code> отключает модерацию для конкретного юзера,
        даже если <code>is_external</code> включён. Добавить/убрать
        <code>is_external</code> у любого юзера — на странице пользователя
        (раздел «Безопасность» → «Модерация»).
      </span>
    </div>

    <div class="su-toolbar">
      <input v-model="query" placeholder="Поиск по имени / email / орг..." class="su-search"/>
      <button class="su-reload" @click="load" :disabled="loading">
        <i class="ti ti-refresh" aria-hidden="true"></i>
      </button>
    </div>

    <div v-if="error" class="su-err">{{ error }}</div>

    <div v-if="loading && !items.length" class="su-empty">Загрузка…</div>
    <div v-else-if="!filtered().length" class="su-empty">
      <i class="ti ti-user-exclamation" style="font-size: 24px; color: #888780;" aria-hidden="true"></i>
      <div v-if="query">По запросу "{{ query }}" ничего не найдено</div>
      <div v-else>Пользователей под модерацию нет</div>
    </div>

    <table v-else class="su-table">
      <thead>
        <tr>
          <th>Пользователь</th>
          <th>Организация</th>
          <th class="su-c">external</th>
          <th class="su-c">обход</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in filtered()" :key="u.id" :class="{ inactive: !u.is_active }">
          <td>
            <div class="su-user-cell">
              <span class="su-avatar" :class="{ ext: u.is_external }">{{ initials(u) }}</span>
              <div>
                <div class="su-user-name">{{ u.full_name || u.email }}</div>
                <div class="su-user-email">{{ u.email }}</div>
              </div>
            </div>
          </td>
          <td>
            <input v-if="u.is_external"
                   class="su-org-input"
                   :value="u.external_org_name ?? ''"
                   placeholder="название организации..."
                   @blur="patchOrg(u, ($event.target as HTMLInputElement).value)"/>
            <span v-else class="su-org-dash">—</span>
          </td>
          <td class="su-c">
            <label class="su-switch">
              <input type="checkbox" :checked="u.is_external" :disabled="!!saving[u.id]"
                     @change="patchFlag(u, 'is_external', ($event.target as HTMLInputElement).checked)"/>
              <span class="su-switch-tr"></span>
            </label>
          </td>
          <td class="su-c">
            <label class="su-switch">
              <input type="checkbox" :checked="u.bypass_moderation" :disabled="!!saving[u.id]"
                     @change="patchFlag(u, 'bypass_moderation', ($event.target as HTMLInputElement).checked)"/>
              <span class="su-switch-tr"></span>
            </label>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.su-wrap { display: flex; flex-direction: column; gap: 10px; }

.su-hd {
  background: rgba(212,83,126,.06);
  border-radius: 7px;
  padding: 8px 12px;
  font-size: 11px;
  color: var(--color-text-secondary);
  display: flex; align-items: flex-start; gap: 7px;
  line-height: 1.45;
  position: relative; overflow: hidden;
}
.su-hd::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #D4537E;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .6s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  pointer-events: none;
}
.su-hd i { font-size: 14px; color: #993556; margin-top: 1px; flex-shrink: 0; }
.su-hd code {
  background: rgba(0,0,0,.04);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
  font-family: monospace;
}

.su-toolbar { display: flex; gap: 6px; align-items: center; }
.su-search {
  flex: 1;
  padding: 7px 11px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 7px;
  font-size: 11.5px;
  font-family: inherit;
  outline: none;
}
.su-reload {
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  color: var(--color-text-secondary);
  padding: 7px 11px;
  border-radius: 7px;
  cursor: pointer;
  font-family: inherit;
}

.su-err { background: rgba(226,75,74,.08); color: #A32D2D; padding: 8px 12px; border-radius: 7px; font-size: 11.5px; }

.su-empty {
  padding: 60px 20px;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 12px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}

.su-table {
  width: 100%;
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 10px;
  border-collapse: separate;
  border-spacing: 0;
  overflow: hidden;
}
.su-table thead th {
  background: #FAFAFC;
  padding: 9px 11px;
  text-align: left;
  font-size: 9.5px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 500;
  border-bottom: 0.5px solid var(--color-border-tertiary);
}
.su-table tbody td {
  padding: 9px 11px;
  border-bottom: 0.5px solid rgba(0,0,0,.04);
  font-size: 11.5px;
  vertical-align: middle;
}
.su-table tbody tr:last-child td { border-bottom: 0; }
.su-table tbody tr.inactive { opacity: .55; }
.su-c { text-align: center; }

.su-user-cell { display: flex; align-items: center; gap: 8px; }
.su-avatar {
  width: 28px; height: 28px;
  border-radius: 50%;
  background: rgba(127,119,221,.15);
  color: #534AB7;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10.5px; font-weight: 500;
  flex-shrink: 0;
}
.su-avatar.ext { background: rgba(212,83,126,.15); color: #993556; }
.su-user-name { font-size: 12px; color: var(--color-text-primary); font-weight: 500; }
.su-user-email { font-size: 10px; color: var(--color-text-tertiary); margin-top: 1px; }

.su-org-input {
  width: 100%;
  padding: 4px 9px;
  border: 0.5px solid transparent;
  border-radius: 5px;
  font-size: 11.5px;
  font-family: inherit;
  background: transparent;
  color: var(--color-text-primary);
  outline: none;
  transition: background .12s, border-color .12s;
}
.su-org-input:hover, .su-org-input:focus {
  background: var(--color-background-secondary);
  border-color: var(--color-border-tertiary);
}
.su-org-dash { color: var(--color-text-tertiary); }

.su-switch { position: relative; display: inline-block; width: 30px; height: 16px; cursor: pointer; }
.su-switch input { opacity: 0; width: 0; height: 0; }
.su-switch input:disabled + .su-switch-tr { opacity: .5; cursor: not-allowed; }
.su-switch-tr { position: absolute; inset: 0; background: #D3D1C7; border-radius: 9px; transition: background .2s; }
.su-switch-tr::before {
  content: "";
  position: absolute;
  top: 2px; left: 2px;
  width: 12px; height: 12px;
  background: #fff;
  border-radius: 50%;
  transition: left .2s;
}
.su-switch input:checked + .su-switch-tr { background: #1D9E75; }
.su-switch input:checked + .su-switch-tr::before { left: 16px; }
</style>
