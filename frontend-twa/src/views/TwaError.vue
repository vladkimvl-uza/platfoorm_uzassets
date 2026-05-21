<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";
const route  = useRoute();
const router = useRouter();
const message = (route.query.msg as string) || "Что-то пошло не так";
</script>

<template>
  <main class="flex flex-col items-center justify-center min-h-screen p-6 gap-4 text-center">
    <div class="w-12 h-12 rounded-full bg-uza-red/15 text-uza-red flex items-center justify-center text-2xl">!</div>
    <div class="font-medium">Ошибка</div>
    <p class="text-sm text-tg-hint max-w-sm">{{ message }}</p>
    <button
      @click="router.replace('/twa/login')"
      class="px-5 py-2 rounded-card bg-tg-button text-tg-button-text text-sm font-medium hover:opacity-90 transition"
    >Назад к входу</button>
  </main>
</template>
