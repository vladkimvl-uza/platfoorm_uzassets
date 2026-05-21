<script setup lang="ts">
/**
 * TWA mini-dashboard (Phase C).
 *
 * Shows 4 tile counts + a CTA to open the full platform in browser.
 * Data comes from /dashboard (existing endpoint) — graceful fallback to
 * zeros if the request fails.
 */
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useTelegramWebApp } from "@/composables/useTelegramWebApp";
import { useTwaAuth } from "@/composables/useTwaAuth";
import { api } from "@/api/client";
import { moderationApi } from "@/api/moderation";

const tg     = useTelegramWebApp();
const auth   = useTwaAuth();
const router = useRouter();

interface DashSummary {
  projects_total: number;
  projects_done:  number;
  tasks_total:    number;
  tasks_overdue:  number;
}
const dash = ref<DashSummary>({ projects_total: 0, projects_done: 0, tasks_total: 0, tasks_overdue: 0 });
const myModerationPending = ref(0);
const loading = ref(true);
const error = ref<string | null>(null);

const PLATFORM_URL =
  (import.meta.env.VITE_PLATFORM_URL as string) || "https://platform.uz-assets.uz";

async function load() {
  loading.value = true;
  error.value = null;
  try {
    // Parallel: dashboard counts + moderation queue size assigned to me
    const [dashRes, modRes] = await Promise.allSettled([
      api.get("/dashboard"),
      moderationApi.queue({ status: ["pending", "in_review"], assignedToMe: true, per_page: 1 }),
    ]);

    if (dashRes.status === "fulfilled") {
      const data = dashRes.value.data;
      dash.value = {
        projects_total: data?.projects_total ?? data?.projects?.total ?? 0,
        projects_done:  data?.projects_done  ?? data?.projects?.done  ?? 0,
        tasks_total:    data?.tasks_total    ?? data?.tasks?.total    ?? 0,
        tasks_overdue:  data?.tasks_overdue  ?? data?.tasks?.overdue  ?? 0,
      };
    }
    if (modRes.status === "fulfilled") {
      myModerationPending.value = modRes.value.total;
    }
    if (dashRes.status === "rejected" && modRes.status === "rejected") {
      error.value = (dashRes.reason as any)?.response?.data?.detail
                 || (dashRes.reason as any)?.message || "Не удалось загрузить данные";
    }
  } finally {
    loading.value = false;
  }
}

function openTaskList() {
  tg.haptics?.selectionChanged();
  router.push("/twa/tasks");
}

function openFullPlatform() {
  tg.haptics?.impactOccurred("light");
  tg.openLink(PLATFORM_URL);
}

function logout() {
  auth.logout();
  location.href = "/twa/login";
}

onMounted(() => {
  tg.setHeaderColor("#1E2A4A");
  load();
});
</script>

<template>
  <main class="flex flex-col gap-4 p-4 min-h-screen">
    <!-- Hero header -->
    <header class="flex items-center justify-between">
      <div>
        <div class="text-[11px] uppercase tracking-wider text-tg-hint">UzAssets</div>
        <h1 class="text-lg font-medium">{{ tg.user?.first_name || "Добро пожаловать" }}</h1>
      </div>
      <button
        @click="logout"
        class="text-[11px] text-tg-hint hover:text-tg-text px-2 py-1 rounded transition"
      >Выйти</button>
    </header>

    <!-- KPI tiles -->
    <section class="grid grid-cols-2 gap-3">
      <div class="rounded-card bg-tg-secondary-bg p-4">
        <div class="text-[10px] uppercase tracking-wider text-tg-hint">Проектов</div>
        <div class="mt-1 text-2xl font-medium tabular-nums">{{ dash.projects_total }}</div>
        <div class="text-[11px] text-uza-green mt-1">{{ dash.projects_done }} завершено</div>
      </div>
      <div class="rounded-card bg-tg-secondary-bg p-4">
        <div class="text-[10px] uppercase tracking-wider text-tg-hint">Задач</div>
        <div class="mt-1 text-2xl font-medium tabular-nums">{{ dash.tasks_total }}</div>
        <div
          class="text-[11px] mt-1"
          :class="dash.tasks_overdue > 0 ? 'text-uza-red' : 'text-uza-green'"
        >
          {{ dash.tasks_overdue > 0 ? `${dash.tasks_overdue} просрочено` : "в графике" }}
        </div>
      </div>
    </section>

    <!-- Loading / error states -->
    <div v-if="loading" class="text-center text-sm text-tg-hint py-2">Загрузка…</div>
    <div v-if="error" class="text-center text-sm text-uza-red bg-uza-red/10 rounded-card p-3">
      {{ error }}
    </div>

    <!-- Quick actions -->
    <section class="flex flex-col gap-2 mt-2">
      <button
        @click="openTaskList"
        class="w-full rounded-card bg-tg-secondary-bg py-3 px-4 text-sm font-medium flex items-center justify-between transition active:scale-[0.99] border-l-2 border-uza-purple"
      >
        <span>На модерации</span>
        <span
          v-if="myModerationPending > 0"
          class="bg-uza-red text-white text-[10px] font-semibold px-2 py-0.5 rounded-full tabular-nums"
        >{{ myModerationPending }}</span>
        <span v-else class="text-tg-hint text-[11px]">пусто</span>
      </button>

      <button
        @click="openFullPlatform"
        class="w-full rounded-card bg-tg-button text-tg-button-text py-3 text-sm font-medium hover:opacity-90 transition flex items-center justify-center gap-2"
      >
        Полная версия в браузере →
      </button>

      <p class="text-[11px] text-tg-hint text-center mt-1">
        Быстрые действия — здесь. Глубокое редактирование — в браузере.
      </p>
    </section>
  </main>
</template>
