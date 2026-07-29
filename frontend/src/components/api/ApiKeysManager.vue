<script setup lang="ts">
import { onMounted, ref } from "vue";
import BIcon from "@/components/broadcasts/BIcon.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import ModalShell from "@/components/ModalShell.vue";
import { useConfirm } from "@/composables/useConfirm";
import {
  apiCatalogApi, apiKeysApi,
  envPill, keyStatusPill,
  type ApiKey, type ApiKeyCreated,
  type Environment, type ScopeItem,
  type ServiceAccount,
} from "@/api/api_catalog";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const emit = defineEmits<{ changed: [] }>();

const { confirmDialog } = useConfirm();

const sas = ref<ServiceAccount[]>([]);
const keys = ref<ApiKey[]>([]);
const scopesByModule = ref<Record<string, ScopeItem[]>>({});
const selectedSa = ref<ServiceAccount | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

// Modals
const showSaCreate = ref(false);
const newSa = ref<{ email: string; full_name: string; description: string }>({
  email: "", full_name: "", description: "",
});

const showKeyCreate = ref(false);
const newKey = ref<{
  name: string; description: string;
  environment: Environment; rate_limit_per_minute: number;
  ip_allowlist: string; expires_at: string; scopes: Set<string>;
}>({
  name: "", description: "",
  environment: "sandbox", rate_limit_per_minute: 600,
  ip_allowlist: "", expires_at: "",
  scopes: new Set(),
});
const plaintextDisplay = ref<ApiKeyCreated | null>(null);

const revokeTarget = ref<ApiKey | null>(null);
const revokeReason = ref("");

