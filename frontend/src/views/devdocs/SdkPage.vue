<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();

const lang = ref<"ts" | "python">("ts");
</script>

<template>
  <article class="dp">
    <h1 class="dp-h1">SDK</h1>
    <p class="dp-lead">
      {{ t('Официальные SDK для TypeScript и Python. Оба обёртывают REST API в типизированный клиент с авто-аутентификацией и обработкой ошибок. Контракт всегда в синхронизации с FastAPI — типы генерируются из OpenAPI на каждом backend-релизе.') }}
    </p>

    <div class="dp-tabs">
      <button class="dp-tab" :class="{ active: lang === 'ts' }" @click="lang = 'ts'">TypeScript</button>
      <button class="dp-tab" :class="{ active: lang === 'python' }" @click="lang = 'python'">Python</button>
    </div>

    <!-- TypeScript -->
    <template v-if="lang === 'ts'">
      <section class="dp-section">
        <h2 class="dp-h2">{{ t('Установка') }}</h2>
        <pre class="dp-code">{{ t('npm install @uzassets/sdk # или прямо из репо (пока не опубликовали) # import { UzAssetsClient } from "@/sdk";') }}</pre>
      </section>

      <section class="dp-section">
        <h2 class="dp-h2">{{ t('Использование') }}</h2>
        <pre class="dp-code">{{ t('import &#123; UzAssetsClient &#125; from "@uzassets/sdk"; const sdk = new UzAssetsClient(&#123; baseUrl: "https://platform.uz-assets.uz/api", token: () =&gt; localStorage.getItem("token"), // function = всегда свежий onUnauthorized: () =&gt; router.push("/login"), &#125;); // 22 портфельных компании const companies = await sdk.companies.list(); // MDM library — фильтрация по сектору const library = await sdk.library.list(&#123; sector: "mining" &#125;); for (const row of library.items) &#123; console.log(row.name_short, row.fields.revenue, row.fields.ebitda); &#125; // Inline edit с авто-роутингом по source_module await sdk.library.updateField(companyId, "rating_fitch", "BB+"); // Полный каталог endpoints const cat = await sdk.catalog.summary(); console.log(`${cat.total_endpoints} endpoints в ${cat.modules.length} модулях`);') }}</pre>
      </section>

      <section class="dp-section">
        <h2 class="dp-h2">{{ t('Обновление типов') }}</h2>
        <p>{{ t('Клиент использует hand-written ресурсы (для удобства). Если нужны полные типы для каждого endpoint\'а:') }}</p>
        <pre class="dp-code">{{ t('cd frontend npm run sdk:types # Генерирует src/sdk/types.generated.ts через openapi-typescript') }}</pre>
      </section>

      <section class="dp-section">
        <h2 class="dp-h2">{{ t('Обработка ошибок') }}</h2>
        <pre class="dp-code">{{ t('import &#123; UzAssetsApiError &#125; from "@uzassets/sdk"; try &#123; await sdk.library.updateField(id, "revenue", 1_000_000); &#125; catch (e) &#123; if (e instanceof UzAssetsApiError) &#123; if (e.status === 403) alert("Нет прав на запись"); if (e.status === 429) // back-off console.error(e.message, e.body); &#125; &#125;') }}</pre>
      </section>
    </template>

    <!-- Python -->
    <template v-else>
      <section class="dp-section">
        <h2 class="dp-h2">{{ t('Установка') }}</h2>
        <pre class="dp-code">{{ t('pip install -e ./sdk/python # или, когда будет опубликовано: pip install uzassets-sdk') }}</pre>
      </section>

      <section class="dp-section">
        <h2 class="dp-h2">Quickstart</h2>
        <pre class="dp-code">{{ t('from uzassets_sdk import UzAssetsClient with UzAssetsClient( base_url="https://platform.uz-assets.uz/api", token="&lt;your_jwt_here&gt;", ) as sdk: companies = sdk.companies.list() for c in companies: print(c["code"], c["name_short"]) library = sdk.library.list(sector="mining") for row in library["items"]: f = row["fields"] print(f"&#123;row[\'name_short\']:20s&#125; rev=&#123;f.get(\'revenue\')&#125; ebitda=&#123;f.get(\'ebitda\')&#125;") sdk.library.update_field( company_id="&lt;uuid&gt;", field_code="rating_fitch", value="BB+", reason="После Fitch upgrade announcement" )') }}</pre>
      </section>

      <section class="dp-section">
        <h2 class="dp-h2">{{ t('Полные типы Pydantic') }}</h2>
        <p>{{ t('Хотите полную типизацию для каждого endpoint\'а? Сгенерируйте клиент через openapi-python-client:') }}</p>
        <pre class="dp-code">{{ t('cd sdk/python pip install openapi-python-client ./generate.sh # Создаст uzassets_sdk_generated/ с Pydantic-моделями') }}</pre>
      </section>

      <section class="dp-section">
        <h2 class="dp-h2">{{ t('Обработка ошибок') }}</h2>
        <pre class="dp-code">{{ t('from uzassets_sdk import UzAssetsApiError try: sdk.library.update_field(id, "revenue", 1_000_000) except UzAssetsApiError as e: if e.status_code == 403: print("Нет прав") elif e.status_code == 429: time.sleep(2) # back-off else: print(e.status_code, e.message, e.body)') }}</pre>
      </section>
    </template>

    <section class="dp-section dp-section-also">
      <h2 class="dp-h2">{{ t('Альтернативы') }}</h2>
      <ul class="dp-list">
        <li><RouterLink to="/api-docs/endpoints/companies">{{ t('Прямой REST') }}</RouterLink> {{ t('— для одноразовых скриптов') }}</li>
        <li><a href="/api/api-catalog/postman.json" target="_blank">Postman collection</a> {{ t('— импорт коллекции в Postman, экспорт в окружения') }}</li>
        <li><a href="/api/api-catalog/openapi.json" target="_blank">OpenAPI JSON</a> {{ t('— для свободной кодогенерации (любой openapi-generator)') }}</li>
      </ul>
    </section>
  </article>
