<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  moderationApi, formatRelativeTime, STATUS_LABELS,
  type Submission, type Comment,
} from "@/api/moderation";
import { useAuthStore } from "@/stores/auth";

const props = defineProps<{ submissionId: string }>();
const emit = defineEmits<{ close: []; resolved: [] }>();

const auth = useAuthStore();

const sub = ref<Submission | null>(null);
const comments = ref<Comment[]>([]);
const loading = ref(false);
const acting = ref(false);
const error = ref<string | null>(null);
const newComment = ref("");
const internalToggle = ref(false);

const canResolve = computed(() => {
  if (!sub.value) return false;
  if (auth.isOwner) return true;
  return auth.user?.id === sub.value.assigned_moderator_id ||
         auth.user?.id === sub.value.coapprover_id;
});
const canWithdraw = computed(() => {
  if (!sub.value) return false;
  return auth.user?.id === sub.value.proposer_user_id &&
         !["approved", "rejected", "expired"].includes(sub.value.status);
});

async function load() {
  loading.value = true;
  error.value = null;
  try {
    sub.value = await moderationApi.get(props.submissionId);
    comments.value = await moderationApi.listComments(props.submissionId);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить";
  } finally { loading.value = false; }
}

onMounted(load);

async function approve() {
  if (!sub.value) return;
  acting.value = true;
  try {
    await moderationApi.approve(sub.value.id, undefined);
    emit("resolved");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { acting.value = false; }
}
async function reject() {
  if (!sub.value) return;
  const note = window.prompt("Причина отклонения (опционально):");
  if (note === null) return;
  acting.value = true;
  try {
    await moderationApi.reject(sub.value.id, note || undefined);
    emit("resolved");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { acting.value = false; }
}
async function setReview() {
  if (!sub.value) return;
  acting.value = true;
  try {
    await moderationApi.setReview(sub.value.id, "Требуется доп. рассмотрение");
    emit("resolved");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { acting.value = false; }
}
async function withdraw() {
  if (!sub.value) return;
  if (!confirm("Отозвать ваше предложение?")) return;
  acting.value = true;
  try {
    await moderationApi.withdraw(sub.value.id);
    emit("resolved");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { acting.value = false; }
}

async function postComment() {
  const text = newComment.value.trim();
  if (!sub.value || !text) return;
  try {
    const c = await moderationApi.addComment(sub.value.id, text, { is_internal: internalToggle.value });
    comments.value.push(c);
    newComment.value = "";
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) emit("close");
}

const diffEntries = computed(() => {
  if (!sub.value) return [];
  const before = sub.value.original_value || {};
  const after  = sub.value.proposed_value || {};
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]));
  return keys.map((k) => ({
    key: k,
    before: (before as Record<string, unknown>)[k],
    after:  (after  as Record<string, unknown>)[k],
    changed: JSON.stringify((before as Record<string, unknown>)[k]) !== JSON.stringify((after as Record<string, unknown>)[k]),
  }));
});

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return v.toLocaleString("ru-RU");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
</script>

<template>
  <div class="mrm-backdrop" @click="onBackdropClick">
    <div class="mrm-card">

      <div v-if="loading" class="mrm-loading">Загрузка…</div>

      <template v-else-if="sub">
        <div class="mrm-topbar">
          <div class="mrm-tb-l">
            <span class="mrm-tb-icn">
              <i class="ti ti-shield-check" aria-hidden="true"></i>
            </span>
            <div>
              <div class="mrm-eyebrow">
                Модерация · <span class="mrm-id">#{{ sub.id.slice(0, 8) }}</span> ·
                <span class="mrm-status-pill" :style="{ background: STATUS_LABELS[sub.status].bg, color: STATUS_LABELS[sub.status].color }">
                  {{ STATUS_LABELS[sub.status].label }}
                </span>
              </div>
              <div class="mrm-title">{{ sub.target_entity_label || sub.target_module }}</div>
            </div>
          </div>
          <button class="mrm-close" @click="emit('close')">
            <i class="ti ti-x" aria-hidden="true"></i>
          </button>
        </div>

        <div class="mrm-meta">
          <div class="mrm-proposer">
            <span class="mrm-avatar mrm-avatar-ext">{{ (sub.proposer_user_id || "").slice(0, 2).toUpperCase() }}</span>
            <div>
              <div class="mrm-proposer-name">
                Предлагающий
                <span v-if="sub.proposer_is_external" class="mrm-ext-pill">EXTERNAL</span>
              </div>
              <div class="mrm-proposer-meta">id <code>{{ sub.proposer_user_id.slice(0, 8) }}</code></div>
            </div>
          </div>
          <div class="mrm-meta-r">
            Предложено: <b>{{ formatRelativeTime(sub.created_at) }}</b>
            <span v-if="sub.expires_at"> · истекает {{ formatRelativeTime(sub.expires_at) }}</span>
          </div>
        </div>

        <div class="mrm-body">

          <div class="mrm-section">
            <div class="mrm-section-hd">Контекст</div>
            <div class="mrm-breadcrumbs">
              <span class="mrm-bc-item"><i class="ti ti-package" style="font-size: 13px;" aria-hidden="true"></i> {{ sub.target_module }}</span>
              <i v-if="sub.target_entity_label" class="ti ti-chevron-right mrm-bc-arr" aria-hidden="true"></i>
              <span v-if="sub.target_entity_label" class="mrm-bc-item">{{ sub.target_entity_label }}</span>
              <i v-if="sub.target_field" class="ti ti-chevron-right mrm-bc-arr" aria-hidden="true"></i>
              <span v-if="sub.target_field" class="mrm-bc-item mrm-bc-strong">{{ sub.target_field }}</span>
            </div>
          </div>

          <div v-if="diffEntries.length > 0" class="mrm-section">
            <div class="mrm-section-hd">Изменения</div>
            <div class="mrm-diff-grid">
              <div v-for="d in diffEntries" :key="d.key" class="mrm-diff-row" :class="{ changed: d.changed }">
                <div class="mrm-diff-key">{{ d.key }}</div>
                <div class="mrm-diff-before">
                  <div class="mrm-diff-label">Было</div>
                  <div class="mrm-diff-val">{{ fmtVal(d.before) }}</div>
                </div>
                <i class="ti ti-arrow-right mrm-diff-arr" aria-hidden="true"></i>
                <div class="mrm-diff-after">
                  <div class="mrm-diff-label">Предложено</div>
                  <div class="mrm-diff-val">{{ fmtVal(d.after) }}</div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="sub.reason" class="mrm-section">
            <div class="mrm-section-hd">Обоснование</div>
            <div class="mrm-reason">{{ sub.reason }}</div>
          </div>

          <div v-if="sub.attachments && sub.attachments.length" class="mrm-section">
            <div class="mrm-section-hd">Вложения</div>
            <div class="mrm-attachments">
              <span v-for="(a, i) in sub.attachments" :key="i" class="mrm-attach">
                <i class="ti ti-paperclip" style="font-size: 11px;" aria-hidden="true"></i>
                {{ (a as Record<string, unknown>).name || "файл" }}
              </span>
            </div>
          </div>

          <div class="mrm-section">
            <div class="mrm-section-hd">Обсуждение · {{ comments.length }}</div>
            <div v-if="!comments.length" class="mrm-empty-comments">Нет комментариев</div>
            <div v-else class="mrm-comments">
              <div v-for="c in comments" :key="c.id" class="mrm-comment" :class="{ internal: c.is_internal }">
                <span class="mrm-c-avatar">{{ (c.user_id || "—").slice(0, 2).toUpperCase() }}</span>
                <div class="mrm-c-body">
                  <div class="mrm-c-meta">
                    <b>{{ c.user_id ? c.user_id.slice(0, 8) : "(удалён)" }}</b>
                    <span v-if="c.is_internal" class="mrm-c-internal">internal</span>
                    <span class="mrm-c-time">{{ formatRelativeTime(c.created_at) }}</span>
                  </div>
                  <div class="mrm-c-text">{{ c.text }}</div>
                </div>
              </div>
            </div>
            <div class="mrm-c-compose">
              <input v-model="newComment" placeholder="Написать комментарий..." @keyup.enter="postComment" />
              <label v-if="canResolve" class="mrm-c-internal-check"><input type="checkbox" v-model="internalToggle"> internal</label>
              <button class="mrm-c-send" @click="postComment" :disabled="!newComment.trim()">
                <i class="ti ti-send" aria-hidden="true"></i> Отправить
              </button>
            </div>
          </div>

          <div v-if="sub.resolution_note" class="mrm-section">
            <div class="mrm-section-hd">Резолюция</div>
            <div class="mrm-resolution">{{ sub.resolution_note }}</div>
          </div>

          <div v-if="error" class="mrm-error">{{ error }}</div>
        </div>

        <div class="mrm-footer">
          <div class="mrm-foot-l">
            <i class="ti ti-history" aria-hidden="true"></i>
            Все действия логируются в audit log
          </div>
          <div class="mrm-foot-r">
            <button v-if="canWithdraw" class="mrm-btn mrm-btn-ghost" :disabled="acting" @click="withdraw">
              Отозвать
            </button>
            <template v-if="canResolve && ['pending','under_review'].includes(sub.status)">
              <button class="mrm-btn mrm-btn-ghost" :disabled="acting" @click="setReview">
                <i class="ti ti-eye" aria-hidden="true"></i> На рассмотрение
              </button>
              <button class="mrm-btn mrm-btn-reject" :disabled="acting" @click="reject">
                <i class="ti ti-x" aria-hidden="true"></i> Отклонить
              </button>
              <button class="mrm-btn mrm-btn-approve" :disabled="acting" @click="approve">
                <i class="ti ti-check" aria-hidden="true"></i> Принять
              </button>
            </template>
          </div>
        </div>
      </template>

      <div v-else-if="error" class="mrm-error">{{ error }}</div>
    </div>
  </div>
</template>

<style scoped>
.mrm-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15,18,40,.45);
  backdrop-filter: blur(8px);
  z-index: 1500;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
  animation: mrmFade .25s cubic-bezier(.34,1.2,.64,1);
}
@keyframes mrmFade { from { opacity: 0; } to { opacity: 1; } }

