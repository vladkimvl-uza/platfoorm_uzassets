<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from '@/composables/useI18n';
import type { PresenceStatus } from '@/composables/usePresence';
import { presenceLabel } from '@/composables/usePresence';

const { t } = useI18n();

const props = defineProps<{
  email?: string;
  fullName?: string;
  avatarUrl?: string | null;  // фото профиля (data-URL) — если есть, рисуем вместо инициалов
  size?: number;
  status?: PresenceStatus;   // online / away / offline — рисует точку-индикатор
}>();
const initials = computed(() => {
  const name = props.fullName?.trim();
  if (name) {
    const parts = name.split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return name.slice(0, 2).toUpperCase();
  }
  const email = props.email || '';
  const local = email.split('@')[0] || '';
  const parts = local.split(/[._-]/);
  if (parts.length >= 2 && parts[0] && parts[1]) return (parts[0][0] + parts[1][0]).toUpperCase();
  return local.slice(0, 2).toUpperCase() || '?';
});
const sz = computed(() => props.size || 30);
const fs = computed(() => Math.round(sz.value * 0.4));
// Диаметр точки ~32% аватара, ограничен 8–14px; бордер белый «вырез».
const dot = computed(() => Math.max(8, Math.min(14, Math.round(sz.value * 0.32))));
const dotTitle = computed(() => (props.status ? t(presenceLabel(props.status)) : ''));
</script>

<template>
  <div class="rv3-avatar-wrap" :style="{ width: sz + 'px', height: sz + 'px' }">
    <img
      v-if="avatarUrl"
      class="rv3-avatar rv3-avatar-img"
      :src="avatarUrl"
      :style="{ width: sz + 'px', height: sz + 'px' }"
      :alt="fullName || email || ''"
    />
    <div v-else class="rv3-avatar" :style="{ width: sz + 'px', height: sz + 'px', fontSize: fs + 'px' }">
      {{ initials }}
    </div>
    <span
      v-if="status"
      class="rv3-presence"
      :class="'rv3-presence-' + status"
      :style="{ width: dot + 'px', height: dot + 'px' }"
      :title="dotTitle"
    ></span>
  </div>
</template>

<style scoped>
.rv3-avatar-wrap {
  position: relative;
  flex-shrink: 0;
  display: inline-flex;
}
.rv3-avatar {
  background: linear-gradient(135deg, #7F77DD, var(--p-deep));
  border-radius: 8px;
  color: #fff;
  font-weight: 500;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  user-select: none;
}
.rv3-avatar-img {
  object-fit: cover;
  display: block;
}
/* Presence-точка: правый-нижний угол, белый «вырез» отделяет её от аватара. */
.rv3-presence {
  position: absolute;
  right: -2px;
  bottom: -2px;
  border-radius: 50%;
  box-shadow: 0 0 0 2px var(--bg1, #fff);
}
.rv3-presence-online {
  background: #1D9E75;
}
/* Лёгкая «дышащая» пульсация только у онлайна */
.rv3-presence-online::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: #1D9E75;
  animation: rv3-presence-pulse 2s ease-out infinite;
}
.rv3-presence-away {
  background: #EF9F27;
}
.rv3-presence-offline {
  background: #B6BCC8;
}
@keyframes rv3-presence-pulse {
  0%   { transform: scale(1);   opacity: 0.55; }
  70%  { transform: scale(2.4); opacity: 0;    }
  100% { transform: scale(2.4); opacity: 0;    }
}
@media (prefers-reduced-motion: reduce) {
  .rv3-presence-online::after { animation: none; }
}
</style>
