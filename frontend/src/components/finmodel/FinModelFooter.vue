<script setup lang="ts">
defineProps<{
  saving: boolean;
  lockStatus: string | null;
}>();
</script>

<template>
  <footer class="fm-footer">
    <span v-if="lockStatus">Статус: <span class="fm-lock-status" :class="`fm-lock-${lockStatus}`">{{ lockStatus }}</span></span>
    <span v-else>Статус: <span class="fm-empty-val">—</span></span>
    <span class="fm-sep">·</span>
    <span class="fm-footer-right">
      <template v-if="saving">
        <span class="fm-pulse-dot fm-pulse-dot-saving"></span>
        Сохраняем…
      </template>
      <template v-else>
        <span class="fm-pulse-dot fm-pulse-dot-idle"></span>
        Автосохранение на blur
      </template>
    </span>
  </footer>
</template>

<style scoped>
.fm-footer {
  padding: 10px 18px;
  border-top: 0.5px solid #F1EFE8;
  background: var(--bg2, #FAFAFC);
  display: flex;
  gap: 14px;
  align-items: center;
  font-size: 10.5px;
  color: var(--t3, var(--t-muted));
}
.fm-sep { color: #C8C7C0; }
.fm-empty-val { color: #C8C7C0; }
.fm-footer-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
}
.fm-pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.fm-pulse-dot-saving {
  background: var(--amber);
  animation: fmPulse 1s infinite;
}
.fm-pulse-dot-idle {
  background: var(--green);
  animation: fmPulse 2s infinite;
}
.fm-lock-status { color: var(--t1, #1E2A4A); }
.fm-lock-draft    { color: var(--p-deep); }
.fm-lock-review   { color: #D97706; }
.fm-lock-approved { color: #0F6E56; }
.fm-lock-locked   { color: #C0322F; }
@keyframes fmPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: .5; transform: scale(1.3); }
}
</style>
