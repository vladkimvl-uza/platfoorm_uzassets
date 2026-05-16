<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <div class="min-h-screen flex items-center justify-center">
    <div class="text-center">
      <div class="uza-section-label">404</div>
      <h1 class="text-[15px] font-medium tracking-uza-snug mt-2">Страница не найдена</h1>
      <RouterLink
        to="/"
        class="inline-block mt-6 px-4 py-2 bg-uza-navy text-white rounded-uza-pill text-sm"
      >
        На главную
      </RouterLink>
    </div>
  </div>
</template>
