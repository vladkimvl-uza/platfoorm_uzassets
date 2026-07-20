<script setup lang="ts">
/**
 * BoardMemberProfileModal — всплывающий премиум-профиль члена совета директоров.
 *
 * Директора совета — НЕ пользователи платформы (это статические записи
 * governance_data), поэтому общий useUserModal тут неприменим. Модалка показывает
 * роль (аватар-градиент), состав-факты (независимость/пол/гражданство) и —
 * ключевое — расчёт СРОКА полномочий: назначен → окончание, лет в совете,
 * сколько осталось, прогресс-бар. Даты приходят ISO; всё считается тут.
 */
import { computed } from "vue";
import ModalShell from "@/components/ModalShell.vue";

export interface BoardMemberProfile {
  id: string;
  fullName: string;
  position: string;
  roleLabel: string;
  roleColor: string;
  initials: string;
  isIndependent: boolean;
  isWoman: boolean;
  isForeign: boolean;
  appointed: string;       // отформатированная строка «дд.мм.гггг» или «—»
  termEnd: string;
  appointedISO: string | null;
  termEndISO: string | null;
  email?: string | null;
  phone?: string | null;
}

const props = defineProps<{
  open: boolean;
  member: BoardMemberProfile | null;
  companyName?: string;
}>();

defineEmits<{ (e: "close"): void }>();

const MS_YEAR = 365.25 * 24 * 3600 * 1000;

function parse(d: string | null): number | null {
  if (!d) return null;
  const t = new Date(d).getTime();
  return isFinite(t) ? t : null;
}

/** Лет в совете с момента назначения (по сегодняшний день). */
const tenure = computed(() => {
  const a = parse(props.member?.appointedISO ?? null);
  if (a == null) return null;
  const yrs = (Date.now() - a) / MS_YEAR;
  return yrs >= 0 ? yrs : null;
});

/** Прогресс срока: 0..1 между назначением и окончанием (clamp). */
const termProgress = computed(() => {
  const a = parse(props.member?.appointedISO ?? null);
  const e = parse(props.member?.termEndISO ?? null);
  if (a == null || e == null || e <= a) return null;
  const p = (Date.now() - a) / (e - a);
  return Math.max(0, Math.min(1, p));
});

/** Осталось до окончания срока (в годах); < 0 → срок истёк. */
const remaining = computed(() => {
  const e = parse(props.member?.termEndISO ?? null);
  if (e == null) return null;
  return (e - Date.now()) / MS_YEAR;
});

function humanYears(yrs: number | null): string {
  if (yrs == null) return "—";
  const abs = Math.abs(yrs);
  if (abs < 1 / 12) return "меньше месяца";
  if (abs < 1) {
    const m = Math.max(1, Math.round(abs * 12));
    return `${m} мес.`;
  }
  const whole = Math.floor(abs);
  const months = Math.round((abs - whole) * 12);
  const yStr = `${whole} ${plural(whole, "год", "года", "лет")}`;
  return months > 0 ? `${yStr} ${months} мес.` : yStr;
}

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

const remainingLabel = computed(() => {
  const r = remaining.value;
  if (r == null) return null;
  if (r < 0) return { text: `Срок истёк ${humanYears(r)} назад`, expired: true };
  return { text: `Осталось ${humanYears(r)}`, expired: false };
});

const facts = computed(() => {
  const m = props.member;
  if (!m) return [];
  return [
    { label: "Независимость", on: m.isIndependent, onText: "Независимый директор", offText: "Аффилированный" },
    { label: "Пол", on: m.isWoman, onText: "Женщина", offText: "Мужчина", neutral: true },
    { label: "Гражданство", on: m.isForeign, onText: "Иностранный", offText: "Резидент РУз", neutral: true },
  ];
});

const hasContact = computed(() => !!(props.member?.email || props.member?.phone));
</script>

