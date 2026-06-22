<script setup lang="ts">
/**
 * ActorAvatar — аватар автора действия (фото или инициалы) по userId.
 * Тянет /users/card?id с кешем. Используется в уведомлениях (кто внёс
 * изменение), ленте и т.п. Если userId нет — fallback-слот (иконка типа).
 */
import { ref, watch } from "vue";
import { api } from "@/api/client";

const props = withDefaults(defineProps<{
  userId?: string | null;
  size?: number;
  /** Показывать золотую звезду владельца. Выкл в плотных контекстах (тосты). */
  star?: boolean;
}>(), { star: true });

const _cache = (window as any).__uhCache || ((window as any).__uhCache = new Map<string, any>());
const card = ref<any | null>(null);

async function loadFor(id: string | null | undefined) {
  if (!id) { card.value = null; return; }
  if (_cache.has(id)) { card.value = _cache.get(id); return; }
  try {
    const { data } = await api.get("/users/card", { params: { id } });
    _cache.set(id, data);
    card.value = data;
  } catch { card.value = null; }
}
watch(() => props.userId, (v) => loadFor(v), { immediate: true });

const dim = () => (props.size || 32);
</script>

<template>
  <span v-if="userId" class="actor-av" :class="{ ext: card?.is_external, owner: star && card?.is_owner }"
        :style="{ width: dim() + 'px', height: dim() + 'px', fontSize: Math.round(dim() * 0.38) + 'px' }"
        :title="card?.full_name || ''">
    <img v-if="card?.avatar_url" :src="card.avatar_url" alt="" />
    <span v-else>{{ card?.initials || '•' }}</span>
    <span v-if="star && card?.is_owner" class="actor-av-star" title="Владелец платформы"
          :style="{ width: Math.max(8, Math.round(dim() * 0.36)) + 'px', height: Math.max(8, Math.round(dim() * 0.36)) + 'px' }">
      <svg viewBox="0 0 16 16" fill="currentColor" width="100%" height="100%"><path d="M8 1 L10 5.6 L15 6.2 L11.3 9.6 L12.3 14.5 L8 12 L3.7 14.5 L4.7 9.6 L1 6.2 L6 5.6 Z"/></svg>
    </span>
  </span>
  <slot v-else />
</template>

<style scoped>
.actor-av {
  position: relative;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(135deg, #8B7FFF, #6C5CE7);
  color: #fff; font-weight: 700; letter-spacing: -.01em;
  box-shadow: inset 0 1px 1px rgba(255,255,255,.25);
}
.actor-av.ext { background: linear-gradient(135deg, #5C3A0A, #854F0B); }
.actor-av img { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }
/* минималистичная звезда владельца — тонкий золотой глиф + белый ореол, без кружка */
.actor-av-star {
  position: absolute; top: -2px; right: -2px;
  display: inline-flex; align-items: center; justify-content: center;
  color: #F5A623;
  filter: drop-shadow(0 0 1px #fff) drop-shadow(0 0 1.5px rgba(255,255,255,.9));
}
</style>
