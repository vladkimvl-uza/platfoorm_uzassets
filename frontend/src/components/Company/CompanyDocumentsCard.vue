<template>
  <div class="cdc-card">
    <AttachmentsPanel
      kind="company"
      :parent-id="companyId"
      title="ДОКУМЕНТЫ КОМПАНИИ"
      hint="Общая папка — учредительные, отчёты, презентации"
      filter="all"
      empty-text="Документов нет"
      :current-user-id="currentUserId"
      :is-admin="isAdmin"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useAuthStore } from "@/stores/auth";
import AttachmentsPanel from "@/components/Attachments/AttachmentsPanel.vue";

defineProps<{ companyId: string }>();

const auth = useAuthStore();
const currentUserId = computed(() => auth.user?.id || "");
const isAdmin = computed(() => {
  const u: any = auth.user;
  if (u?.is_owner || u?.is_admin) return true;
  const roles = u?.roles || [];
  const admin = new Set(["admin", "ROLE_ADMIN", "ROLE_OWNER", "owner"]);
  return Array.isArray(roles) && roles.some((r: string) => admin.has(r));
});
</script>

<style scoped>
.cdc-card {
  background: white;
  border: 0.5px solid #E5E7EB;
  border-radius: 11px;
  padding: 14px 16px;
}
</style>