<template>
  <ModalShell :open="open" size="md" @close="$emit('close')">
    <template #header>
      <div v-if="member" class="bmp-hd">
        <div class="bmp-av" :style="{ background: member.roleColor }">
          <span>{{ member.initials }}</span>
        </div>
        <div class="bmp-hd-info">
          <div class="bmp-name">{{ member.fullName }}</div>
          <div class="bmp-role">
            <span class="bmp-role-pill" :style="{ background: member.roleColor + '22', color: member.roleColor }">
              {{ member.roleLabel }}
            </span>
            <span v-if="member.isIndependent" class="bmp-tag">Независимый</span>
          </div>
        </div>
      </div>
    </template>

    <div v-if="member" class="bmp-body">
      <!-- Должность -->
      <div v-if="member.position" class="bmp-pos" style="--d:0">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
        <div>
          <div class="bmp-pos-l">Должность</div>
          <div class="bmp-pos-v">{{ member.position }}</div>
        </div>
      </div>

      <!-- Контакты -->
      <div v-if="hasContact" class="bmp-contact" style="--d:1">
        <a v-if="member.email" class="bmp-contact-row" :href="`mailto:${member.email}`">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>
          <div>
            <div class="bmp-contact-l">Email</div>
            <div class="bmp-contact-v">{{ member.email }}</div>
          </div>
        </a>
        <a v-if="member.phone" class="bmp-contact-row" :href="`tel:${member.phone}`">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3.1-8.6A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.4-1.2a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/></svg>
          <div>
            <div class="bmp-contact-l">Телефон</div>
            <div class="bmp-contact-v">{{ member.phone }}</div>
          </div>
        </a>
      </div>

      <!-- Состав-факты -->
      <div class="bmp-facts">
        <div
          v-for="(f, i) in facts"
          :key="f.label"
          class="bmp-fact"
          :class="{ 'bmp-fact--on': f.on && !f.neutral }"
          :style="{ '--d': (i + 1) }"
        >
          <div class="bmp-fact-l">{{ f.label }}</div>
          <div class="bmp-fact-v">{{ f.on ? f.onText : f.offText }}</div>
        </div>
      </div>

      <!-- Срок полномочий -->
      <div class="bmp-term" style="--d:4">
        <div class="bmp-term-hd">
          <span class="bmp-term-title">Срок полномочий</span>
          <span v-if="tenure != null" class="bmp-term-tenure">в совете {{ humanYears(tenure) }}</span>
        </div>

        <div class="bmp-term-dates">
          <div class="bmp-term-date">
            <div class="bmp-term-date-l">Назначен</div>
            <div class="bmp-term-date-v">{{ member.appointed }}</div>
          </div>
          <div class="bmp-term-arrow">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </div>
          <div class="bmp-term-date bmp-term-date--r">
            <div class="bmp-term-date-l">Окончание</div>
            <div class="bmp-term-date-v">{{ member.termEnd }}</div>
          </div>
        </div>

        <div v-if="termProgress != null" class="bmp-progress">
          <div class="bmp-progress-track">
            <div
              class="bmp-progress-fill"
              :class="{ 'bmp-progress-fill--expired': remainingLabel?.expired }"
              :style="{ width: (termProgress * 100).toFixed(1) + '%', background: remainingLabel?.expired ? '#E24B4A' : member.roleColor }"
            ></div>
          </div>
          <div v-if="remainingLabel" class="bmp-progress-cap" :class="{ 'bmp-progress-cap--expired': remainingLabel.expired }">
            {{ remainingLabel.text }}
          </div>
        </div>
        <div v-else class="bmp-term-nodata">Даты срока не заданы</div>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
