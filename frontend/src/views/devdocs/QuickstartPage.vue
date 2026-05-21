<script setup lang="ts">
import { computed } from "vue";
import { useApiCatalogStore } from "@/stores/apiCatalog";

const catalog = useApiCatalogStore();

// Example: prefer GET /companies (list of SOEs)
const exampleEndpoint = computed(() => {
  if (!catalog.summary) return null;
  return catalog.summary.endpoints.find(
    e => e.method === "GET" && e.path === "/companies"
  ) || catalog.summary.endpoints.find(e => e.method === "GET");
});

const curlSnippet = computed(() => {
  if (!exampleEndpoint.value) return "# Loading example…";
  return [
    "curl -X GET 'https://platform.uz-assets.uz/api" + exampleEndpoint.value.path + "' \\",
    "  -H 'Authorization: Bearer <your_jwt>' \\",
    "  -H 'Accept: application/json'",
  ].join("\n");
});
</script>

<template>
  <article class="qs">
    <header class="qs-head">
      <h1 class="qs-h1">3 шага до первого запроса</h1>
      <p class="qs-sub">Получите токен, найдите endpoint, отправьте запрос.</p>
    </header>

    <ol class="qs-steps">
      <li class="qs-step">
        <div class="qs-num">1</div>
        <div>
          <div class="qs-step-h">Получите JWT-токен</div>
          <p class="qs-step-p">
            POST <code class="qs-code">/auth/login</code> с email и паролем. В ответе —
            <code class="qs-code">access_token</code> со сроком действия 30 мин.
            Также возвращается <code class="qs-code">refresh_token</code> для обновления.
            <RouterLink to="/api-docs/authentication" class="qs-link">Подробнее →</RouterLink>
          </p>
        </div>
      </li>

      <li class="qs-step">
        <div class="qs-num">2</div>
        <div>
          <div class="qs-step-h">Найдите нужный endpoint</div>
          <p class="qs-step-p">
            Откройте каталог endpoints в боковой панели. Можно фильтровать по модулю,
            HTTP методу и правам доступа. Каждая страница endpoint'а содержит описание
            параметров, схему ответа и code samples на 4 языках.
          </p>
        </div>
      </li>

      <li class="qs-step">
        <div class="qs-num">3</div>
        <div>
          <div class="qs-step-h">Отправьте запрос</div>
          <p class="qs-step-p">
            Добавьте header <code class="qs-code">Authorization: Bearer &lt;token&gt;</code>
            и сделайте HTTP запрос. Для тестирования есть «Try it out» прямо на странице
            endpoint'а — без необходимости писать клиент.
          </p>
        </div>
      </li>
    </ol>

    <section class="qs-example">
      <h2 class="qs-h2">Пример: получить список компаний портфеля</h2>
      <pre class="qs-snippet">{{ curlSnippet }}</pre>
      <p class="qs-resp">
        Ответ — JSON с массивом из 22 SOE: <code class="qs-code">id</code>, <code class="qs-code">code</code>,
        <code class="qs-code">name_ru</code>, <code class="qs-code">sector_id</code>,
        и базовая мета (сотрудники, год основания, директор).
      </p>
    </section>

    <section class="qs-next">
      <h2 class="qs-h2">Что дальше</h2>
      <div class="qs-next-grid">
        <RouterLink to="/api-docs/endpoints/companies" class="qs-card">
          <div class="qs-card-h">Каталог endpoints</div>
          <div class="qs-card-p">Полный список с описаниями и code samples</div>
        </RouterLink>
        <RouterLink to="/api-docs/authentication" class="qs-card">
          <div class="qs-card-h">Authentication</div>
          <div class="qs-card-p">JWT, refresh tokens, MFA, scopes</div>
        </RouterLink>
        <RouterLink to="/api-docs/rate-limits" class="qs-card">
          <div class="qs-card-h">Rate limits</div>
          <div class="qs-card-p">Лимиты по типу endpoint'а и обработка 429</div>
        </RouterLink>
        <RouterLink to="/api-docs/webhooks" class="qs-card">
          <div class="qs-card-h">Webhooks</div>
          <div class="qs-card-p">Push-уведомления о событиях в платформе</div>
        </RouterLink>
        <RouterLink to="/api-docs/sdk" class="qs-card">
          <div class="qs-card-h">SDK · TS + Python</div>
          <div class="qs-card-p">Готовые клиенты с типами и авто-аутентификацией</div>
        </RouterLink>
      </div>
    </section>
  </article>
</template>

<style scoped>
.qs { max-width: 760px; }
.qs-head { margin-bottom: 28px; }
.qs-h1 { font-size: 24px; font-weight: 500; letter-spacing: -0.01em; color: #1E2A4A; margin: 0; }
.qs-sub { font-size: 14px; color: #888780; margin-top: 6px; }
.qs-h2 { font-size: 15px; font-weight: 500; color: #1E2A4A; margin: 0 0 12px 0; letter-spacing: -0.01em; }

.qs-steps { list-style: none; padding: 0; margin: 0 0 32px 0; display: flex; flex-direction: column; gap: 18px; }
.qs-step  { display: grid; grid-template-columns: 36px 1fr; gap: 14px; align-items: flex-start; }
.qs-num   { width: 32px; height: 32px; border-radius: 50%; background: rgba(127,119,221,.12); color: #534AB7; font-weight: 600; display: flex; align-items: center; justify-content: center; font-size: 14px; }
.qs-step-h { font-size: 14px; font-weight: 500; color: #1E2A4A; margin-bottom: 4px; }
.qs-step-p { font-size: 13px; color: #444; line-height: 1.55; margin: 0; }

.qs-code { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 11.5px; background: rgba(127,119,221,.08); color: #534AB7; padding: 1px 5px; border-radius: 4px; }
.qs-link { color: #534AB7; text-decoration: none; margin-left: 6px; }
.qs-link:hover { text-decoration: underline; }

.qs-example { margin-bottom: 32px; }
.qs-snippet {
  background: #1E2A4A; color: #E2E8F0;
  border-radius: 10px;
  padding: 16px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 12px; line-height: 1.55;
  overflow-x: auto;
  margin: 0;
}
.qs-resp { font-size: 12.5px; color: #888780; margin-top: 10px; line-height: 1.5; }

.qs-next-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.qs-card {
  background: white;
  border: 0.5px solid #F1EFE8;
  border-radius: 10px;
  padding: 14px;
  text-decoration: none;
  transition: all 150ms;
}
.qs-card:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(15,23,60,.06); border-color: rgba(127,119,221,.3); }
.qs-card-h { font-size: 13px; font-weight: 500; color: #1E2A4A; }
.qs-card-p { font-size: 11.5px; color: #888780; margin-top: 4px; line-height: 1.45; }

@media (max-width: 700px) { .qs-next-grid { grid-template-columns: 1fr; } }
</style>
