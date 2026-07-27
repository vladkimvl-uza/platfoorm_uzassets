<template>
  <aside class="ai-sb">
    <header class="ai-sb-head">
      <button class="ai-sb-new" type="button" @click="$emit('new-chat')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 5v14M5 12h14"/>
        </svg>
        Новый разговор
      </button>
    </header>

    <div v-if="loading" class="ai-sb-empty">
      <span class="ai-sb-empty-spinner"></span>
      <span>Загрузка</span>
    </div>
    <div v-else-if="!items.length" class="ai-sb-empty">
      Здесь появятся ваши разговоры
    </div>
    <ul v-else class="ai-sb-list">
      <!-- a11y (P2 аудита): строка беседы была <li @click> без tabindex/role/
           keydown — выбрать беседу с клавиатуры было НЕВОЗМОЖНО (фокус
           перескакивал сразу на иконки действий). Теперь это кнопка-строка:
           Tab доводит фокус, Enter/Space открывают. -->
      <li
        v-for="(c, idx) in items"
        :key="c.id"
        :class="['ai-sb-item', { active: c.id === activeId, editing: editingId === c.id }]"
        :style="{ animationDelay: `${Math.min(idx, 8) * 30}ms` }"
        :tabindex="editingId === c.id ? -1 : 0"
        role="button"
        :aria-current="c.id === activeId ? 'true' : undefined"
        :aria-label="`Открыть разговор: ${c.title || 'Без названия'}`"
        @click="editingId === c.id ? null : $emit('select', c.id)"
        @keydown.enter.prevent="editingId === c.id ? null : $emit('select', c.id)"
        @keydown.space.prevent="editingId === c.id ? null : $emit('select', c.id)"
      >
        <div class="ai-sb-item-head">
          <input
            v-if="editingId === c.id"
            ref="renameInputs"
            v-model="renameDraft"
            class="ai-sb-item-rename"
            type="text"
            maxlength="80"
            @click.stop
            @keydown.enter.stop.prevent="commitRename(c.id)"
            @keydown.escape.stop="cancelRename"
            @blur="commitRename(c.id)"
          />
          <div v-else class="ai-sb-item-title">
            {{ c.title || "Без названия" }}
          </div>
          <button
            v-if="editingId !== c.id"
            class="ai-sb-item-act"
            type="button"
            title="Переименовать"
            @click.stop="startRename(c)"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </button>
          <button
            v-if="editingId !== c.id"
            class="ai-sb-item-del"
            type="button"
            title="Удалить"
            @click.stop="$emit('delete', c.id)"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
              <path d="M10 11v6M14 11v6"/>
            </svg>
          </button>
        </div>
        <div v-if="c.last_message_preview && editingId !== c.id" class="ai-sb-item-prev">
          {{ c.last_message_preview }}
        </div>
        <div v-if="editingId !== c.id" class="ai-sb-item-meta">
          <span
            v-if="tagFor(c)"
            class="ai-sb-tag"
            :style="{ '--tag-c': tagFor(c)!.color }"
          >{{ tagFor(c)!.label }}</span>
          <span class="ai-sb-item-date">{{ formatDate(c.updated_at) }}</span>
          <span class="ai-sb-item-cnt">{{ c.message_count }}</span>
        </div>
      </li>
    </ul>

    <footer class="ai-sb-foot">
      <div v-if="canToggle" class="ai-sb-act" :class="{ off: !aiActive }">
        <span class="ai-sb-act-l">
          <span class="ai-sb-act-dot" :class="{ on: aiActive }" />
          ИИ-ассистент {{ aiActive ? 'активен' : 'выключен' }}
        </span>
        <button class="ai-sb-switch" :class="{ on: aiActive }" :disabled="toggling"
                @click="toggleActive" :title="aiActive ? 'Деактивировать' : 'Активировать'">
          <span class="ai-sb-knob" />
        </button>
      </div>
      <div v-if="canToggle" class="ai-sb-act" :title="accessMode === 'owner_only' ? 'Сейчас доступ только у владельца' : 'Доступ по праву ai.view'">
        <span class="ai-sb-act-l">
          <span class="ai-sb-act-dot" :class="{ on: accessMode === 'owner_only' }" />
          Доступ: {{ accessMode === 'owner_only' ? 'только владелец' : 'по правам (ai.view)' }}
        </span>
        <button class="ai-sb-switch" :class="{ on: accessMode === 'owner_only' }" :disabled="savingMode"
                @click="toggleAccessMode" :title="accessMode === 'owner_only' ? 'Открыть по правам RBAC' : 'Ограничить владельцем'">
          <span class="ai-sb-knob" />
        </button>
      </div>
      <div v-else-if="!aiActive" class="ai-sb-act off">
        <span class="ai-sb-act-l"><span class="ai-sb-act-dot" /> ИИ-ассистент выключен владельцем</span>
      </div>
      <button v-if="canToggle" class="ai-sb-set" type="button" @click="kbOpen = true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
        </svg>
        <span>База знаний</span>
      </button>
      <button class="ai-sb-set" type="button" @click="$emit('open-settings')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
        <span>Настройки</span>
      </button>
    </footer>

    <KnowledgeBaseModal v-if="kbOpen" @close="kbOpen = false" />
  </aside>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, computed } from "vue";
