<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BIcon from "@/components/broadcasts/BIcon.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import ModalShell from "@/components/ModalShell.vue";
import {
  partnersApi, partnerStatusPill, partnerTierColor, PARTNER_KIND_LABELS,
  type IntegrationPartner, type LinkedResource, type PartnerKind,
  type PartnerResources, type PartnerStatus, type PartnerTier,
} from "@/api/partners";
import { useConfirm } from "@/composables/useConfirm";

const { confirmDialog } = useConfirm();

const partners = ref<IntegrationPartner[]>([]);
const selected = ref<IntegrationPartner | null>(null);
const resources = ref<PartnerResources | null>(null);
const loading  = ref(false);
const error    = ref<string | null>(null);
const searchQ  = ref("");
const filterStatus = ref<PartnerStatus | "">("");

const showCreate = ref(false);
const newPartner = ref<{
  slug: string; name: string; legal_name: string;
  description: string; kind: PartnerKind | "";
  status: PartnerStatus; tier: PartnerTier | "";
  contract_ref: string; contract_start: string; contract_end: string;
  tags: string; notes: string;
}>({
  slug: "", name: "", legal_name: "",
  description: "", kind: "",
  status: "active", tier: "",
  contract_ref: "", contract_start: "", contract_end: "",
  tags: "", notes: "",
});

const showDelete = ref<IntegrationPartner | null>(null);
const showEdit = ref(false);
const editingDraft = ref<Partial<IntegrationPartner>>({});

