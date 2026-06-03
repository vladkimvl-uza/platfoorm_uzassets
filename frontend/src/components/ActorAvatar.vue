<script setup lang="ts">
/**
 * ActorAvatar — аватар автора действия (фото или инициалы) по userId.
 * Тянет /users/card?id с кешем. Используется в уведомлениях (кто внёс
 * изменение), ленте и т.п. Если userId нет — fallback-слот (иконка типа).
 */
import { ref, watch } from "vue";
import { api } from "@/api/client";

const props = defineProps<{ userId?: string | null; size?: number }>();

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
  <span v-if="userId" class="actor-av" :class="{ ext: card?.is_external }"
        :style="{ width: dim() + 'px', height: dim() + 'px', fontSize: Math.round(dim() * 0.38) + 'px' }"
        :title="card?.full_name || ''">
    <img v-if="card?.avatar_url" :src="card.avatar_url" alt="" />
    <span v-else>{{ card?.initials || '•' }}</span>
  </span>
  <slot v-else />
</template>

<style scoped>
.actor-av {
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 50%; flex-shrink: 0; overflow: hidden;
  background: linear-gradient(135deg, #8B7FFF, #6C5CE7);
  color: #fff; font-weight: 700; letter-spacing: -.01em;
  box-shadow: inset 0 1px 1px rgba(255,255,255,.25);
}
.actor-av.ext { background: linear-gradient(135deg, #5C3A0A, #854F0B); }
.actor-av img { width: 100%; height: 100%; object-fit: cover; }
</style>
