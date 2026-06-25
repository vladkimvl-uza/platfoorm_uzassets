<script setup lang="ts">
/**
 * ESGSwotEditor — «Выводы» ESG: сильные/слабые стороны портфеля + редактируемая
 * таблица по компаниям. Inline-правка: клик → textarea → Enter/✓ сохранить,
 * Esc/✕ отмена. Add/edit через PUT /esg/swot (единый upsert, scope portfolio|company).
 * Премиум UX: top-accent, TransitionGroup-анимации, мягкие карточки.
 */
import { computed, nextTick, ref } from "vue";
import { esgApi, type ESGSwotResponse, type ESGSwotItemBrief } from "@/api/esg";
import { useToast } from "@/composables/useToast";

interface CoBrief { company_id: string; company_name: string; sector_color?: string | null }

const props = defineProps<{
  swot: ESGSwotResponse | null;
  companies: CoBrief[];
  canEdit: boolean;
}>();
const emit = defineEmits<{ (e: "saved"): void }>();

const toast = useToast();

// ── деривация из props ────────────────────────────────────────────
const portStrengths = computed(() => props.swot?.portfolio_strengths ?? []);
const portWeaknesses = computed(() => props.swot?.portfolio_weaknesses ?? []);

const byCompany = computed(() => {
  const m = new Map<string, { strengths: ESGSwotItemBrief[]; weaknesses: ESGSwotItemBrief[] }>();
  for (const it of (props.swot?.company_items ?? [])) {
    if (!it.company_id) continue;
    let g = m.get(it.company_id);
    if (!g) { g = { strengths: [], weaknesses: [] }; m.set(it.company_id, g); }
    (it.kind === "strength" ? g.strengths : g.weaknesses).push(it);
  }
  return m;
});
function coItems(cid: string, kind: "strength" | "weakness"): ESGSwotItemBrief[] {
  const g = byCompany.value.get(cid);
  return g ? (kind === "strength" ? g.strengths : g.weaknesses) : [];
}
// компании с выводами — наверх, затем остальные (чтобы заполненные были видны первыми)
const sortedCompanies = computed(() => {
  const withItems = (c: CoBrief) => byCompany.value.has(c.company_id);
  return [...props.companies].sort((a, b) => Number(withItems(b)) - Number(withItems(a)));
});

// ── inline-edit ───────────────────────────────────────────────────
const editKey = ref<string | null>(null);
const draft = ref("");
const saving = ref(false);
const taRef = ref<HTMLTextAreaElement | null>(null);

function keyOf(it: ESGSwotItemBrief): string { return "id:" + (it.id || ""); }
function newKey(scope: string, kind: string, cid: string): string { return `new:${scope}:${kind}:${cid}`; }

async function startEdit(it: ESGSwotItemBrief) {
  if (!props.canEdit) return;
  editKey.value = keyOf(it);
  draft.value = it.body;
  await nextTick(); taRef.value?.focus();
}
async function startAdd(scope: "portfolio" | "company", kind: "strength" | "weakness", cid = "") {
  if (!props.canEdit) return;
  editKey.value = newKey(scope, kind, cid);
  draft.value = "";
  await nextTick(); taRef.value?.focus();
}
function cancelEdit() { editKey.value = null; draft.value = ""; }