async function loadList() {
  loading.value = true; error.value = null;
  try {
    const r = await partnersApi.list(searchQ.value || undefined, filterStatus.value || undefined);
    partners.value = r.items;
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { loading.value = false; }
}

async function select(p: IntegrationPartner) {
  selected.value = p;
  resources.value = null;
  try { resources.value = await partnersApi.resources(p.id); }
  catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

onMounted(loadList);

async function submitCreate() {
  if (!newPartner.value.slug || !newPartner.value.name) { error.value = "Slug и name обязательны"; return; }
  try {
    const created = await partnersApi.create({
      slug: newPartner.value.slug.trim(),
      name: newPartner.value.name.trim(),
      legal_name: newPartner.value.legal_name.trim() || null,
      description: newPartner.value.description.trim() || null,
      kind: newPartner.value.kind || null,
      status: newPartner.value.status,
      tier: newPartner.value.tier || null,
      contract_ref:   newPartner.value.contract_ref.trim() || null,
      contract_start: newPartner.value.contract_start || null,
      contract_end:   newPartner.value.contract_end || null,
      tags: newPartner.value.tags.split(",").map((s) => s.trim()).filter(Boolean),
      notes: newPartner.value.notes.trim() || null,
    });
    showCreate.value = false;
    newPartner.value = {
      slug: "", name: "", legal_name: "", description: "", kind: "",
      status: "active", tier: "", contract_ref: "", contract_start: "", contract_end: "",
      tags: "", notes: "",
    };
    await loadList();
    await select(created);
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

function openEdit() {
  if (!selected.value) return;
  editingDraft.value = {
    name: selected.value.name,
    legal_name: selected.value.legal_name,
    description: selected.value.description,
    kind: selected.value.kind,
    status: selected.value.status,
    tier: selected.value.tier,
    contract_ref: selected.value.contract_ref,
    contract_start: selected.value.contract_start,
    contract_end: selected.value.contract_end,
    notes: selected.value.notes,
  };
  showEdit.value = true;
}

async function saveEdit() {
  if (!selected.value) return;
  try {
    const upd = await partnersApi.update(selected.value.id, editingDraft.value);
    showEdit.value = false;
    await loadList();
    await select(upd);
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function confirmDelete() {
  if (!showDelete.value) return;
  try {
    await partnersApi.remove(showDelete.value.id);
    if (selected.value?.id === showDelete.value.id) { selected.value = null; resources.value = null; }
    showDelete.value = null;
    await loadList();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function detach(r: LinkedResource) {
  if (!selected.value) return;
  if (!(await confirmDialog({ message: `Отвязать "${r.label}" от партнёра ${selected.value.name}?`, danger: true }))) return;
  try {
    await partnersApi.detach(selected.value.id, r.resource_type, r.resource_id);
    await select(selected.value);
    await loadList();
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
}

const totalResources = computed(() => {
  if (!resources.value) return 0;
  return resources.value.service_accounts.length + resources.value.external_apis.length + resources.value.webhooks.length;
});
</script>

<template>
  <div class="pt-wrap">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" style="margin: 8px 18px;" />

    <div class="pt-body">
      <!-- LEFT: list -->
      <div class="pt-side">
        <div class="pt-side-hd">
          <div class="pt-side-t">Партнёры</div>
          <button class="pt-add" @click="showCreate = true">
            <BIcon name="plus" :size="14" />
          </button>
        </div>
        <div class="pt-filt">
          <input v-model="searchQ" @input="loadList" placeholder="Поиск…" class="pt-i"/>
          <select v-model="filterStatus" @change="loadList" class="pt-s">
            <option value="">все</option>
            <option value="active">active</option>
            <option value="suspended">suspended</option>
            <option value="terminated">terminated</option>
          </select>
        </div>

        <UzaStateBlock v-if="!partners.length" state="empty" variant="block" title="Партнёров нет" desc="Создайте первого">
          <template #icon><BIcon name="building-arch" :size="14" /></template>
        </UzaStateBlock>

        <div v-else class="pt-list">
          <div v-for="p in partners" :key="p.id" class="pt-row"
               :class="{ active: selected?.id === p.id }"
               @click="select(p)">
            <div class="pt-row-tier" :style="{ background: partnerTierColor(p.tier) }"></div>
            <div class="pt-row-info">
              <div class="pt-row-t">{{ p.name }}</div>
              <div class="pt-row-slug"><code>{{ p.slug }}</code><span v-if="p.kind" class="pt-kind">{{ PARTNER_KIND_LABELS[p.kind] }}</span></div>
              <div class="pt-row-meta">
                <span class="pt-pill" :style="{ color: partnerStatusPill(p.status).color, background: partnerStatusPill(p.status).bg }">
                  {{ partnerStatusPill(p.status).label }}
                </span>
                <span class="pt-c-sa" :title="`${p.service_accounts_count} service accounts`">
                  <BIcon name="robot" :size="14" /> {{ p.service_accounts_count }}
                </span>
                <span class="pt-c-api" :title="`${p.external_apis_count} external APIs`">
                  <BIcon name="plug" :size="14" /> {{ p.external_apis_count }}
                </span>
                <span class="pt-c-wh" :title="`${p.webhooks_count} webhooks`">
                  <BIcon name="webhook" :size="14" /> {{ p.webhooks_count }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- RIGHT: detail -->
      <div class="pt-main">
        <template v-if="selected">
          <div class="pt-hero">
            <div class="pt-hero-lvl" :style="{ background: partnerTierColor(selected.tier) }"></div>
            <div style="flex: 1;">
              <div class="pt-hero-eye">
                <code class="pt-slug">{{ selected.slug }}</code>
                <span v-if="selected.kind" class="pt-kind">{{ PARTNER_KIND_LABELS[selected.kind] }}</span>
                <span class="pt-pill" :style="{ color: partnerStatusPill(selected.status).color, background: partnerStatusPill(selected.status).bg }">
                  {{ partnerStatusPill(selected.status).label }}
                </span>
                <span v-if="selected.tier" class="pt-tier-pill" :style="{ color: partnerTierColor(selected.tier), background: partnerTierColor(selected.tier) + '15' }">
                  {{ selected.tier }}
                </span>
              </div>
              <div class="pt-hero-t">{{ selected.name }}</div>
              <div v-if="selected.legal_name" class="pt-hero-legal">{{ selected.legal_name }}</div>
              <div v-if="selected.description" class="pt-hero-d">{{ selected.description }}</div>
            </div>
            <div class="pt-hero-actions">
              <button class="pt-btn" @click="openEdit">
                <BIcon name="pencil" :size="14" /> Изменить
              </button>
              <button class="pt-btn pt-btn-danger" @click="showDelete = selected">
                <BIcon name="trash" :size="14" />
              </button>
            </div>
          </div>

          <div class="pt-grid">
            <div class="pt-card">
              <div class="pt-card-hd">Контракт</div>
              <div class="pt-kv">
                <div><span>Reference</span><code>{{ selected.contract_ref || "—" }}</code></div>
                <div><span>Начало</span><span>{{ fmtDate(selected.contract_start) }}</span></div>
                <div><span>Конец</span><span>{{ fmtDate(selected.contract_end) }}</span></div>
              </div>
            </div>
            <div class="pt-card">
              <div class="pt-card-hd">Tags</div>
              <div v-if="!selected.tags || !selected.tags.length" style="color: var(--color-text-tertiary); font-size: 11px;">—</div>
              <div v-else>
                <span v-for="t in selected.tags" :key="t" class="pt-tag">{{ t }}</span>
              </div>
            </div>
          </div>

          <div v-if="selected.notes" class="pt-notes">
            <div class="pt-card-hd">Заметки</div>
            <pre>{{ selected.notes }}</pre>
          </div>

          <!-- ─── Linked resources ─── -->
          <div class="pt-res">
            <div class="pt-res-hd">
              <span>Связанные ресурсы · {{ totalResources }}</span>
              <span style="font-size: 10.5px; color: var(--color-text-tertiary);">
                Привязывайте Service accounts / External APIs / Webhooks через их собственные tabs (PATCH с partner_id)
              </span>
            </div>

            <div v-if="resources" class="pt-res-cols">
              <div class="pt-res-col">
                <div class="pt-res-col-hd"><BIcon name="robot" :size="14" /> Service accounts · {{ resources.service_accounts.length }}</div>
                <UzaStateBlock v-if="!resources.service_accounts.length" state="empty" variant="inline" text="не привязаны" />
                <div v-for="r in resources.service_accounts" :key="r.resource_id" class="pt-res-item">
                  <div>
                    <div class="pt-res-l">{{ r.label }}</div>
                    <div v-if="r.extra" class="pt-res-sub">{{ r.extra.email }}</div>
                  </div>
                  <button class="pt-icon-btn" @click="detach(r)" title="Отвязать"><BIcon name="x" :size="14" /></button>
                </div>
              </div>

              <div class="pt-res-col">
                <div class="pt-res-col-hd"><BIcon name="plug" :size="14" /> External APIs · {{ resources.external_apis.length }}</div>
                <UzaStateBlock v-if="!resources.external_apis.length" state="empty" variant="inline" text="не привязаны" />
                <div v-for="r in resources.external_apis" :key="r.resource_id" class="pt-res-item">
                  <div>
                    <div class="pt-res-l">{{ r.label }}</div>
                    <div v-if="r.extra" class="pt-res-sub"><code>{{ r.extra.slug }}</code> · {{ r.extra.status }}</div>
                  </div>
                  <button class="pt-icon-btn" @click="detach(r)" title="Отвязать"><BIcon name="x" :size="14" /></button>
                </div>
              </div>

              <div class="pt-res-col">
                <div class="pt-res-col-hd"><BIcon name="webhook" :size="14" /> Webhooks · {{ resources.webhooks.length }}</div>
                <UzaStateBlock v-if="!resources.webhooks.length" state="empty" variant="inline" text="не привязаны" />
                <div v-for="r in resources.webhooks" :key="r.resource_id" class="pt-res-item">
                  <div>
                    <div class="pt-res-l">{{ r.label }}</div>
                    <div v-if="r.extra" class="pt-res-sub"><code>{{ r.extra.target_url }}</code></div>
                  </div>
                  <button class="pt-icon-btn" @click="detach(r)" title="Отвязать"><BIcon name="x" :size="14" /></button>
                </div>
              </div>
            </div>
          </div>
        </template>

        <UzaStateBlock v-else state="empty" variant="block" text="Выберите партнёра слева или создайте нового">
          <template #icon><BIcon name="arrow-left" :size="14" /></template>
        </UzaStateBlock>
      </div>
    </div>

    <!-- ───── Modal: create ───── -->
    <ModalShell :open="showCreate" size="lg" title="Новый партнёр" @close="showCreate = false">
        <div class="pt-modal-body">
          <div class="pt-mgrid">
            <div class="pt-field">
              <label>Slug</label>
              <input v-model="newPartner.slug" placeholder="minfin, sap_uzb, central_bank"/>
            </div>
            <div class="pt-field">
              <label>Тип</label>
              <select v-model="newPartner.kind">
                <option value="">—</option>
                <option v-for="(label, code) in PARTNER_KIND_LABELS" :key="code" :value="code">{{ label }}</option>
              </select>
            </div>
          </div>
          <div class="pt-field">
            <label>Имя</label>
            <input v-model="newPartner.name" placeholder="Министерство финансов Республики Узбекистан"/>
          </div>
          <div class="pt-field">
            <label>Юридическое наименование</label>
            <input v-model="newPartner.legal_name" placeholder="(полное)"/>
          </div>
          <div class="pt-field">
            <label>Описание</label>
            <textarea v-model="newPartner.description" rows="2"></textarea>
          </div>
          <div class="pt-mgrid" style="grid-template-columns: 1fr 1fr;">
            <div class="pt-field">
              <label>Статус</label>
              <select v-model="newPartner.status">
                <option value="active">active</option>
                <option value="suspended">suspended</option>
                <option value="terminated">terminated</option>
              </select>
            </div>
            <div class="pt-field">
              <label>Тир</label>
              <select v-model="newPartner.tier">
                <option value="">—</option>
                <option value="platinum">platinum</option>
                <option value="gold">gold</option>
                <option value="silver">silver</option>
                <option value="standard">standard</option>
              </select>
            </div>
          </div>
          <div class="pt-field">
            <label>Reference контракта</label>
            <input v-model="newPartner.contract_ref" placeholder="UZA-2026-001"/>
          </div>
          <div class="pt-mgrid">
            <div class="pt-field">
              <label>Начало контракта</label>
              <input v-model="newPartner.contract_start" type="date"/>
            </div>
            <div class="pt-field">
              <label>Конец контракта</label>
              <input v-model="newPartner.contract_end" type="date"/>
            </div>
          </div>
          <div class="pt-field">
            <label>Tags (через запятую)</label>
            <input v-model="newPartner.tags" placeholder="strategic, government, regulatory"/>
          </div>
          <div class="pt-field">
            <label>Заметки</label>
            <textarea v-model="newPartner.notes" rows="2"></textarea>
          </div>
        </div>
      <template #footer>
        <button class="pt-btn pt-btn-ghost" @click="showCreate = false">Отмена</button>
        <button class="pt-btn pt-btn-primary" @click="submitCreate">Создать</button>
      </template>
    </ModalShell>

    <!-- ───── Modal: edit (compact) ───── -->
    <ModalShell :open="!!(showEdit && selected)" size="md"
                :title="selected ? 'Изменить · ' + selected.name : ''" @close="showEdit = false">
        <div class="pt-modal-body" v-if="selected">
          <div class="pt-field">
            <label>Имя</label>
            <input v-model="editingDraft.name"/>
          </div>
          <div class="pt-field">
            <label>Описание</label>
            <textarea v-model="editingDraft.description" rows="2"></textarea>
          </div>
          <div class="pt-mgrid" style="grid-template-columns: 1fr 1fr 1fr;">
            <div class="pt-field">
              <label>Статус</label>
              <select v-model="editingDraft.status">
                <option value="active">active</option>
                <option value="suspended">suspended</option>
                <option value="terminated">terminated</option>
              </select>
            </div>
            <div class="pt-field">
              <label>Тир</label>
              <select v-model="editingDraft.tier">
                <option :value="null">—</option>
                <option value="platinum">platinum</option>
                <option value="gold">gold</option>
                <option value="silver">silver</option>
                <option value="standard">standard</option>
              </select>
            </div>
            <div class="pt-field">
              <label>Тип</label>
              <select v-model="editingDraft.kind">
                <option :value="null">—</option>
                <option v-for="(label, code) in PARTNER_KIND_LABELS" :key="code" :value="code">{{ label }}</option>
              </select>
            </div>
          </div>
          <div class="pt-field">
            <label>Заметки</label>
            <textarea v-model="editingDraft.notes" rows="3"></textarea>
          </div>
        </div>
      <template #footer>
        <button class="pt-btn pt-btn-ghost" @click="showEdit = false">Отмена</button>
        <button class="pt-btn pt-btn-primary" @click="saveEdit">Сохранить</button>
      </template>
    </ModalShell>

    <!-- ───── Modal: delete ───── -->
    <ModalShell :open="!!showDelete" size="sm" @close="showDelete = null">
      <template v-if="showDelete" #header>
        <h2 style="margin:0; font-size:15px; font-weight:500; color:#A32D2D;">Удалить "{{ showDelete.name }}"?</h2>
      </template>
      <div class="pt-modal-body" v-if="showDelete">
          <div style="font-size: 11.5px; color: var(--color-text-secondary);">
            Связанные ресурсы (SA, API, webhooks) НЕ удаляются — у них просто отвяжется partner_id.
          </div>
        </div>
      <template #footer>
        <button class="pt-btn pt-btn-ghost" @click="showDelete = null">Отмена</button>
        <button class="pt-btn pt-btn-danger" @click="confirmDelete">Удалить</button>
      </template>
    </ModalShell>

  </div>
</template>

<style scoped>
.pt-wrap { flex: 1; display: flex; flex-direction: column; background: var(--color-background-tertiary); }

.pt-body { display: grid; grid-template-columns: 320px 1fr; flex: 1; min-height: 0; }

.pt-side { background: var(--color-background-primary); border-right: 0.5px solid var(--color-border-tertiary); overflow-y: auto; display: flex; flex-direction: column; }
.pt-side-hd { padding: 12px 14px 8px; display: flex; justify-content: space-between; align-items: center; }
.pt-side-t { font-size: 12px; color: var(--color-text-primary); font-weight: 500; }
.pt-add { background: rgba(127,119,221,.1); color: var(--p-deep); border: 0; padding: 4px 9px; border-radius: 5px; font-size: 10.5px; cursor: pointer; font-family: inherit; }
.pt-add:hover { background: rgba(127,119,221,.2); }
.pt-filt { display: flex; gap: 5px; padding: 0 14px 8px; }
.pt-i, .pt-s { padding: 5px 9px; border: 0.5px solid var(--color-border-tertiary); border-radius: 5px; font-size: 11px; font-family: inherit; outline: none; }
.pt-i { flex: 1; }

.pt-list { display: flex; flex-direction: column; }
.pt-row { display: flex; gap: 10px; padding: 10px 14px; cursor: pointer; border-bottom: 0.5px solid rgba(0,0,0,.04); }
.pt-row:hover { background: rgba(127,119,221,.04); }
.pt-row.active { background: rgba(127,119,221,.08); }
.pt-row-tier { width: 3px; border-radius: 2px; flex-shrink: 0; }
.pt-row-info { flex: 1; min-width: 0; }
.pt-row-t { font-size: 12px; color: var(--color-text-primary); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pt-row-slug { font-size: 10px; color: var(--color-text-tertiary); margin-top: 1px; display: flex; gap: 6px; align-items: center; }
.pt-row-slug code { font-family: var(--font-mono, monospace); }
.pt-kind { background: rgba(0,0,0,.05); padding: 1px 6px; border-radius: 3px; font-size: 9px; }
.pt-row-meta { display: flex; gap: 4px; margin-top: 5px; align-items: center; }
.pt-pill { padding: 1px 6px; border-radius: 3px; font-size: 9px; font-weight: 600; text-transform: lowercase; }
.pt-c-sa, .pt-c-api, .pt-c-wh { background: rgba(0,0,0,.04); padding: 1px 5px; border-radius: 3px; font-size: 9.5px; color: var(--color-text-secondary); display: inline-flex; align-items: center; gap: 2px; font-feature-settings: "tnum"; }

.pt-main { padding: 16px 22px; overflow-y: auto; }

.pt-hero { display: flex; gap: 14px; padding: 14px 16px; background: linear-gradient(90deg, rgba(127,119,221,.06), transparent); border-radius: 0 7px 7px 0; margin-bottom: 14px; align-items: flex-start; }
.pt-hero-lvl { width: 4px; align-self: stretch; border-radius: 2px; }
.pt-hero-eye { display: flex; gap: 7px; align-items: center; flex-wrap: wrap; }
.pt-slug { font-family: var(--font-mono, monospace); font-size: 10.5px; background: rgba(0,0,0,.05); padding: 2px 7px; border-radius: 4px; color: var(--color-text-secondary); }
.pt-tier-pill { padding: 2px 8px; border-radius: 4px; font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.pt-hero-t { font-size: 16px; font-weight: 500; color: var(--color-text-primary); margin-top: 5px; }
.pt-hero-legal { font-size: 11px; color: var(--color-text-secondary); margin-top: 2px; }
.pt-hero-d { font-size: 11.5px; color: var(--color-text-secondary); margin-top: 3px; line-height: 1.5; }
.pt-hero-actions { display: flex; gap: 5px; flex-shrink: 0; }

.pt-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px; }
.pt-card { background: var(--color-background-primary); border: 0.5px solid var(--color-border-tertiary); border-radius: 7px; padding: 11px 14px; }
.pt-card-hd { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .06em; font-weight: 500; margin-bottom: 7px; }
.pt-kv { display: flex; flex-direction: column; gap: 5px; }
.pt-kv > div { display: flex; gap: 9px; align-items: baseline; font-size: 11.5px; }
.pt-kv > div > span:first-child { color: var(--color-text-tertiary); font-size: 9.5px; text-transform: uppercase; letter-spacing: .04em; min-width: 80px; }
.pt-kv code { font-family: var(--font-mono, monospace); font-size: 10.5px; }
.pt-tag { background: rgba(127,119,221,.08); color: var(--p-deep); padding: 1px 7px; border-radius: 9px; font-size: 9.5px; margin-right: 3px; display: inline-block; }

.pt-notes { background: var(--bg2, #FAFAFC); border: 0.5px solid var(--color-border-tertiary); border-radius: 7px; padding: 11px 14px; margin-bottom: 14px; }
.pt-notes pre { font-family: inherit; white-space: pre-wrap; font-size: 11.5px; color: var(--color-text-secondary); margin: 0; line-height: 1.5; }

.pt-res { background: var(--color-background-primary); border: 0.5px solid var(--color-border-tertiary); border-radius: 7px; padding: 12px; }
.pt-res-hd { display: flex; flex-direction: column; gap: 3px; margin-bottom: 10px; font-size: 12px; color: var(--color-text-primary); font-weight: 500; }
.pt-res-cols { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
.pt-res-col { display: flex; flex-direction: column; gap: 6px; }
.pt-res-col-hd { font-size: 10px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .05em; font-weight: 500; display: flex; align-items: center; gap: 4px; }
.pt-res-item { display: flex; justify-content: space-between; align-items: flex-start; gap: 6px; padding: 6px 9px; background: var(--bg2, #FAFAFC); border-radius: 5px; }
.pt-res-l { font-size: 11px; color: var(--color-text-primary); font-weight: 500; }
.pt-res-sub { font-size: 10px; color: var(--color-text-tertiary); margin-top: 2px; }
.pt-res-sub code { font-family: var(--font-mono, monospace); }
.pt-icon-btn { background: transparent; border: 0; color: var(--color-text-tertiary); cursor: pointer; padding: 2px; font-size: 12px; }
.pt-icon-btn:hover { color: var(--sev-critical); }

/* Buttons */
.pt-btn { background: var(--color-background-primary); border: 0.5px solid var(--color-border-tertiary); padding: 6px 12px; border-radius: 6px; font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit; color: var(--color-text-secondary); display: inline-flex; align-items: center; gap: 4px; }
.pt-btn:hover:not(:disabled) { background: rgba(127,119,221,.05); }
.pt-btn-ghost { background: transparent; }
.pt-btn-primary { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.pt-btn-primary:hover:not(:disabled) { background: var(--p-deep); }
.pt-btn-danger { background: rgba(226,75,74,.08); color: var(--sev-critical); border-color: rgba(226,75,74,.2); }
.pt-btn-danger:hover { background: var(--sev-high); color: #fff; }

/* Modal */
.pt-modal-bg { position: fixed; inset: 0; z-index: 1000; background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.pt-modal { background: var(--color-background-primary); width: 100%; max-width: 460px; border-radius: 12px; overflow: hidden; box-shadow: 0 24px 64px rgba(15,23,60,.18); animation: ptIn .35s var(--ease-standard); }
@keyframes ptIn { from { transform: scale(.95) translateY(15px); opacity: 0; } to { transform: scale(1) translateY(0); opacity: 1; } }
.pt-modal-hd { padding: 12px 18px; background: linear-gradient(90deg, rgba(127,119,221,.06), transparent); border-bottom: 0.5px solid var(--color-border-tertiary); font-size: 12px; color: var(--color-text-primary); font-weight: 500; }
.pt-modal-body { padding: 14px 18px; display: flex; flex-direction: column; gap: 10px; max-height: 70dvh; overflow-y: auto; }
.pt-modal-footer { padding: 11px 18px; background: var(--bg2, #FAFAFC); border-top: 0.5px solid var(--color-border-tertiary); display: flex; gap: 6px; justify-content: flex-end; }
.pt-mgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.pt-field { display: flex; flex-direction: column; gap: 3px; }
.pt-field label { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .05em; }
.pt-field input, .pt-field textarea, .pt-field select { padding: 6px 10px; border: 0.5px solid var(--color-border-tertiary); border-radius: 6px; font-size: 12px; font-family: inherit; outline: none; }
</style>