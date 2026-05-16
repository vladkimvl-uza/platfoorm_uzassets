<script setup lang="ts">
defineProps<{ targetEmail: string }>();
defineEmits<{ (e: 'exit'): void }>();
</script>

<template>
  <div class="rv3-imp-banner">
    <div class="rv3-imp-l">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="8" cy="5" r="2.5"/><path d="M3 13c0-2.5 2-4 5-4s5 1.5 5 4"/></svg>
      <span>Вы вошли как <strong>{{ targetEmail }}</strong> (режим просмотра, 30 мин)</span>
    </div>
    <button class="rv3-imp-exit" @click="$emit('exit')">
      Вернуться в свой аккаунт
    </button>
  </div>
</template>

<style scoped>
.rv3-imp-banner {
  position: fixed; top: 0; left: 0; right: 0;
  height: 36px; z-index: 9999;
  background: linear-gradient(90deg, #534AB7 0%, #7F77DD 100%);
  color: #fff;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 22px;
  font-size: 12px; font-weight: 500;
  box-shadow: 0 2px 8px rgba(83,74,183,.3);
}
.rv3-imp-l { display: flex; align-items: center; gap: 9px; }
.rv3-imp-l strong { font-weight: 600; }
.rv3-imp-exit {
  padding: 5px 12px;
  background: rgba(255,255,255,.15);
  border: 1px solid rgba(255,255,255,.25);
  color: #fff;
  border-radius: 7px;
  font-size: 11.5px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  transition: background .12s;
}
.rv3-imp-exit:hover { background: rgba(255,255,255,.25); }
</style>