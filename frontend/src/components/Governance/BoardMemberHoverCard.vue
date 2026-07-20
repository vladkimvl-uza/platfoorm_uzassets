<script setup lang="ts">
/**
 * BoardMemberHoverCard — быстрая всплывающая карточка члена совета по наведению
 * (аналог UserCardHost для сотрудников, но директора совета — не пользователи
 * платформы, поэтому данные передаются напрямую, без directory-fetch).
 *
 * Позиционируется под якорем (rect в координатах viewport, position: fixed),
 * при нехватке места снизу — переворачивается наверх; по горизонтали clamp.
 * Клик по карточке → полноценная модалка профиля (событие open).
 */
import { computed, ref, watch, nextTick } from "vue";
import type { BoardMemberProfile } from "./BoardMemberProfileModal.vue";

export interface HoverAnchor {
  top: number; left: number; bottom: number; right: number; width: number; height: number;
}

const props = defineProps<{
  open: boolean;
  member: BoardMemberProfile | null;
  anchor: HoverAnchor | null;
}>();

const emit = defineEmits<{
  (e: "enter"): void;
  (e: "leave"): void;
  (e: "open"): void;
}>();

const cardRef = ref<HTMLElement | null>(null);
const pos = ref<{ top: number; left: number; placement: "below" | "above" }>({ top: 0, left: 0, placement: "below" });

const CARD_W = 300;

async function reposition() {
  if (!props.anchor) return;
  await nextTick();
  const h = cardRef.value?.offsetHeight || 180;
  const a = props.anchor;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const gap = 8;
  // По вертикали: под якорем, если не влезает — над.
  let placement: "below" | "above" = "below";
  let top = a.bottom + gap;
  if (top + h > vh - 8 && a.top - gap - h > 8) {
    placement = "above";
    top = a.top - gap - h;
  }
  // По горизонтали: слева по якорю, clamp в вьюпорт.
  let left = a.left;
  if (left + CARD_W > vw - 8) left = vw - 8 - CARD_W;
  if (left < 8) left = 8;
  pos.value = { top, left, placement };
}

watch(() => [props.open, props.anchor], () => { if (props.open) reposition(); }, { deep: true });

const tenure = computed(() => {
  const iso = props.member?.appointedISO;
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (!isFinite(t)) return null;
  const yrs = (Date.now() - t) / (365.25 * 24 * 3600 * 1000);
  if (yrs < 0) return null;
  if (yrs < 1) return `${Math.max(1, Math.round(yrs * 12))} мес.`;
  return `${yrs.toFixed(1)} лет`;
});

const tags = computed(() => {
  const m = props.member;
  if (!m) return [];
  const out: { t: string; on: boolean }[] = [];
  if (m.isIndependent) out.push({ t: "Независимый", on: true });
  if (m.isWoman) out.push({ t: "Женщина", on: false });
  if (m.isForeign) out.push({ t: "Иностранец", on: false });
  return out;
});
</script>

