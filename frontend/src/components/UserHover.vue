<script setup lang="ts">
/**
 * UserHover — оборачивает имя/аватар пользователя и показывает hover-поповер
 * с инфо (ФИО, роль, отдел, должность, email, телефон). Данные тянутся по
 * email (или userId) с кешем. Используется в комментах, ленте изменений и т.п.
 *
 * Usage: <UserHover :email="author_email">{{ author_name }}</UserHover>
 */
import { ref } from "vue";
import { api } from "@/api/client";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const props = defineProps<{ email?: string | null; userId?: string | null }>();

interface Card {
  full_name: string | null; email: string; initials: string;
  department: string | null; job_title: string | null; phone: string | null;
  avatar_url: string | null; is_external: boolean; is_active: boolean; role: string | null;
}

// модульный кеш — одна загрузка на пользователя за сессию
const _cache = (window as any).__uhCache || ((window as any).__uhCache = new Map<string, Card>());

const show = ref(false);
const loading = ref(false);
const card = ref<Card | null>(null);
const pos = ref({ top: 0, left: 0 });
let timer: any = null;

function key(): string | null { return props.userId || props.email || null; }

async function fetchCard() {
  const k = key();
  if (!k) return;
  if (_cache.has(k)) { card.value = _cache.get(k)!; return; }
  loading.value = true;
  try {
    const params: any = {};
    if (props.userId) params.id = props.userId; else params.email = props.email;
    const { data } = await api.get<Card>("/users/card", { params });
    _cache.set(k, data);
    card.value = data;
  } catch { card.value = null; }
  finally { loading.value = false; }
}

function place(el: HTMLElement) {
  const r = el.getBoundingClientRect();
  const W = 290, margin = 10;
  let left = r.left;
  if (left + W > window.innerWidth - margin) left = window.innerWidth - W - margin;
  let top = r.bottom + 7;
  if (top + 160 > window.innerHeight) top = r.top - 160 - 7;
  pos.value = { top: Math.max(margin, top), left: Math.max(margin, left) };
}

function onEnter(e: MouseEvent) {
  if (!key()) return;
  const el = e.currentTarget as HTMLElement;
  clearTimeout(timer);
  timer = setTimeout(() => { place(el); show.value = true; fetchCard(); }, 130);
}
function onLeave() { clearTimeout(timer); timer = setTimeout(() => { show.value = false; }, 120); }
</script>

<template>
  <span ref="anchor" class="uh-anchor" @mouseenter="onEnter" @mouseleave="onLeave"><slot /></span>
  <Teleport to="body">
    <Transition name="uh-fade">
      <div v-if="show" class="uh-pop" :style="{ top: pos.top + 'px', left: pos.left + 'px' }"
           @mouseenter="show = true" @mouseleave="onLeave">
        <div v-if="loading && !card" class="uh-load">{{ t('Загрузка…') }}</div>
        <template v-else-if="card">
          <div class="uh-head">
            <div class="uh-av" :class="{ ext: card.is_external }">
              <img v-if="card.avatar_url" :src="card.avatar_url" alt="" />
              <span v-else>{{ card.initials }}</span>
            </div>
            <div class="uh-id">
              <div class="uh-name">{{ card.full_name || card.email }}</div>
              <div class="uh-role">
                <span v-if="card.role" class="uh-tag">{{ card.role }}</span>
                <span v-if="card.is_external" class="uh-tag ext">{{ t('внешний') }}</span>
                <span v-if="!card.is_active" class="uh-tag off">{{ t('неактивен') }}</span>
              </div>
            </div>
          </div>
          <div class="uh-rows">
            <div v-if="card.job_title" class="uh-row"><span>{{ t('Должность') }}</span><b>{{ card.job_title }}</b></div>
            <div v-if="card.department" class="uh-row"><span>{{ t('Отдел') }}</span><b>{{ card.department }}</b></div>
            <div class="uh-row"><span>Email</span><b class="mono">{{ card.email }}</b></div>
            <div v-if="card.phone" class="uh-row"><span>{{ t('Телефон') }}</span><b class="mono">{{ card.phone }}</b></div>
          </div>
        </template>
        <div v-else class="uh-load">{{ t('Нет данных') }}</div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.uh-anchor { cursor: default; border-bottom: 1px dashed transparent; transition: border-color .15s; }
.uh-anchor:hover { border-bottom-color: rgba(124,111,247,.5); }
.uh-pop {
  position: fixed; z-index: var(--z-top, 9990); width: 290px;
  background: #fff; border: 1px solid #EAEBF2; border-radius: 14px;
  box-shadow: 0 16px 44px rgba(15,23,60,.18), 0 4px 12px rgba(15,23,60,.08);
  padding: 14px; font-size: 12px;
}
.uh-load { padding: 8px; color: #94A3B8; font-size: 12px; text-align: center; }
.uh-head { display: flex; align-items: center; gap: 11px; padding-bottom: 11px; border-bottom: 1px solid #F0F1F6; }
.uh-av { width: 40px; height: 40px; border-radius: 11px; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; display: grid; place-items: center; font-size: 13px; font-weight: 700; flex-shrink: 0; overflow: hidden; }
.uh-av.ext { background: linear-gradient(135deg,#5C3A0A,#854F0B); }
.uh-av img { width: 100%; height: 100%; object-fit: cover; }
.uh-id { min-width: 0; }
.uh-name { font-size: 13.5px; font-weight: 600; color: #1E2A4A; }
.uh-role { display: flex; gap: 5px; margin-top: 4px; flex-wrap: wrap; }
.uh-tag { font-size: 9.5px; font-weight: 600; padding: 2px 7px; border-radius: 6px; background: #F0EEFF; color: #534AB7; text-transform: uppercase; letter-spacing: .03em; }
.uh-tag.ext { background: #FBF0DC; color: #854F0B; } .uh-tag.off { background: #FCE7E7; color: #B23434; }
.uh-rows { margin-top: 11px; display: flex; flex-direction: column; gap: 8px; }
.uh-row { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.uh-row span { font-size: 10.5px; color: #94A3B8; text-transform: uppercase; letter-spacing: .03em; flex-shrink: 0; }
.uh-row b { font-size: 12px; font-weight: 500; color: #1E2A4A; text-align: right; word-break: break-word; }
.uh-row b.mono { font-family: ui-monospace, 'SF Mono', monospace; font-size: 11px; }
.uh-fade-enter-active, .uh-fade-leave-active { transition: opacity .14s ease, transform .14s ease; }
.uh-fade-enter-from, .uh-fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