async function commit(
  scope: "portfolio" | "company", kind: "strength" | "weakness",
  cid: string, existing: ESGSwotItemBrief | null, listLen: number,
) {
  const body = draft.value.trim();
  if (!body) { cancelEdit(); return; }
  if (saving.value) return;
  saving.value = true;
  try {
    const r = await esgApi.upsertSwot({
      id: existing?.id ?? null, kind, scope,
      company_id: scope === "company" ? cid : null,
      body, order_idx: existing?.order_idx ?? listLen,
    });
    if ((r as { queued?: boolean }).queued) toast.info("Отправлено на согласование");
    else { toast.success("Сохранено"); emit("saved"); }
    cancelEdit();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не сохранено: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally { saving.value = false; }
}
</script>

<template>
  <div class="swe">
    <div class="swe-head">
      <h2 class="swe-title">Выводы</h2>
      <span class="swe-sub">ESG-аналитика портфеля и по компаниям</span>
    </div>

    <!-- Портфельные сильные/слабые стороны -->
    <div class="swe-port">
      <div class="swe-col" v-for="col in [
        { kind: 'strength', label: 'Сильные стороны портфеля', items: portStrengths, accent: '#1D9E75' },
        { kind: 'weakness', label: 'Проблемные зоны портфеля', items: portWeaknesses, accent: '#EF9F27' },
      ]" :key="col.kind">
        <div class="swe-col-h">
          <span class="swe-dot" :style="{ background: col.accent }"></span>{{ col.label }}
          <span class="swe-cnt">{{ col.items.length }}</span>
        </div>
        <TransitionGroup name="swe-list" tag="div" class="swe-items">
          <div v-for="(it, i) in col.items" :key="it.id || ('p'+i)" class="swe-item" :style="{ '--ac': col.accent, '--d': (i*40)+'ms' }">
            <textarea v-if="editKey === keyOf(it)" ref="taRef" v-model="draft" class="swe-ta" rows="2"
                      @keydown.enter.exact.prevent="commit('portfolio', col.kind as any, '', it, col.items.length)"
                      @keydown.esc.prevent="cancelEdit"></textarea>
            <template v-else>
              <span class="swe-marker" :style="{ background: col.accent + '22', color: col.accent }">{{ i + 1 }}</span>
              <p class="swe-body" :class="{ ed: canEdit }" @click="startEdit(it)">{{ it.body }}</p>
            </template>
            <div v-if="editKey === keyOf(it)" class="swe-confirm">
              <button class="swe-ok" :disabled="saving" @click="commit('portfolio', col.kind as any, '', it, col.items.length)">✓</button>
              <button class="swe-no" @click="cancelEdit">✕</button>
            </div>
          </div>
        </TransitionGroup>
        <!-- add -->
        <div v-if="editKey === newKey('portfolio', col.kind, '')" class="swe-item swe-item-new" :style="{ '--ac': col.accent }">
          <textarea ref="taRef" v-model="draft" class="swe-ta" rows="2" placeholder="Новый вывод…"
                    @keydown.enter.exact.prevent="commit('portfolio', col.kind as any, '', null, col.items.length)"
                    @keydown.esc.prevent="cancelEdit"></textarea>
          <div class="swe-confirm">
            <button class="swe-ok" :disabled="saving" @click="commit('portfolio', col.kind as any, '', null, col.items.length)">✓</button>
            <button class="swe-no" @click="cancelEdit">✕</button>
          </div>
        </div>
        <button v-else-if="canEdit" class="swe-add" @click="startAdd('portfolio', col.kind as any)">+ добавить</button>
      </div>
    </div>

    <!-- Редактируемая таблица по компаниям -->
    <div class="swe-co-h">По компаниям</div>
    <div class="swe-table">
      <div class="swe-tr swe-thead">
        <div class="swe-th swe-th-co">Компания</div>
        <div class="swe-th"><span class="swe-dot" style="background:#1D9E75"></span>Сильные стороны</div>
        <div class="swe-th"><span class="swe-dot" style="background:#EF9F27"></span>Проблемные зоны</div>
      </div>
      <div v-for="c in sortedCompanies" :key="c.company_id" class="swe-tr swe-trow"
           :class="{ filled: byCompany.has(c.company_id) }">
        <div class="swe-td swe-td-co">
          <span class="swe-co-dot" :style="{ background: c.sector_color || '#94A3B8' }"></span>{{ c.company_name }}
        </div>
        <div v-for="kind in (['strength','weakness'] as const)" :key="kind" class="swe-td">
          <div class="swe-cell-list">
            <div v-for="(it, i) in coItems(c.company_id, kind)" :key="it.id || (kind+i)" class="swe-citem"
                 :style="{ '--ac': kind === 'strength' ? '#1D9E75' : '#EF9F27' }">
              <textarea v-if="editKey === keyOf(it)" ref="taRef" v-model="draft" class="swe-ta sm" rows="2"
                        @keydown.enter.exact.prevent="commit('company', kind, c.company_id, it, coItems(c.company_id, kind).length)"
                        @keydown.esc.prevent="cancelEdit"></textarea>
              <template v-else>
                <p class="swe-cbody" :class="{ ed: canEdit }" @click="startEdit(it)">{{ it.body }}</p>
              </template>
              <div v-if="editKey === keyOf(it)" class="swe-confirm sm">
                <button class="swe-ok" :disabled="saving" @click="commit('company', kind, c.company_id, it, coItems(c.company_id, kind).length)">✓</button>
                <button class="swe-no" @click="cancelEdit">✕</button>
              </div>
            </div>
            <div v-if="editKey === newKey('company', kind, c.company_id)" class="swe-citem swe-item-new"
                 :style="{ '--ac': kind === 'strength' ? '#1D9E75' : '#EF9F27' }">
              <textarea ref="taRef" v-model="draft" class="swe-ta sm" rows="2" placeholder="Текст…"
                        @keydown.enter.exact.prevent="commit('company', kind, c.company_id, null, coItems(c.company_id, kind).length)"
                        @keydown.esc.prevent="cancelEdit"></textarea>
              <div class="swe-confirm sm">
                <button class="swe-ok" :disabled="saving" @click="commit('company', kind, c.company_id, null, coItems(c.company_id, kind).length)">✓</button>
                <button class="swe-no" @click="cancelEdit">✕</button>
              </div>
            </div>
            <button v-else-if="canEdit" class="swe-add sm" @click="startAdd('company', kind, c.company_id)">+ добавить</button>
            <span v-if="!coItems(c.company_id, kind).length && !canEdit" class="swe-empty">—</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.swe { margin-top: 26px; }