.mrm-card {
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  width: 720px; max-width: 100%;
  max-height: 90vh;
  display: flex; flex-direction: column;
  overflow: hidden;
  animation: mrmIn .45s cubic-bezier(.34,1.2,.64,1);
}
@keyframes mrmIn {
  from { opacity: 0; transform: scale(.96) translateY(-8px); }
  to   { opacity: 1; transform: scale(1)    translateY(0);    }
}

.mrm-loading { padding: 60px; text-align: center; color: var(--color-text-tertiary); font-size: 13px; }

.mrm-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 12px 18px;
  display: flex; align-items: center; justify-content: space-between;
}
.mrm-tb-l { display: flex; align-items: center; gap: 10px; }
.mrm-tb-icn {
  width: 30px; height: 30px;
  border-radius: 7px;
  background: rgba(239,159,39,.2);
  color: #FAC775;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 16px;
}
.mrm-eyebrow {
  font-size: 10px;
  color: rgba(255,255,255,.55);
  text-transform: uppercase;
  letter-spacing: .08em;
  font-weight: 500;
  display: flex; align-items: center; gap: 5px;
}
.mrm-id { font-family: monospace; }
.mrm-status-pill {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .04em;
  color: #fff !important;
  background: rgba(255,255,255,.15) !important;
}
.mrm-title { font-size: 14px; color: #fff; font-weight: 500; margin-top: 1px; }
.mrm-close {
  background: rgba(255,255,255,.1);
  border: 0;
  color: #fff;
  width: 26px; height: 26px;
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 14px;
}

.mrm-meta {
  padding: 11px 18px;
  background: #FAFAFC;
  border-bottom: 0.5px solid rgba(0,0,0,.05);
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.mrm-proposer { display: flex; align-items: center; gap: 8px; }
.mrm-avatar {
  width: 30px; height: 30px;
  border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 500;
}
.mrm-avatar-ext { background: rgba(212,83,126,.15); color: #993556; }
.mrm-proposer-name { font-size: 12px; color: var(--color-text-primary); font-weight: 500; display: flex; align-items: center; gap: 6px; }
.mrm-proposer-meta { font-size: 10px; color: var(--color-text-tertiary); }
.mrm-ext-pill {
  background: #D4537E; color: #fff;
  padding: 1px 5px; border-radius: 3px;
  font-size: 8.5px; font-weight: 600; letter-spacing: .04em;
}
.mrm-meta-r { font-size: 11px; color: var(--color-text-secondary); margin-left: auto; }

.mrm-body { padding: 14px 18px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 14px; }

.mrm-section-hd {
  font-size: 9.5px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 500;
  margin-bottom: 6px;
}

.mrm-breadcrumbs {
  background: var(--color-background-secondary);
  border-radius: 7px;
  padding: 9px 12px;
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  font-size: 11.5px;
}
.mrm-bc-item { color: var(--color-text-secondary); display: inline-flex; align-items: center; gap: 4px; }
.mrm-bc-strong { color: var(--color-text-primary); font-weight: 500; }
.mrm-bc-arr { font-size: 10px; color: var(--color-text-tertiary); }

.mrm-diff-grid { display: flex; flex-direction: column; gap: 6px; }
.mrm-diff-row {
  display: grid;
  grid-template-columns: 120px 1fr 24px 1fr;
  gap: 8px;
  align-items: stretch;
}
.mrm-diff-key { font-size: 11px; color: var(--color-text-tertiary); padding-top: 11px; font-family: monospace; }
.mrm-diff-before, .mrm-diff-after {
  background: var(--color-background-secondary);
  border-radius: 6px;
  padding: 7px 10px;
}
.mrm-diff-row.changed .mrm-diff-before {
  background: rgba(226,75,74,.05);
  border: 0.5px solid rgba(226,75,74,.2);
}
.mrm-diff-row.changed .mrm-diff-after {
  background: rgba(29,158,117,.05);
  border: 0.5px solid rgba(29,158,117,.2);
}
.mrm-diff-label {
  font-size: 8.5px;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--color-text-tertiary);
}
.mrm-diff-row.changed .mrm-diff-before .mrm-diff-label { color: #A32D2D; font-weight: 600; }
.mrm-diff-row.changed .mrm-diff-after  .mrm-diff-label { color: #0F6E56; font-weight: 600; }
.mrm-diff-val { font-size: 13px; color: var(--color-text-primary); font-weight: 500; font-feature-settings: "tnum"; margin-top: 2px; word-break: break-word; }
.mrm-diff-arr {
  align-self: center; text-align: center;
  font-size: 16px; color: var(--color-text-tertiary);
}

.mrm-reason {
  background: var(--color-background-secondary);
  border-radius: 7px;
  padding: 9px 12px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}
.mrm-resolution {
  background: rgba(127,119,221,.06);
  border-left: 3px solid #7F77DD;
  border-radius: 0 7px 7px 0;
  padding: 8px 12px;
  font-size: 11.5px;
  color: var(--color-text-primary);
  line-height: 1.45;
}

.mrm-attachments { display: flex; gap: 5px; flex-wrap: wrap; }
.mrm-attach {
  background: var(--color-background-secondary);
  border: 0.5px solid var(--color-border-tertiary);
  padding: 3px 9px;
  border-radius: 6px;
  font-size: 11px;
  color: var(--color-text-secondary);
  display: inline-flex; align-items: center; gap: 4px;
}

.mrm-comments { display: flex; flex-direction: column; gap: 7px; }
.mrm-empty-comments { font-size: 11px; color: var(--color-text-tertiary); padding: 6px 0; }
.mrm-comment { display: flex; gap: 8px; }
.mrm-c-avatar {
  width: 24px; height: 24px;
  border-radius: 50%;
  background: rgba(127,119,221,.15);
  color: #534AB7;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 9.5px; font-weight: 500;
  flex-shrink: 0;
}
.mrm-c-body {
  flex: 1;
  background: var(--color-background-secondary);
  border-radius: 7px;
  padding: 7px 10px;
  font-size: 11.5px;
  color: var(--color-text-primary);
  line-height: 1.4;
}
.mrm-comment.internal .mrm-c-body { background: rgba(239,159,39,.08); border: 0.5px solid rgba(239,159,39,.2); }
.mrm-c-meta { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; font-size: 10.5px; }
.mrm-c-meta b { font-family: monospace; }
.mrm-c-internal { background: rgba(239,159,39,.15); color: #854F0B; padding: 1px 5px; border-radius: 3px; font-size: 8.5px; font-weight: 600; }
.mrm-c-time { color: var(--color-text-tertiary); }
.mrm-c-text { white-space: pre-wrap; }

.mrm-c-compose {
  display: flex; gap: 6px; align-items: center; margin-top: 8px;
}
.mrm-c-compose input {
  flex: 1;
  padding: 7px 10px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 7px;
  font-size: 11.5px;
  font-family: inherit;
  outline: none;
}
.mrm-c-internal-check { font-size: 10px; color: var(--color-text-tertiary); display: inline-flex; align-items: center; gap: 3px; cursor: pointer; }
.mrm-c-send {
  background: rgba(127,119,221,.1);
  color: #534AB7;
  border: 0;
  padding: 7px 12px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
}
.mrm-c-send:disabled { opacity: .4; cursor: not-allowed; }

.mrm-error {
  background: rgba(226,75,74,.08);
  color: #A32D2D;
  padding: 9px 12px;
  border-radius: 6px;
  font-size: 11.5px;
}

.mrm-footer {
  padding: 11px 18px;
  background: #FAFAFC;
  border-top: 0.5px solid rgba(0,0,0,.05);
  display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;
}
.mrm-foot-l {
  font-size: 11px;
  color: var(--color-text-tertiary);
  display: inline-flex; align-items: center; gap: 5px;
}
.mrm-foot-r { display: flex; gap: 6px; flex-wrap: wrap; }

.mrm-btn {
  border: 0;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
  transition: background .12s, color .12s;
}
.mrm-btn:disabled { opacity: .5; cursor: not-allowed; }
.mrm-btn-ghost { background: transparent; border: 0.5px solid var(--color-border-tertiary); color: var(--color-text-secondary); }
.mrm-btn-ghost:hover:not(:disabled) { background: rgba(0,0,0,.03); }
.mrm-btn-reject { background: rgba(226,75,74,.1); color: #A32D2D; }
.mrm-btn-reject:hover:not(:disabled) { background: rgba(226,75,74,.2); }
.mrm-btn-approve { background: #1D9E75; color: #fff; }
.mrm-btn-approve:hover:not(:disabled) { background: #0F6E56; }
</style>
