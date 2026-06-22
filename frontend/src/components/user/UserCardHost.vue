<script setup lang="ts">
/**
 * UserCardHost — единый плавающий поповер-карточка пользователя.
 *
 * Монтируется ОДИН раз в AppShell. Любой <UserCardAnchor> открывает его через
 * composable useUserCard. Показывает: аватар (accent), имя, роль/владелец,
 * бейджи принадлежности (компания/сектор/отдел/должность), последнюю активность.
 *
 * Поведение: hover-intent открытие/закрытие; клик «закрепляет» карточку
 * (закрывается по клику вне или Esc). Позиция якорится к элементу-источнику,
 * с переворотом вверх и зажимом в вьюпорт.
 */
import { computed, onBeforeUnmount, onMounted } from "vue";
import { useUserCard } from "@/composables/useUserCard";
import UserAffiliationBadge from "@/components/rbac-v3/UserAffiliationBadge.vue";
import SocialLinks from "@/components/user/SocialLinks.vue";
import { formatRelativeTime } from "@/api/audit";

const { state, setOverCard, closeNow } = useUserCard();

const CARD_W = 288;

const merged = computed(() => ({ ...(state.preview || {}), ...(state.data || {}) } as Record<string, any>));

const pos = computed(() => {
  const a = state.anchor;
  if (!a) return { display: "none" } as Record<string, string>;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const margin = 10;

  let left = a.left;
  if (left + CARD_W + margin > vw) left = vw - CARD_W - margin;
  if (left < margin) left = margin;

  const spaceBelow = vh - a.bottom;
  const flipUp = spaceBelow < 240 && a.top > spaceBelow;
  const style: Record<string, string> = { left: `${Math.round(left)}px`, width: `${CARD_W}px` };
  if (flipUp) style.bottom = `${Math.round(vh - a.top + 8)}px`;
  else style.top = `${Math.round(a.bottom + 8)}px`;
  return style;
});

const lastActiveLabel = computed(() => {
  const la = merged.value.last_active;
  return la ? formatRelativeTime(la) : null;
});

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape" && state.visible) closeNow();
}
function onDocClick() {
  if (state.visible && state.pinned) closeNow();
}
onMounted(() => {
  window.addEventListener("keydown", onKey);
  window.addEventListener("click", onDocClick, true);
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  window.removeEventListener("click", onDocClick, true);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="ucard">
      <div
        v-if="state.visible"
        class="ucard"
        :style="pos"
        @mouseenter="setOverCard(true)"
        @mouseleave="setOverCard(false)"
        @click.stop
      >
        <div class="ucard-head">
          <div class="ucard-avatar" :class="{ 'ucard-avatar-photo': merged.avatar_url }" :style="{ background: merged.avatar_url ? 'transparent' : (merged.accent || '#7F77DD') }">
            <img v-if="merged.avatar_url" :src="merged.avatar_url" alt="" />
            <template v-else>{{ merged.initials || (merged.full_name || '?').slice(0, 1).toUpperCase() }}</template>
          </div>
          <div class="ucard-id">
            <div class="ucard-name" :title="merged.full_name">
              {{ merged.full_name || '—' }}
              <span v-if="merged.is_owner" class="ucard-owner" title="Владелец">★</span>
            </div>
            <div v-if="merged.role" class="ucard-role">{{ merged.role }}</div>
            <a v-if="merged.email" class="ucard-email" :href="'mailto:' + merged.email" @click.stop>{{ merged.email }}</a>
          </div>
        </div>

        <div v-if="merged.company || merged.sector || merged.department || merged.job_title" class="ucard-badges">
          <UserAffiliationBadge
            :company="merged.company"
            :sector="merged.sector"
            :department="merged.department"
            :job-title="merged.job_title"
            size="sm"
          />
        </div>

        <div v-if="merged.linkedin_url || merged.website_url || merged.telegram_username || merged.phone" class="ucard-social">
          <SocialLinks
            :linkedin="merged.linkedin_url"
            :website="merged.website_url"
            :telegram="merged.telegram_username"
            :phone="merged.phone"
            size="sm"
          />
        </div>

        <div class="ucard-foot">
          <span v-if="merged.is_active === false" class="ucard-inactive">● Отключён</span>
          <span v-else-if="lastActiveLabel" class="ucard-active">Активность: {{ lastActiveLabel }}</span>
          <span v-else-if="state.loading" class="ucard-active ucard-skeleton">загрузка…</span>
          <span v-else class="ucard-active ucard-muted">нет активности</span>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ucard {
  position: fixed;
  z-index: 9000;
  background: var(--bg1, #fff);
  border: 1px solid var(--line, #E8E6F0);
  border-radius: 14px;
  box-shadow: 0 12px 40px -8px rgba(40, 32, 80, .22), 0 2px 8px rgba(40, 32, 80, .08);
  padding: 14px;
  font-family: Geist, system-ui, sans-serif;
}
.ucard-head { display: flex; gap: 11px; align-items: flex-start; }
.ucard-avatar {
  width: 42px; height: 42px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 600; font-size: 16px; flex-shrink: 0;
  box-shadow: 0 2px 8px -2px rgba(0, 0, 0, .25);
}
.ucard-avatar-photo { overflow: hidden; }
.ucard-avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ucard-id { min-width: 0; flex: 1; }
.ucard-name {
  font-size: 14px; font-weight: 600; color: var(--t1, #1A1730);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  display: flex; align-items: center; gap: 5px;
}
.ucard-owner { color: #EF9F27; font-size: 12px; }
.ucard-role { font-size: 11.5px; color: var(--t2, #6B6880); margin-top: 1px; }
.ucard-email {
  font-size: 11px; color: var(--p-deep, #534AB7); text-decoration: none;
  display: block; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ucard-email:hover { text-decoration: underline; }
.ucard-badges { margin-top: 11px; }
.ucard-badges :deep(.uab-chip) { max-width: none; white-space: normal; line-height: 1.3; }
.ucard-social { margin-top: 11px; }
.ucard-foot {
  margin-top: 11px; padding-top: 10px; border-top: 1px solid var(--line, #EEEDF4);
  font-size: 11px; color: var(--t3, #8B889C);
}
.ucard-active { color: var(--t2, #6B6880); }
.ucard-muted { color: var(--t3, #A6A3B8); }
.ucard-skeleton { opacity: .6; }
.ucard-inactive { color: #B6BCC8; }

.ucard-enter-active, .ucard-leave-active { transition: opacity .16s ease, transform .16s ease; }
.ucard-enter-from, .ucard-leave-to { opacity: 0; transform: translateY(-4px) scale(.98); }
</style>
