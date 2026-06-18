<script setup lang="ts">
/**
 * UserAffiliationBadge — компактные чипы принадлежности пользователя:
 * компания · сектор · отдел · должность. Переиспользуется везде, где
 * показываем пользователя (списки RBAC, аудит, профиль).
 *
 * Показывает только заполненные поля. size="sm" — мельче для плотных списков.
 */
withDefaults(defineProps<{
  company?: string | null;
  sector?: string | null;
  department?: string | null;
  jobTitle?: string | null;
  size?: "sm" | "md";
}>(), { size: "md" });
</script>

<template>
  <span class="uab" :class="'uab-' + size">
    <span v-if="company" class="uab-chip uab-company" :title="'Компания: ' + company">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-2"/></svg>
      {{ company }}
    </span>
    <span v-if="sector" class="uab-chip uab-sector" :title="'Сектор: ' + sector">{{ sector }}</span>
    <span v-if="department" class="uab-chip uab-dept" :title="'Отдел: ' + department">{{ department }}</span>
    <span v-if="jobTitle" class="uab-chip uab-job" :title="'Должность: ' + jobTitle">{{ jobTitle }}</span>
  </span>
</template>

<style scoped>
.uab { display: inline-flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.uab-chip {
  display: inline-flex; align-items: center; gap: 4px;
  border-radius: 999px; padding: 2px 9px;
  font-size: 11px; font-weight: 500; line-height: 1.4;
  /* длинные названия отделов/направлений переносятся, а не обрезаются «…» */
  white-space: normal; overflow-wrap: anywhere; text-align: left;
}
.uab-sm .uab-chip { font-size: 10px; padding: 1px 7px; gap: 3px; }
.uab-chip svg { width: 11px; height: 11px; flex-shrink: 0; }
.uab-sm .uab-chip svg { width: 9px; height: 9px; }
/* Бренд-палитра, по семантике поля */
.uab-company { background: rgba(124,111,247,.12); color: #534AB7; }
.uab-sector  { background: rgba(8,145,178,.12);  color: #0E7490; }
.uab-dept    { background: rgba(29,158,117,.12);  color: #0F6E56; }
.uab-job     { background: rgba(100,116,139,.12); color: #475569; }
</style>
