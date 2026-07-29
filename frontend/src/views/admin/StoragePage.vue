<script setup lang="ts">
/**
 * Admin → Хранилище файлов: статус backend'а + smoke test + inline guide.
 *
 * Конфигурация storage делается через env vars (см. docs/S3_SETUP.md),
 * этот UI только показывает текущее состояние и позволяет проверить
 * подключение.
 */
import { ref, onMounted, computed } from "vue";
import { api } from "@/api/client";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


interface StorageStatus {
  config: {
    backend: string;
    local_root: string;
    s3_endpoint: string;
    s3_bucket: string;
    s3_region: string;
    s3_access_key: string;
    s3_force_path_style: boolean;
    s3_sse: string;
  };
  backend_class: string;
  init_ok: boolean;
  init_error: string | null;
  now: string;
}

interface TestStep {
  step: string;
  ok: boolean;
  ms: number;
  error: string | null;
  [k: string]: any;
}

const status = ref<StorageStatus | null>(null);
const testResult = ref<{ ok: boolean; steps: TestStep[]; key: string } | null>(null);
const loading = ref(false);
const testing = ref(false);
const error = ref<string | null>(null);
const guideOpen = ref(false);

async function loadStatus() {
  loading.value = true;
  error.value = null;
  try {
    const { data } = await api.get<StorageStatus>("/admin/storage/status");
    status.value = data;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Ошибка загрузки');
  } finally {
    loading.value = false;
  }
}

async function runTest() {
  testing.value = true;
  testResult.value = null;
  try {
    const { data } = await api.post("/admin/storage/test");
    testResult.value = data;
  } catch (e: any) {
    testResult.value = {
      ok: false,
      steps: [{ step: "request", ok: false, ms: 0, error: e?.response?.data?.detail || t("Сбой запроса") }],
      key: "",
    };
  } finally {
    testing.value = false;
  }
}

onMounted(loadStatus);

const isS3 = computed(() => status.value?.config?.backend === "s3");
const isLocal = computed(() => status.value?.config?.backend === "local");
</script>