.swe-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 16px; }
.swe-title { font-size: 17px; font-weight: 600; color: var(--t1, #1E2A4A); margin: 0; }
.swe-sub { font-size: 11.5px; color: var(--t3, #94A3B8); }

.swe-port { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; margin-bottom: 28px; }
.swe-col { display: flex; flex-direction: column; gap: 10px; }
.swe-col-h { display: flex; align-items: center; gap: 9px; font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); }
.swe-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.swe-cnt { margin-left: auto; font-size: 11px; font-weight: 700; color: var(--t3, #94A3B8); background: var(--bg2, #F4F3F9); border-radius: 999px; padding: 1px 9px; }
.swe-items { display: flex; flex-direction: column; gap: 9px; }
.swe-item { position: relative; display: flex; gap: 11px; align-items: flex-start; padding: 13px 15px; background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.05); border-radius: 13px; box-shadow: 0 1px 2px rgba(16,24,64,.03); transition: box-shadow .18s, transform .18s; }
.swe-item::before { content: ''; position: absolute; top: 0; left: 15px; right: 15px; height: 2px; border-radius: 0 0 2px 2px; background: linear-gradient(90deg, var(--ac), transparent); }
.swe-item:hover { box-shadow: 0 6px 20px rgba(16,24,64,.07); transform: translateY(-1px); }
.swe-marker { flex-shrink: 0; width: 23px; height: 23px; border-radius: 7px; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
.swe-body { margin: 1px 0 0; font-size: 12.5px; line-height: 1.5; color: var(--t2, #3a4256); flex: 1; }
.swe-body.ed { cursor: text; }
.swe-body.ed:hover { color: var(--t1, #1E2A4A); }

.swe-ta { flex: 1; width: 100%; resize: vertical; min-height: 42px; padding: 7px 10px; border: 1.5px solid #7C6FF7; border-radius: 9px; font-family: inherit; font-size: 12.5px; line-height: 1.45; color: var(--t1, #1E2A4A); outline: none; }
.swe-ta.sm { font-size: 11.5px; min-height: 38px; }
.swe-confirm { display: inline-flex; gap: 4px; flex-shrink: 0; align-self: flex-start; }
.swe-confirm.sm { margin-top: 4px; }
.swe-ok, .swe-no { width: 24px; height: 24px; border-radius: 7px; border: none; cursor: pointer; font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; transition: background .12s, color .12s; }
.swe-ok { background: #DCFCE7; color: #1D9E75; }
.swe-ok:hover:not(:disabled) { background: #16A34A; color: #fff; }
.swe-ok:disabled { opacity: .5; cursor: default; }
.swe-no { background: #F1F5F9; color: #94A3B8; }
.swe-no:hover { background: #E2E8F0; color: #475569; }
.swe-add { align-self: flex-start; font-size: 11.5px; font-weight: 600; color: var(--p-deep, #5B53B8); background: rgba(124,111,247,.08); border: 1px dashed rgba(124,111,247,.4); border-radius: 9px; padding: 6px 12px; cursor: pointer; font-family: inherit; transition: background .14s, border-color .14s; }
.swe-add:hover { background: rgba(124,111,247,.15); border-color: #7C6FF7; }
.swe-add.sm { padding: 4px 10px; font-size: 11px; }
.swe-item-new { border-style: dashed; border-color: rgba(124,111,247,.5); flex-direction: column; }

/* per-company table */
.swe-co-h { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: var(--p-deep, #5B53B8); margin-bottom: 12px; }
.swe-table { border: 1px solid rgba(0,0,0,.06); border-radius: 14px; overflow: hidden; background: var(--bg1, #fff); }
.swe-tr { display: grid; grid-template-columns: 230px 1fr 1fr; }
.swe-thead { background: #F6F5FB; position: sticky; top: 0; }
.swe-th { padding: 10px 14px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--p-deep, #534AB7); display: flex; align-items: center; gap: 7px; }
.swe-trow { border-top: 1px solid #F1F0F7; transition: background .12s; animation: sweRowIn .4s var(--ease-standard, ease) both; }
.swe-trow:hover { background: #FBFAFF; }
.swe-trow.filled .swe-td-co { font-weight: 600; }
@keyframes sweRowIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.swe-td { padding: 10px 14px; border-left: 1px solid #F1F0F7; }
.swe-td-co { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--t1, #1E2A4A); border-left: none; }
.swe-co-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.swe-cell-list { display: flex; flex-direction: column; gap: 6px; }
.swe-citem { position: relative; padding-left: 12px; }
.swe-citem::before { content: ''; position: absolute; left: 0; top: 7px; width: 5px; height: 5px; border-radius: 50%; background: var(--ac); }
.swe-cbody { margin: 0; font-size: 11.5px; line-height: 1.45; color: var(--t2, #3a4256); }
.swe-cbody.ed { cursor: text; }
.swe-cbody.ed:hover { color: var(--t1, #1E2A4A); }
.swe-citem.swe-item-new { padding-left: 0; }
.swe-citem.swe-item-new::before { display: none; }
.swe-empty { color: #CBD2E0; font-size: 12px; }

.swe-list-enter-active, .swe-list-leave-active { transition: opacity .3s, transform .3s; }
.swe-list-enter-from, .swe-list-leave-to { opacity: 0; transform: translateY(-6px); }

@media (max-width: 900px) {
  .swe-port { grid-template-columns: 1fr; }
  .swe-tr { grid-template-columns: 1fr; }
  .swe-td { border-left: none; border-top: 1px dashed #F1F0F7; }
  .swe-td-co { border-top: none; }
}
@media (min-width: 2200px) {
  .swe-title { font-size: 21px; } .swe-body { font-size: 15px; } .swe-cbody { font-size: 14px; }
  .swe-tr { grid-template-columns: 320px 1fr 1fr; } .swe-th { font-size: 13px; } .swe-td-co { font-size: 15px; }
}
</style>
