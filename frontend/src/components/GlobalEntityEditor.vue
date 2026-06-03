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

  <!-- Ошибка загрузки (невалидный id и т.п.) -->
  <div v-else-if="state.open && state.error" class="gee-loading" @click.self="close">
    <div class="gee-error">
      <span>{{ state.error }}</span>
      <button class="gee-error-btn" @click="close">Закрыть</button>
    </div>
  </div>

  <!-- Сам редактор (self-contained .editor-backdrop, position:fixed z-index:1000) -->
  <TaskProjectEditor
    v-if="state.open && state.entity"
    :entity="state.entity"
    :kind="state.kind"
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
.gee-error {
  display: flex;
  flex-direction: column;
  gap: 14px;
  align-items: center;
  background: #fff;
  border-radius: 14px;
  padding: 24px 28px;
  font-size: 13px;
  color: var(--t1, #1e2a4a);
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.2);
  max-width: 360px;
  text-align: center;
}
.gee-error-btn {
  padding: 7px 18px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid rgba(15, 23, 60, 0.12);
  background: var(--bg1, #fff);
  color: var(--t1, #1e2a4a);
  border-radius: 8px;
  cursor: pointer;
}
.gee-error-btn:hover {
  background: rgba(127, 119, 221, 0.06);
  border-color: #7f77dd;
  color: #7f77dd;
}
</style>