<template>
  <Teleport to="body">
    <Transition name="bmh-fade">
      <div
        v-if="open && member"
        ref="cardRef"
        class="bmh"
        :class="`bmh--${pos.placement}`"
        :style="{ top: pos.top + 'px', left: pos.left + 'px' }"
        @mouseenter="emit('enter')"
        @mouseleave="emit('leave')"
        @click="emit('open')"
      >
        <div class="bmh-top">
          <div class="bmh-av" :style="{ background: member.roleColor }">{{ member.initials }}</div>
          <div class="bmh-id">
            <div class="bmh-name">{{ member.fullName }}</div>
            <span class="bmh-role" :style="{ background: member.roleColor + '22', color: member.roleColor }">{{ member.roleLabel }}</span>
          </div>
        </div>

        <div v-if="member.position" class="bmh-pos">{{ member.position }}</div>

        <div v-if="tags.length" class="bmh-tags">
          <span v-for="tg in tags" :key="tg.t" class="bmh-tag" :class="{ 'bmh-tag--on': tg.on }">{{ tg.t }}</span>
        </div>

        <div class="bmh-meta">
          <div v-if="member.email" class="bmh-meta-row">
            <span class="bmh-meta-l">Email</span>
            <span class="bmh-meta-v bmh-meta-v--trunc">{{ member.email }}</span>
          </div>
          <div v-if="member.phone" class="bmh-meta-row">
            <span class="bmh-meta-l">Телефон</span>
            <span class="bmh-meta-v">{{ member.phone }}</span>
          </div>
          <div class="bmh-meta-row">
            <span class="bmh-meta-l">Назначен</span>
            <span class="bmh-meta-v">{{ member.appointed }}</span>
          </div>
          <div v-if="tenure" class="bmh-meta-row">
            <span class="bmh-meta-l">В совете</span>
            <span class="bmh-meta-v">{{ tenure }}</span>
          </div>
        </div>

        <div class="bmh-cta">Открыть профиль
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.bmh {
  position: fixed; z-index: var(--z-top, 9990); width: 300px;
  background: var(--bg1, #fff); border: 1px solid var(--line, #ECEAF4);
  border-radius: 14px; padding: 14px;
  box-shadow: 0 18px 44px -14px rgba(20, 16, 50, .34), 0 6px 16px -8px rgba(20, 16, 50, .18);
  cursor: pointer;
}
.bmh-top { display: flex; align-items: center; gap: 11px; }
.bmh-av {
  width: 42px; height: 42px; border-radius: 12px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 600; font-size: 14px;
  box-shadow: 0 4px 12px -4px rgba(40, 32, 80, .4);
}
.bmh-id { min-width: 0; }
.bmh-name { font-size: 14px; font-weight: 600; color: var(--t1, #1A1730); line-height: 1.25; }
.bmh-role { display: inline-block; margin-top: 4px; font-size: 10.5px; font-weight: 600; padding: 1px 8px; border-radius: 999px; }
.bmh-pos { font-size: 12px; color: var(--t2, #6B6880); margin-top: 10px; line-height: 1.4; }
.bmh-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 10px; }
.bmh-tag {
  font-size: 10px; font-weight: 500; padding: 2px 8px; border-radius: 999px;
  background: var(--bg2, #F1F0F7); color: var(--t2, #6B6880);
}
.bmh-tag--on { background: rgba(29, 158, 117, .12); color: #158063; }
.bmh-meta {
  margin-top: 12px; padding-top: 11px; border-top: 1px dashed var(--line, #ECEAF4);
  display: flex; flex-direction: column; gap: 6px;
}
.bmh-meta-row { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.bmh-meta-l { font-size: 11px; color: var(--t3, #94A3B8); flex-shrink: 0; }
.bmh-meta-v { font-size: 12px; font-weight: 500; color: var(--t1, #1A1730); font-variant-numeric: tabular-nums; }
.bmh-meta-v--trunc { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bmh-cta {
  display: flex; align-items: center; justify-content: center; gap: 5px;
  margin-top: 13px; padding-top: 11px; border-top: 1px solid var(--line, #ECEAF4);
  font-size: 12px; font-weight: 500; color: var(--p-deep, #534AB7);
}
.bmh-cta svg { width: 13px; height: 13px; }

.bmh-fade-enter-active, .bmh-fade-leave-active { transition: opacity .16s, transform .18s var(--ease-standard, cubic-bezier(.4,0,.2,1)); }
.bmh-fade-enter-from.bmh--below, .bmh-fade-leave-to.bmh--below { opacity: 0; transform: translateY(-6px); }
.bmh-fade-enter-from.bmh--above, .bmh-fade-leave-to.bmh--above { opacity: 0; transform: translateY(6px); }
@media (prefers-reduced-motion: reduce) {
  .bmh-fade-enter-from, .bmh-fade-leave-to { transform: none; }
}
</style>
