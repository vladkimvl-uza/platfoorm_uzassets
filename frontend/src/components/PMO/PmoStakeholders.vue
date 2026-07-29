<script setup lang="ts">
/**
 * PmoStakeholders — реестр заинтересованных сторон (PMBOK 7).
 * Сетка власть×интерес (Mendelow) + матрица вовлечённости (current→desired) + реестр.
 */
import { ref, computed, watch, onMounted } from "vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { pmoApi, type Stakeholder, type StakeholderPayload, type Engagement } from "@/api/pmo";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();


const props = defineProps<{ companyCode: string; canEdit?: boolean }>();

const ENG: { v: Engagement; l: string }[] = [
  { v: "unaware", l: i18nKey("Не в курсе") },
  { v: "resistant", l: i18nKey("Сопротивл.") },
  { v: "neutral", l: i18nKey("Нейтрален") },
  { v: "supportive", l: i18nKey("Поддерживает") },
  { v: "leading", l: i18nKey("Ведущий") },
];
const ENG_I: Record<string, number> = Object.fromEntries(ENG.map((e, i) => [e.v, i]));

const loading = ref(true);
const error = ref<string | null>(null);
const items = ref<Stakeholder[]>([]);

async function load() {
  loading.value = true; error.value = null;
  try { items.value = await pmoApi.listStakeholders(props.companyCode); }
  catch (e: any) { error.value = e?.response?.data?.detail || e?.message || t('Не удалось загрузить'); }
  finally { loading.value = false; }
}
onMounted(load);
watch(() => props.companyCode, load);

function quadrant(power: number, interest: number): { l: string; c: string } {
  const hp = power > 3, hi = interest > 3;
  if (hp && hi) return { l: i18nKey("Управлять тесно"), c: "#7C6FF7" };
  if (hp && !hi) return { l: i18nKey("Удовлетворять"), c: "#D97706" };
  if (!hp && hi) return { l: i18nKey("Информировать"), c: "#0891B2" };
  return { l: i18nKey("Мониторить"), c: "#94a3b8" };
}
// Позиция точки на сетке: X = интерес, Y = власть (снизу-вверх)
function dotStyle(s: Stakeholder) {
  return { left: ((s.interest - 1) / 4) * 100 + "%", bottom: ((s.power - 1) / 4) * 100 + "%" };
}
const initials = (n: string) => n.split(/\s+/).map(w => w[0] || "").join("").slice(0, 2).toUpperCase();

// ── Форма ──
const blank = (): StakeholderPayload => ({
  name: "", role: "", organization: "", power: 3, interest: 3,
  engagement_current: "neutral", engagement_desired: "supportive",
  strategy: "", contact: "", notes: "",
});
const form = ref<StakeholderPayload>(blank());
const editingId = ref<string | null>(null);
const formOpen = ref(false);
const saving = ref(false);

function openCreate() { form.value = blank(); editingId.value = null; formOpen.value = true; }
function openEdit(s: Stakeholder) {
  form.value = {
    name: s.name, role: s.role || "", organization: s.organization || "",
    power: s.power, interest: s.interest,
    engagement_current: s.engagement_current, engagement_desired: s.engagement_desired,
    strategy: s.strategy || "", contact: s.contact || "", notes: s.notes || "",
  };
  editingId.value = s.id; formOpen.value = true;
}
async function save() {
  if (!form.value.name?.trim()) { error.value = t('Имя обязательно'); return; }
  saving.value = true; error.value = null;
  try {
    if (editingId.value) await pmoApi.updateStakeholder(editingId.value, form.value);
    else await pmoApi.createStakeholder(props.companyCode, form.value);
    formOpen.value = false;
    await load();
  } catch (e: any) { error.value = e?.response?.data?.detail || t('Не удалось сохранить'); }
  finally { saving.value = false; }
}
async function removeItem(s: Stakeholder) {
  if (!confirm(t("Удалить «{name}»?", { name: s.name }))) return;
  try { await pmoApi.deleteStakeholder(s.id); await load(); }
  catch (e: any) { error.value = e?.response?.data?.detail || t('Не удалось удалить'); }
}
</script>

