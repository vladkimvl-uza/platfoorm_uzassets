<script setup lang="ts">
/**
 * ESGSwotPanel — SWOT (сильные стороны / проблемные зоны) ОДНОЙ компании для
 * встраивания в воркспейс. Данные из общего getSwot → company_items своей
 * компании (синк с /esg). Правка через upsertSwot (scope=company).
 */
import { computed, ref, watch } from "vue";
import { esgApi, type ESGSwotItemBrief } from "@/api/esg";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
const { t } = useI18n();

// ── Подпись автора: инициалы + локализованная дата ──
function authorInitials(name: string): string {
  const parts = name.split(" ").filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}
function authorSub(it: ESGSwotItemBrief): string {
  return [it.created_by_title, it.created_by_org].filter(Boolean).join(" · ");
}
function authorDate(it: ESGSwotItemBrief): string {
  if (!it.created_at) return "";
  try {
    return new Date(it.created_at).toLocaleDateString(getCurrentIntlLocale(), {
      day: "numeric", month: "short", year: "numeric",
    });
  } catch { return ""; }
}



const props = defineProps<{ companyId: string; canEdit?: boolean }>();
const emit = defineEmits<{ (e: "changed"): void }>();

const toast = useToast();
const loading = ref(true);
const error = ref<string | null>(null);
const items = ref<ESGSwotItemBrief[]>([]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const data = await esgApi.getSwot();
    items.value = (data.company_items || []).filter(i => i.company_id === props.companyId);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось загрузить SWOT');
    items.value = [];
  } finally {
    loading.value = false;
  }
}
watch(() => props.companyId, load, { immediate: true });

const strengths = computed(() => items.value.filter(i => i.kind === "strength").sort((a, b) => a.order_idx - b.order_idx));
const weaknesses = computed(() => items.value.filter(i => i.kind === "weakness").sort((a, b) => a.order_idx - b.order_idx));

// ─── Инлайн-правка / добавление ───
const editing = ref<{ id: string | null; kind: "strength" | "weakness" } | null>(null);
const draft = ref("");
const saving = ref(false);

function startEdit(it: ESGSwotItemBrief) {
  if (!props.canEdit) return;
  editing.value = { id: it.id || null, kind: it.kind };
  draft.value = it.body || "";
}
function startAdd(kind: "strength" | "weakness") {
  editing.value = { id: null, kind };
  draft.value = "";
}
function cancel() { editing.value = null; draft.value = ""; }

const { confirmDialog } = useConfirm();
async function removeItem(it: ESGSwotItemBrief) {
  if (!props.canEdit || !it.id || saving.value) return;
  const ok = await confirmDialog({
    title: t("Удалить вывод"),
    message: t("«{text}» будет удалён. Действие необратимо.", { text: (it.body || "").slice(0, 120) }),
    confirmText: t("Удалить"),
    danger: true,
  });
  if (!ok) return;
  saving.value = true;
  try {
    await esgApi.deleteSwot(it.id);
    toast.success(t('Вывод удалён')); emit("changed");
    await load();
  } catch (e: any) {
    toast.error(t('Не удалено: {value0}', { value0: (e?.response?.data?.detail || e?.message || t("ошибка")) }));
  } finally { saving.value = false; }
}

