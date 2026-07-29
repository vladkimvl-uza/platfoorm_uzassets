<script setup lang="ts">
/**
 * CompanyEmployeesSummary — компактная карточка «Сотрудники» для вкладки «Обзор».
 * Стек аватаров + счётчики + переход на полный таб «Сотрудники».
 * Аватары — с поповер-карточкой пользователя (UserCardAnchor).
 */
import { computed, ref, watch } from "vue";
import { companiesApi, type CompanyEmployee } from "@/api/companies";
import UserCardAnchor from "@/components/user/UserCardAnchor.vue";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const props = defineProps<{ code: string }>();
const emit = defineEmits<{ "open-people": [] }>();

const loading = ref(true);
const employees = ref<CompanyEmployee[]>([]);

async function load() {
  if (!props.code) return;
  loading.value = true;
  try {
    const res = await companiesApi.getEmployees(props.code);
    employees.value = res.employees;
  } catch {
    employees.value = [];
  } finally {
    loading.value = false;
  }
}
watch(() => props.code, load, { immediate: true });

const shown = computed(() => employees.value.slice(0, 7));
const overflow = computed(() => Math.max(0, employees.value.length - shown.value.length));
const departments = computed(() => new Set(employees.value.map((e) => e.department || "—")).size);
const onlineCount = computed(() =>
  employees.value.filter((e) => e.last_active && Date.now() - new Date(e.last_active).getTime() < 5 * 60 * 1000).length,
);
</script>

<template>
  <div v-if="loading || employees.length" class="ces" :class="{ 'ces-skel': loading }">
    <div class="ces-hd">
      <div class="ces-hd-l">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        <span class="ces-title">{{ t('Сотрудники') }}</span>
        <span v-if="!loading" class="ces-count">{{ employees.length }}</span>
      </div>
      <button v-if="!loading" class="ces-all" @click="emit('open-people')">
        {{ t('Все') }}
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 3l5 5-5 5"/></svg>
      </button>
    </div>

    <div v-if="loading" class="ces-skel-row">
      <span v-for="i in 6" :key="i" class="ces-skel-av"></span>
    </div>

    <template v-else>
      <div class="ces-avatars">
        <UserCardAnchor
          v-for="e in shown" :key="e.id" tag="span" :user-id="e.id" :preview="e"
          class="ces-av-wrap"
        >
          <span class="ces-av" :style="{ background: e.accent }" :title="e.full_name">
            <img v-if="e.avatar_url" :src="e.avatar_url" alt="" />
            <span v-else>{{ e.initials }}</span>
          </span>
        </UserCardAnchor>
        <button v-if="overflow" class="ces-av ces-more" @click="emit('open-people')">+{{ overflow }}</button>
      </div>

      <div class="ces-meta">
        <span><b>{{ departments }}</b> {{ departments === 1 ? 'отдел' : 'отделов' }}</span>
        <span v-if="onlineCount" class="ces-online"><span class="ces-dot"></span>{{ onlineCount }} {{ t('в сети') }}</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ces {
  margin-top: 16px; padding: 16px 18px;
  background: var(--bg1, #fff); border: 1px solid var(--line, #ECEAF4); border-radius: 14px;
}
.ces-hd { display: flex; align-items: center; justify-content: space-between; }
.ces-hd-l { display: flex; align-items: center; gap: 8px; }
.ces-hd-l svg { width: 16px; height: 16px; color: var(--p-deep, #534AB7); }
.ces-title { font-size: 13px; font-weight: 600; color: var(--t1, #1A1730); }
.ces-count { font-size: 11px; font-weight: 600; color: var(--p-deep, #534AB7); background: rgba(124,111,247,.12); border-radius: 999px; padding: 1px 8px; }
.ces-all {
  display: inline-flex; align-items: center; gap: 3px;
  background: transparent; border: none; color: var(--p-deep, #534AB7);
  font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.ces-all svg { width: 11px; height: 11px; }
.ces-all:hover { color: #3C3489; }

.ces-avatars { display: flex; align-items: center; margin-top: 13px; }
.ces-av-wrap { margin-right: -8px; transition: transform .14s; }
.ces-av-wrap:hover { transform: translateY(-3px); z-index: 2; }
.ces-av {
  width: 34px; height: 34px; border-radius: 9px;
  display: inline-flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 600; font-size: 12px; overflow: hidden;
  border: 2px solid var(--bg1, #fff); box-shadow: 0 1px 4px rgba(0,0,0,.16);
}
.ces-av img { width: 100%; height: 100%; object-fit: cover; }
.ces-more {
  margin-left: 0; background: var(--bg2, #EEEDF4); color: var(--t2, #6B6880);
  cursor: pointer; font-family: inherit;
}
.ces-more:hover { background: rgba(124,111,247,.14); color: var(--p-deep, #534AB7); }

.ces-meta { display: flex; gap: 14px; margin-top: 12px; font-size: 11.5px; color: var(--t3, #8B889C); }
.ces-meta b { color: var(--t1, #1A1730); }
.ces-online { display: inline-flex; align-items: center; gap: 5px; }
.ces-dot { width: 6px; height: 6px; border-radius: 50%; background: #1D9E75; }

.ces-skel-row { display: flex; gap: 6px; margin-top: 13px; }
.ces-skel-av { width: 34px; height: 34px; border-radius: 9px; background: var(--bg2, #EEEDF4); animation: cesPulse 1.3s ease-in-out infinite; }
@keyframes cesPulse { 0%,100% { opacity: 1; } 50% { opacity: .5; } }
</style>