import { renameConversation, type ConversationListItem } from "@/api/aiClient";
import { useAiActivation } from "@/composables/useAiActivation";
import KnowledgeBaseModal from "@/components/Ai/KnowledgeBaseModal.vue";
import { useToast } from "@/composables/useToast";

const toast = useToast();
const kbOpen = ref(false);

// ─── Глобальная активация ассистента (owner) ───
const ai = useAiActivation();
const aiActive = computed(() => ai.state.active);
const canToggle = computed(() => ai.state.canToggle);
const toggling = ref(false);
onMounted(() => ai.load(true));
async function toggleActive() {
  if (toggling.value || !canToggle.value) return;
  toggling.value = true;
  try { await ai.toggle(); } finally { toggling.value = false; }
}

// ─── Режим доступа: только владелец ⇄ по правам RBAC (owner) ───
const accessMode = computed(() => ai.state.accessMode);
const savingMode = ref(false);
async function toggleAccessMode() {
  if (savingMode.value || !canToggle.value) return;
  savingMode.value = true;
  try {
    await ai.setAccessMode(accessMode.value === "owner_only" ? "rbac" : "owner_only");
  } finally { savingMode.value = false; }
}

const props = defineProps<{
  items: ConversationListItem[];
  activeId: string | null;
  loading: boolean;
}>();
const emit = defineEmits<{
  "new-chat": [];
  select: [id: string];
  delete: [id: string];
  "open-settings": [];
  renamed: [id: string, title: string];
}>();

const editingId = ref<string | null>(null);
const renameDraft = ref("");
const renameInputs = ref<HTMLInputElement[] | null>(null);

function startRename(c: ConversationListItem) {
  editingId.value = c.id;
  renameDraft.value = c.title || "";
  nextTick(() => {
    const el = Array.isArray(renameInputs.value) ? renameInputs.value[0] : null;
    if (el) { el.focus(); el.select(); }
  });
}

function cancelRename() {
  editingId.value = null;
  renameDraft.value = "";
}

async function commitRename(id: string) {
  if (editingId.value !== id) return;
  const title = renameDraft.value.trim();
  const original = props.items.find((x) => x.id === id)?.title || "";
  editingId.value = null;
  if (!title || title === original) return;
  try {
    await renameConversation(id, title);
    emit("renamed", id, title);
  } catch (e) {
    console.warn("[AiSidebar] rename failed", e);
    toast.error("Не удалось переименовать разговор");
  }
}

// Тема разговора — выводим из заголовка/превью по ключевым словам, чтобы
// в истории было видно чего касался запрос (рейтинги/компании/финансы/…).
const TAG_RULES: { re: RegExp; label: string; color: string }[] = [
  { re: /рейтинг|fitch|moody|s&p|s\s*&\s*p|агентств/i, label: "Рейтинги", color: "#534AB7" },
  { re: /кредит|займ|долг|loan|ковенант|просрочк.*кредит/i, label: "Кредиты", color: "#E24B4A" },
  { re: /kpi|кипиай|ключев.* показател/i, label: "KPI", color: "#EF9F27" },
  { re: /esg|углерод|выброс|экологи/i, label: "ESG", color: "#1D9E75" },
  { re: /закуп|поставщик|тендер|контракт/i, label: "Закупки", color: "#7F77DD" },
  { re: /бизнес[\s-]?план|\bбп\b|план[\s-]?факт/i, label: "Бизнес-план", color: "#0F6E56" },
  { re: /финанс|выручк|ebitda|прибыл|мсфо|нсбу|баланс|opex|capex/i, label: "Финансы", color: "#0F6E56" },
  { re: /governance|корп.*управлен|совет директор|наблюдат/i, label: "Корпуправление", color: "#854F0B" },
  { re: /сценари|симуляц|what.?if|шок|эластичн/i, label: "Сценарии", color: "#534AB7" },
  { re: /задач|проект|дедлайн|просроч|срок/i, label: "Задачи", color: "#378ADD" },
  { re: /консультант|big\s?4|аудитор/i, label: "Консультанты", color: "#888780" },
  { re: /нефтегаз|горнодоб|энергетик|транспорт|сектор/i, label: "Сектор", color: "#1E2A4A" },
  { re: /компани|предприят|портфел/i, label: "Компании", color: "#1E2A4A" },
];
function tagFor(c: ConversationListItem): { label: string; color: string } | null {
  const hay = `${c.title || ""} ${c.last_message_preview || ""}`;
  for (const r of TAG_RULES) if (r.re.test(hay)) return { label: r.label, color: r.color };
  return null;
}

