<script setup lang="ts">
/**
 * GlobalEntityEditor — глобальный хост модалки задачи/проекта.
 *
 * Монтируется один раз в AppShell. Открывается из useEntityEditor() (клик по
 * уведомлению о задаче/проекте, drill-модали) и рендерит self-contained
 * TaskProjectEditor (fixed-overlay) ПОВЕРХ текущей страницы — без навигации
 * на /tasks. См. composables/useEntityEditor.ts.
 */
import { useEntityEditor } from "@/composables/useEntityEditor";
import TaskProjectEditor from "@/components/TaskProjectEditor.vue";
import ModalShell from "@/components/ModalShell.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const { state, close } = useEntityEditor();

function onSaved() {
  close();
}
</script>

<template>
  <!-- Загрузка: лёгкий полупрозрачный оверлей пока тянем entity по id -->
  <div v-if="state.open && state.loading" class="gee-loading">
    <div class="gee-spinner" />
  </div>

  <!-- Ошибка загрузки (невалидный id и т.п.) — канон ModalShell + UzaStateBlock -->
  <ModalShell v-else-if="state.open && !!state.error" :open="true" size="sm" :title="t('Ошибка')" @close="close">
    <UzaStateBlock state="error" variant="block" :text="state.error || ''" />
  </ModalShell>

  <!-- Сам редактор (self-contained .editor-backdrop, position:fixed z-index:1000) -->
  <!-- Просмотр/редактирование существующей сущности -->
  <TaskProjectEditor
    v-if="state.open && state.mode === 'view' && state.entity"
    :entity="state.entity"
    :kind="state.kind"
    @close="close"
    @saved="onSaved"
  />

  <!-- Создание новой задачи/проекта (из календаря: дедлайн + компания предзаполнены) -->
  <TaskProjectEditor
    v-else-if="state.open && state.mode === 'create'"
    :entity="null"
    :kind="state.kind"
    :company-id="state.createCompanyId"
    :initial-due="state.createDue"
    @close="close"
    @saved="onSaved"
  />
</template>

<style scoped>
.gee-loading {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(15, 18, 40, 0.45);
  -webkit-backdrop-filter: blur(6px);
          backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
}
.gee-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(127, 119, 221, 0.25);
  border-top-color: #7f77dd;
  border-radius: 50%;
  animation: gee-spin 0.7s linear infinite;
}
@keyframes gee-spin {
  to { transform: rotate(360deg); }
}
</style>
