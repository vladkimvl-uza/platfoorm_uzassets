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
      <li
        v-for="(c, idx) in items"
        :key="c.id"
        :class="['ai-sb-item', { active: c.id === activeId }]"
        :style="{ animationDelay: `${Math.min(idx, 8) * 30}ms` }"
        @click="$emit('select', c.id)"
      >
        <div class="ai-sb-item-head">
          <div class="ai-sb-item-title">
            {{ c.title || "Без названия" }}
          </div>
          <button
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
        <div v-if="c.last_message_preview" class="ai-sb-item-prev">
          {{ c.last_message_preview }}
        </div>
        <div class="ai-sb-item-meta">
          <span class="ai-sb-item-date">{{ formatDate(c.updated_at) }}</span>
          <span class="ai-sb-item-cnt">{{ c.message_count }}</span>
        </div>
      </li>
    </ul>

    <footer class="ai-sb-foot">
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
  </aside>
</template>

<script setup lang="ts">
import type { ConversationListItem } from "@/api/aiClient";

defineProps<{
  items: ConversationListItem[];
  activeId: string | null;
  loading: boolean;
}>();
defineEmits<{
  "new-chat": [];
  select: [id: string];
  delete: [id: string];
  "open-settings": [];
}>();

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

.ai-sb-item-del {
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
.ai-sb-item:hover .ai-sb-item-del { opacity: 1; }
.ai-sb-item-del:hover {
  background: rgba(226, 75, 74, 0.10);
  color: var(--uza-red);
}

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

.ai-sb-foot {
  border-top: 1px solid rgba(127, 119, 221, 0.10);
  padding: 10px 12px;
}

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
