<script setup lang="ts">
/**
 * SocialLinks — премиум-ряд соцссылок профиля с фирменными логотипами.
 * LinkedIn · сайт · Telegram · email · телефон. Показывает только заполненные.
 *
 * Используется в карточке пользователя (UserCardHost) и в модалке профиля.
 */
import { computed } from "vue";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const props = withDefaults(defineProps<{
  linkedin?: string | null;
  website?: string | null;
  telegram?: string | null;   // username без @
  email?: string | null;
  phone?: string | null;
  size?: "sm" | "md";
  /** Показывать подписи рядом с иконкой (для модалки профиля) */
  labels?: boolean;
}>(), { size: "md", labels: false });

const tgHref = computed(() =>
  props.telegram ? `https://t.me/${props.telegram.replace(/^@/, "")}` : null,
);

const hasAny = computed(() =>
  !!(props.linkedin || props.website || props.telegram || props.email || props.phone),
);

function host(url?: string | null): string {
  if (!url) return "";
  try { return new URL(url).host.replace(/^www\./, ""); } catch { return url.replace(/^https?:\/\//, ""); }
}
</script>

<template>
  <div v-if="hasAny" class="social" :class="['social-' + size, { 'social-labels': labels }]">
    <a v-if="linkedin" :href="linkedin" target="_blank" rel="noopener noreferrer"
       class="soc soc-linkedin" title="LinkedIn" @click.stop>
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.06 2.06 0 1 1 0-4.13 2.06 2.06 0 0 1 0 4.13zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.72V1.72C24 .77 23.2 0 22.22 0z"/></svg>
      <span v-if="labels" class="soc-lbl">LinkedIn</span>
    </a>

    <a v-if="website" :href="website" target="_blank" rel="noopener noreferrer"
       class="soc soc-web" :title="t('Сайт')" @click.stop>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
      <span v-if="labels" class="soc-lbl">{{ host(website) }}</span>
    </a>

    <a v-if="tgHref" :href="tgHref" target="_blank" rel="noopener noreferrer"
       class="soc soc-tg" title="Telegram" @click.stop>
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.3-.07-.45-.52-.18L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71l-4.14-3.05-1.99 1.93c-.23.23-.42.42-.86.42z"/></svg>
      <span v-if="labels" class="soc-lbl">@{{ telegram?.replace(/^@/, "") }}</span>
    </a>

    <a v-if="email" :href="'mailto:' + email" class="soc soc-mail" title="Email" @click.stop>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/></svg>
      <span v-if="labels" class="soc-lbl">{{ email }}</span>
    </a>

    <a v-if="phone" :href="'tel:' + phone" class="soc soc-phone" :title="t('Телефон')" @click.stop>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
      <span v-if="labels" class="soc-lbl">{{ phone }}</span>
    </a>
  </div>
</template>

<style scoped>
.social { display: inline-flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.social-labels { flex-direction: column; align-items: stretch; gap: 7px; }

.soc {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  width: 32px; height: 32px; border-radius: 9px;
  color: #fff; text-decoration: none; flex-shrink: 0;
  transition: transform .15s var(--ease-standard), box-shadow .15s, filter .15s;
}
.social-sm .soc { width: 27px; height: 27px; border-radius: 8px; }
.soc svg { width: 15px; height: 15px; }
.social-sm .soc svg { width: 13px; height: 13px; }
.soc:hover { transform: translateY(-1px); filter: brightness(1.06); box-shadow: 0 4px 12px -3px rgba(0,0,0,.3); }

/* Подписи — пилюля с иконкой слева (для модалки профиля) */
.social-labels .soc {
  width: auto; height: auto; justify-content: flex-start;
  padding: 8px 12px; border-radius: 10px; font-size: 12.5px; font-weight: 500;
}
.soc-lbl { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Фирменные цвета */
.soc-linkedin { background: #0A66C2; }
.soc-web      { background: linear-gradient(135deg, #6E61E8, #534AB7); }
.soc-tg       { background: #229ED9; }
.soc-mail     { background: #5B6472; }
.soc-phone    { background: #1D9E75; }
</style>
