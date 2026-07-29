<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { rbacV3Api, rolesApi, type RbacV3Role } from '@/api/rbacV3';
import ModalShell from '@/components/ModalShell.vue';
import BIcon from '@/components/broadcasts/BIcon.vue';
import { useI18n } from '@/composables/useI18n';
import { INTL_LOCALE } from '@/locale';
import RoleAssignmentPicker from './RoleAssignmentPicker.vue';

const props = defineProps<{ selectedIds: string[] }>();
const emit = defineEmits<{ (e: 'close'): void; (e: 'done'): void }>();
const { t, locale } = useI18n();

type Mode = 'add' | 'replace' | 'remove';

const mode = ref<Mode>('add');
const allRoles = ref<RbacV3Role[]>([]);
const chosenRole = ref<string | null>(null);
const loading = ref(true);
const catalogError = ref<string | null>(null);
const applying = ref(false);
const progress = ref({ done: 0, total: 0, failed: [] as string[] });
// Причины отказов: без них администратор видел только «Ошибок: N» и не понимал,
// что бэкенд отклонил операцию (например, роль admin назначает только owner).
const failReasons = ref<string[]>([]);

onMounted(async () => {
  try {
    allRoles.value = await rolesApi.list();
  } catch (error: any) {
    catalogError.value = error?.response?.data?.detail || t('Не удалось загрузить роли');
  } finally {
    loading.value = false;
  }
});

const chosenRoles = computed<string[]>({
  get: () => chosenRole.value ? [chosenRole.value] : [],
  set: value => { chosenRole.value = value[0] || null; },
});

const selectedRoleName = computed(() =>
  allRoles.value.find(role => role.code === chosenRole.value)?.name_ru || t('Роль не выбрана'));

function formatCount(value: number): string {
  return value.toLocaleString(INTL_LOCALE[locale.value]);
}

const actionSummary = computed(() => {
  const values = { count: formatCount(props.selectedIds.length), role: selectedRoleName.value };
  if (!chosenRole.value) return t('Выбрано пользователей: {count}', values);
  if (mode.value === 'add') return t('Добавить роль «{role}» · Пользователей: {count}', values);
  if (mode.value === 'replace') return t('Оставить только роль «{role}» · Пользователей: {count}', values);
  return t('Убрать роль «{role}» · Пользователей: {count}', values);
});

const complete = computed(() => progress.value.total > 0 && progress.value.done === progress.value.total);

async function apply() {
  if (!chosenRole.value || applying.value) return;
  applying.value = true;
  progress.value = { done: 0, total: props.selectedIds.length, failed: [] };
  failReasons.value = [];

  for (const userId of props.selectedIds) {
    try {
      const detail = await rbacV3Api.getUser(userId);
      let nextRoles: string[];
      if (mode.value === 'add') {
        nextRoles = Array.from(new Set([...detail.role_codes, chosenRole.value]));
      } else if (mode.value === 'replace') {
        nextRoles = [chosenRole.value];
      } else {
        nextRoles = detail.role_codes.filter(role => role !== chosenRole.value);
      }
      await rbacV3Api.update(userId, { role_codes: nextRoles });
    } catch (e: any) {
      progress.value.failed.push(userId);
      const detail = e?.response?.data?.detail;
      const reason = typeof detail === 'string' ? detail : t('Не удалось обновить роли');
      if (!failReasons.value.includes(reason)) failReasons.value.push(reason);
    } finally {
      progress.value.done++;
    }
  }
  applying.value = false;
}

function finish() {
  emit('done');
  emit('close');
}

function requestClose() {
  if (!applying.value) emit('close');
}
</script>

<template>
  <ModalShell :open="true" size="lg" :close-on-overlay="!applying" :hide-close="applying" @close="requestClose">
    <template #header>
      <div class="brp-header">
        <h2>{{ t('Изменить роли') }}</h2>
        <p>{{ t('Пользователей: {count}', { count: formatCount(selectedIds.length) }) }}</p>
      </div>
    </template>

    <div v-if="!complete" class="brp-body">
      <div class="brp-label">{{ t('Действие') }}</div>
      <div class="brp-modes" role="tablist" :aria-label="t('Действие с ролью')">
        <button type="button" :class="{ on: mode === 'add' }" :disabled="applying" @click="mode = 'add'">
          <BIcon name="plus" :size="16" />
          <span><b>{{ t('Добавить') }}</b><small>{{ t('Сохранить текущие роли') }}</small></span>
        </button>
        <button type="button" :class="{ on: mode === 'replace' }" :disabled="applying" @click="mode = 'replace'">
          <BIcon name="refresh" :size="16" />
          <span><b>{{ t('Заменить') }}</b><small>{{ t('Оставить одну роль') }}</small></span>
        </button>
        <button type="button" :class="{ on: mode === 'remove' }" :disabled="applying" @click="mode = 'remove'">
          <BIcon name="x" :size="16" />
          <span><b>{{ t('Убрать') }}</b><small>{{ t('Остальные роли сохранятся') }}</small></span>
        </button>
      </div>

      <div class="brp-label role">{{ t('Роль') }}</div>
      <RoleAssignmentPicker
        v-model="chosenRoles"
        :roles="allRoles"
        :multiple="false"
        :disabled="applying"
        compact
      />
      <div v-if="loading" class="brp-loading">{{ t('Загрузка ролей...') }}</div>
      <div v-else-if="catalogError" class="brp-error">{{ catalogError }}</div>

      <div :class="['brp-summary', { warning: mode !== 'add' }]">
        <BIcon :name="mode === 'add' ? 'info-circle' : 'lock'" :size="15" />
        <span>{{ actionSummary }}</span>
      </div>

      <div v-if="applying" class="brp-progress">
        <div class="brp-progress-track">
          <span :style="{ width: `${progress.total ? progress.done / progress.total * 100 : 0}%` }"></span>
        </div>
        <div>
          <span>{{ t('Обработано: {done} из {total}', {
            done: formatCount(progress.done),
            total: formatCount(progress.total),
          }) }}</span>
          <b v-if="progress.failed.length">{{ t('Ошибок: {count}', { count: formatCount(progress.failed.length) }) }}</b>
        </div>
      </div>
    </div>

    <div v-else class="brp-complete">
      <span class="brp-complete-icon"><BIcon name="check" :size="24" /></span>
      <h3>{{ t('Роли обновлены') }}</h3>
      <p>{{ t('Обработано пользователей: {count}', { count: formatCount(progress.done) }) }}</p>
      <div v-if="progress.failed.length" class="brp-failed">
        <div>{{ t('Не удалось обновить: {count}', { count: formatCount(progress.failed.length) }) }}</div>
        <div v-for="reason in failReasons" :key="reason" class="brp-failed-reason">{{ reason }}</div>
      </div>
    </div>

    <template #footer>
      <div class="brp-footer">
        <button v-if="!complete" type="button" class="brp-btn secondary" :disabled="applying" @click="requestClose">{{ t('Отмена') }}</button>
        <button
          v-if="!complete"
          type="button"
          :class="['brp-btn', mode === 'remove' ? 'danger' : 'primary']"
          :disabled="!chosenRole || applying"
          @click="apply"
        >
          {{ applying ? t('Применение...') : t('Применить') }}
        </button>
        <button v-else type="button" class="brp-btn primary" @click="finish">{{ t('Готово') }}</button>
      </div>
    </template>
  </ModalShell>