async function save() {
  if (!editing.value) return;
  const body = draft.value.trim();
  if (!body) { toast.error(t('Введите текст')); return; }
  saving.value = true;
  try {
    const nextIdx = items.value.filter(i => i.kind === editing.value!.kind).length;
    await esgApi.upsertSwot({
      id: editing.value.id,
      kind: editing.value.kind,
      scope: "company",
      company_id: props.companyId,
      body,
      order_idx: editing.value.id ? undefined as any : nextIdx,
    } as any);
    toast.success(t('Сохранено'));
    editing.value = null; draft.value = "";
    await load();
    emit("changed");
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t('Не удалось сохранить'));
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="sw">
    <UzaStateBlock v-if="loading" state="loading" :text="t('Загрузка SWOT…')" />
    <UzaStateBlock v-else-if="error" state="error" variant="block" :text="error" retry @retry="load" />

    <template v-else>
      <div class="sw-grid">
        <!-- Сильные стороны -->
        <div class="sw-col sw-col-good">
          <div class="sw-col-h">
            <span class="sw-col-t">{{ t('Сильные стороны') }}</span>
            <button v-if="canEdit && !(editing && editing.id === null && editing.kind === 'strength')" class="sw-add" @click="startAdd('strength')">{{ t('+ добавить') }}</button>
          </div>
          <div class="sw-list">
            <div v-for="it in strengths" :key="it.id || it.order_idx" class="sw-item"
                 :class="{ 'sw-item-edit': canEdit }" @click="canEdit && editing?.id !== it.id && startEdit(it)">
              <template v-if="editing && editing.id === it.id">
                <textarea v-model="draft" class="sw-ta" rows="2" :disabled="saving" @click.stop></textarea>
                <div class="sw-acts">
                  <button class="sw-ok" :disabled="saving" @click.stop="save">{{ t('Сохранить') }}</button>
                  <button class="sw-x" @click.stop="cancel">{{ t('Отмена') }}</button>
                </div>
              </template>
              <template v-else>
                <button v-if="canEdit && it.id" class="sw-del" :disabled="saving"
                        :title="t('Удалить вывод')" @click.stop="removeItem(it)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2m1 0-1 14H8L7 6"/></svg>
                </button>
                <span class="sw-body">{{ it.body }}</span>
                <div v-if="it.created_by_name" class="sw-author">
                  <span class="sw-author-ava">{{ authorInitials(it.created_by_name) }}</span>
                  <span class="sw-author-col">
                    <span class="sw-author-name">{{ it.created_by_name }}</span>
                    <span v-if="authorSub(it)" class="sw-author-sub">{{ authorSub(it) }}</span>
                  </span>
                  <span v-if="authorDate(it)" class="sw-author-date">{{ authorDate(it) }}</span>
                </div>
              </template>
            </div>
            <div v-if="editing && editing.id === null && editing.kind === 'strength'" class="sw-item sw-item-new">
              <textarea v-model="draft" class="sw-ta" rows="2" :disabled="saving" :placeholder="t('Новая сильная сторона…')" @click.stop></textarea>
              <div class="sw-acts">
                <button class="sw-ok" :disabled="saving" @click.stop="save">{{ t('Добавить') }}</button>
                <button class="sw-x" @click.stop="cancel">{{ t('Отмена') }}</button>
              </div>
            </div>
            <div v-if="!strengths.length && !(editing && editing.kind === 'strength' && editing.id === null)" class="sw-empty">{{ t('Не указаны') }}</div>
          </div>
        </div>

        <!-- Проблемные зоны -->
        <div class="sw-col sw-col-bad">
          <div class="sw-col-h">
            <span class="sw-col-t">{{ t('Проблемные зоны') }}</span>
            <button v-if="canEdit && !(editing && editing.id === null && editing.kind === 'weakness')" class="sw-add" @click="startAdd('weakness')">{{ t('+ добавить') }}</button>
          </div>
          <div class="sw-list">
            <div v-for="it in weaknesses" :key="it.id || it.order_idx" class="sw-item"
                 :class="{ 'sw-item-edit': canEdit }" @click="canEdit && editing?.id !== it.id && startEdit(it)">
              <template v-if="editing && editing.id === it.id">
                <textarea v-model="draft" class="sw-ta" rows="2" :disabled="saving" @click.stop></textarea>
                <div class="sw-acts">
                  <button class="sw-ok" :disabled="saving" @click.stop="save">{{ t('Сохранить') }}</button>
                  <button class="sw-x" @click.stop="cancel">{{ t('Отмена') }}</button>
                </div>
              </template>
              <template v-else>
                <button v-if="canEdit && it.id" class="sw-del" :disabled="saving"
                        :title="t('Удалить вывод')" @click.stop="removeItem(it)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2m1 0-1 14H8L7 6"/></svg>
                </button>
                <span class="sw-body">{{ it.body }}</span>
                <div v-if="it.created_by_name" class="sw-author">
                  <span class="sw-author-ava">{{ authorInitials(it.created_by_name) }}</span>
                  <span class="sw-author-col">
                    <span class="sw-author-name">{{ it.created_by_name }}</span>
                    <span v-if="authorSub(it)" class="sw-author-sub">{{ authorSub(it) }}</span>
                  </span>
                  <span v-if="authorDate(it)" class="sw-author-date">{{ authorDate(it) }}</span>
                </div>
              </template>
            </div>
            <div v-if="editing && editing.id === null && editing.kind === 'weakness'" class="sw-item sw-item-new">
              <textarea v-model="draft" class="sw-ta" rows="2" :disabled="saving" :placeholder="t('Новая проблемная зона…')" @click.stop></textarea>
              <div class="sw-acts">
                <button class="sw-ok" :disabled="saving" @click.stop="save">{{ t('Добавить') }}</button>
                <button class="sw-x" @click.stop="cancel">{{ t('Отмена') }}</button>
              </div>
            </div>
            <div v-if="!weaknesses.length && !(editing && editing.kind === 'weakness' && editing.id === null)" class="sw-empty">{{ t('Не указаны') }}</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sw-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 760px) { .sw-grid { grid-template-columns: 1fr; } }