function formatDate(s: string) {
  try {
    const d = new Date(s);
    const now = new Date();
    const diff = (now.getTime() - d.getTime()) / 1000;
    if (diff < 60) return "только что";
    if (diff < 3600) return `${Math.floor(diff / 60)} мин`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} ч`;
    if (diff < 604800) return `${Math.floor(diff / 86400)} дн`;
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  } catch {
    return s;
  }
}
</script>

<style scoped>
.ai-sb {
  position: relative;
  z-index: 1;
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.55);
  -webkit-backdrop-filter: var(--ai-glass-blur);
          backdrop-filter: var(--ai-glass-blur);
  border-right: 1px solid var(--ai-glass-border);
  overflow: hidden;
}

.ai-sb-head {
  padding: 16px 12px 12px;
  border-bottom: 1px solid rgba(127, 119, 221, 0.10);
}

.ai-sb-new {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 12px;
  background: var(--ai-glass-bg-strong);
  border: 1px solid var(--ai-glass-border);
  border-radius: var(--ai-radius-md);
  font-size: 12.5px;
  font-weight: 500;
  color: var(--uza-navy);
  cursor: pointer;
  transition: all 0.2s var(--ai-easing-soft);
}
.ai-sb-new:hover {
  background: white;
  border-color: var(--uza-purple);
  color: var(--uza-purple);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(127, 119, 221, 0.18);
}

.ai-sb-empty {
  padding: 22px 14px;
  font-size: 12px;
  color: rgba(30, 42, 74, 0.5);
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.ai-sb-empty-spinner {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid rgba(127, 119, 221, 0.2);
  border-top-color: var(--uza-purple);
  animation: ai-sb-spin 0.7s linear infinite;
}
@keyframes ai-sb-spin { to { transform: rotate(360deg); } }

.ai-sb-list {
  flex: 1;
  list-style: none;
  margin: 0;
  padding: 8px;
  overflow-y: auto;
}

.ai-sb-item {
  position: relative;
  padding: 10px 12px;
  border-radius: var(--ai-radius-md);
  cursor: pointer;
  transition: all 0.18s var(--ai-easing-soft);
  margin-bottom: 4px;
  border: 1px solid transparent;
  animation: ai-sb-item-in 0.4s var(--ai-easing) both;
}
@keyframes ai-sb-item-in {
  from { opacity: 0; transform: translateX(-4px); }
  to   { opacity: 1; transform: translateX(0); }
}

.ai-sb-item:hover {
  background: rgba(255, 255, 255, 0.7);
  border-color: var(--ai-glass-border);
  transform: translateX(2px);
}

.ai-sb-item.active {
  background: rgba(127, 119, 221, 0.08);
  border-color: rgba(127, 119, 221, 0.25);
}
.ai-sb-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 12px;
  bottom: 12px;
  width: 2px;
  background: var(--uza-purple);
  border-radius: 0 2px 2px 0;
}
.ai-sb-item.active .ai-sb-item-title {
  color: var(--uza-purple);
}

.ai-sb-item-head {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.ai-sb-item-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--uza-navy);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.01em;
  min-width: 0;
}

.ai-sb-item-act, .ai-sb-item-del {
  border: 0;
  background: transparent;
  padding: 3px;
  border-radius: 5px;
  color: rgba(30, 42, 74, 0.4);
  cursor: pointer;
  display: flex;
  opacity: 0;
  transition: all 0.15s;
  flex-shrink: 0;
}
/* a11y: кнопки действий показывались ТОЛЬКО по hover мышью — клавиатурный
   пользователь не мог ни переименовать, ни удалить беседу. Показываем их
   также при фокусе внутри строки и при фокусе самой кнопки. */
.ai-sb-item:hover .ai-sb-item-act,
.ai-sb-item:hover .ai-sb-item-del,
.ai-sb-item:focus-within .ai-sb-item-act,
.ai-sb-item:focus-within .ai-sb-item-del,
.ai-sb-item-act:focus-visible,
.ai-sb-item-del:focus-visible { opacity: 1; }
.ai-sb-item:focus-visible {
  outline: 2px solid var(--uza-purple, #7C6FF7);
  outline-offset: -2px;
}
.ai-sb-item-act:focus-visible,
.ai-sb-item-del:focus-visible {
  outline: 2px solid var(--uza-purple, #7C6FF7);
  outline-offset: 1px;
}
.ai-sb-item-act:hover {
  background: rgba(127, 119, 221, 0.10);
  color: var(--uza-purple);
}
.ai-sb-item-del:hover {
  background: rgba(226, 75, 74, 0.10);
  color: var(--uza-red);
}

.ai-sb-item-rename {
  flex: 1;
  min-width: 0;
  padding: 4px 7px;
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  color: var(--uza-navy);
  background: var(--bg1, #fff);
  border: 1px solid rgba(127, 119, 221, 0.4);
  border-radius: 6px;
  outline: none;
  letter-spacing: -0.01em;
}
.ai-sb-item-rename:focus {
  border-color: var(--uza-purple);
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.15);
}
.ai-sb-item.editing { cursor: default; }
.ai-sb-item.editing:hover { transform: none; }

.ai-sb-item-prev {
  font-size: 11px;
  color: rgba(30, 42, 74, 0.55);
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.ai-sb-item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  color: rgba(30, 42, 74, 0.4);
  margin-top: 6px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.ai-sb-item-cnt::before {
  content: '·';
  margin-right: 4px;
}
.ai-sb-tag {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--tag-c, #534AB7);
  background: color-mix(in srgb, var(--tag-c, #534AB7) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--tag-c, #534AB7) 26%, transparent);
  line-height: 1.5;
}

.ai-sb-foot {
  border-top: 1px solid rgba(127, 119, 221, 0.10);
  padding: 10px 12px;
}
.ai-sb-act {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 10px; margin-bottom: 8px;
  border: 1px solid rgba(127,119,221,.16); border-radius: 10px;
  background: rgba(124,111,247,.05);
}
.ai-sb-act.off { background: rgba(226,75,74,.05); border-color: rgba(226,75,74,.16); }
.ai-sb-act-l { display: inline-flex; align-items: center; gap: 7px; font-size: 11.5px; font-weight: 500; color: var(--uza-navy, #1E2A4A); }
.ai-sb-act-dot { width: 7px; height: 7px; border-radius: 50%; background: #C7C9D1; }
.ai-sb-act-dot.on { background: #1D9E75; box-shadow: 0 0 0 3px rgba(29,158,117,.16); }
.ai-sb-switch {
  position: relative; width: 38px; height: 21px; border-radius: 99px;
  border: none; background: #D7D9E0; cursor: pointer; transition: background .2s; flex-shrink: 0;
}
.ai-sb-switch.on { background: linear-gradient(135deg,#8B7FFF,#6C5CE7); }
.ai-sb-switch:disabled { opacity: .6; cursor: default; }
.ai-sb-knob {
  position: absolute; top: 2px; left: 2px; width: 17px; height: 17px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 3px rgba(15,23,60,.3); transition: transform .2s cubic-bezier(.34,1.2,.64,1);
}
.ai-sb-switch.on .ai-sb-knob { transform: translateX(17px); }

.ai-sb-set {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  background: transparent;
  border: 1px solid var(--ai-glass-border);
  border-radius: var(--ai-radius-md);
  font-size: 12px;
  color: rgba(30, 42, 74, 0.65);
  cursor: pointer;
  transition: all 0.15s var(--ai-easing-soft);
}
.ai-sb-set:hover {
  background: rgba(255, 255, 255, 0.7);
  color: var(--uza-navy);
  border-color: var(--uza-purple);
}

@media (max-width: 768px) {
  .ai-sb { display: none; }
}
</style>
