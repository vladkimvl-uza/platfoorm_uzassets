<script setup lang="ts">
import { onMounted } from "vue";
import { useTelegramWebApp } from "@/composables/useTelegramWebApp";

const tg = useTelegramWebApp();

onMounted(() => {
  tg.ready();
  tg.expand();
});
</script>

<template>
  <RouterView v-slot="{ Component }">
    <Transition name="twa-fade" mode="out-in">
      <component :is="Component" />
    </Transition>
  </RouterView>
</template>