</template>

<style scoped>
.brp-header h2 { margin: 0; color: var(--t1, #172033); font-size: 15px; font-weight: 650; letter-spacing: 0; }
.brp-header p { margin: 3px 0 0; color: var(--t3, #7b8498); font-size: 10.5px; }
.brp-body { min-height: 440px; }
.brp-label {
  margin-bottom: 7px;
  color: #687287;
  font-size: 10px;
  font-weight: 650;
  text-transform: uppercase;
}
.brp-label.role { margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--border-hard, #e2e5ec); }
.brp-modes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; }
.brp-modes button {
  min-width: 0;
  min-height: 58px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 10px;
  text-align: left;
  color: #687287;
  background: #f8f9fb;
  border: 1px solid var(--border-hard, #e2e5ec);
  border-radius: 7px;
  font: inherit;
  cursor: pointer;
}
.brp-modes button:hover:not(:disabled) { border-color: #b6b1e7; }
.brp-modes button.on { color: #5147ad; background: rgba(98, 87, 200, .065); border-color: #8a82dc; }
.brp-modes button:disabled { opacity: .55; cursor: default; }
.brp-modes span { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.brp-modes b { font-size: 11.5px; font-weight: 650; }
.brp-modes small { overflow: hidden; color: #8a92a3; font-size: 9.5px; text-overflow: ellipsis; white-space: nowrap; }
.brp-loading { padding: 20px; text-align: center; color: #8a92a3; font-size: 11px; }
.brp-error { margin-top: 10px; padding: 8px 10px; color: #a52f34; background: #fff3f3; border: 1px solid #efc8ca; border-radius: 6px; font-size: 10.5px; }
.brp-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  padding: 9px 11px;
  color: #526176;
  background: #f3f7fa;
  border: 1px solid #dbe7ee;
  border-radius: 7px;
  font-size: 10.5px;
}
.brp-summary.warning { color: #8a5b0b; background: #fff8e8; border-color: #edd9a8; }
.brp-progress { margin-top: 14px; }
.brp-progress-track { height: 5px; overflow: hidden; background: #eceef3; border-radius: 3px; }
.brp-progress-track span { display: block; height: 100%; background: #268f77; transition: width .2s; }
.brp-progress > div:last-child { display: flex; justify-content: space-between; margin-top: 6px; color: #7b8498; font-size: 10px; }
.brp-progress b { color: #a52f34; }
.brp-complete {
  min-height: 440px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.brp-complete-icon {
  width: 48px;
  height: 48px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: #268f77;
  border-radius: 50%;
  box-shadow: 0 0 0 7px rgba(38, 143, 119, .1);
}
.brp-complete h3 { margin: 8px 0 0; color: #172033; font-size: 16px; font-weight: 650; letter-spacing: 0; }
.brp-complete p { margin: 0; color: #7b8498; font-size: 11px; }
.brp-failed { margin-top: 6px; padding: 7px 10px; color: #a52f34; background: #fff3f3; border-radius: 6px; font-size: 10.5px; text-align: left; }
.brp-failed-reason { margin-top: 4px; opacity: .85; }
.brp-footer { width: 100%; display: flex; justify-content: flex-end; gap: 8px; }
.brp-btn {
  min-height: 36px;
  padding: 0 15px;
  border-radius: 7px;
  font: inherit;
  font-size: 11.5px;
  font-weight: 650;
  cursor: pointer;
}
.brp-btn.secondary { color: #4e586d; background: #fff; border: 1px solid var(--border-hard, #dfe3ea); }
.brp-btn.primary { color: #fff; background: #6257c8; border: 1px solid #6257c8; }
.brp-btn.danger { color: #fff; background: #b83b42; border: 1px solid #b83b42; }
.brp-btn:disabled { opacity: .48; cursor: default; }

@media (max-width: 620px) {
  .brp-modes { grid-template-columns: 1fr; }
}
</style>
