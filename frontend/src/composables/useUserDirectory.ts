/**
 * useUserDirectory — shared cache of users for UI resolution.
 *
 * Fetches /rbac/v3/users once (per app session), exposes:
 *   - users:        ref of all RbacV3UserBrief
 *   - byId(id):     resolve UUID → { email, full_name } or undefined
 *   - display(id):  resolve UUID → "Full Name (email)" or fallback to short id
 *   - ensureLoaded(): trigger fetch if not yet loaded
 *
 * Used by moderation UI to show proposer / moderator / commenter names
 * instead of raw UUIDs.
 */
import { ref, computed } from "vue";
import { rbacV3Api, type RbacV3UserBrief } from "@/api/rbacV3";

const users = ref<RbacV3UserBrief[]>([]);
const loaded = ref(false);
const loading = ref(false);

const byIdMap = computed<Record<string, RbacV3UserBrief>>(() => {
  const m: Record<string, RbacV3UserBrief> = {};
  for (const u of users.value) m[u.id] = u;
  return m;
});

async function ensureLoaded(force = false): Promise<void> {
  if (loaded.value && !force) return;
  if (loading.value) return;
  loading.value = true;
  try {
    const r = await rbacV3Api.listUsers({ limit: 500 });
    users.value = r.items;
    loaded.value = true;
  } catch (e) {
    console.warn("[useUserDirectory] load failed", e);
  } finally {
    loading.value = false;
  }
}

function byId(id: string | null | undefined): RbacV3UserBrief | undefined {
  if (!id) return undefined;
  return byIdMap.value[id];
}

/**
 * Display string: "Full Name (email)" if known, else fallback to short id.
 * Use this everywhere a UUID would otherwise appear in the UI.
 */
function display(id: string | null | undefined, fallbackLabel?: string): string {
  if (!id) return fallbackLabel || "—";
  const u = byId(id);
  if (!u) return fallbackLabel || `id:${id.slice(0, 8)}`;
  if (u.full_name) return `${u.full_name} (${u.email})`;
  return u.email;
}

/** Short variant — for compact spots (avatars, chips). */
function shortName(id: string | null | undefined): string {
  if (!id) return "—";
  const u = byId(id);
  if (!u) return id.slice(0, 8);
  return u.full_name || u.email;
}

/** Initials for avatar — 1–2 chars. */
function initials(id: string | null | undefined): string {
  if (!id) return "—";
  const u = byId(id);
  const src = u?.full_name || u?.email || id;
  return src.replace(/[«»"']/g, "").slice(0, 2).toUpperCase();
}

export function useUserDirectory() {
  return {
    users,
    loaded,
    loading,
    ensureLoaded,
    byId,
    display,
    shortName,
    initials,
  };
}
