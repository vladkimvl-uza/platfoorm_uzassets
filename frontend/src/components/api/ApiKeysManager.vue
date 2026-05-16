<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  apiCatalogApi, apiKeysApi,
  envPill, keyStatusPill,
  type ApiKey, type ApiKeyCreated,
  type Environment, type ScopeItem,
  type ServiceAccount,
} from "@/api/api_catalog";

const emit = defineEmits<{ changed: [] }>();

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
    error.value = "Заполните email и имя"; return;
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
  if (!confirm(`Деактивировать service account "${sa.full_name || sa.email}" и отозвать все его ключи?`)) return;
  try {
    await apiKeysApi.deleteServiceAccount(sa.id);
    if (selectedSa.value?.id === sa.id) selectedSa.value = null;
    await loadAll();
    emit("changed");
  } catch (e: any) { error.value = e?.response?.data?.detail || e?.message; }
}

function openKeyCreate() {
  if (!selectedSa.value) { error.value = "Сначала выберите service account"; return; }
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
  if (!newKey.value.name.trim()) { error.value = "Укажите имя ключа"; return; }
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

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
function fmtRel(iso: string | null): string {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return "только что";
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  return `${Math.floor(diff / 86400)} дн назад`;
}
</script>

<template>
  <div class="km-wrap">
    <div v-if="error" class="km-err">{{ error }} <button @click="error = null">×</button></div>

    <div class="km-grid">

      <!-- LEFT: Service Accounts -->
      <div class="km-col km-sa-col">
        <div class="km-col-hd">
          <div class="km-col-t">Service accounts</div>
          <button class="km-add" @click="showSaCreate = true">
            <i class="ti ti-plus" aria-hidden="true"></i>
          </button>
        </div>

        <div v-if="loading && !sas.length" class="km-empty">Загрузка…</div>
        <div v-else-if="!sas.length" class="km-empty">
          <i class="ti ti-robot" style="font-size: 24px; opacity: .3;" aria-hidden="true"></i>
          <div>Нет service accounts</div>
          <div style="font-size: 10px; margin-top: 4px;">Создайте первый</div>
        </div>

        <div v-else class="km-sa-list">
          <div v-for="sa in sas" :key="sa.id"
               class="km-sa-row"
               :class="{ active: selectedSa?.id === sa.id, inactive: !sa.is_active }"
               @click="loadKeys(sa)">
            <div class="km-sa-avatar">{{ (sa.full_name || sa.email).slice(0, 2).toUpperCase() }}</div>
            <div class="km-sa-info">
              <div class="km-sa-name">{{ sa.full_name || sa.email }}</div>
              <div class="km-sa-meta">
                <span>{{ sa.keys_count ?? 0 }} ключей</span>
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
              <div class="km-col-s">{{ selectedSa.email }} · {{ selectedSa.description || "без описания" }}</div>
            </div>
            <div style="display: flex; gap: 6px;">
              <button class="km-add" @click="deactivateSa(selectedSa)" title="Деактивировать SA"
                      style="background: rgba(226,75,74,.08); color: #A32D2D;">
                <i class="ti ti-trash" aria-hidden="true"></i>
              </button>
              <button class="km-add km-add-primary" @click="openKeyCreate">
                <i class="ti ti-plus" aria-hidden="true"></i> Выпустить ключ
              </button>
            </div>
          </div>

          <div v-if="!keys.length" class="km-empty">
            <i class="ti ti-key" style="font-size: 24px; opacity: .3;" aria-hidden="true"></i>
            <div>Ключей нет</div>
          </div>

          <table v-else class="km-keys">
            <thead>
              <tr>
                <th>Имя</th>
                <th>Префикс</th>
                <th>Env</th>
                <th>Scopes</th>
                <th>Last used</th>
                <th>Calls</th>
                <th>Статус</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="k in keys" :key="k.id" class="km-key-row"
                  :style="{ borderLeftColor: keyStatusPill(k).color }">
                <td>
                  <div style="font-weight: 500;">{{ k.name }}</div>
                  <div style="font-size: 10px; color: var(--color-text-tertiary);">{{ k.description || "—" }}</div>
                </td>
                <td><code class="km-prefix">{{ k.prefix }}…</code></td>
                <td>
                  <span class="km-pill" :style="{ color: envPill(k.environment).color, background: envPill(k.environment).bg }">
                    {{ envPill(k.environment).label }}
                  </span>
                </td>
                <td>
                  <span v-if="k.scopes.length === 0" style="color: var(--color-text-tertiary); font-size: 10.5px;">(нет)</span>
                  <span v-else class="km-scope-chip">{{ k.scopes[0] }}</span>
                  <span v-if="k.scopes.length > 1" class="km-scope-chip km-scope-more">+ {{ k.scopes.length - 1 }}</span>
                </td>
                <td class="km-tact">{{ fmtRel(k.last_used_at) }}</td>
                <td class="km-num">{{ k.total_calls }}<span v-if="k.failed_calls > 0" style="color: #A32D2D;"> · {{ k.failed_calls }} fail</span></td>
                <td>
                  <span class="km-pill" :style="{ color: keyStatusPill(k).color, background: keyStatusPill(k).bg }">
                    {{ keyStatusPill(k).label }}
                  </span>
                </td>
                <td>
                  <button v-if="!k.revoked_at" class="km-icon-btn" title="Отозвать" @click="revokeTarget = k">
                    <i class="ti ti-shield-x" aria-hidden="true"></i>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </template>

        <div v-else class="km-empty">
          <i class="ti ti-arrow-left" style="font-size: 18px; opacity: .3;" aria-hidden="true"></i>
          Выберите service account слева, чтобы увидеть его ключи
        </div>
      </div>
    </div>

    <!-- ───── Modal: create SA ───── -->
    <div v-if="showSaCreate" class="km-modal-bg" @click.self="showSaCreate = false">
      <div class="km-modal">
        <div class="km-modal-hd">Новый service account</div>
        <div class="km-modal-body">
          <div class="km-field">
            <label>Email (идентификатор)</label>
            <input v-model="newSa.email" type="email" placeholder="sa-minfin-reporting@uz-assets.uz"/>
          </div>
          <div class="km-field">
            <label>Имя · назначение</label>
            <input v-model="newSa.full_name" placeholder="МинФин · отчёты SAP→UzAssets"/>
          </div>
          <div class="km-field">
            <label>Описание</label>
            <textarea v-model="newSa.description" rows="2" placeholder="Контактное лицо, контракт, цель интеграции"></textarea>
          </div>
        </div>
        <div class="km-modal-footer">
          <button class="km-btn km-btn-ghost" @click="showSaCreate = false">Отмена</button>
          <button class="km-btn km-btn-primary" @click="createServiceAccount">Создать</button>
        </div>
      </div>
    </div>

    <!-- ───── Modal: create key ───── -->
    <div v-if="showKeyCreate" class="km-modal-bg" @click.self="showKeyCreate = false">
      <div class="km-modal" style="max-width: 640px;">
        <div class="km-modal-hd">Выпуск API ключа для {{ selectedSa?.full_name || selectedSa?.email }}</div>
        <div class="km-modal-body">
          <div class="km-field-grid">
            <div class="km-field">
              <label>Имя ключа</label>
              <input v-model="newKey.name" placeholder="Production · IFRS export"/>
            </div>
            <div class="km-field">
              <label>Окружение</label>
              <select v-model="newKey.environment">
                <option value="sandbox">Sandbox</option>
                <option value="production">Production</option>
              </select>
            </div>
            <div class="km-field">
              <label>Истекает</label>
              <input v-model="newKey.expires_at" type="datetime-local"/>
            </div>
            <div class="km-field">
              <label>Rate limit (req/мин)</label>
              <input v-model.number="newKey.rate_limit_per_minute" type="number" min="10" max="60000"/>
            </div>
          </div>
          <div class="km-field">
            <label>IP allowlist (CIDR через запятую)</label>
            <input v-model="newKey.ip_allowlist" placeholder="195.158.0.0/16, 84.54.96.32"/>
          </div>
          <div class="km-field">
            <label>Описание</label>
            <input v-model="newKey.description" placeholder="(необязательно)"/>
          </div>

          <div class="km-field">
            <label>Scopes · {{ newKey.scopes.size }} выбрано из {{ Object.values(scopesByModule).flat().length }}</label>
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
        <div class="km-modal-footer">
          <button class="km-btn km-btn-ghost" @click="showKeyCreate = false">Отмена</button>
          <button class="km-btn km-btn-primary" @click="submitKeyCreate">
            <i class="ti ti-key" aria-hidden="true"></i> Выпустить
          </button>
        </div>
      </div>
    </div>

    <!-- ───── Modal: plaintext token display ───── -->
    <div v-if="plaintextDisplay" class="km-modal-bg">
      <div class="km-modal" style="max-width: 580px;">
        <div class="km-modal-hd" style="background: linear-gradient(90deg, rgba(29,158,117,.1), transparent); color: #0F6E56;">
          <i class="ti ti-check" aria-hidden="true"></i> Ключ выпущен — сохраните токен СЕЙЧАС
        </div>
        <div class="km-modal-body">
          <div style="background: rgba(239,159,39,.08); border-left: 3px solid #EF9F27; padding: 9px 12px; border-radius: 0 5px 5px 0; font-size: 11.5px; color: #854F0B; margin-bottom: 12px;">
            <b>Полный токен показывается ОДИН раз.</b> После закрытия окна его восстановить нельзя — только выпустить новый.
          </div>
          <div class="km-token-box">
            <code>{{ plaintextDisplay.plaintext_token }}</code>
            <button class="km-btn km-btn-primary" @click="copyToken">
              <i class="ti ti-copy" aria-hidden="true"></i> Скопировать
            </button>
          </div>
          <div style="font-size: 10.5px; color: var(--color-text-tertiary); margin-top: 8px;">
            Префикс: <code>{{ plaintextDisplay.prefix }}</code> ·
            Scopes: {{ plaintextDisplay.scopes.length }} ·
            Env: {{ plaintextDisplay.environment }}
          </div>
        </div>
        <div class="km-modal-footer">
          <button class="km-btn km-btn-primary" @click="plaintextDisplay = null">Я сохранил — закрыть</button>
        </div>
      </div>
    </div>

    <!-- ───── Modal: revoke key ───── -->
    <div v-if="revokeTarget" class="km-modal-bg" @click.self="revokeTarget = null">
      <div class="km-modal">
        <div class="km-modal-hd" style="color: #A32D2D;">Отозвать ключ "{{ revokeTarget.name }}"</div>
        <div class="km-modal-body">
          <div style="font-size: 11.5px; color: var(--color-text-secondary); margin-bottom: 9px;">
            После отзыва все запросы с этим токеном начнут получать 401. Действие необратимо.
          </div>
          <div class="km-field">
            <label>Причина (для audit log)</label>
            <textarea v-model="revokeReason" rows="2" placeholder="Скомпрометирован / не используется / истек контракт..."></textarea>
          </div>
        </div>
        <div class="km-modal-footer">
          <button class="km-btn km-btn-ghost" @click="revokeTarget = null">Отмена</button>
          <button class="km-btn" style="background: #E24B4A; color: #fff;" @click="confirmRevoke">
            <i class="ti ti-shield-x" aria-hidden="true"></i> Отозвать
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.km-wrap { flex: 1; display: flex; flex-direction: column; background: var(--color-background-tertiary); }
.km-err {
  margin: 8px 18px;
  padding: 8px 12px;
  background: rgba(226,75,74,.08);
  border: 0.5px solid rgba(226,75,74,.3);
  color: #A32D2D;
  border-radius: 7px;
  font-size: 11.5px;
  display: flex; justify-content: space-between; align-items: center;
}
.km-err button { background: transparent; border: 0; color: #A32D2D; font-size: 16px; cursor: pointer; }

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
  color: #534AB7;
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
.km-add-primary:hover { background: #534AB7; }

.km-empty {
  padding: 40px 18px; text-align: center;
  color: var(--color-text-tertiary); font-size: 11.5px;
  display: flex; flex-direction: column; align-items: center; gap: 6px;
}

.km-sa-list { display: flex; flex-direction: column; }
.km-sa-row {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  border-left: 3px solid transparent;
  border-bottom: 0.5px solid rgba(0,0,0,.04);
}
.km-sa-row:hover { background: rgba(127,119,221,.04); }
.km-sa-row.active { background: rgba(127,119,221,.08); border-left-color: #7F77DD; }
.km-sa-row.inactive { opacity: .55; }
.km-sa-avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: rgba(127,119,221,.15);
  color: #534AB7;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10.5px; font-weight: 600;
}
.km-sa-info { flex: 1; min-width: 0; }
.km-sa-name {
  font-size: 12px; color: var(--color-text-primary); font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.km-sa-meta { font-size: 10px; color: var(--color-text-tertiary); margin-top: 1px; display: flex; gap: 6px; }
.km-sa-disabled { background: rgba(226,75,74,.1); color: #A32D2D; padding: 0 5px; border-radius: 3px; font-weight: 500; }

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
  background: #FAFAFC;
  border-bottom: 0.5px solid var(--color-border-tertiary);
}
.km-key-row td {
  padding: 9px 10px;
  font-size: 11.5px;
  border-bottom: 0.5px solid rgba(0,0,0,.04);
}
.km-key-row { border-left: 3px solid transparent; }
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
  background: rgba(127,119,221,.08); color: #534AB7;
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
.km-icon-btn:hover { color: #A32D2D; }

/* ─── Modals ─── */
.km-modal-bg {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(15,18,40,.45); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.km-modal {
  background: var(--color-background-primary);
  width: 100%; max-width: 440px;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  animation: kmIn .35s cubic-bezier(.34,1.2,.64,1);
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
.km-modal-body { padding: 14px 18px; display: flex; flex-direction: column; gap: 10px; max-height: 60vh; overflow-y: auto; }
.km-modal-footer {
  padding: 11px 18px;
  background: #FAFAFC;
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
.km-scope-opt.on code { color: #534AB7; font-weight: 500; }

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
.km-btn-primary:hover { background: #534AB7; }

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
</style>
