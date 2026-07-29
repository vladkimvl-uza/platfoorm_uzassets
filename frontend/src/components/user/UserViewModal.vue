<script setup lang="ts">
/**
 * UserViewModal — премиум-модалка профиля пользователя (по клику на имя/аватар).
 * Монтируется один раз в AppShell; управляется через useUserModal.
 *
 * Показывает: крупный аватар, имя/роль/владелец, контакты (email/телефон/соцсети),
 * принадлежность (компания/сектор/отдел/должность), активность. Анимации входа.
 */
import { computed } from "vue";
import { useUserModal } from "@/composables/useUserModal";
import UserAffiliationBadge from "@/components/rbac-v3/UserAffiliationBadge.vue";
import SocialLinks from "@/components/user/SocialLinks.vue";
import { formatRelativeTime } from "@/api/audit";
import ModalShell from "@/components/ModalShell.vue";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const { state, close } = useUserModal();

const u = computed(() => ({ ...(state.preview || {}), ...(state.data || {}) } as Record<string, any>));
const hasContacts = computed(() =>
  !!(u.value.email || u.value.phone || u.value.linkedin_url || u.value.website_url || u.value.telegram_username),
);
const lastActive = computed(() => (u.value.last_active ? formatRelativeTime(u.value.last_active) : null));
const isOnline = computed(() =>
  u.value.last_active && Date.now() - new Date(u.value.last_active).getTime() < 5 * 60 * 1000,
);
</script>

<template>
  <ModalShell :open="state.open" size="sm" @close="close">
    <template #header>
      <div class="uvm-head">
        <div class="uvm-avatar" :style="{ background: u.accent || '#7F77DD' }">
          <img v-if="u.avatar_url" :src="u.avatar_url" alt="" />
          <span v-else>{{ u.initials || (u.full_name || '?').slice(0, 1).toUpperCase() }}</span>
          <span v-if="isOnline" class="uvm-online" :title="t('В сети')"></span>
        </div>
        <div class="uvm-id">
          <div class="uvm-name">
            {{ u.full_name || '—' }}
            <span v-if="u.is_owner" class="uvm-owner" :title="t('Владелец')">★</span>
          </div>
          <div v-if="u.role" class="uvm-role">{{ u.role }}</div>
          <span v-if="u.is_active === false" class="uvm-inactive">{{ t('Аккаунт отключён') }}</span>
        </div>
      </div>
    </template>

    <!-- Принадлежность -->
    <div v-if="u.company || u.sector || u.department || u.job_title" class="uvm-sec">
      <div class="uvm-sec-t">{{ t('Принадлежность') }}</div>
      <UserAffiliationBadge :company="u.company" :sector="u.sector" :department="u.department" :job-title="u.job_title" />
    </div>

    <!-- Контакты -->
    <div v-if="hasContacts" class="uvm-sec">
      <div class="uvm-sec-t">{{ t('Контакты') }}</div>
      <div v-if="u.email" class="uvm-contact">
        <span class="uvm-contact-k">Email</span>
        <a :href="'mailto:' + u.email" class="uvm-contact-v">{{ u.email }}</a>
      </div>
      <div v-if="u.phone" class="uvm-contact">
        <span class="uvm-contact-k">{{ t('Телефон') }}</span>
        <a :href="'tel:' + u.phone" class="uvm-contact-v">{{ u.phone }}</a>
      </div>
      <SocialLinks
        v-if="u.linkedin_url || u.website_url || u.telegram_username"
        class="uvm-social"
        :linkedin="u.linkedin_url" :website="u.website_url" :telegram="u.telegram_username"
      />
    </div>

    <!-- Активность -->
    <div class="uvm-foot">
      <span class="uvm-foot-dot" :class="{ on: isOnline }"></span>
      <template v-if="isOnline">{{ t('Сейчас в сети') }}</template>
      <template v-else-if="lastActive">{{ t('Последняя активность:') }} {{ lastActive }}</template>
      <template v-else-if="state.loading">{{ t('загрузка…') }}</template>
      <template v-else>{{ t('нет данных об активности') }}</template>
    </div>
  </ModalShell>
</template>

<style scoped>
.uvm-head { display: flex; align-items: center; gap: 14px; min-width: 0; }
.uvm-avatar {
  position: relative; flex-shrink: 0;
  width: 48px; height: 48px; border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 600; font-size: 20px;
  box-shadow: 0 4px 12px -4px rgba(0, 0, 0, .3);
}
.uvm-avatar img { width: 100%; height: 100%; border-radius: 14px; object-fit: cover; }
.uvm-online {
  position: absolute; right: -2px; bottom: -2px; width: 13px; height: 13px;
  border-radius: 50%; background: #1D9E75; border: 3px solid var(--bg1, #fff);
}
.uvm-id { min-width: 0; }
.uvm-name {
  font-size: 16px; font-weight: 600; color: var(--t1, #1A1730);
  display: flex; align-items: center; gap: 6px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.uvm-owner { color: #EF9F27; font-size: 14px; }
.uvm-role { font-size: 12.5px; color: var(--t2, #6B6880); margin-top: 2px; }
.uvm-inactive { display: inline-block; margin-top: 4px; font-size: 11px; color: #B6BCC8; }

.uvm-sec { margin-bottom: 18px; }
.uvm-sec-t {
  font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em;
  color: var(--t3, #94A3B8); margin-bottom: 9px;
}
.uvm-contact { display: flex; align-items: baseline; gap: 10px; margin-bottom: 7px; }
.uvm-contact-k { font-size: 11px; color: var(--t3, #94A3B8); width: 58px; flex-shrink: 0; }
.uvm-contact-v {
  font-size: 13px; color: var(--p-deep, #534AB7); text-decoration: none;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.uvm-contact-v:hover { text-decoration: underline; }
.uvm-social { margin-top: 13px; }
/* В модалке — полные названия принадлежности (не обрезаем сектор/должность). */
.uvm-sec :deep(.uab) { gap: 6px; }
.uvm-sec :deep(.uab-chip) { max-width: none; white-space: normal; line-height: 1.35; }

.uvm-foot {
  display: flex; align-items: center; gap: 8px;
  padding-top: 14px; border-top: 1px solid var(--line, #EEEDF4);
  font-size: 12px; color: var(--t2, #6B6880);
}
.uvm-foot-dot { width: 8px; height: 8px; border-radius: 50%; background: #C9C6DA; flex-shrink: 0; }
.uvm-foot-dot.on { background: #1D9E75; box-shadow: 0 0 0 3px rgba(29, 158, 117, .18); }
</style>
