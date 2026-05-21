<script setup lang="ts">
/**
 * TWA: list of moderation submissions awaiting MY review.
 *
 * Tap a row → /twa/approve/:id (universal) or /twa/procurement/:id (rich card).
 * BackButton returns to /twa/.
 */
import { onMounted, onBeforeUnmount, ref } from "vue";
import { useRouter } from "vue-router";
import { moderationApi, moduleLabel, type ModSubmission } from "@/api/moderation";
import { useTelegramWebApp } from "@/composables/useTelegramWebApp";

const router = useRouter();
const tg = useTelegramWebApp();

const items = ref<ModSubmission[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const data = await moderationApi.queue({
      status: ["pending", "in_review"],
      assignedToMe: true,
      per_page: 50,
    });
    items.value = data.items;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить очередь";
  } finally {
    loading.value = false;
  }
}

function openRow(it: ModSubmission) {
  tg.haptics?.selectionChanged();
  if (it.target_module === "procurement") {
    router.push(`/twa/procurement/${it.id}`);
  } else {
    router.push(`/twa/approve/${it.id}`);
  }
}

function fmtWhen(iso: string): string {
  try {
    const d = new Date(iso);
    const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
    if (diffMin < 1) return "только что";
    if (diffMin < 60) return `${diffMin} мин назад`;
    const h = Math.floor(diffMin / 60);
    if (h < 24) return `${h} ч назад`;
    return `${Math.floor(h / 24)} дн назад`;
  } catch { return ""; }
}

function onBack() {
  router.push("/twa/");
}

onMounted(() => {
  tg.setHeaderColor("#1E2A4A");
  tg.backButton?.show();
  tg.backButton?.onClick(onBack);
  load();
});

onBeforeUnmount(() => {
  tg.backButton?.offClick(onBack);
  tg.backButton?.hide();
});
</script>

<template>
  <main class="flex flex-col gap-3 p-4 min-h-screen">
    <header class="flex items-center justify-between">
      <div>
        <div class="text-[11px] uppercase tracking-wider text-tg-hint">UzAssets · Модерация</div>
        <h1 class="text-lg font-medium">На моей очереди</h1>
      </div>
      <button
        @click="load"
        class="text-[11px] text-tg-hint hover:text-tg-text px-2 py-1 rounded transition"
        title="Обновить"
      >↻</button>
    </header>

    <div v-if="loading" class="text-center text-sm text-tg-hint py-8">Загрузка…</div>

    <div v-else-if="error" class="text-sm text-uza-red bg-uza-red/10 rounded-card p-3">
      {{ error }}
    </div>

    <div v-else-if="items.length === 0" class="text-center text-sm text-tg-hint py-12">
      <div class="text-4xl mb-2 opacity-30">∅</div>
      Очередь пуста. Заявки появятся здесь, когда вы будете назначены модератором.
    </div>

    <ul v-else class="flex flex-col gap-2">
      <li
        v-for="it in items"
        :key="it.id"
        class="rounded-card bg-tg-secondary-bg p-3 cursor-pointer transition active:scale-[0.98] hover:bg-tg-secondary-bg/80 border-l-2"
        :class="it.target_module === 'procurement' ? 'border-uza-blue' : 'border-uza-purple'"
        @click="openRow(it)"
      >
        <div class="flex items-baseline justify-between gap-2">
          <div class="text-[10px] uppercase tracking-wider text-tg-hint font-medium">
            {{ moduleLabel(it.target_module) }} · {{ it.target_action }}
          </div>
          <div class="text-[10px] text-tg-hint">{{ fmtWhen(it.created_at) }}</div>
        </div>
        <div class="mt-1 text-sm font-medium leading-tight truncate">
          {{ it.target_entity_label || it.field_path || it.target_entity_id || "(без названия)" }}
        </div>
        <div v-if="it.proposer_name || it.proposer_email" class="mt-0.5 text-[11px] text-tg-hint">
          От <b class="text-tg-text font-medium">{{ it.proposer_name || it.proposer_email }}</b>
        </div>
        <div v-if="it.reason" class="mt-1 text-[11px] text-tg-hint italic line-clamp-2">
          {{ it.reason }}
        </div>
      </li>
    </ul>
  </main>
</template>
