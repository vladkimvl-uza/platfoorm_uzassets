<script setup lang="ts">
/**
 * Root mount point. Just renders the active route (Login or AppShell).
 *
 * NO WRAPPER DIV: a wrapper here would (a) impose its own width/height,
 * blocking AppShell's full-viewport flex layout, and (b) paint a background
 * over the UZA gradient that lives on <body> (see main.css).
 */
import { RouterView } from "vue-router";
import ToastContainer from "@/components/ToastContainer.vue";
import ConfirmHost from "@/components/ConfirmHost.vue";
import ScrollToTopButton from "@/components/ScrollToTopButton.vue";
import StickyAckModal from "@/components/broadcasts/StickyAckModal.vue";
import VersionUpdateBanner from "@/components/VersionUpdateBanner.vue";
import NotificationDetailModal from "@/components/notifications/NotificationDetailModal.vue";
import { useAuthStore } from "@/stores/auth";
import { computed } from "vue";

const auth = useAuthStore();
const isAuthed = computed(() => !!auth.accessToken && !!auth.user);
</script>

<template>
  <RouterView />
  <StickyAckModal v-if="isAuthed" />
  <ToastContainer />
  <ConfirmHost />
  <ScrollToTopButton />
  <VersionUpdateBanner />
  <NotificationDetailModal />
</template>
