<script setup lang="ts">
import { onMounted, ref } from "vue";
import { moderationApi, type ModeratorUser } from "@/api/moderation";

const items = ref<ModeratorUser[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

async function load() {
  loading.value = true;
  try {
    const r = await moderationApi.moderators();
    items.value = r.items;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  } finally { loading.value = false; }
}
onMounted(load);

function initials(u: ModeratorUser): string {
  if (!u.full_name) return u.email.slice(0, 2).toUpperCase();
  const parts = u.full_name.split(" ").filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return u.full_name.slice(0, 2).toUpperCase();
}
</script>

<template>
  <div class="mm-wrap">
    <div class="mm-hd">
      <i class="ti ti-info-circle" aria-hidden="true"></i>
      <span>Список формируется автоматически из правил модерации: всех, кого указали как primary, co-approver или owner. Чтобы добавить нового — назначьте в правиле.</span>
    </div>

    <div v-if="error" class="mm-err">{{ error }}</div>

    <div v-if="loading" class="mm-empty">Загрузка…</div>
    <div v-else-if="!items.length" class="mm-empty">
      <i class="ti ti-user-check" style="font-size: 24px; color: #888780;" aria-hidden="true"></i>
      <div>Модераторов пока нет</div>
      <div style="font-size: 10px; margin-top: 4px;">Назначьте модераторов в правилах</div>
    </div>

    <div v-else class="mm-grid">
      <div v-for="u in items" :key="u.id" class="mm-card" :class="{ inactive: !u.is_active }">
        <span class="mm-avatar">{{ initials(u) }}</span>
        <div class="mm-body">
          <div class="mm-name">
            {{ u.full_name || u.email }}
            <span v-if="u.is_owner" class="mm-owner-pill">OWNER</span>
          </div>
          <div class="mm-email">{{ u.email }}</div>
          <div v-if="u.job_title || u.department" class="mm-job">
            <span v-if="u.job_title">{{ u.job_title }}</span>
            <span v-if="u.job_title && u.department"> · </span>
            <span v-if="u.department">{{ u.department }}</span>
          </div>
        </div>
        <div class="mm-status">
          <span v-if="!u.is_active" class="mm-inactive">неактивен</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mm-wrap { display: flex; flex-direction: column; gap: 10px; }

.mm-hd {
  background: rgba(55,138,221,.06);
  border-left: 3px solid #378ADD;
  border-radius: 0 7px 7px 0;
  padding: 8px 12px;
  font-size: 11px;
  color: var(--color-text-secondary);
  display: flex; align-items: flex-start; gap: 7px;
  line-height: 1.45;
}
.mm-hd i { font-size: 14px; color: #185FA5; margin-top: 1px; flex-shrink: 0; }

.mm-err { background: rgba(226,75,74,.08); color: #A32D2D; padding: 8px 12px; border-radius: 7px; font-size: 11.5px; }

.mm-empty {
  padding: 60px 20px;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 12px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}

.mm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 8px;
}

.mm-card {
  display: flex; align-items: center; gap: 9px;
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-left: 3px solid #7F77DD;
  border-radius: 8px;
  padding: 10px 12px;
  transition: background .12s, border-color .12s;
}
.mm-card:hover { background: rgba(127,119,221,.03); }
.mm-card.inactive { opacity: .55; border-left-color: #888780; }

.mm-avatar {
  width: 34px; height: 34px;
  border-radius: 50%;
  background: rgba(127,119,221,.15);
  color: #534AB7;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 11.5px; font-weight: 500;
  flex-shrink: 0;
}

.mm-body { flex: 1; min-width: 0; }
.mm-name {
  font-size: 12.5px;
  color: var(--color-text-primary);
  font-weight: 500;
  display: flex; align-items: center; gap: 5px;
}
.mm-owner-pill {
  background: linear-gradient(95deg, #1E2A4A, #4B477E);
  color: #fff;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: .04em;
}
.mm-email { font-size: 10.5px; color: var(--color-text-tertiary); margin-top: 1px; }
.mm-job { font-size: 10px; color: var(--color-text-secondary); margin-top: 2px; }
.mm-status { flex-shrink: 0; }
.mm-inactive {
  background: rgba(0,0,0,.04);
  color: var(--color-text-tertiary);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: .04em;
}
</style>