async function loadAll() {
  loading.value = true;
  error.value = null;
  try {
    const [saR, scR] = await Promise.all([
      apiKeysApi.listServiceAccounts(),
      apiCatalogApi.scopes(),
    ]);
    sas.value = saR.items;
    scopesByModule.value = scR.grouped_by_module;
    if (selectedSa.value) {
      // Refresh keys for current SA if selection persisted
      const stillThere = sas.value.find((s) => s.id === selectedSa.value!.id);
      if (stillThere) await loadKeys(stillThere);
      else { selectedSa.value = null; keys.value = []; }
    }
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
  finally { loading.value = false; }
}

async function loadKeys(sa: ServiceAccount) {
  selectedSa.value = sa;
  try {
    const r = await apiKeysApi.listKeys(sa.id, true);
    keys.value = r.items;
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

onMounted(loadAll);

async function createServiceAccount() {
  if (!newSa.value.email || !newSa.value.full_name) {
    error.value = t('Заполните email и имя'); return;
  }
  try {
    const created = await apiKeysApi.createServiceAccount({
      email: newSa.value.email.trim(),
      full_name: newSa.value.full_name.trim(),
      description: newSa.value.description.trim() || null,
    });
    newSa.value = { email: "", full_name: "", description: "" };
    showSaCreate.value = false;
    await loadAll();
    emit("changed");
    await loadKeys(created);
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function deactivateSa(sa: ServiceAccount) {
  if (!(await confirmDialog({ message: t('Деактивировать service account "{value0}" и отозвать все его ключи?', { value0: sa.full_name || sa.email }), danger: true }))) return;
  try {
    await apiKeysApi.deleteServiceAccount(sa.id);
    if (selectedSa.value?.id === sa.id) selectedSa.value = null;
    await loadAll();
    emit("changed");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

function openKeyCreate() {
  if (!selectedSa.value) { error.value = t('Сначала выберите service account'); return; }
  newKey.value = {
    name: "", description: "",
    environment: "sandbox", rate_limit_per_minute: 600,
    ip_allowlist: "", expires_at: "",
    scopes: new Set(),
  };
  showKeyCreate.value = true;
}

function toggleScope(code: string) {
  if (newKey.value.scopes.has(code)) newKey.value.scopes.delete(code);
  else newKey.value.scopes.add(code);
  // Trigger reactivity
  newKey.value.scopes = new Set(newKey.value.scopes);
}

async function submitKeyCreate() {
  if (!selectedSa.value) return;
  if (!newKey.value.name.trim()) { error.value = t('Укажите имя ключа'); return; }
  try {
    const allowlist = newKey.value.ip_allowlist.trim()
      ? newKey.value.ip_allowlist.split(",").map((s) => s.trim()).filter(Boolean)
      : null;
    const created = await apiKeysApi.createKey({
      service_account_id: selectedSa.value.id,
      name: newKey.value.name.trim(),
      description: newKey.value.description.trim() || null,
      scopes: Array.from(newKey.value.scopes),
      environment: newKey.value.environment,
      rate_limit_per_minute: newKey.value.rate_limit_per_minute,
      ip_allowlist: allowlist,
      expires_at: newKey.value.expires_at ? new Date(newKey.value.expires_at).toISOString() : null,
    });
    showKeyCreate.value = false;
    plaintextDisplay.value = created;
    await loadKeys(selectedSa.value);
    emit("changed");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

async function copyToken() {
  if (!plaintextDisplay.value) return;
  try { await navigator.clipboard.writeText(plaintextDisplay.value.plaintext_token); }
  catch { /* silent */ }
}

async function confirmRevoke() {
  if (!revokeTarget.value) return;
  try {
    await apiKeysApi.revokeKey(revokeTarget.value.id, revokeReason.value.trim() || undefined);
    if (selectedSa.value) await loadKeys(selectedSa.value);
    revokeTarget.value = null;
    revokeReason.value = "";
    emit("changed");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

function fmtRel(iso: string | null): string {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return t('только что');
  if (diff < 3600) return t('{value0} мин назад', { value0: Math.floor(diff / 60) });
  if (diff < 86400) return t('{value0} ч назад', { value0: Math.floor(diff / 3600) });
  return t('{value0} дн назад', { value0: Math.floor(diff / 86400) });
}
</script>

<template>
  <div class="km-wrap">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />

    <div class="km-grid">

      <!-- LEFT: Service Accounts -->
      <div class="km-col km-sa-col">
        <div class="km-col-hd">
          <div class="km-col-t">Service accounts</div>
          <button class="km-add" @click="showSaCreate = true">
            <BIcon name="plus" :size="14" />
          </button>
        </div>

        <UzaStateBlock v-if="loading && !sas.length" state="loading" variant="text" />
      <UzaStateBlock v-else-if="!sas.length" state="empty" :title="t('Нет service accounts')" :desc="t('Создайте первый')">
          <template #icon><BIcon name="robot" :size="14" /></template>
        </UzaStateBlock>

        <div v-else class="km-sa-list">
          <div v-for="sa in sas" :key="sa.id"
               class="km-sa-row"
               :class="{ active: selectedSa?.id === sa.id, inactive: !sa.is_active }"
               @click="loadKeys(sa)">
            <div class="km-sa-avatar">{{ (sa.full_name || sa.email).slice(0, 2).toUpperCase() }}</div>
            <div class="km-sa-info">
              <div class="km-sa-name">{{ sa.full_name || sa.email }}</div>
              <div class="km-sa-meta">
                <span>{{ sa.keys_count ?? 0 }} {{ t('ключей') }}</span>
                <span v-if="!sa.is_active" class="km-sa-disabled">disabled</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- RIGHT: Keys for selected SA -->
      <div class="km-col km-keys-col">
        <template v-if="selectedSa">
          <div class="km-col-hd">
            <div>
              <div class="km-col-t">{{ selectedSa.full_name || selectedSa.email }}</div>
              <div class="km-col-s">{{ selectedSa.email }} · {{ selectedSa.description || t('без описания') }}</div>
            </div>
            <div style="display: flex; gap: 6px;">
              <button class="km-add" @click="deactivateSa(selectedSa)" :title="t('Деактивировать SA')"
                      style="background: rgba(226,75,74,.08); color: #A32D2D;">
                <BIcon name="trash" :size="14" />
              </button>
              <button class="km-add km-add-primary" @click="openKeyCreate">
                <BIcon name="plus" :size="14" /> {{ t('Выпустить ключ') }}
              </button>
            </div>
          </div>

          <UzaStateBlock v-if="!keys.length" state="empty" :text="t('Ключей нет')">
            <template #icon><BIcon name="key" :size="14" /></template>
          </UzaStateBlock>

          <table v-else class="km-keys">
            <thead>
              <tr>
                <th>{{ t('Имя') }}</th>
                <th>{{ t('Префикс') }}</th>
                <th>Env</th>
                <th>Scopes</th>
                <th>Last used</th>
                <th>Calls</th>
                <th>{{ t('Статус') }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="k in keys" :key="k.id" class="km-key-row">
                <td>
                  <span class="uza-stripe-el" :style="{ '--stripe-color': keyStatusPill(k).color }" />
                  <div style="font-weight: 500;">{{ k.name }}</div>
                  <div style="font-size: 10px; color: var(--color-text-tertiary);">{{ k.description || "—" }}</div>
                </td>
                <td><code class="km-prefix">{{ k.prefix }}…</code></td>
                <td>
                  <span class="km-pill" :style="{ color: envPill(k.environment).color, background: envPill(k.environment).bg }">
                    {{ t(envPill(k.environment).label) }}
                  </span>
                </td>
                <td>
                  <span v-if="k.scopes.length === 0" style="color: var(--color-text-tertiary); font-size: 10.5px;">{{ t('(нет)') }}</span>
                  <span v-else class="km-scope-chip">{{ k.scopes[0] }}</span>
                  <span v-if="k.scopes.length > 1" class="km-scope-chip km-scope-more">+ {{ k.scopes.length - 1 }}</span>
                </td>
                <td class="km-tact">{{ fmtRel(k.last_used_at) }}</td>
                <td class="km-num">{{ k.total_calls }}<span v-if="k.failed_calls > 0" style="color: #A32D2D;"> · {{ k.failed_calls }} fail</span></td>
                <td>
                  <span class="km-pill" :style="{ color: keyStatusPill(k).color, background: keyStatusPill(k).bg }">
                    {{ t(keyStatusPill(k).label) }}
                  </span>
                </td>
                <td>
                  <button v-if="!k.revoked_at" class="km-icon-btn" :title="t('Отозвать')" @click="revokeTarget = k">
                    <BIcon name="shield-x" :size="14" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </template>

        <UzaStateBlock v-else state="empty" :text="t('Выберите service account слева, чтобы увидеть его ключи')">
          <template #icon><BIcon name="arrow-left" :size="14" /></template>
        </UzaStateBlock>
      </div>
    </div>

    <!-- ───── Modal: create SA ───── -->
    <ModalShell :open="showSaCreate" size="md" :title="t('Новый service account')" @close="showSaCreate = false">
        <div class="km-modal-body">
          <div class="km-field">
            <label>{{ t('Email (идентификатор)') }}</label>
            <input v-model="newSa.email" type="email" placeholder="sa-minfin-reporting@uz-assets.uz"/>
          </div>
          <div class="km-field">
            <label>{{ t('Имя · назначение') }}</label>
            <input v-model="newSa.full_name" :placeholder="t('МинФин · отчёты SAP→UzAssets')"/>
          </div>
          <div class="km-field">
            <label>{{ t('Описание') }}</label>
            <textarea v-model="newSa.description" rows="2" :placeholder="t('Контактное лицо, контракт, цель интеграции')"></textarea>
          </div>
        </div>
      <template #footer>
        <button class="km-btn km-btn-ghost" @click="showSaCreate = false">{{ t('Отмена') }}</button>
        <button class="km-btn km-btn-primary" @click="createServiceAccount">{{ t('Создать') }}</button>
      </template>
    </ModalShell>

    <!-- ───── Modal: create key ───── -->
    <ModalShell :open="showKeyCreate" size="lg"
                :title="t('Выпуск API ключа для {value0}', { value0: (selectedSa?.full_name || selectedSa?.email || '') })"
                @close="showKeyCreate = false">
        <div class="km-modal-body">
          <div class="km-field-grid">
            <div class="km-field">
              <label>{{ t('Имя ключа') }}</label>
              <input v-model="newKey.name" placeholder="Production · IFRS export"/>
            </div>
            <div class="km-field">
              <label>{{ t('Окружение') }}</label>
              <select v-model="newKey.environment">
                <option value="sandbox">Sandbox</option>
                <option value="production">Production</option>
              </select>
            </div>
            <div class="km-field">
              <label>{{ t('Истекает') }}</label>
              <input v-model="newKey.expires_at" type="datetime-local"/>
            </div>
            <div class="km-field">
              <label>{{ t('Rate limit (req/мин)') }}</label>
              <input v-model.number="newKey.rate_limit_per_minute" type="number" min="10" max="60000"/>
            </div>
          </div>
          <div class="km-field">
            <label>{{ t('IP allowlist (CIDR через запятую)') }}</label>
            <input v-model="newKey.ip_allowlist" placeholder="195.158.0.0/16, 84.54.96.32"/>
          </div>
          <div class="km-field">
            <label>{{ t('Описание') }}</label>
            <input v-model="newKey.description" :placeholder="t('(необязательно)')"/>
          </div>

          <div class="km-field">
            <label>Scopes · {{ newKey.scopes.size }} {{ t('выбрано из') }} {{ Object.values(scopesByModule).flat().length }}</label>
            <div class="km-scope-tree">
              <div v-for="(items, module) in scopesByModule" :key="module" class="km-scope-grp">
                <div class="km-scope-grp-hd">{{ module }}</div>
                <div class="km-scope-items">
                  <label v-for="s in items" :key="s.code" class="km-scope-opt"
                         :class="{ on: newKey.scopes.has(s.code) }">
                    <input type="checkbox" :checked="newKey.scopes.has(s.code)" @change="toggleScope(s.code)"/>
                    <code>{{ s.code }}</code>
                  </label>
                </div>
              </div>
            </div>
          </div>
        </div>
      <template #footer>
        <button class="km-btn km-btn-ghost" @click="showKeyCreate = false">{{ t('Отмена') }}</button>
        <button class="km-btn km-btn-primary" @click="submitKeyCreate">
          <BIcon name="key" :size="14" /> {{ t('Выпустить') }}
        </button>
      </template>
    </ModalShell>

    <!-- ───── Modal: plaintext token display (без закрытия по фону) ───── -->
    <ModalShell :open="!!plaintextDisplay" size="md" :close-on-overlay="false" @close="plaintextDisplay = null">
      <template v-if="plaintextDisplay" #header>
        <h2 style="margin:0; font-size:15px; font-weight:500; color:#0F6E56; display:flex; align-items:center; gap:6px;"><BIcon name="check" :size="14" /> {{ t('Ключ выпущен — сохраните токен СЕЙЧАС') }}</h2>
      </template>
      <div class="km-modal-body" v-if="plaintextDisplay">
          <div class="km-amber-banner">
            <b>{{ t('Полный токен показывается ОДИН раз.') }}</b> {{ t('После закрытия окна его восстановить нельзя — только выпустить новый.') }}
          </div>
          <div class="km-token-box">
            <code>{{ plaintextDisplay.plaintext_token }}</code>
            <button class="km-btn km-btn-primary" @click="copyToken">
              <BIcon name="copy" :size="14" /> {{ t('Скопировать') }}
            </button>
          </div>
          <div style="font-size: 10.5px; color: var(--color-text-tertiary); margin-top: 8px;">
            {{ t('Префикс:') }} <code>{{ plaintextDisplay.prefix }}</code> ·
            Scopes: {{ plaintextDisplay.scopes.length }} ·
            Env: {{ plaintextDisplay.environment }}
          </div>
        </div>
      <template #footer>
        <button class="km-btn km-btn-primary" @click="plaintextDisplay = null">{{ t('Я сохранил — закрыть') }}</button>
      </template>
    </ModalShell>

    <!-- ───── Modal: revoke key ───── -->
    <ModalShell :open="!!revokeTarget" size="sm" @close="revokeTarget = null">
      <template v-if="revokeTarget" #header>
        <h2 style="margin:0; font-size:15px; font-weight:500; color:#A32D2D;">{{ t('Отозвать ключ "') }}{{ revokeTarget.name }}"</h2>
      </template>
      <div class="km-modal-body" v-if="revokeTarget">
          <div style="font-size: 11.5px; color: var(--color-text-secondary); margin-bottom: 9px;">
            {{ t('После отзыва все запросы с этим токеном начнут получать 401. Действие необратимо.') }}
          </div>
          <div class="km-field">
            <label>{{ t('Причина (для audit log)') }}</label>
            <textarea v-model="revokeReason" rows="2" :placeholder="t('Скомпрометирован / не используется / истек контракт...')"></textarea>
          </div>
        </div>
      <template #footer>
        <button class="km-btn km-btn-ghost" @click="revokeTarget = null">{{ t('Отмена') }}</button>
        <button class="km-btn" style="background: #E24B4A; color: #fff;" @click="confirmRevoke">
          <BIcon name="shield-x" :size="14" /> {{ t('Отозвать') }}
        </button>
      </template>
    </ModalShell>

  </div>
</template>

<style scoped>
.km-wrap { flex: 1; display: flex; flex-direction: column; background: var(--color-background-tertiary); }

.km-grid { display: grid; grid-template-columns: 280px 1fr; flex: 1; min-height: 0; }

.km-col { display: flex; flex-direction: column; overflow-y: auto; }
.km-sa-col { background: var(--color-background-primary); border-right: 0.5px solid var(--color-border-tertiary); }
.km-keys-col { padding: 0 18px; }

.km-col-hd {
  padding: 12px 14px 10px;
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 0.5px solid var(--color-border-tertiary);
}
.km-keys-col .km-col-hd { padding: 14px 0 12px; }
.km-col-t { font-size: 12px; color: var(--color-text-primary); font-weight: 500; }
.km-col-s { font-size: 10px; color: var(--color-text-tertiary); margin-top: 2px; }

.km-add {
  background: rgba(127,119,221,.1);
  color: var(--p-deep);
  border: 0;
  padding: 4px 8px;
  border-radius: 5px;
  font-size: 10.5px;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 3px;
}
.km-add:hover { background: rgba(127,119,221,.18); }
.km-add-primary { background: #7F77DD; color: #fff; padding: 6px 12px; }
.km-add-primary:hover { background: var(--p-deep); }

.km-sa-list { display: flex; flex-direction: column; }
.km-sa-row {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 0.5px solid rgba(0,0,0,.04);
  position: relative; overflow: hidden;
}
.km-sa-row:hover { background: rgba(127,119,221,.04); }
.km-sa-row.active { background: rgba(127,119,221,.08); }
.km-sa-row.active::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.km-sa-row.inactive { opacity: .55; }
.km-sa-avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: rgba(127,119,221,.15);
  color: var(--p-deep);
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10.5px; font-weight: 600;
}
.km-sa-info { flex: 1; min-width: 0; }
.km-sa-name {
  font-size: 12px; color: var(--color-text-primary); font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.km-sa-meta { font-size: 10px; color: var(--color-text-tertiary); margin-top: 1px; display: flex; gap: 6px; }
.km-sa-disabled { background: rgba(226,75,74,.1); color: var(--sev-critical); padding: 0 5px; border-radius: 3px; font-weight: 500; }

.km-keys {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  margin-top: 4px;
}
.km-keys th {
  text-align: left;
  padding: 7px 10px;
  font-size: 9px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .06em;
  font-weight: 500;
  background: var(--bg2, #FAFAFC);
  border-bottom: 0.5px solid var(--color-border-tertiary);
}
.km-key-row td {
  padding: 9px 10px;
  font-size: 11.5px;
  border-bottom: 0.5px solid rgba(0,0,0,.04);
}
.km-key-row { position: relative; }
.km-key-row td:first-child { padding-left: 18px; }
.km-prefix {
  font-family: var(--font-mono, monospace);
  font-size: 10.5px;
  color: var(--color-text-secondary);
}
.km-pill {
  padding: 2px 7px; border-radius: 4px;
  font-size: 9.5px; font-weight: 600;
  letter-spacing: .03em; text-transform: lowercase;
}
.km-scope-chip {
  background: rgba(127,119,221,.08); color: var(--p-deep);
  padding: 1px 6px; border-radius: 3px;
  font-size: 9.5px; font-family: var(--font-mono, monospace); margin-right: 3px;
}
.km-scope-more { background: rgba(0,0,0,.05); color: var(--color-text-secondary); font-family: inherit; }
.km-tact { color: var(--color-text-tertiary); font-size: 10.5px; }
.km-num { font-feature-settings: "tnum"; font-size: 11px; }

.km-icon-btn {
  background: transparent; border: 0; padding: 4px;
  color: var(--color-text-tertiary); cursor: pointer; font-size: 13px;
}
.km-icon-btn:hover { color: var(--sev-critical); }

/* ─── Modals ─── */
.km-modal-bg {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.km-modal {
  background: var(--color-background-primary);
  width: 100%; max-width: 440px;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  animation: kmIn .35s var(--ease-standard);
}
@keyframes kmIn { from { transform: scale(.95) translateY(15px); opacity: 0; } to { transform: scale(1) translateY(0); opacity: 1; } }
.km-modal-hd {
  padding: 12px 18px;
  background: linear-gradient(90deg, rgba(127,119,221,.06), transparent);
  border-bottom: 0.5px solid var(--color-border-tertiary);
  font-size: 12px;
  color: var(--color-text-primary);
  font-weight: 500;
}
.km-modal-body { padding: 14px 18px; display: flex; flex-direction: column; gap: 10px; max-height: 60dvh; overflow-y: auto; }
.km-modal-footer {
  padding: 11px 18px;
  background: var(--bg2, #FAFAFC);
  border-top: 0.5px solid var(--color-border-tertiary);
  display: flex; gap: 6px; justify-content: flex-end;
}

.km-field { display: flex; flex-direction: column; gap: 3px; }
.km-field label {
  font-size: 9.5px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: .05em;
}
.km-field input, .km-field textarea, .km-field select {
  padding: 6px 10px;
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 6px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
}
.km-field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }

.km-scope-tree {
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 7px;
  max-height: 220px;
  overflow-y: auto;
}
.km-scope-grp { padding: 6px 9px; border-bottom: 0.5px solid rgba(0,0,0,.04); }
.km-scope-grp-hd { font-size: 9.5px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .04em; margin-bottom: 4px; }
.km-scope-items { display: flex; flex-wrap: wrap; gap: 4px; }
.km-scope-opt {
  display: inline-flex; align-items: center; gap: 3px;
  background: var(--color-background-secondary);
  padding: 3px 7px;
  border-radius: 4px;
  font-size: 10.5px;
  cursor: pointer;
}
.km-scope-opt input { margin: 0; }
.km-scope-opt code { font-family: var(--font-mono, monospace); font-size: 10px; color: var(--color-text-secondary); }
.km-scope-opt.on { background: rgba(127,119,221,.15); }
.km-scope-opt.on code { color: var(--p-deep); font-weight: 500; }

.km-btn {
  border: 0;
  padding: 7px 14px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
}
.km-btn-ghost { background: transparent; border: 0.5px solid var(--color-border-tertiary); color: var(--color-text-secondary); }
.km-btn-primary { background: #7F77DD; color: #fff; }
.km-btn-primary:hover { background: var(--p-deep); }

.km-token-box {
  background: #1E2A4A;
  color: #C9D1E0;
  padding: 12px;
  border-radius: 7px;
  display: flex; align-items: center; gap: 8px;
  word-break: break-all;
}
.km-token-box code {
  flex: 1;
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  word-break: break-all;
  line-height: 1.5;
}

.km-amber-banner {
  background: rgba(239,159,39,.08);
  padding: 9px 12px; border-radius: 5px;
  font-size: 11.5px; color: #854F0B; margin-bottom: 12px;
  position: relative; overflow: hidden;
}
.km-amber-banner::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--amber);
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
</style>
