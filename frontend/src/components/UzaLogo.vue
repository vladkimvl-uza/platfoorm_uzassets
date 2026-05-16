<script setup lang="ts">
/**
 * UzaLogo — UzAssets brand mark (image-based, served from /uzassets-logo.png).
 * Pack 13.3.2: replaced the hand-drawn SVG approximation with the real logo.
 */
withDefaults(defineProps<{
  size?: number | string;
}>(), {
  size: 32,
});
</script>

<template>
  <img
    src="/uzassets-logo.png"
    :width="size"
    :height="size"
    alt="UzAssets"
    class="uza-logo"
  />
</template>

<style scoped>
.uza-logo {
  display: inline-block;
  object-fit: contain;
  user-select: none;
}
</style>