/* Акцент — ::before со скруглением карточки: border-top тянулся по углам. */
.sw-col { position: relative; overflow: hidden; background: #fff; border: .5px solid var(--line, #ECEAF4); border-radius: 12px; padding: 14px 16px; }
.sw-col::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--c, #94A3B8); border-radius: inherit; border-bottom-left-radius: 0; border-bottom-right-radius: 0; pointer-events: none; }
.sw-col-good { --c: #1D9E75; }
.sw-col-bad { --c: #E24B4A; }
.sw-col-h { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.sw-col-t { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t2, #6B6880); }
.sw-add { font-size: 11px; color: var(--p-deep, #534AB7); background: rgba(124,111,247,.1); border: none; border-radius: 999px; padding: 3px 10px; cursor: pointer; font-family: inherit; }
.sw-add:hover { background: rgba(124,111,247,.18); }
.sw-list { display: flex; flex-direction: column; gap: 8px; }
.sw-item { background: var(--bg2, #F8FAFC); border: 1px solid var(--line, #ECEAF4); border-radius: 9px; padding: 10px 12px; }
.sw-item-edit { cursor: pointer; transition: border-color .14s, box-shadow .14s; }
.sw-item-edit:hover { border-color: rgba(124,111,247,.4); }
.sw-item-new { border-style: dashed; }
.sw-body { font-size: 12.5px; color: var(--t1, #1A1730); line-height: 1.45; white-space: pre-wrap; }
.sw-ta { width: 100%; box-sizing: border-box; border: 1.5px solid var(--p, #7C6FF7); border-radius: 8px; background: #fff; padding: 6px 9px; font-size: 12.5px; font-family: inherit; color: var(--t1, #1A1730); outline: none; resize: vertical; }
.sw-ta:focus { box-shadow: 0 0 0 3px rgba(124,111,247,.14); }
.sw-acts { display: flex; gap: 7px; margin-top: 7px; }
.sw-ok { font-size: 11.5px; font-weight: 500; color: #fff; background: #1D9E75; border: none; border-radius: 7px; padding: 4px 12px; cursor: pointer; font-family: inherit; }
.sw-ok:disabled { opacity: .6; cursor: default; }
.sw-x { font-size: 11.5px; color: var(--t2, #6B6880); background: var(--bg3, #F1F0F7); border: none; border-radius: 7px; padding: 4px 12px; cursor: pointer; font-family: inherit; }
.sw-empty { font-size: 11.5px; color: var(--t3, #A6A3B8); font-style: italic; padding: 4px 2px; }

/* ── Подпись автора: премиум-футер карточки вывода ── */
.sw-author {
  display: flex; align-items: center; gap: 8px;
  margin-top: 7px; padding-top: 7px;
  border-top: 1px solid rgba(127, 119, 221, .14);
}
.sw-author-ava {
  width: 22px; height: 22px; border-radius: 50%; flex: none;
  display: inline-flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #8B83E8 0%, #534AB7 100%);
  color: #fff; font-size: 8.5px; font-weight: 600; letter-spacing: .03em;
  box-shadow: 0 1px 3px rgba(83, 74, 183, .30);
}
.sw-author-col { display: flex; flex-direction: column; min-width: 0; line-height: 1.25; }
.sw-author-name { font-size: 10.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.sw-author-sub {
  font-size: 9.5px; color: var(--t3, #94A3B8);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.sw-author-date {
  margin-left: auto; flex: none;
  font-size: 9.5px; color: var(--t3, #94A3B8);
  font-variant-numeric: tabular-nums;
}

/* Удаление вывода: тихая кнопка в углу карточки, видна при наведении */
.sw-item { position: relative; }
.sw-del {
  position: absolute; top: 6px; right: 6px;
  width: 24px; height: 24px; border: none; border-radius: 6px;
  background: transparent; color: var(--t3, #94A3B8); cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity .12s, background .12s, color .12s;
}
.sw-item:hover .sw-del { opacity: 1; }
.sw-del:hover { background: rgba(226, 75, 74, .10); color: #E24B4A; }
.sw-del:disabled { opacity: .4; cursor: default; }
</style>
