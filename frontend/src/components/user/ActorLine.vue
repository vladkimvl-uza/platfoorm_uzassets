<script setup lang="ts">
/**
 * ActorLine — имя пользователя + компактные бейджи принадлежности (компания/сектор),
 * с поповер-карточкой по ховеру/клику. Делит кэш с ActorAvatar (window.__uhCache),
 * чтобы не дублировать запрос /users/card.
 *
 * Usage: <ActorLine :user-id="n.source_user_id" show-badges />
 */
import { ref, watch } from "vue";
import { directoryApi, type UserCard } from "@/api/directory";
import UserAffiliationBadge from "@/components/rbac-v3/UserAffiliationBadge.vue";
import UserCardAnchor from "@/components/user/UserCardAnchor.vue";

const props = withDefaults(defineProps<{
  userId?: string | null;
  showBadges?: boolean;
  /** Запасное имя, если карточка ещё не загружена / нет userId */
  fallbackName?: string | null;
}>(), { showBadges: true });

const _cache = (window as any).__uhCache || ((window as any).__uhCache = new Map<string, any>());
const card = ref<UserCard | null>(null);

async function load(id?: string | null) {
  if (!id) { card.value = null; return; }
  if (_cache.has(id)) { card.value = _cache.get(id); return; }
  try {
    const d = await directoryApi.userCard(id);
    _cache.set(id, d);
    card.value = d;
  } catch {
    card.value = null;
  }
}
watch(() => props.userId, (v) => load(v), { immediate: true });
</script>

<template>
  <span v-if="userId || fallbackName" class="actor-line">
    <UserCardAnchor :user-id="userId" :preview="card || undefined">
      <span class="actor-line__name">{{ card?.full_name || fallbackName || card?.email || "—" }}</span>
    </UserCardAnchor>
    <UserAffiliationBadge
      v-if="showBadges && card && (card.company || card.sector)"
      :company="card.company"
      :sector="card.sector"
      size="sm"
    />
  </span>
</template>

<style scoped>
.actor-line { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; min-width: 0; }
.actor-line__name {
  font-size: 11.5px; font-weight: 600; color: var(--t1, #1E2A4A);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 160px;
}
.actor-line__name:hover { color: var(--p-deep, #534AB7); }
</style>
