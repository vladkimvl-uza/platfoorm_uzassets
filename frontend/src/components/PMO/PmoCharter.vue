<script setup lang="ts">
/**
 * PmoCharter — Устав проекта (PMBOK 7, формальная инициация).
 *
 * Слева — сетка проектов (+ «Программа/портфель»), у каждого статус устава.
 * Клик → документ-вид устава с разделами; правка через секционную модалку;
 * утверждение штампует кто/когда.
 */
import { ref, computed, watch, onMounted } from "vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import NoteAssigneePicker from "@/components/NoteAssigneePicker.vue";
import { useToast } from "@/composables/useToast";
import { pmoApi, type Charter, type CharterPayload } from "@/api/pmo";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();
const { confirmDialog } = useConfirm();


const props = defineProps<{
  companyCode: string;
  canEdit?: boolean;
  projects?: { id: string; title: string }[];
}>();

const toast = useToast();

const loading = ref(true);
const error = ref<string | null>(null);
const saving = ref(false);
const charters = ref<Charter[]>([]);
const selectedId = ref<string | null>(null);

async function load() {
  loading.value = true; error.value = null;
  try {
    charters.value = await pmoApi.listCharters(props.companyCode);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || t('Не удалось загрузить уставы');
  } finally { loading.value = false; }
}
onMounted(load);
watch(() => props.companyCode, () => { selectedId.value = null; load(); });

// карта project_id → charter
const byProject = computed(() => {
  const m = new Map<string, Charter>();
  for (const c of charters.value) if (c.project_id) m.set(c.project_id, c);
  return m;
});
const programCharter = computed(() => charters.value.find(c => !c.project_id) || null);

// Список «плиток»: программа + проекты
interface Tile { key: string; projectId: string | null; title: string; charter: Charter | null; }
const tiles = computed<Tile[]>(() => {
  const out: Tile[] = [
    { key: "__program__", projectId: null, title: i18nKey("Программа / портфель"), charter: programCharter.value },
  ];
  for (const p of (props.projects || [])) {
    out.push({ key: p.id, projectId: p.id, title: p.title, charter: byProject.value.get(p.id) || null });
  }
  return out;
});

const selected = computed<Charter | null>(() =>
  selectedId.value ? charters.value.find(c => c.id === selectedId.value) || null : null,
);

const stats = computed(() => {
  const total = charters.value.length;
  const approved = charters.value.filter(c => c.status === "approved").length;
  return { total, approved, draft: total - approved };
});

// ── Форма ──
const blank = (): CharterPayload & { project_id: string | null; project_title: string | null } => ({
  project_id: null, project_title: null,
  purpose: "", objectives: "", scope_in: "", scope_out: "",
  success_criteria: "", deliverables: "", milestones: "",
  assumptions: "", constraints: "",
  sponsor_name: "", manager_name: "",
  budget_amount: null, start_date: null, target_end_date: null,
});
const form = ref(blank());
const editId = ref<string | null>(null);
const modalOpen = ref(false);
// Dirty-guard: устав — девять текстовых разделов, закрытие «мимо» теряло всё.
// Снимок делаем в момент открытия, сравниваем перед закрытием.
const formSnapshot = ref<string>("");
// Что подставлено из данных проекта и откуда — показываем пользователю,
// иначе предзаполнение выглядит как выдуманный текст.
const prefilled = ref<{ field: string; source: string }[]>([]);
const prefillBusy = ref(false);
const FIELD_RU: Record<string, string> = {
  manager_name: "Руководитель", sponsor_name: "Спонсор", budget_amount: "Бюджет",
  start_date: "Старт", target_end_date: "Завершение", purpose: "Обоснование",
  milestones: "Вехи", deliverables: "Ключевые результаты", scope_in: "В границах",
};
const isDirty = computed(() => JSON.stringify(form.value) !== formSnapshot.value);
async function closeModal() {
  if (isDirty.value) {
    const ok = await confirmDialog({
      title: t("Закрыть без сохранения?"),
      message: t("В уставе есть несохранённые изменения — они будут потеряны."),
      danger: true,
    });
    if (!ok) return;
  }
  modalOpen.value = false;
}
// id-пикеров спонсора/РП (хранится только имя на бэке — id для работы пикера)
const sponsorId = ref<string | null>(null);
const managerId = ref<string | null>(null);

