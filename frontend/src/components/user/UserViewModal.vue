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

const { state, close } = useUserModal();

const u = computed(() => ({ ...(state.preview || {}), ...(state.data || {}) } as Record<string, any>));
const hasContacts = computed(() =>
  !!(u.value.email || u.value.phone || u.value.linkedin_url || u.value.website_url || u.value.telegram_username),
);
const lastActive = computed(() => (u.value.last_active ? formatRelativeTime(u.value.last_active) : null));
const isOnline = computed(() =>
  u.value.last_active && Date.now() - new Date(u.value.last_active).getTime() < 5 * 60 * 1000,
);

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") close();
}
</script>

<template>
  <Teleport to="body">
    <Transition name="uvm">
      <div v-if="state.open" class="uvm-overlay" @click.self="close" @keydown="onKey" tabindex="-1">
        <div class="uvm" role="dialog" aria-modal="true">
          <button class="uvm-x" @click="close" title="Закрыть">×</button>

          <!-- Шапка-баннер с акцентом -->
          <div class="uvm-banner" :style="{ background: `linear-gradient(135deg, ${u.accent || '#7C6FF7'}, ${u.accent || '#534AB7'}22)` }"></div>

          <div class="uvm-head">
            <div class="uvm-avatar" :style="{ background: u.accent || '#7F77DD' }">
              <img v-if="u.avatar_url" :src="u.avatar_url" alt="" />
              <span v-else>{{ u.initials || (u.full_name || '?').slice(0, 1).toUpperCase() }}</span>
              <span v-if="isOnline" class="uvm-online" title="В сети"></span>
            </div>
            <div class="uvm-id">
              <div class="uvm-name">
                {{ u.full_name || '—' }}
                <span v-if="u.is_owner" class="uvm-owner" title="Владелец">★</span>
              </div>
              <div v-if="u.role" class="uvm-role">{{ u.role }}</div>
              <span v-if="u.is_active === false" class="uvm-inactive">Аккаунт отключён</span>
            </div>
          </div>

          <div class="uvm-body">
            <!-- Принадлежность -->
            <div v-if="u.company || u.sector || u.department || u.job_title" class="uvm-sec">
              <div class="uvm-sec-t">Принадлежность</div>
              <UserAffiliationBadge :company="u.company" :sector="u.sector" :department="u.department" :job-title="u.job_title" />
            </div>

            <!-- Контакты -->
            <div v-if="hasContacts" class="uvm-sec">
              <div class="uvm-sec-t">Контакты</div>
              <div v-if="u.email" class="uvm-contact">
                <span class="uvm-contact-k">Email</span>
                <a :href="'mailto:' + u.email" class="uvm-contact-v">{{ u.email }}</a>
              </div>
              <div v-if="u.phone" class="uvm-contact">
                <span class="uvm-contact-k">Телефон</span>
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
              <template v-if="isOnline">Сейчас в сети</template>
              <template v-else-if="lastActive">Последняя активность: {{ lastActive }}</template>
              <template v-else-if="state.loading">загрузка…</template>
              <template v-else>нет данных об активности</template>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.uvm-overlay {
  position: fixed; inset: 0; z-index: 9400;
  background: rgba(20, 16, 40, .46); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.uvm {
  position: relative; width: 400px; max-width: 100%;
  background: var(--bg1, #fff); border-radius: 20px; overflow: hidden;
  box-shadow: 0 30px 70px -15px rgba(30, 20, 70, .5);
  font-family: Geist, system-ui, sans-serif;
}
.uvm-x {
  position: absolute; top: 12px; right: 12px; z-index: 3;
  width: 28px; height: 28px; border-radius: 9px; border: none;
  background: rgba(255, 255, 255, .25); color: #fff; font-size: 17px; cursor: pointer;
  backdrop-filter: blur(4px); transition: background .14s;
}
.uvm-x:hover { background: rgba(255, 255, 255, .45); }

.uvm-banner { height: 72px; }
.uvm-head { display: flex; align-items: flex-end; gap: 14px; padding: 0 22px; margin-top: -34px; }
.uvm-avatar {
  position: relative; width: 76px; height: 76px; border-radius: 20px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 600; font-size: 28px; overflow: visible;
  border: 4px solid var(--bg1, #fff); box-shadow: 0 6px 18px -6px rgba(0, 0, 0, .35);
}
.uvm-avatar img { width: 100%; height: 100%; border-radius: 16px; object-fit: cover; }
.uvm-online {
  position: absolute; right: 2px; bottom: 2px; width: 15px; height: 15px;
  border-radius: 50%; background: #1D9E75; border: 3px solid var(--bg1, #fff);
}
.uvm-id { flex: 1; min-width: 0; padding-bottom: 6px; }
.uvm-name {
  font-size: 19px; font-weight: 600; color: var(--t1, #1A1730);
  display: flex; align-items: center; gap: 6px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.uvm-owner { color: #EF9F27; font-size: 15px; }
.uvm-role { font-size: 13px; color: var(--t2, #6B6880); margin-top: 2px; }
.uvm-inactive { display: inline-block; margin-top: 4px; font-size: 11px; color: #B6BCC8; }

.uvm-body { padding: 18px 22px 22px; }
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
.uvm :deep(.uab) { gap: 6px; }
.uvm :deep(.uab-chip) { max-width: none; white-space: normal; line-height: 1.35; }

.uvm-foot {
  display: flex; align-items: center; gap: 8px;
  padding-top: 14px; border-top: 1px solid var(--line, #EEEDF4);
  font-size: 12px; color: var(--t2, #6B6880);
}
.uvm-foot-dot { width: 8px; height: 8px; border-radius: 50%; background: #C9C6DA; flex-shrink: 0; }
.uvm-foot-dot.on { background: #1D9E75; box-shadow: 0 0 0 3px rgba(29, 158, 117, .18); }

/* Анимации */
.uvm-enter-active, .uvm-leave-active { transition: opacity .2s ease; }
.uvm-enter-from, .uvm-leave-to { opacity: 0; }
.uvm-enter-active .uvm { animation: uvmPop .32s cubic-bezier(.34, 1.4, .5, 1); }
@keyframes uvmPop {
  0%   { transform: translateY(16px) scale(.94); opacity: 0; }
  100% { transform: none; opacity: 1; }
}
</style>
