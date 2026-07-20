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
import { isModerationQueued } from "@/api/client";

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
    error.value = e?.response?.data?.detail || "Не удалось загрузить SWOT";
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

async function save() {
  if (!editing.value) return;
  const body = draft.value.trim();
  if (!body) { toast.error("Введите текст"); return; }
  saving.value = true;
  try {
    const nextIdx = items.value.filter(i => i.kind === editing.value!.kind).length;
    const res = await esgApi.upsertSwot({
      id: editing.value.id,
      kind: editing.value.kind,
      scope: "company",
      company_id: props.companyId,
      body,
      order_idx: editing.value.id ? undefined as any : nextIdx,
    } as any);
    if (isModerationQueued(res)) toast.info("Изменение отправлено на модерацию");
    else toast.success("Сохранено");
    editing.value = null; draft.value = "";
    await load();
    emit("changed");
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Не удалось сохранить");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="sw">
    <UzaStateBlock v-if="loading" state="loading" text="Загрузка SWOT…" />
    <UzaStateBlock v-else-if="error" state="error" variant="block" :text="error" retry @retry="load" />

    <template v-else>
      <div class="sw-grid">
        <!-- Сильные стороны -->
        <div class="sw-col sw-col-good">
          <div class="sw-col-h">
            <span class="sw-col-t">Сильные стороны</span>
            <button v-if="canEdit && !(editing && editing.id === null && editing.kind === 'strength')" class="sw-add" @click="startAdd('strength')">+ добавить</button>
          </div>
          <div class="sw-list">
            <div v-for="it in strengths" :key="it.id || it.order_idx" class="sw-item"
                 :class="{ 'sw-item-edit': canEdit }" @click="canEdit && editing?.id !== it.id && startEdit(it)">
              <template v-if="editing && editing.id === it.id">
                <textarea v-model="draft" class="sw-ta" rows="2" :disabled="saving" @click.stop></textarea>
                <div class="sw-acts">
                  <button class="sw-ok" :disabled="saving" @click.stop="save">Сохранить</button>
                  <button class="sw-x" @click.stop="cancel">Отмена</button>
                </div>
              </template>
              <span v-else class="sw-body">{{ it.body }}</span>
            </div>
            <div v-if="editing && editing.id === null && editing.kind === 'strength'" class="sw-item sw-item-new">
              <textarea v-model="draft" class="sw-ta" rows="2" :disabled="saving" placeholder="Новая сильная сторона…" @click.stop></textarea>
              <div class="sw-acts">
                <button class="sw-ok" :disabled="saving" @click.stop="save">Добавить</button>
                <button class="sw-x" @click.stop="cancel">Отмена</button>
              </div>
            </div>
            <div v-if="!strengths.length && !(editing && editing.kind === 'strength' && editing.id === null)" class="sw-empty">Не указаны</div>
          </div>
        </div>

        <!-- Проблемные зоны -->
        <div class="sw-col sw-col-bad">
          <div class="sw-col-h">
            <span class="sw-col-t">Проблемные зоны</span>
            <button v-if="canEdit && !(editing && editing.id === null && editing.kind === 'weakness')" class="sw-add" @click="startAdd('weakness')">+ добавить</button>
          </div>
          <div class="sw-list">
            <div v-for="it in weaknesses" :key="it.id || it.order_idx" class="sw-item"
                 :class="{ 'sw-item-edit': canEdit }" @click="canEdit && editing?.id !== it.id && startEdit(it)">
              <template v-if="editing && editing.id === it.id">
                <textarea v-model="draft" class="sw-ta" rows="2" :disabled="saving" @click.stop></textarea>
                <div class="sw-acts">
                  <button class="sw-ok" :disabled="saving" @click.stop="save">Сохранить</button>
                  <button class="sw-x" @click.stop="cancel">Отмена</button>
                </div>
              </template>
              <span v-else class="sw-body">{{ it.body }}</span>
            </div>
            <div v-if="editing && editing.id === null && editing.kind === 'weakness'" class="sw-item sw-item-new">
              <textarea v-model="draft" class="sw-ta" rows="2" :disabled="saving" placeholder="Новая проблемная зона…" @click.stop></textarea>
              <div class="sw-acts">
                <button class="sw-ok" :disabled="saving" @click.stop="save">Добавить</button>
                <button class="sw-x" @click.stop="cancel">Отмена</button>
              </div>
            </div>
            <div v-if="!weaknesses.length && !(editing && editing.kind === 'weakness' && editing.id === null)" class="sw-empty">Не указаны</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sw-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 760px) { .sw-grid { grid-template-columns: 1fr; } }
.sw-col { background: #fff; border: .5px solid var(--line, #ECEAF4); border-radius: 12px; padding: 14px 16px; border-top: 3px solid var(--c, #94A3B8); }
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
</style>
