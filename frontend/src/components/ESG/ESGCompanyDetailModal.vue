<script setup lang="ts">
/**
 * ESGCompanyDetailModal — модалка ESG-деталей компании в /esg. Содержимое
 * вынесено в ESGCompanyDetailPanel (общее с вкладкой воркспейса → синк).
 */
import ESGCompanyDetailPanel from "@/components/ESG/ESGCompanyDetailPanel.vue";

defineProps<{
  companyId: string;
  initialYear?: number | null;
}>();

defineEmits<{ (e: "close"): void }>();
</script>

<template>
  <div class="ec-backdrop" @click.self="$emit('close')">
    <div class="ec-modal">
      <ESGCompanyDetailPanel
        :company-id="companyId"
        :initial-year="initialYear"
        variant="modal"
        @close="$emit('close')"
      />
    </div>
  </div>
</template>

<style scoped>
.ec-backdrop {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  z-index: var(--z-overlay, 9000);
  display: flex; align-items: center; justify-content: center;
}
.ec-modal {
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  width: min(1100px, 96vw);
  max-height: 92dvh;
  display: flex; flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18);
  animation: modalIn .45s var(--ease-standard);
  overflow: hidden;
}
@keyframes modalIn { from { opacity: 0; transform: scale(.96) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }
</style>