.bmp-hd { display: flex; align-items: center; gap: 14px; min-width: 0; }
.bmp-av {
  width: 52px; height: 52px; border-radius: 15px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 600; font-size: 18px;
  box-shadow: 0 6px 18px -6px rgba(40, 32, 80, .45);
}
.bmp-hd-info { min-width: 0; }
.bmp-name {
  font-size: 17px; font-weight: 600; color: var(--t1, #1A1730);
  letter-spacing: -.01em; line-height: 1.2;
}
.bmp-role { display: flex; align-items: center; gap: 7px; margin-top: 6px; flex-wrap: wrap; }
.bmp-role-pill {
  font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 999px;
}
.bmp-tag {
  font-size: 10.5px; font-weight: 500; color: var(--t2, #6B6880);
  background: var(--bg2, #F1F0F7); padding: 2px 8px; border-radius: 999px;
}

.bmp-body { display: flex; flex-direction: column; gap: 16px; }
.bmp-body > * { animation: bmpIn .42s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both; animation-delay: calc(var(--d, 0) * 55ms); }
@keyframes bmpIn { from { opacity: 0; transform: translateY(9px); } to { opacity: 1; transform: none; } }

.bmp-pos {
  display: flex; align-items: center; gap: 12px;
  padding: 13px 15px; border-radius: 13px;
  background: var(--bg2, #F8FAFC); border: 1px solid var(--line, #ECEAF4);
}
.bmp-pos svg { width: 22px; height: 22px; color: var(--p, #7C6FF7); flex-shrink: 0; }
.bmp-pos-l { font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.bmp-pos-v { font-size: 14px; font-weight: 500; color: var(--t1, #1A1730); margin-top: 2px; }

.bmp-contact { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
.bmp-contact-row {
  display: flex; align-items: center; gap: 11px; text-decoration: none;
  padding: 11px 13px; border-radius: 12px;
  background: var(--bg2, #F8FAFC); border: 1px solid var(--line, #ECEAF4);
  transition: border-color .16s, box-shadow .16s, transform .16s;
}
.bmp-contact-row:hover {
  border-color: rgba(124, 111, 247, .4);
  box-shadow: 0 6px 16px -10px rgba(40, 32, 80, .28);
  transform: translateY(-1px);
}
.bmp-contact-row svg { width: 19px; height: 19px; color: var(--p, #7C6FF7); flex-shrink: 0; }
.bmp-contact-l { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.bmp-contact-v { font-size: 13px; font-weight: 500; color: var(--t1, #1A1730); margin-top: 2px; word-break: break-all; }

.bmp-facts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.bmp-fact {
  padding: 12px 13px; border-radius: 12px; text-align: center;
  background: var(--bg2, #F8FAFC); border: 1px solid var(--line, #ECEAF4);
  transition: border-color .16s, box-shadow .16s;
}
.bmp-fact--on {
  background: rgba(29, 158, 117, .08);
  border-color: rgba(29, 158, 117, .35);
}
.bmp-fact-l { font-size: 10.5px; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94A3B8); }
.bmp-fact-v { font-size: 13px; font-weight: 500; color: var(--t1, #1A1730); margin-top: 5px; line-height: 1.3; }
.bmp-fact--on .bmp-fact-v { color: #158063; }

.bmp-term {
  padding: 16px; border-radius: 14px;
  background: linear-gradient(180deg, var(--bg1, #fff), var(--bg2, #FAFBFF));
  border: 1px solid var(--line, #ECEAF4);
}
.bmp-term-hd { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.bmp-term-title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t2, #6B6880); }
.bmp-term-tenure { font-size: 12px; font-weight: 500; color: var(--p-deep, #534AB7); }

.bmp-term-dates { display: flex; align-items: center; gap: 10px; margin-top: 14px; }
.bmp-term-date { flex: 1; }
.bmp-term-date--r { text-align: right; }
.bmp-term-date-l { font-size: 10.5px; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94A3B8); }
.bmp-term-date-v { font-size: 15px; font-weight: 400; color: var(--t1, #1A1730); margin-top: 3px; font-variant-numeric: tabular-nums; }
.bmp-term-arrow { color: var(--t3, #C9C6DA); flex-shrink: 0; }
.bmp-term-arrow svg { width: 20px; height: 20px; }

.bmp-progress { margin-top: 15px; }
.bmp-progress-track {
  height: 7px; border-radius: 999px; overflow: hidden;
  background: var(--bg3, #EEEDF4);
}
.bmp-progress-fill {
  height: 100%; border-radius: 999px;
  transform-origin: left;
  animation: bmpFill .8s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both;
  animation-delay: .28s;
}
@keyframes bmpFill { from { transform: scaleX(0); } to { transform: scaleX(1); } }
.bmp-progress-cap { font-size: 11.5px; color: var(--t2, #6B6880); margin-top: 8px; }
.bmp-progress-cap--expired { color: #C5352F; font-weight: 500; }
.bmp-term-nodata { font-size: 12px; color: var(--t3, #A6A3B8); margin-top: 12px; font-style: italic; }

@media (max-width: 520px) {
  .bmp-facts { grid-template-columns: 1fr; }
}
</style>