/** Подставить в ПУСТЫЕ поля формы данные проекта (правку не трогаем). */
async function applyPrefill(projectId: string | null) {
  prefilled.value = [];
  if (!projectId) return;
  prefillBusy.value = true;
  try {
    const res = await pmoApi.charterPrefill(props.companyCode, projectId);
    const f: any = res?.fields || {};
    const src: any = res?.sources || {};
    for (const key of Object.keys(f)) {
      const cur = (form.value as any)[key];
      const isEmpty = cur === null || cur === undefined || cur === "";
      if (!isEmpty) continue;               // введённое пользователем не трогаем
      (form.value as any)[key] = f[key];
      prefilled.value.push({ field: FIELD_RU[key] || key, source: src[key] || "" });
    }
    formSnapshot.value = JSON.stringify(form.value);   // предзаполнение — не «грязь»
  } catch {
    /* предзаполнение необязательно: молча оставляем пустую форму */
  } finally {
    prefillBusy.value = false;
  }
}

function openCreate(tile: Tile) {
  form.value = blank();
  form.value.project_id = tile.projectId;
  form.value.project_title = tile.projectId ? tile.title : null;
  sponsorId.value = null; managerId.value = null;
  editId.value = null;
  formSnapshot.value = JSON.stringify(form.value);
  modalOpen.value = true;
  void applyPrefill(tile.projectId);
}
function openEdit(c: Charter) {
  form.value = {
    project_id: c.project_id, project_title: c.project_title,
    purpose: c.purpose || "", objectives: c.objectives || "",
    scope_in: c.scope_in || "", scope_out: c.scope_out || "",
    success_criteria: c.success_criteria || "", deliverables: c.deliverables || "",
    milestones: c.milestones || "", assumptions: c.assumptions || "", constraints: c.constraints || "",
    sponsor_name: c.sponsor_name || "", manager_name: c.manager_name || "",
    budget_amount: c.budget_amount, start_date: c.start_date, target_end_date: c.target_end_date,
  };
  sponsorId.value = c.sponsor_name ? "x" : null;
  managerId.value = c.manager_name ? "x" : null;
  editId.value = c.id;
  prefilled.value = [];
  formSnapshot.value = JSON.stringify(form.value);
  modalOpen.value = true;
}

async function save() {
  saving.value = true; error.value = null;
  try {
    const payload: CharterPayload = { ...form.value };
    let saved: Charter;
    if (editId.value) saved = await pmoApi.updateCharter(editId.value, payload);
    else saved = await pmoApi.createCharter(props.companyCode, payload);
    formSnapshot.value = JSON.stringify(form.value);
    modalOpen.value = false;
    await load();
    selectedId.value = saved.id;
    toast.success(editId.value ? t('Устав сохранён') : t('Устав создан'));
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось сохранить устав');
    toast.error(t('Не удалось сохранить устав'));
  } finally { saving.value = false; }
}

async function toggleApprove(c: Charter) {
  saving.value = true;
  try {
    const next = c.status === "approved" ? "draft" : "approved";
    await pmoApi.updateCharter(c.id, { status: next });
    await load();
    toast.success(next === "approved" ? t('Устав утверждён') : t('Возвращён в черновик'));
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t('Не удалось изменить статус'));
  } finally { saving.value = false; }
}

async function remove(c: Charter) {
  const ok = await confirmDialog({
    title: t("Удалить устав?"),
    message: t("«{title}» будет удалён безвозвратно.", { title: c.project_title || t("Программа") }),
    danger: true,
  });
  if (!ok) return;
  try {
    await pmoApi.deleteCharter(c.id);
    if (selectedId.value === c.id) selectedId.value = null;
    await load();
    toast.success(t('Устав удалён'));
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t('Не удалось удалить'));
  }
}

const fmtDate = (s: string | null) => s
  ? new Date(s).toLocaleDateString(getCurrentIntlLocale(), { day: "numeric", month: "short", year: "numeric" })
  : "—";
