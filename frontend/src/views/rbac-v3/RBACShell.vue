<script setup lang="ts">
/**
 * RBAC v3 — top-level shell. Renders topbar with 4 tab links and
 * <router-view /> for the active child route.
 */
import { computed, inject } from 'vue';
import { useRouter, useRoute } from 'vue-router';

const router = useRouter();
const route = useRoute();
const toggleSidebar = inject<() => void>('toggleSidebar', () => {});

const TABS = [
  { name: 'rbac-v3-users',  label: 'Пользователи' },
  { name: 'rbac-v3-roles',  label: 'Роли' },
  { name: 'rbac-v3-groups', label: 'Группы' },
  { name: 'rbac-v3-audit',  label: 'Аудит' },
];
const activeTab = computed(() => route.name as string);
function goTab(name: string) { router.push({ name }); }

import { ref as _ref } from 'vue';
import InviteUserModal from '@/components/rbac-v3/InviteUserModal.vue';
const showInvite = _ref(false);
function onUserCreated(userId: string) {
  // Notify UsersPage to refresh
  window.dispatchEvent(new CustomEvent('rbac-v3:users-changed', { detail: { id: userId } }));
}
</script>

<template>
  <div class="rv3-shell">
    <div class="rv3-topbar">
      <div class="rv3-tb-l">
        <button class="rv3-sb-toggle" @click="toggleSidebar()" aria-label="toggle sidebar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <div class="rv3-tabs">
          <button
            v-for="t in TABS"
            :key="t.name"
            :class="['rv3-tab', { on: activeTab === t.name }]"
            @click="goTab(t.name)"
          >{{ t.label }}</button>
        </div>
      </div>
      <div class="rv3-tb-c">
        <div class="rv3-tb-eyebrow">UzAssets · Администрирование</div>
        <div class="rv3-tb-title">Управление доступом · v3</div>
      </div>
      <div class="rv3-tb-r">
        <button
          v-if="activeTab === 'rbac-v3-users'"
          class="rv3-invite-btn"
          @click="showInvite = true"
          aria-label="invite"
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="3" x2="8" y2="13"/><line x1="3" y1="8" x2="13" y2="8"/></svg>
          Пригласить
        </button>
        <span class="rv3-new-badge">NEW</span>
      </div>
    </div>
    <div class="rv3-content">
      <router-view />
    </div>
    <InviteUserModal
      v-if="showInvite"
      @close="showInvite = false"
      @created="onUserCreated"
    />
  </div>
</template>

<style scoped>
.rv3-shell { display: flex; flex-direction: column; min-height: 100vh; background: #F4F3F9; }
.rv3-topbar {
  display: grid; grid-template-columns: auto 1fr auto;
  grid-template-rows: 56px;
  align-items: center; gap: 16px;
  padding: 0 24px;
  background: linear-gradient(180deg, #1E2A4A 0%, #1A2440 100%);
  color: #fff;
  border-bottom: 0.5px solid rgba(255,255,255,0.06);
  position: sticky; top: 0; z-index: 10;
}
.rv3-tb-l { display: flex; align-items: center; gap: 12px; }
.rv3-tb-c { display: flex; flex-direction: column; align-items: center; gap: 1px; min-width: 0; text-align: center; }
.rv3-tb-r { justify-self: end; display: flex; align-items: center; gap: 8px; }
.rv3-tb-eyebrow {
  font-size: 9.5px; font-weight: 500; letter-spacing: .1em;
  text-transform: uppercase; color: rgba(255,255,255,.5);
}
.rv3-tb-title { font-size: 15px; font-weight: 500; letter-spacing: -.01em; }
.rv3-sb-toggle {
  width: 32px; height: 32px;
  border: 1px solid rgba(255,255,255,.15);
  background: rgba(255,255,255,.06);
  border-radius: 8px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: rgba(255,255,255,.7); transition: all .15s; padding: 0;
}
.rv3-sb-toggle:hover { background: rgba(255,255,255,.14); color: #fff; }
.rv3-tabs {
  display: flex; background: rgba(255,255,255,.06);
  border-radius: 8px; padding: 2px;
  font-size: 12px; font-weight: 500;
}
.rv3-tab {
  padding: 5px 14px; border-radius: 6px;
  background: transparent; border: none;
  color: rgba(255,255,255,.55); cursor: pointer;
  font-family: inherit; font-size: 12px; font-weight: 500;
  transition: all .15s;
}
.rv3-tab:hover { color: rgba(255,255,255,.85); }
.rv3-tab.on { background: rgba(255,255,255,.14); color: #fff; }
.rv3-invite-btn {
  display: flex; align-items: center; gap: 6px;
  height: 32px; padding: 0 14px;
  background: var(--green); border: none; border-radius: 8px;
  color: #fff; font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  transition: background .12s;
}
.rv3-invite-btn:hover { background: #178760; }
.rv3-new-badge {
  padding: 2px 7px;
  background: var(--green);
  color: #fff;
  border-radius: 8px;
  font-size: 9.5px; font-weight: 500; letter-spacing: .06em;
}
.rv3-content { flex: 1; }
</style>