<template>
  <div class="stg-page">
    <header class="stg-header">
      <div>
        <div class="stg-eyebrow">{{ t('Администрирование') }}</div>
        <h1 class="stg-title">{{ t('Хранилище файлов') }}</h1>
        <p class="stg-sub">{{ t('Backend для вложений к задачам, проектам, документам компаний') }}</p>
      </div>
      <div class="stg-actions">
        <button class="stg-btn-ghost" @click="guideOpen = !guideOpen">
          {{ guideOpen ? t('× Закрыть инструкцию') : t('? Как подключить S3') }}
        </button>
        <button class="stg-btn-ghost" @click="loadStatus" :disabled="loading">{{ t('↻ Обновить') }}</button>
      </div>
    </header>

    <div v-if="error" class="stg-state stg-state-err">{{ error }}</div>

    <!-- ════════ STATUS ════════ -->
    <section v-if="status" class="stg-card">
      <div class="stg-card-head">
        <span class="stg-card-ttl">{{ t('Текущее состояние') }}</span>
        <span class="stg-status-chip" :class="{ ok: status.init_ok, err: !status.init_ok }">
          {{ status.init_ok ? t('● работает') : t('● ошибка') }}
        </span>
      </div>

      <div class="stg-grid">
        <div class="stg-row">
          <span class="stg-k">Backend</span>
          <span class="stg-v">
            <span class="stg-badge" :class="{ 's3': isS3, 'local': isLocal }">
              {{ status.config.backend.toUpperCase() }}
            </span>
            <code class="stg-mono">{{ status.backend_class }}</code>
          </span>
        </div>

        <template v-if="isLocal">
          <div class="stg-row">
            <span class="stg-k">{{ t('Папка') }}</span>
            <span class="stg-v"><code class="stg-mono">{{ status.config.local_root }}</code></span>
          </div>
          <div class="stg-row stg-row-hint">
            <span class="stg-k"></span>
            <span class="stg-v stg-hint">
              {{ t('⚠ Файлы хранятся локально в Docker volume') }} <code>backend_uploads</code>{{ t('. Не масштабируется; для production переключи на S3 (см. инструкцию).') }}
            </span>
          </div>
        </template>

        <template v-if="isS3">
          <div class="stg-row">
            <span class="stg-k">Endpoint</span>
            <span class="stg-v"><code class="stg-mono">{{ status.config.s3_endpoint || '(AWS default)' }}</code></span>
          </div>
          <div class="stg-row">
            <span class="stg-k">Bucket</span>
            <span class="stg-v"><code class="stg-mono">{{ status.config.s3_bucket }}</code></span>
          </div>
          <div class="stg-row">
            <span class="stg-k">Region</span>
            <span class="stg-v"><code class="stg-mono">{{ status.config.s3_region }}</code></span>
          </div>
          <div class="stg-row">
            <span class="stg-k">Access Key</span>
            <span class="stg-v"><code class="stg-mono">{{ status.config.s3_access_key || '—' }}</code></span>
          </div>
          <div class="stg-row">
            <span class="stg-k">Path-style</span>
            <span class="stg-v">{{ status.config.s3_force_path_style ? t('Да (MinIO/uzcloud)') : t('Нет (AWS native)') }}</span>
          </div>
          <div class="stg-row">
            <span class="stg-k">Server-side encryption</span>
            <span class="stg-v">{{ status.config.s3_sse || '—' }}</span>
          </div>
        </template>

        <div v-if="!status.init_ok" class="stg-row stg-row-hint">
          <span class="stg-k">{{ t('Ошибка init') }}</span>
          <span class="stg-v stg-err">{{ status.init_error }}</span>
        </div>
      </div>
    </section>

    <!-- ════════ SMOKE TEST ════════ -->
    <section class="stg-card">
      <div class="stg-card-head">
        <span class="stg-card-ttl">Smoke-test</span>
        <button class="stg-btn-primary" @click="runTest" :disabled="testing">
          {{ testing ? t('Тест…') : t('▶ Запустить') }}
        </button>
      </div>
      <p class="stg-hint">
        {{ t('Загружает тестовый файл в storage, скачивает его обратно, генерирует signed URL, затем удаляет. Использует тот же код-путь, что и реальные attachments.') }}
      </p>

      <div v-if="testResult" class="stg-test-result">
        <div class="stg-test-summary" :class="{ ok: testResult.ok, err: !testResult.ok }">
          {{ testResult.ok ? t('✓ Все шаги прошли') : t('✗ Часть шагов упала') }}
        </div>
        <div v-if="testResult.key" class="stg-test-key">
          <span class="stg-k">{{ t('Ключ объекта') }}</span>
          <code class="stg-mono">{{ testResult.key }}</code>
        </div>
        <table class="stg-test-table">
          <thead>
            <tr>
              <th>{{ t('Шаг') }}</th>
              <th>{{ t('Результат') }}</th>
              <th>{{ t('Время') }}</th>
              <th>{{ t('Детали / ошибка') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(s, i) in testResult.steps" :key="i" :class="{ 'row-err': !s.ok }">
              <td><code>{{ s.step }}</code></td>
              <td>{{ s.ok ? '✓' : '✗' }}</td>
              <td class="num">{{ s.ms }} ms</td>
              <td>
                <span v-if="s.error" class="stg-err">{{ s.error }}</span>
                <span v-else class="stg-test-detail">
                  <template v-if="s.step === 'upload' && s.size">size: {{ s.size }} bytes</template>
                  <template v-if="s.step === 'download' && s.match !== undefined">match: {{ s.match ? t('да') : t('нет') }}</template>
                  <template v-if="s.step === 'signed_url' && s.sample">URL: <code>{{ s.sample }}</code></template>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ════════ INLINE GUIDE ════════ -->
    <section v-if="guideOpen" class="stg-card stg-guide">
      <div class="stg-card-head">
        <span class="stg-card-ttl">{{ t('Как подключить S3 / uzcloud Object Storage') }}</span>
      </div>

      <ol class="stg-steps">
        <li>
          <b>{{ t('Создай bucket') }}</b> {{ t('в') }} <a href="https://console.uzcloud.uz/" target="_blank" rel="noopener">uzcloud Object Storage</a>:
          <ul>
            <li>{{ t('Имя:') }} <code>uzassets-platform-prod</code></li>
            <li>{{ t('Регион:') }} <code>tashkent-1</code></li>
            <li><b>Public access: BLOCKED</b> {{ t('— все скачивания через signed URLs') }}</li>
            <li>Versioning + Server-side encryption (AES256)</li>
          </ul>
        </li>
        <li>
          <b>{{ t('Создай IAM-user') }}</b> {{ t('с минимальными правами (S3 RW на этот bucket). Сохрани') }} <code>Access Key ID</code> + <code>Secret Access Key</code>.
        </li>
        <li>
          <b>{{ t('Добавь env vars') }}</b> {{ t('в') }} <code>backend/.env.uzassets006</code>:
          <pre>STORAGE_BACKEND=s3
STORAGE_S3_ENDPOINT_URL=https://s3.uzcloud.uz
STORAGE_S3_BUCKET=uzassets-platform-prod
STORAGE_S3_REGION=tashkent-1
STORAGE_S3_ACCESS_KEY=AKIAxxxxxxxxxxxxxxxx
STORAGE_S3_SECRET_KEY=*****************************
STORAGE_S3_FORCE_PATH_STYLE=true
STORAGE_S3_SSE=AES256</pre>
        </li>
        <li>
          <b>Recreate backend container</b>:
          <pre>docker compose --project-directory . \
  --env-file backend/.env.uzassets006 \
  -f backend/docker-compose.yml \
  up -d --force-recreate backend</pre>
        </li>
        <li>
          <b>Verify</b>{{ t(': вернись на эту страницу, нажми «↻ Обновить» — backend поменяется на') }} <code>S3</code>{{ t('. Затем нажми «▶ Запустить» smoke-test — все 4 шага должны быть ✓.') }}
        </li>
      </ol>

      <p class="stg-hint">
        {{ t('Полный гайд (включая резервное копирование через cross-region replication, миграцию существующих файлов с local на S3, troubleshooting):') }}
        <code>docs/S3_SETUP.md</code> {{ t('в репозитории.') }}
      </p>
    </section>
  </div>
</template>

<style scoped>
.stg-page { padding: 24px 28px; max-width: 1100px; margin: 0 auto; font-family: -apple-system, system-ui, sans-serif; }
.stg-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; margin-bottom: 22px; flex-wrap: wrap; }
.stg-eyebrow { font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .08em; }
.stg-title { font-size: 24px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 4px 0 2px; letter-spacing: -.01em; }
.stg-sub { font-size: 13px; color: var(--t3, var(--t-muted)); margin: 0; }
.stg-actions { display: flex; gap: 8px; }
.stg-btn-ghost {
  padding: 7px 12px; border-radius: 8px;
  background: transparent; border: 0.5px solid var(--border-hard); color: var(--t3, var(--t-muted));
  font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit;
}
.stg-btn-ghost:hover { border-color: #7F77DD; color: var(--p-deep); }
.stg-btn-primary {
  padding: 6px 14px; border-radius: 8px; border: none;
  background: #7F77DD; color: white; font-size: 11.5px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.stg-btn-primary:hover { background: #6E66D0; }
.stg-btn-primary:disabled { opacity: 0.55; cursor: wait; }

.stg-card {
  background: white; border: 0.5px solid var(--border-hard); border-radius: 14px;
  padding: 18px 22px; margin-bottom: 16px;
}
.stg-card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.stg-card-ttl { font-size: 14px; font-weight: 500; color: var(--t1, #1E2A4A); }
.stg-status-chip {
  font-size: 11px; font-weight: 500; padding: 3px 10px; border-radius: 8px;
}
.stg-status-chip.ok { background: rgba(29, 158, 117, .12); color: #0F6E56; }
.stg-status-chip.err { background: rgba(226, 75, 74, .12); color: #B91C1C; }

.stg-grid { display: flex; flex-direction: column; gap: 6px; }
.stg-row { display: grid; grid-template-columns: 220px 1fr; gap: 12px; padding: 6px 0; }
.stg-k { font-size: 11px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .04em; }
.stg-v { font-size: 12.5px; color: var(--t1, #1E2A4A); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.stg-row-hint { padding-top: 4px; }
.stg-hint { font-size: 11.5px; color: var(--t3, var(--t-muted)); font-style: italic; }
.stg-err { color: var(--sev-high); }
.stg-mono { font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: 11.5px; background: #F3F4F8; padding: 2px 6px; border-radius: 4px; }

.stg-badge {
  display: inline-block; padding: 2px 8px; border-radius: 5px;
  font-size: 10.5px; font-weight: 600; letter-spacing: .03em;
}
.stg-badge.s3 { background: rgba(127, 119, 221, .14); color: var(--p-deep); }
.stg-badge.local { background: rgba(239, 159, 39, .14); color: #B27015; }

.stg-test-result { margin-top: 14px; padding-top: 12px; border-top: 0.5px solid #F0F0F4; }
.stg-test-summary {
  font-size: 12.5px; font-weight: 500; padding: 8px 12px; border-radius: 7px; margin-bottom: 12px;
}
.stg-test-summary.ok { background: rgba(29, 158, 117, .10); color: #0F6E56; }
.stg-test-summary.err { background: rgba(226, 75, 74, .10); color: #B91C1C; }
.stg-test-key { display: flex; gap: 12px; margin-bottom: 10px; align-items: center; }
.stg-test-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.stg-test-table th { text-align: left; padding: 6px 8px; color: var(--t3, var(--t-muted)); font-weight: 500; font-size: 10.5px; text-transform: uppercase; letter-spacing: .04em; border-bottom: 0.5px solid var(--border-hard); }
.stg-test-table td { padding: 8px; border-bottom: 0.5px solid #F0F0F4; }
.stg-test-table td.num { font-family: ui-monospace, monospace; text-align: right; color: var(--p-deep); }
.stg-test-table tr.row-err { background: rgba(226, 75, 74, .04); }
.stg-test-detail { font-size: 11px; color: var(--p-deep); }

.stg-state { padding: 30px; text-align: center; font-size: 13px; color: var(--t3, var(--t-muted)); }
.stg-state-err { color: var(--sev-high); }

.stg-guide ol.stg-steps {
  margin: 0; padding-left: 22px; counter-reset: stg-step;
}
.stg-guide li {
  margin-bottom: 14px; padding-left: 6px; font-size: 13px; color: var(--t1, #1E2A4A);
}
.stg-guide ul { margin: 8px 0; padding-left: 20px; font-size: 12.5px; }
.stg-guide ul li { margin-bottom: 4px; }
.stg-guide pre {
  background: #1E2A4A; color: var(--border-hard);
  padding: 12px 14px; border-radius: 8px;
  font-family: ui-monospace, monospace; font-size: 11.5px;
  white-space: pre-wrap; overflow-x: auto;
  margin: 8px 0;
}
.stg-guide code { font-family: ui-monospace, monospace; font-size: 11.5px; background: #F3F4F8; padding: 1px 6px; border-radius: 4px; color: var(--t1, #1E2A4A); }
.stg-guide pre code { background: transparent; padding: 0; color: inherit; }
.stg-guide a { color: var(--p-deep); text-decoration: none; }
.stg-guide a:hover { text-decoration: underline; }
</style>