</template>

<style scoped>
.dp { max-width: 760px; }
.dp-h1 { font-size: 24px; font-weight: 500; color: var(--t1, #1E2A4A); letter-spacing: -0.01em; margin: 0 0 12px 0; }
.dp-h2 { font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 0 0 8px 0; }
.dp-lead { font-size: 14px; color: #444; line-height: 1.55; margin-bottom: 18px; }

.dp-tabs { display: flex; gap: 2px; margin-bottom: -1px; }
.dp-tab {
  background: transparent; border: 1px solid transparent;
  padding: 7px 18px; border-radius: 8px 8px 0 0;
  font-size: 12.5px; color: var(--t3, var(--t-muted)); cursor: pointer; font-weight: 500;
  transition: all 120ms;
}
.dp-tab:hover { color: var(--t1, #1E2A4A); }
.dp-tab.active { background: white; color: var(--t1, #1E2A4A); border-color: #F1EFE8; border-bottom-color: white; }

.dp-section { margin-bottom: 22px; padding: 18px 20px; background: white; border: 0.5px solid #F1EFE8; border-radius: 0 12px 12px 12px; }
.dp-section:not(:first-of-type) { border-radius: 12px; }
.dp-section-also { background: rgba(127,119,221,.04); border-color: rgba(127,119,221,.18); }
.dp-section p { font-size: 13px; color: #444; line-height: 1.55; margin: 6px 0; }
.dp-list { padding-left: 20px; font-size: 13px; color: #444; line-height: 1.7; }
.dp-list a { color: var(--p-deep); text-decoration: none; }
.dp-list a:hover { text-decoration: underline; }

.dp-code {
  background: #1E2A4A; color: var(--border-input);
  padding: 14px 16px; border-radius: 10px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 12px; line-height: 1.55;
  overflow-x: auto;
  margin: 8px 0 0 0;
  white-space: pre-wrap; word-wrap: break-word;
}
</style>
