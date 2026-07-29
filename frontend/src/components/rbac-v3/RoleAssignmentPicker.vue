<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { RbacV3Role } from '@/api/rbacV3';
import BIcon from '@/components/broadcasts/BIcon.vue';
import RoleChip from './RoleChip.vue';
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();


const props = withDefaults(defineProps<{
  roles: RbacV3Role[];
  modelValue: string[];
  multiple?: boolean;
  disabled?: boolean;
  compact?: boolean;
}>(), {
  multiple: true,
  disabled: false,
  compact: false,
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[]): void;
}>();

const CATEGORY_DEFS = [
  {
    id: 'base',
    label: i18nKey('Основные'),
    codes: ['admin', 'organization', 'viewer', 'readonly', 'audit_viewer', 'ceo'],
  },
  {
    id: 'finance',
    label: i18nKey('Финансы'),
    codes: ['financier', 'finmodel', 'finance_controller', 'monitoring', 'fid', 'debt'],
  },
  {
    id: 'treasury',
    label: i18nKey('Казначейство'),
    codes: ['treasure_user', 'cfo_department', 'cfo_committee'],
  },
  {
    id: 'procurement',
    label: i18nKey('Закупки'),
    codes: ['purchase_department', 'initiator', 'procurement_owner'],
  },
  {
    id: 'organization',
    label: i18nKey('Организация'),
    codes: ['department_worker', 'department_head', 'department_director', 'plan_department'],
  },
  {
    id: 'special',
    label: i18nKey('Специальные'),
    codes: ['lawyer', 'investment', 'mdm_steward'],
  },
] as const;

const query = ref('');
const activeCategory = ref('all');

watch(() => props.modelValue.length, (count) => {
  if (!count && activeCategory.value === 'selected') activeCategory.value = 'all';
});

const categoryByCode = computed(() => {
  const result = new Map<string, string>();
  for (const category of CATEGORY_DEFS) {
    for (const code of category.codes) result.set(code, category.id);
  }
  return result;
});

const categories = computed(() => {
  const roleCounts = new Map<string, number>();
  for (const role of props.roles) {
    const category = categoryByCode.value.get(role.code) || 'other';
    roleCounts.set(category, (roleCounts.get(category) || 0) + 1);
  }

  return [
    { id: 'all', label: i18nKey('Все'), count: props.roles.length },
    ...(props.modelValue.length
      ? [{ id: 'selected', label: i18nKey('Выбрано'), count: props.modelValue.length }]
      : []),
    ...CATEGORY_DEFS
      .filter(category => roleCounts.has(category.id))
      .map(category => ({
        id: category.id,
        label: category.label,
        count: roleCounts.get(category.id) || 0,
      })),
    ...(roleCounts.has('other')
      ? [{ id: 'other', label: i18nKey('Другие'), count: roleCounts.get('other') || 0 }]
      : []),
  ];
});

const filteredRoles = computed(() => {
  const normalizedQuery = query.value.trim().toLocaleLowerCase('ru');
  return props.roles
    .filter((role) => {
      if (activeCategory.value === 'selected' && !props.modelValue.includes(role.code)) return false;
      if (
        activeCategory.value !== 'all' &&
        activeCategory.value !== 'selected' &&
        (categoryByCode.value.get(role.code) || 'other') !== activeCategory.value
      ) return false;
      if (!normalizedQuery) return true;
      return [role.name_ru, role.code, role.description_ru || '']
        .some(value => value.toLocaleLowerCase('ru').includes(normalizedQuery));
    })
    .sort((a, b) => {
      const selectedDelta = Number(props.modelValue.includes(b.code)) - Number(props.modelValue.includes(a.code));
      return selectedDelta || a.sort_order - b.sort_order || a.name_ru.localeCompare(b.name_ru, 'ru');
    });
});

function isSelected(code: string): boolean {
  return props.modelValue.includes(code);
}

function toggleRole(code: string) {
  if (props.disabled) return;
  if (!props.multiple) {
    emit('update:modelValue', isSelected(code) ? [] : [code]);
    return;
  }
  emit(
    'update:modelValue',
    isSelected(code)
      ? props.modelValue.filter(value => value !== code)
      : [...props.modelValue, code],
  );
}

function clearSelection() {
  if (!props.disabled) emit('update:modelValue', []);
}
</script>