const fmtMoney = (n: number | null) => n == null ? "—" : new Intl.NumberFormat(getCurrentIntlLocale()).format(n);

// Разделы документа для рендера
const DOC_SECTIONS: { key: keyof Charter; label: string }[] = [
  { key: "purpose", label: i18nKey("Обоснование и назначение") },
  { key: "objectives", label: i18nKey("Цели проекта") },
  { key: "scope_in", label: i18nKey("В границах (scope in)") },
  { key: "scope_out", label: i18nKey("Вне границ (scope out)") },
  { key: "success_criteria", label: i18nKey("Критерии успеха") },
  { key: "deliverables", label: i18nKey("Ключевые результаты") },
  { key: "milestones", label: i18nKey("Вехи") },
  { key: "assumptions", label: i18nKey("Допущения") },
  { key: "constraints", label: i18nKey("Ограничения") },
];
function secVal(c: Charter, k: keyof Charter): string {
  return (c[k] as string) || "";
}
</script>

<template>
  <div class="pc">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />

    <!-- header strip -->
    <div class="pc-head">
      <div class="pc-stats">
        <div class="pc-stat"><span class="pc-stat-n">{{ stats.total }}</span><span class="pc-stat-l">{{ t('всего') }}</span></div>
        <div class="pc-stat pc-stat-ok"><span class="pc-stat-n">{{ stats.approved }}</span><span class="pc-stat-l">{{ t('утверждено') }}</span></div>
        <div class="pc-stat pc-stat-draft"><span class="pc-stat-n">{{ stats.draft }}</span><span class="pc-stat-l">{{ t('черновик') }}</span></div>
      </div>
    </div>

    <UzaStateBlock v-if="loading" state="loading" :text="t('Загрузка уставов…')" />

    <template v-else>
      <div class="pc-grid">
        <!-- tiles -->
        <div class="pc-tiles">
          <button
            v-for="(tile, i) in tiles"
            :key="tile.key"
            class="pc-tile"
            :class="{ 'pc-tile-on': tile.charter && selectedId === tile.charter.id, 'pc-tile-empty': !tile.charter, 'pc-tile-program': tile.projectId === null }"
            :style="{ animationDelay: Math.min(i * 0.03, 0.4) + 's' }"
            @click="tile.charter ? (selectedId = tile.charter.id) : (canEdit && openCreate(tile))"
          >
            <div class="pc-tile-top">
              <span class="pc-tile-title">{{ tile.title }}</span>
              <span
                v-if="tile.charter"
                class="pc-badge"
                :class="tile.charter.status === 'approved' ? 'pc-badge-ok' : 'pc-badge-draft'"
              >{{ tile.charter.status === "approved" ? t('Утверждён') : t('Черновик') }}</span>
              <span v-else class="pc-badge pc-badge-none">{{ t('Нет устава') }}</span>
            </div>
            <div v-if="tile.charter" class="pc-tile-meta">
              <span v-if="tile.charter.manager_name" class="pc-tile-m">{{ t('РП:') }} {{ tile.charter.manager_name }}</span>
              <span v-if="tile.charter.budget_amount != null" class="pc-tile-m">{{ fmtMoney(tile.charter.budget_amount) }}</span>
            </div>
            <div v-else-if="canEdit" class="pc-tile-cta">{{ t('+ Создать устав') }}</div>
            <div v-else class="pc-tile-cta pc-tile-cta-muted">—</div>
          </button>
        </div>

        <!-- document -->
        <div class="pc-doc-wrap">
          <UzaStateBlock
            v-if="!selected"
            state="empty"
            variant="block"
            :title="t('Выберите устав')"
            :text="t('Слева — проекты портфеля. Откройте существующий устав или создайте новый для формальной инициации проекта.')"
          />
          <div v-else class="pc-doc" :key="selected.id">
            <div class="pc-doc-head">
              <div>
                <div class="pc-doc-eyebrow">{{ t('Устав проекта') }}</div>
                <div class="pc-doc-title">{{ selected.project_title || t('Программа / портфель') }}</div>
              </div>
              <span
                class="pc-badge pc-badge-lg"
                :class="selected.status === 'approved' ? 'pc-badge-ok' : 'pc-badge-draft'"
              >{{ selected.status === "approved" ? t('Утверждён') : t('Черновик') }}</span>
            </div>

            <!-- key facts -->
            <div class="pc-facts">
              <div class="pc-fact"><span class="pc-fact-l">{{ t('Спонсор') }}</span><span class="pc-fact-v">{{ selected.sponsor_name || "—" }}</span></div>
              <div class="pc-fact"><span class="pc-fact-l">{{ t('Руководитель') }}</span><span class="pc-fact-v">{{ selected.manager_name || "—" }}</span></div>
              <div class="pc-fact"><span class="pc-fact-l">{{ t('Бюджет') }}</span><span class="pc-fact-v">{{ fmtMoney(selected.budget_amount) }}</span></div>
              <div class="pc-fact"><span class="pc-fact-l">{{ t('Старт') }}</span><span class="pc-fact-v">{{ fmtDate(selected.start_date) }}</span></div>
              <div class="pc-fact"><span class="pc-fact-l">{{ t('Завершение') }}</span><span class="pc-fact-v">{{ fmtDate(selected.target_end_date) }}</span></div>
            </div>

            <!-- sections -->
            <div class="pc-sections">
              <div v-for="s in DOC_SECTIONS" :key="s.key" class="pc-sec" :class="{ 'pc-sec-empty': !secVal(selected, s.key) }">
                <div class="pc-sec-l">{{ t(s.label) }}</div>
                <div class="pc-sec-v">{{ secVal(selected, s.key) || t('— не заполнено —') }}</div>
              </div>
            </div>

            <div v-if="selected.status === 'approved' && selected.approved_by" class="pc-approved">
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M3 8.5 L6.5 12 L13 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg>
              {{ t('Утверждён:') }} {{ selected.approved_by }}<template v-if="selected.approved_at"> · {{ fmtDate(selected.approved_at) }}</template>
            </div>

            <!-- actions -->
            <div v-if="canEdit" class="pc-actions">
              <button class="pc-btn pc-btn-ghost" @click="openEdit(selected)">{{ t('Редактировать') }}</button>
              <button
                class="pc-btn"
                :class="selected.status === 'approved' ? 'pc-btn-ghost' : 'pc-btn-ok'"
                :disabled="saving"
                @click="toggleApprove(selected)"
              >{{ selected.status === "approved" ? t('Вернуть в черновик') : t('Утвердить') }}</button>
              <button class="pc-btn pc-btn-del" @click="remove(selected)">{{ t('Удалить') }}</button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- edit modal -->
    <Transition name="pc-modal">
      <div v-if="modalOpen" class="pc-ov" @click.self="closeModal">
        <div class="pc-modal">
          <div class="pc-mh">
            {{ editId ? t('Правка устава') : t('Новый устав') }}
            <span v-if="form.project_title" class="pc-mh-proj">· {{ form.project_title }}</span>
          </div>
          <div class="pc-mb">
            <!-- Что подставлено автоматически и откуда: пользователь должен
                 понимать, что это черновик из данных проекта, а не готовый текст. -->
            <div v-if="prefillBusy" class="pc-prefill pc-prefill-busy">{{ t('Подставляю данные проекта…') }}</div>
            <div v-else-if="prefilled.length" class="pc-prefill">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z"/>
              </svg>
              <span>{{ t('Заполнено из проекта — проверьте и поправьте:') }}</span>
              <span v-for="(pf, i) in prefilled" :key="i" class="pc-prefill-chip" :title="pf.source">
                {{ t(pf.field) }}
              </span>
            </div>
            <div class="pc-row3">
              <div class="pc-f"><label>{{ t('Спонсор') }}</label>
                <NoteAssigneePicker :id="sponsorId" :name="form.sponsor_name || null" :placeholder="t('Спонсор')"
                  :company-code="companyCode" allow-custom
                  @update:id="sponsorId = $event" @update:name="form.sponsor_name = $event || ''" />
              </div>
              <div class="pc-f"><label>{{ t('Руководитель') }}</label>
                <NoteAssigneePicker :id="managerId" :name="form.manager_name || null" :placeholder="t('РП')"
                  :company-code="companyCode" allow-custom
                  @update:id="managerId = $event" @update:name="form.manager_name = $event || ''" />
              </div>
            </div>
            <div class="pc-row3">
              <div class="pc-f"><label>{{ t('Бюджет') }}</label><input v-model.number="form.budget_amount" type="number" min="0" placeholder="0" /></div>
              <div class="pc-f"><label>{{ t('Старт') }}</label><input v-model="form.start_date" type="date" /></div>
              <div class="pc-f"><label>{{ t('Завершение') }}</label><input v-model="form.target_end_date" type="date" /></div>
            </div>
            <div class="pc-f"><label>{{ t('Обоснование и назначение') }}</label><textarea v-model="form.purpose" rows="2" :placeholder="t('Зачем проект, какую проблему решает')"></textarea></div>
            <div class="pc-f"><label>{{ t('Цели проекта') }}</label><textarea v-model="form.objectives" rows="2" :placeholder="t('Измеримые цели')"></textarea></div>
            <div class="pc-row2">
              <div class="pc-f"><label>{{ t('В границах') }}</label><textarea v-model="form.scope_in" rows="2"></textarea></div>
              <div class="pc-f"><label>{{ t('Вне границ') }}</label><textarea v-model="form.scope_out" rows="2"></textarea></div>
            </div>
            <div class="pc-f"><label>{{ t('Критерии успеха') }}</label><textarea v-model="form.success_criteria" rows="2"></textarea></div>
            <div class="pc-f"><label>{{ t('Ключевые результаты') }}</label><textarea v-model="form.deliverables" rows="2"></textarea></div>
            <div class="pc-f"><label>{{ t('Вехи') }}</label><textarea v-model="form.milestones" rows="2"></textarea></div>
            <div class="pc-row2">
              <div class="pc-f"><label>{{ t('Допущения') }}</label><textarea v-model="form.assumptions" rows="2"></textarea></div>
              <div class="pc-f"><label>{{ t('Ограничения') }}</label><textarea v-model="form.constraints" rows="2"></textarea></div>
            </div>
          </div>
          <div class="pc-mf">
            <button class="pc-btn pc-btn-ghost" @click="closeModal">{{ t('Отмена') }}</button>
            <button class="pc-btn pc-btn-primary" :disabled="saving" @click="save">{{ saving ? t('Сохраняю…') : t('Сохранить') }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.pc { padding: 4px 2px 24px; }

.pc-head { margin-bottom: 14px; }
.pc-stats { display: inline-flex; gap: 8px; }
.pc-stat {
  display: inline-flex; flex-direction: column; align-items: center;
  min-width: 78px; padding: 7px 12px;
  border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 11px;
  background: var(--bg1, #fff);
}
.pc-stat-n { font-size: 18px; font-weight: 400; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.pc-stat-l { font-size: 9px; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94a3b8); margin-top: 1px; }
/* Акцент — верхняя полоса по канону (::before), не border-top. */
.pc-stat-ok, .pc-stat-draft { position: relative; overflow: hidden; }
.pc-stat-ok::before, .pc-stat-draft::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px; border-radius: inherit; border-bottom-left-radius: 0; border-bottom-right-radius: 0; pointer-events: none; }
.pc-stat-ok::before { background: #1d9e75; }
.pc-stat-draft::before { background: #d97706; }

.pc-grid { display: grid; grid-template-columns: 300px 1fr; gap: 16px; align-items: start; }

/* tiles */
.pc-tiles { display: flex; flex-direction: column; gap: 8px; }
.pc-tile {
  text-align: left; width: 100%;
  padding: 11px 13px;
  border: 1px solid var(--border, rgba(99,102,180,.14)); border-radius: 12px;
  background: var(--bg1, #fff); cursor: pointer; font-family: inherit;
  transition: all .2s var(--ease-standard, cubic-bezier(.4,0,.2,1));
  animation: pcIn .4s var(--ease-out, cubic-bezier(.16,1,.3,1)) both;
}
.pc-tile:hover { border-color: rgba(127,119,221,.5); transform: translateY(-1px); box-shadow: 0 6px 16px rgba(15,23,60,.07); }
.pc-tile-on { border-color: #7f77dd; background: rgba(127,119,221,.05); box-shadow: 0 4px 14px rgba(127,119,221,.14); }
.pc-tile-program { background: linear-gradient(135deg, rgba(127,119,221,.06), rgba(127,119,221,.02)); }
.pc-tile-empty { border-style: dashed; }
.pc-tile-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.pc-tile-title { font-size: 12.5px; font-weight: 500; color: var(--t1, #1e2a4a); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pc-tile-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
.pc-tile-m { font-size: 10px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; }
.pc-tile-cta { margin-top: 6px; font-size: 11px; font-weight: 600; color: var(--p, #7f77dd); }
.pc-tile-cta-muted { color: var(--t3, #94a3b8); font-weight: 400; }

.pc-badge { font-size: 9px; font-weight: 700; padding: 2px 7px; border-radius: 6px; white-space: nowrap; flex-shrink: 0; }
.pc-badge-ok { color: #1d9e75; background: rgba(29,158,117,.12); }
.pc-badge-draft { color: #d97706; background: rgba(217,119,6,.12); }
.pc-badge-none { color: var(--t3, #94a3b8); background: rgba(99,102,180,.08); }
.pc-badge-lg { font-size: 10.5px; padding: 4px 11px; border-radius: 8px; }

/* document */
.pc-doc-wrap { min-width: 0; }
.pc-doc {
  border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 14px;
  background: var(--bg1, #fff); padding: 20px 22px;
  animation: pcDocIn .4s var(--ease-out, cubic-bezier(.16,1,.3,1)) both;
}
.pc-doc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding-bottom: 14px; border-bottom: 1px solid var(--border, rgba(99,102,180,.1)); }
.pc-doc-eyebrow { font-size: 9.5px; text-transform: uppercase; letter-spacing: .08em; color: var(--p, #7f77dd); font-weight: 700; }
.pc-doc-title { font-size: 17px; font-weight: 500; color: var(--t1, #1e2a4a); margin-top: 3px; }

.pc-facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; margin: 16px 0; }
.pc-fact { display: flex; flex-direction: column; gap: 2px; padding: 9px 11px; background: var(--bg2, #fafafc); border-radius: 9px; }
.pc-fact-l { font-size: 9px; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); font-weight: 600; }
.pc-fact-v { font-size: 12.5px; font-weight: 500; color: var(--t1, #1e2a4a); }

.pc-sections { display: flex; flex-direction: column; gap: 14px; }
.pc-sec { animation: pcSecIn .4s var(--ease-out) both; }
.pc-sec-l { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--p-deep, #6b62cc); font-weight: 700; margin-bottom: 4px; }
.pc-sec-v { font-size: 12.5px; line-height: 1.55; color: var(--t1, #1e2a4a); white-space: pre-wrap; }
.pc-sec-empty .pc-sec-v { color: var(--t3, #94a3b8); font-style: italic; }

.pc-approved {
  display: inline-flex; align-items: center; gap: 7px;
  margin-top: 16px; padding: 8px 13px; border-radius: 10px;
  background: rgba(29,158,117,.1); color: #1d9e75; font-size: 11.5px; font-weight: 600;
}

.pc-actions { display: flex; gap: 8px; margin-top: 18px; flex-wrap: wrap; }
.pc-btn { padding: 8px 15px; border-radius: 9px; font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; border: 1px solid transparent; transition: all .16s; }
.pc-btn-primary, .pc-btn-ok { background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; box-shadow: 0 2px 8px rgba(127,119,221,.28); }
.pc-btn-ok { background: linear-gradient(135deg, #1d9e75, #17916a); box-shadow: 0 2px 8px rgba(29,158,117,.25); }
.pc-btn-primary:hover:not(:disabled), .pc-btn-ok:hover:not(:disabled) { transform: translateY(-1px); }
.pc-btn-primary:disabled, .pc-btn-ok:disabled { opacity: .55; cursor: default; }
.pc-btn-ghost { background: var(--bg1, #fff); border-color: var(--border, rgba(99,102,180,.2)); color: var(--t2, #475569); }
.pc-btn-ghost:hover { border-color: #7f77dd; color: #7f77dd; }
.pc-btn-del { background: transparent; color: var(--t3, #94a3b8); border-color: transparent; }
.pc-btn-del:hover { background: rgba(226,75,74,.1); color: #e24b4a; }

/* modal */
.pc-ov { position: fixed; inset: 0; z-index: var(--z-modal, 9100); background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(7px); backdrop-filter: blur(7px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.pc-prefill {
  display: flex; align-items: center; gap: 7px; flex-wrap: wrap;
  font-size: 11.5px; color: var(--p-deep, #534AB7);
  background: rgba(124,111,247,.08); border: 1px solid rgba(124,111,247,.18);
  border-radius: 10px; padding: 8px 11px; margin-bottom: 14px;
}
.pc-prefill-busy { color: var(--t3, #94A3B8); background: var(--bg2, #F8F9FC); border-color: var(--border, #EEF0F5); }
.pc-prefill-chip {
  font-size: 10.5px; font-weight: 600; background: #fff; border-radius: 6px;
  padding: 2px 8px; border: 1px solid rgba(124,111,247,.22);
}
.pc-modal { background: var(--bg1, #fff); border-radius: 16px; width: min(680px, 96vw); max-height: 92dvh; overflow: hidden; display: flex; flex-direction: column; box-shadow: var(--shl, 0 24px 64px rgba(15,23,60,.22)); }
.pc-mh { padding: 15px 20px; font-size: 13.5px; font-weight: 600; color: var(--t1, #1e2a4a); border-bottom: 1px solid var(--border, rgba(99,102,180,.12)); }
.pc-mh-proj { font-weight: 400; color: var(--t3, #94a3b8); }
.pc-mb { padding: 16px 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 11px; }
.pc-f { display: flex; flex-direction: column; gap: 5px; }
.pc-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 11px; }
.pc-row3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 11px; }
.pc-f label { font-size: 9px; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); font-weight: 600; }
.pc-f input, .pc-f textarea { padding: 8px 11px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 8px; font-size: 12.5px; font-family: inherit; outline: none; background: var(--bg1, #fff); color: var(--t1, #1e2a4a); transition: border-color .15s; }
.pc-f input:focus, .pc-f textarea:focus { border-color: #7f77dd; }
.pc-f textarea { resize: vertical; line-height: 1.45; }
.pc-mf { padding: 13px 20px; border-top: 1px solid var(--border, rgba(99,102,180,.12)); display: flex; justify-content: flex-end; gap: 8px; background: var(--bg2, #fafafc); }

/* animations */
@keyframes pcIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes pcDocIn { from { opacity: 0; transform: translateY(10px) scale(.99); } to { opacity: 1; transform: none; } }
@keyframes pcSecIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: none; } }
.pc-modal-enter-active { transition: opacity .2s ease; }
.pc-modal-enter-active .pc-modal { transition: transform .32s var(--ease-out, cubic-bezier(.16,1,.3,1)), opacity .2s ease; }
.pc-modal-leave-active { transition: opacity .16s ease; }
.pc-modal-enter-from { opacity: 0; }
.pc-modal-enter-from .pc-modal { transform: scale(.95) translateY(14px); opacity: 0; }
.pc-modal-leave-to { opacity: 0; }

/* ≤14″ / narrow */
@media (max-width: 1100px) {
  .pc-grid { grid-template-columns: 1fr; }
  .pc-tiles { flex-direction: row; flex-wrap: wrap; }
  .pc-tile { flex: 1 1 200px; }
}
@media (max-width: 620px) {
  .pc-row2, .pc-row3 { grid-template-columns: 1fr; }
}

/* Доступность: пользователю с настройкой «меньше движения» анимации не нужны —
   в PMO их много (каскады строк, полосы Гантта, всплытие модалок). */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .001ms !important;
    scroll-behavior: auto !important;
  }
}
</style>
