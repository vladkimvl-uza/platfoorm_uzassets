<script setup lang="ts">
/**
 * UserCardAnchor — оборачивает аватар/имя пользователя и открывает поповер-карточку
 * (UserCardHost) по наведению (hover-intent) и клику (закрепляет).
 *
 * Usage:
 *   <UserCardAnchor :user-id="u.id" :preview="{ full_name: u.name, initials: u.initials, accent: u.accent }">
 *     <UserAvatar … />
 *   </UserCardAnchor>
 */
import { ref } from "vue";
import { useUserCard } from "@/composables/useUserCard";
import { useUserModal } from "@/composables/useUserModal";
import type { UserCard } from "@/api/directory";

const props = withDefaults(defineProps<{
  userId?: string | null;
  /** Превью для мгновенного показа, пока грузится полная карточка */
  preview?: Partial<UserCard> | null;
  /** Тег-обёртка (span по умолчанию, чтобы не ломать flow) */
  tag?: string;
  /** Открывать по клику (по умолчанию да) */
  clickable?: boolean;
}>(), { tag: "span", clickable: true });

const el = ref<HTMLElement | null>(null);
const { open, scheduleClose, closeNow } = useUserCard();
const userModal = useUserModal();

function onEnter() {
  if (props.userId && el.value) open(props.userId, el.value, props.preview);
}
function onLeave() {
  scheduleClose();
}
function onClick(e: MouseEvent) {
  if (!props.clickable || !props.userId) return;
  e.stopPropagation();
  // Ховер показывает быструю карточку, клик — полноценную модалку профиля.
  closeNow();
  userModal.open(props.userId, props.preview);
}
</script>

<template>
  <component
    :is="tag"
    ref="el"
    class="user-card-anchor"
    :class="{ 'uca-clickable': clickable && userId }"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
    @click="onClick"
  >
    <slot />
  </component>
</template>

<style scoped>
.user-card-anchor { display: inline-flex; align-items: center; }
.uca-clickable { cursor: pointer; }
</style>
