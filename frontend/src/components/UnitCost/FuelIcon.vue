<script setup lang="ts">
/** FuelIcon — SVG-иконка вида энергоносителя (без эмодзи). */
defineProps<{ fuel: string; size?: number }>();
</script>

<template>
  <svg :width="size || 15" :height="size || 15" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" class="fi">
    <!-- Электроэнергия — молния -->
    <polygon v-if="fuel === 'electricity'" points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    <!-- Природный газ — пламя -->
    <path v-else-if="fuel === 'gas'" d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z" />
    <!-- Керосин — самолет -->
    <path v-else-if="fuel === 'kerosene'" d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z" />
    <!-- Уголь — куб -->
    <path v-else-if="fuel === 'coal'" d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
    <!-- Дизель/мазут — капля -->
    <path v-else d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
  </svg>
</template>

<style scoped>
.fi { flex-shrink: 0; }
</style>