<template>
  <div class="ps">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />

    <div class="ps-bar">
      <div class="ps-bar-t">{{ t('Заинтересованные стороны') }} <span class="ps-cnt">{{ items.length }}</span></div>
      <button v-if="canEdit" class="ps-add" @click="openCreate">{{ t('+ Стейкхолдер') }}</button>
    </div>

    <UzaStateBlock v-if="loading" state="loading" :text="t('Загрузка реестра…')" />
    <UzaStateBlock
      v-else-if="!items.length"
      state="empty" variant="block"
      :title="t('Стейкхолдеров нет')"
      :text="t('Добавьте заинтересованные стороны — появятся на сетке власть×интерес и в матрице вовлечённости.')"
    />

    <template v-else>
      <div class="ps-cols">
        <!-- Сетка власть × интерес -->
        <div class="ps-grid-card">
          <div class="ps-card-t">{{ t('Власть × Интерес') }}</div>
          <div class="ps-grid">
            <div class="ps-q ps-q-tl"><span>{{ t('Удовлетворять') }}</span></div>
            <div class="ps-q ps-q-tr"><span>{{ t('Управлять тесно') }}</span></div>
            <div class="ps-q ps-q-bl"><span>{{ t('Мониторить') }}</span></div>
            <div class="ps-q ps-q-br"><span>{{ t('Информировать') }}</span></div>
            <div class="ps-axis-y">{{ t('Власть →') }}</div>
            <div class="ps-axis-x">{{ t('Интерес →') }}</div>
            <button
              v-for="s in items"
              :key="'d' + s.id"
              class="ps-dot"
              :style="{ ...dotStyle(s), background: quadrant(s.power, s.interest).c }"
              :title="t('{value0} · власть {value1}/5 · интерес {value2}/5', { value0: s.name, value1: s.power, value2: s.interest })"
              @click="canEdit && openEdit(s)"
            >{{ initials(s.name) }}</button>
          </div>
        </div>

        <!-- Матрица вовлечённости -->
        <div class="ps-eng-card">
          <div class="ps-card-t">{{ t('Вовлечённость:') }} <b>●</b> {{ t('текущая →') }} <b>○</b> {{ t('целевая') }}</div>
          <div class="ps-eng-wrap">
            <table class="ps-eng">
              <thead>
                <tr><th class="ps-eng-name"></th><th v-for="e in ENG" :key="e.v">{{ e.l }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="s in items" :key="'e' + s.id" :class="{ gap: ENG_I[s.engagement_desired] > ENG_I[s.engagement_current] }">
                  <td class="ps-eng-name" :title="s.name">{{ s.name }}</td>
                  <td v-for="e in ENG" :key="e.v" class="ps-eng-c">
                    <span v-if="s.engagement_current === e.v" class="ps-eng-cur"></span>
                    <span v-if="s.engagement_desired === e.v" class="ps-eng-des"></span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Реестр -->
      <div class="ps-table-wrap">
        <table class="uza-table ps-tbl">
          <thead>
            <tr><th>{{ t('Имя') }}</th><th>{{ t('Роль') }}</th><th>{{ t('Организация') }}</th><th style="text-align:center">{{ t('Вл.') }}</th><th style="text-align:center">{{ t('Инт.') }}</th><th>{{ t('Квадрант') }}</th><th>{{ t('Вовлечённость') }}</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="(s, idx) in items" :key="s.id" class="ps-row" :style="{ animationDelay: Math.min(idx * 0.03, 0.4) + 's' }">
              <td><div class="ps-name"><span class="ps-ava" :style="{ background: quadrant(s.power, s.interest).c }">{{ initials(s.name) }}</span>{{ s.name }}</div></td>
              <td>{{ s.role || "—" }}</td>
              <td>{{ s.organization || "—" }}</td>
              <td style="text-align:center" class="is-mono">{{ s.power }}</td>
              <td style="text-align:center" class="is-mono">{{ s.interest }}</td>
              <td><span class="ps-quad" :style="{ color: quadrant(s.power, s.interest).c }">{{ quadrant(s.power, s.interest).l }}</span></td>
              <td><span class="ps-eng-txt">{{ ENG.find(e => e.v === s.engagement_current)?.l }}<span v-if="s.engagement_desired !== s.engagement_current"> → {{ ENG.find(e => e.v === s.engagement_desired)?.l }}</span></span></td>
              <td style="text-align:right">
                <button v-if="canEdit" class="ps-ia" :title="t('Править')" @click="openEdit(s)">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button v-if="canEdit" class="ps-ia ps-ia-del" :title="t('Удалить')" @click="removeItem(s)">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- Модалка -->
    <div v-if="formOpen" class="ps-modal-ov" @click.self="formOpen = false">
      <div class="ps-modal">
        <div class="ps-modal-h">{{ editingId ? t('Правка стейкхолдера') : t('Новый стейкхолдер') }}</div>
        <div class="ps-modal-b">
          <div class="ps-f"><label>{{ t('Имя') }}</label><input v-model="form.name" :placeholder="t('ФИО / название стороны')" /></div>
          <div class="ps-f2">
            <div class="ps-f"><label>{{ t('Роль') }}</label><input v-model="form.role" :placeholder="t('Напр. Спонсор')" /></div>
            <div class="ps-f"><label>{{ t('Организация') }}</label><input v-model="form.organization" /></div>
          </div>
          <div class="ps-f2">
            <div class="ps-f"><label>{{ t('Власть (1–5)') }}</label><input type="number" min="1" max="5" v-model.number="form.power" /></div>
            <div class="ps-f"><label>{{ t('Интерес (1–5)') }}</label><input type="number" min="1" max="5" v-model.number="form.interest" /></div>
          </div>
          <div class="ps-f2">
            <div class="ps-f"><label>{{ t('Вовлечённость сейчас') }}</label>
              <select v-model="form.engagement_current"><option v-for="e in ENG" :key="e.v" :value="e.v">{{ e.l }}</option></select>
            </div>
            <div class="ps-f"><label>{{ t('Цель') }}</label>
              <select v-model="form.engagement_desired"><option v-for="e in ENG" :key="e.v" :value="e.v">{{ e.l }}</option></select>
            </div>
          </div>
          <div class="ps-f"><label>{{ t('Контакт') }}</label><input v-model="form.contact" :placeholder="t('email / телефон')" /></div>
          <div class="ps-f"><label>{{ t('Стратегия вовлечения') }}</label><textarea v-model="form.strategy" rows="2"></textarea></div>
        </div>
        <div class="ps-modal-f">
          <button class="ps-btn-ghost" @click="formOpen = false">{{ t('Отмена') }}</button>
          <button class="ps-btn" :disabled="saving" @click="save">{{ saving ? t('Сохраняю…') : t('Сохранить') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ps { padding: 4px 2px 24px; }
.ps-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.ps-bar-t { font-size: var(--fs-md, 13px); font-weight: 600; color: var(--t1, #1e2a4a); }
.ps-cnt { display: inline-block; min-width: 18px; text-align: center; padding: 1px 6px; border-radius: 8px; background: rgba(124,111,247,.12); color: var(--p-deep, #534ab7); font-size: var(--fs-2xs, 9px); font-weight: 700; margin-left: 4px; }
.ps-add { margin-left: auto; padding: 7px 14px; border-radius: 9px; border: 1px solid var(--p, #7c6ff7); background: var(--p, #7c6ff7); color: #fff; font-size: var(--fs-sm, 11.5px); font-weight: 500; cursor: pointer; font-family: inherit; }

.ps-cols { display: grid; grid-template-columns: minmax(0, 360px) 1fr; gap: 18px; align-items: start; margin-bottom: 14px; }
/* ≤14″: сетка власть×интерес встаёт над матрицей вовлечённости */
@media (max-width: 1200px) { .ps-cols { grid-template-columns: 1fr; } .ps-grid-card { max-width: 460px; } }

.ps-grid-card, .ps-eng-card { border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: var(--r, 10px); padding: 12px; background: var(--bg1, #fff); animation: psIn .45s var(--ease-out) both; }
.ps-card-t { font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94a3b8); font-weight: 600; margin-bottom: 10px; }
.ps-card-t b { color: var(--p, #7c6ff7); }

/* Сетка власть×интерес */
.ps-grid { position: relative; width: 100%; aspect-ratio: 1 / 1; display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 2px; }
.ps-q { position: relative; display: flex; align-items: flex-start; justify-content: center; padding-top: 6px; border-radius: 6px; }
.ps-q span { font-size: var(--fs-2xs, 9px); font-weight: 600; color: var(--t3, #94a3b8); text-align: center; }
.ps-q-tl { background: rgba(217,119,6,.06); }
.ps-q-tr { background: rgba(124,111,247,.08); }
.ps-q-bl { background: rgba(148,163,184,.06); }
.ps-q-br { background: rgba(8,145,178,.06); }
.ps-axis-y { position: absolute; left: -2px; top: 50%; transform: rotate(-90deg) translateX(50%); transform-origin: left; font-size: 8px; color: var(--t3, #94a3b8); pointer-events: none; }
.ps-axis-x { position: absolute; bottom: -14px; left: 50%; transform: translateX(-50%); font-size: 8px; color: var(--t3, #94a3b8); pointer-events: none; }
.ps-dot {
  position: absolute; transform: translate(-50%, 50%); width: 26px; height: 26px; border-radius: 50%;
  color: #fff; font-size: 9px; font-weight: 700; border: 2px solid #fff; cursor: pointer;
  box-shadow: 0 2px 6px rgba(15,23,60,.22); transition: transform .14s var(--ease-standard), box-shadow .14s; z-index: 2;
  display: flex; align-items: center; justify-content: center; padding: 0;
  animation: psDotIn .45s var(--ease-bounce) both;
}
.ps-dot:hover { transform: translate(-50%, 50%) scale(1.18); box-shadow: 0 5px 14px rgba(15,23,60,.32); z-index: 3; }
@keyframes psDotIn { from { opacity: 0; transform: translate(-50%, 50%) scale(.3); } to { opacity: 1; transform: translate(-50%, 50%) scale(1); } }

/* Матрица вовлечённости */
.ps-eng-wrap { overflow-x: auto; }
.ps-eng { width: 100%; border-collapse: collapse; }
.ps-eng th { font-size: var(--fs-2xs, 9px); color: var(--t3, #94a3b8); font-weight: 600; padding: 4px 6px; text-align: center; white-space: nowrap; border-bottom: 1px solid var(--border, rgba(99,102,180,.1)); }
.ps-eng-name { text-align: left !important; max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ps-eng td.ps-eng-name { font-size: var(--fs-sm, 11px); color: var(--t1, #1e2a4a); padding: 6px; }
.ps-eng-c { position: relative; height: 28px; text-align: center; border-bottom: 1px solid rgba(99,102,180,.05); }
.ps-eng tr.gap td { background: rgba(217,119,6,.04); }
.ps-eng-cur { display: inline-block; width: 11px; height: 11px; border-radius: 50%; background: var(--p, #7c6ff7); vertical-align: middle; }
.ps-eng-des { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 16px; height: 16px; border-radius: 50%; border: 2px solid #1D9E75; }

/* Реестр */
.ps-table-wrap { overflow-x: auto; }
.ps-tbl { font-size: var(--fs-sm, 11.5px); min-width: 720px; }
.ps-row { animation: psRowIn .4s var(--ease-out) both; }
.ps-row:hover { background: rgba(124,111,247,.04); }
.ps-name { display: flex; align-items: center; gap: 8px; font-weight: 500; color: var(--t1, #1e2a4a); }
.ps-ava { width: 22px; height: 22px; border-radius: 50%; color: #fff; font-size: 8.5px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
.ps-quad, .ps-eng-txt { font-weight: 500; white-space: nowrap; }
.ps-eng-txt { color: var(--t2, #475569); font-size: var(--fs-xs, 10.5px); }
.ps-ia { background: none; border: none; cursor: pointer; color: var(--t3, #94a3b8); padding: 4px; border-radius: 6px; }
.ps-ia:hover { background: rgba(124,111,247,.08); color: var(--p-deep, #534ab7); }
.ps-ia-del:hover { background: rgba(226,75,74,.08); color: #E24B4A; }

@keyframes psIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes psRowIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

/* Модалка */
.ps-modal-ov { position: fixed; inset: 0; z-index: var(--z-modal, 9100); background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(7px); backdrop-filter: blur(7px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.ps-modal { background: var(--bg1, #fff); border-radius: 14px; width: min(540px, 96vw); max-height: 92dvh; overflow: hidden; display: flex; flex-direction: column; box-shadow: var(--shl); animation: psModalIn .34s var(--ease-standard) both; }
@keyframes psModalIn { from { opacity: 0; transform: scale(.96) translateY(12px); } to { opacity: 1; transform: scale(1) translateY(0); } }
.ps-modal-h { padding: 14px 18px; font-size: var(--fs-md, 13px); font-weight: 600; color: var(--t1, #1e2a4a); border-bottom: 1px solid var(--border, rgba(99,102,180,.12)); }
.ps-modal-b { padding: 14px 18px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.ps-f { display: flex; flex-direction: column; gap: 4px; }
.ps-f2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ps-f label { font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); font-weight: 600; }
.ps-f input, .ps-f select, .ps-f textarea { padding: 7px 10px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 8px; font-size: var(--fs-base, 12px); font-family: inherit; outline: none; background: var(--bg1, #fff); color: var(--t1, #1e2a4a); }
.ps-f textarea { resize: vertical; }
.ps-modal-f { padding: 12px 18px; border-top: 1px solid var(--border, rgba(99,102,180,.12)); display: flex; justify-content: flex-end; gap: 8px; background: var(--bg2, #fafafc); }
.ps-btn { padding: 8px 16px; border-radius: 9px; border: 1px solid var(--p, #7c6ff7); background: var(--p, #7c6ff7); color: #fff; font-size: var(--fs-sm, 11.5px); font-weight: 500; cursor: pointer; font-family: inherit; }
.ps-btn:disabled { opacity: .5; }
.ps-btn-ghost { padding: 8px 16px; border-radius: 9px; border: 1px solid var(--border, rgba(99,102,180,.18)); background: transparent; color: var(--t2, #475569); font-size: var(--fs-sm, 11.5px); cursor: pointer; font-family: inherit; }

@media (max-width: 560px) { .ps-f2 { grid-template-columns: 1fr; } }
</style>