<template>
  <div class="rap" :class="{ compact }">
    <div class="rap-toolbar">
      <label class="rap-search">
        <BIcon name="search" :size="14" />
        <input
          v-model="query"
          type="search"
          autocomplete="off"
          :placeholder="t('Найти роль')"
          :disabled="disabled"
        />
        <button
          v-if="query"
          type="button"
          class="rap-icon-btn"
          :aria-label="t('Очистить поиск')"
          :title="t('Очистить поиск')"
          @click="query = ''"
        >
          <BIcon name="x" :size="13" />
        </button>
      </label>
      <div class="rap-selection">
        <span>{{ modelValue.length }} {{ t('выбрано') }}</span>
        <button
          v-if="modelValue.length"
          type="button"
          class="rap-clear"
          :disabled="disabled"
          @click="clearSelection"
        >{{ t('Очистить') }}</button>
      </div>
    </div>

    <div class="rap-categories" role="tablist" :aria-label="t('Категории ролей')">
      <button
        v-for="category in categories"
        :key="category.id"
        type="button"
        role="tab"
        :aria-selected="activeCategory === category.id"
        :class="['rap-category', { on: activeCategory === category.id }]"
        @click="activeCategory = category.id"
      >
        {{ t(category.label) }}
        <span>{{ category.count }}</span>
      </button>
    </div>

    <div class="rap-list" :aria-busy="!roles.length">
      <button
        v-for="role in filteredRoles"
        :key="role.code"
        type="button"
        :disabled="disabled"
        :aria-pressed="isSelected(role.code)"
        :class="['rap-role', { on: isSelected(role.code) }]"
        @click="toggleRole(role.code)"
      >
        <span :class="['rap-control', { radio: !multiple }]">
          <BIcon v-if="isSelected(role.code)" name="check" :size="12" />
        </span>
        <span class="rap-copy">
          <span class="rap-role-head">
            <span class="rap-name">{{ role.name_ru }}</span>
            <RoleChip :code="role.code" size="sm" />
          </span>
          <span v-if="role.description_ru" class="rap-description">{{ role.description_ru }}</span>
          <span v-else class="rap-description muted">{{ t('Описание роли не задано') }}</span>
        </span>
      </button>

      <div v-if="!roles.length" class="rap-empty">{{ t('Загрузка ролей...') }}</div>
      <div v-else-if="!filteredRoles.length" class="rap-empty">{{ t('Роли не найдены') }}</div>
    </div>
  </div>
</template>

<style scoped>
.rap {
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  min-height: 0;
  color: var(--t1, #172033);
}
.rap-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.rap-search {
  height: 34px;
  min-width: 200px;
  max-width: 360px;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  color: #7b8498;
  background: var(--bg2, #f7f8fb);
  border: 1px solid var(--border-hard, #e2e5ec);
  border-radius: 7px;
}
.rap-search:focus-within {
  color: #6257c8;
  border-color: #8a82dc;
  box-shadow: 0 0 0 3px rgba(98, 87, 200, .1);
}
.rap-search input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 12px;
}
.rap-icon-btn {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #7b8498;
  background: transparent;
  border: 0;
  border-radius: 5px;
  cursor: pointer;
}
.rap-icon-btn:hover { background: #eceef4; color: #172033; }
.rap-selection {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  color: var(--t3, #7b8498);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.rap-clear {
  padding: 0;
  color: #6257c8;
  background: transparent;
  border: 0;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.rap-clear:disabled { opacity: .5; cursor: default; }
.rap-categories {
  display: flex;
  gap: 4px;
  padding-bottom: 10px;
  overflow-x: auto;
  scrollbar-width: thin;
}
.rap-category {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  white-space: nowrap;
  color: #657087;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  font: inherit;
  font-size: 10.5px;
  cursor: pointer;
}
.rap-category:hover { background: #f2f3f7; color: #30394c; }
.rap-category.on {
  color: #5147ad;
  background: rgba(98, 87, 200, .09);
  border-color: rgba(98, 87, 200, .22);
}
.rap-category span {
  min-width: 16px;
  padding: 1px 4px;
  text-align: center;
  color: inherit;
  background: rgba(23, 32, 51, .06);
  border-radius: 4px;
  font-size: 9.5px;
  font-variant-numeric: tabular-nums;
}
.rap-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  max-height: 330px;
  padding: 1px;
  overflow-y: auto;
}
.rap-role {
  min-height: 64px;
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 10px;
  text-align: left;
  color: var(--t1, #172033);
  background: #fff;
  border: 1px solid var(--border-hard, #e2e5ec);
  border-radius: 7px;
  font: inherit;
  cursor: pointer;
  transition: border-color .14s, background .14s, box-shadow .14s;
}
.rap-role:hover:not(:disabled) {
  border-color: #b6b1e7;
  box-shadow: 0 2px 8px rgba(32, 38, 61, .06);
}
.rap-role.on {
  background: rgba(98, 87, 200, .055);
  border-color: #8a82dc;
  box-shadow: inset 3px 0 0 #6257c8;
}
.rap-role:disabled { opacity: .55; cursor: default; }
.rap-control {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
  color: #fff;
  background: #fff;
  border: 1px solid #c7ccd6;
  border-radius: 5px;
}
.rap-control.radio { border-radius: 50%; }
.rap-role.on .rap-control { background: #6257c8; border-color: #6257c8; }
.rap-copy { min-width: 0; display: flex; flex: 1; flex-direction: column; gap: 4px; }
.rap-role-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rap-name { min-width: 0; font-size: 12px; font-weight: 650; line-height: 1.25; }
.rap-description {
  display: -webkit-box;
  overflow: hidden;
  color: var(--t3, #7b8498);
  font-size: 10.5px;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.rap-description.muted { color: #adb3c0; }
.rap-empty {
  grid-column: 1 / -1;
  padding: 28px 12px;
  text-align: center;
  color: var(--t3, #7b8498);
  font-size: 12px;
}
.rap.compact .rap-list { max-height: 260px; }
.rap.compact .rap-role { min-height: 54px; padding: 8px 9px; }
.rap.compact .rap-description { -webkit-line-clamp: 1; }

@container (max-width: 560px) {
  .rap-list { grid-template-columns: 1fr; }
}

@media (max-width: 720px) {
  .rap-toolbar { align-items: stretch; flex-direction: column; gap: 7px; }
  .rap-search { width: 100%; max-width: none; }
  .rap-selection { justify-content: flex-end; }
  .rap-list { grid-template-columns: 1fr; max-height: none; }
}
</style>
