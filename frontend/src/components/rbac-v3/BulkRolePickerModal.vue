<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { rolesApi, rbacV3Api } from '@/api/rbacV3';
import type { RbacV3Role } from '@/api/rbacV3';
import RoleChip from './RoleChip.vue';

const props = defineProps<{ selectedIds: string[] }>();
const emit = defineEmits<{ (e: 'close'): void; (e: 'done'): void }>();

type Mode = 'add' | 'replace' | 'remove';
const mode = ref<Mode>('add');
const allRoles = ref<RbacV3Role[]>([]);
const chosenRole = ref<string | null>(null);
const progress = ref<{ done: number; total: number; failed: string[] }>({ done: 0, total: 0, failed: [] });
const applying = ref(false);

onMounted(async () => {
  try { allRoles.value = await rolesApi.list(); }
  catch (e) { console.error(e); }
});

const modeLabel = computed(() => {
  if (mode.value === 'add') return 'Добавить роль ' + props.selectedIds.length + ' пользователям';
  if (mode.value === 'replace') return 'Заменить все роли на одну у ' + props.selectedIds.length + ' пользователей';
  return 'Убрать роль у ' + props.selectedIds.length + ' пользователей';
});

async function apply() {
  if (!chosenRole.value) return;
  applying.value = true;
  progress.value = { done: 0, total: props.selectedIds.length, failed: [] };
  for (const uid of props.selectedIds) {
    try {
      const detail = await rbacV3Api.getUser(uid);
      let next: string[];
      if (mode.value === 'add') {
        next = Array.from(new Set([...detail.role_codes, chosenRole.value!]));
      } else if (mode.value === 'replace') {
        next = [chosenRole.value!];
      } else {
        next = detail.role_codes.filter(r => r !== chosenRole.value);
      }
      await rbacV3Api.update(uid, { role_codes: next });
    } catch (e: any) {
      progress.value.failed.push(uid);
    } finally {
      progress.value.done++;
    }
  }
  applying.value = false;
}

function done() { emit('done'); emit('close'); }
</script>

<template>
  <div class="rv3-modal-bd" @click.self="emit('close')">
    <div class="rv3-modal">
      <div class="rv3-modal-hd">{{ modeLabel }}</div>

      <!-- Mode selector -->
      <div class="rv3-edit-label">Действие</div>
      <div class="rv3-mode-row">
        <button :class="['rv3-mode-btn', { on: mode === 'add' }]" @click="mode = 'add'" :disabled="applying">+ Добавить роль</button>
        <button :class="['rv3-mode-btn', { on: mode === 'replace' }]" @click="mode = 'replace'" :disabled="applying">↻ Заменить все роли</button>
        <button :class="['rv3-mode-btn', { on: mode === 'remove' }]" @click="mode = 'remove'" :disabled="applying">− Убрать роль</button>
      </div>

      <div class="rv3-edit-label" style="margin-top:14px">Роль</div>
      <div class="rv3-role-picker">
        <button
          v-for="r in allRoles"
          :key="r.code"
          type="button"
          :class="['rv3-role-toggle', { on: chosenRole === r.code }]"
          :disabled="applying"
          @click="chosenRole = r.code"
        >
          <RoleChip :code="r.code" size="sm" />
          <span class="rv3-role-toggle-name">{{ r.name_ru }}</span>
        </button>
      </div>

      <!-- Progress -->
      <div v-if="applying || (progress.done > 0 && !applying)" class="rv3-progress">
        <div class="rv3-progress-bar">
          <div class="rv3-progress-fill" :style="{ width: (progress.done / progress.total * 100) + '%' }"></div>
        </div>
        <div class="rv3-progress-text">
          {{ progress.done }} / {{ progress.total }}
          <span v-if="progress.failed.length > 0" style="color:#E24B4A">· ошибок: {{ progress.failed.length }}</span>
        </div>
      </div>

      <div class="rv3-modal-foot">
        <button class="rv3-btn rv3-btn-ghost" @click="emit('close')" :disabled="applying">
          {{ progress.done > 0 && !applying ? 'Закрыть' : 'Отмена' }}
        </button>
        <button
          v-if="!(progress.done > 0 && !applying)"
          class="rv3-save"
          :disabled="!chosenRole || applying"
          @click="apply"
        >{{ applying ? 'Применение...' : 'Применить' }}</button>
        <button
          v-if="progress.done > 0 && !applying"
          class="rv3-save"
          @click="done"
        >Готово</button>
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
  width: 520px; max-width: 100%;
  background: var(--bg1, #fff); border: 1px solid var(--card-border, transparent); border-radius: 14px;
  padding: 22px 24px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18);
}
.rv3-modal-hd { font-size: 14px; font-weight: 500; letter-spacing: -.01em; margin-bottom: 14px; }
.rv3-edit-label {
  font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase; margin-bottom: 6px;
}
.rv3-mode-row { display: flex; gap: 6px; }
.rv3-mode-btn {
  flex: 1;
  padding: 8px 11px;
  background: var(--bg2, #F9FAFB); border: 1px solid var(--border-hard); border-radius: 8px;
  font-size: 11px; font-weight: 500; color: var(--t1, #1E2A4A);
  cursor: pointer; font-family: inherit;
}
.rv3-mode-btn:hover:not(:disabled) { border-color: #D1D5DB; }
.rv3-mode-btn.on { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.4); color: var(--p-deep); }
.rv3-mode-btn:disabled { opacity: .55; cursor: not-allowed; }
.rv3-role-picker { display: flex; flex-wrap: wrap; gap: 6px; }
.rv3-role-toggle {
  display: flex; align-items: center; gap: 7px;
  padding: 5px 10px;
  background: var(--bg2, #F9FAFB); border: 1px solid var(--border-hard); border-radius: 14px;
  cursor: pointer; font-family: inherit; font-size: 11px;
}
.rv3-role-toggle:hover:not(:disabled) { background: var(--bg1, #fff); border-color: #D1D5DB; }
.rv3-role-toggle.on { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.4); }
.rv3-role-toggle:disabled { opacity: .55; cursor: not-allowed; }
.rv3-role-toggle-name { color: var(--t1, #1E2A4A); }
.rv3-progress { margin-top: 14px; }
.rv3-progress-bar {
  height: 6px; background: #F3F4F8; border-radius: 3px; overflow: hidden;
}
.rv3-progress-fill {
  height: 100%; background: var(--green); transition: width .15s;
}
.rv3-progress-text { margin-top: 6px; font-size: 11px; color: var(--t3, var(--t-muted)); }
.rv3-modal-foot {
  display: flex; gap: 8px; justify-content: flex-end;
  margin-top: 16px;
}
.rv3-btn {
  padding: 7px 14px; border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-btn-ghost { background: transparent; border: 1px solid var(--border-hard); color: var(--t1, #1E2A4A); }
.rv3-save {
  padding: 7px 14px;
  background: var(--green); color: #fff; border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit;
}
.rv3-save:disabled { background: var(--border-hard); color: var(--t3, var(--t-muted)); cursor: not-allowed; }
</style>