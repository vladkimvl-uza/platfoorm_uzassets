// frontend/src/composables/useSavedFilter.ts
//
// Universal persistent-filter helper.
// Drop-in replacement for `ref<T>(default)` that auto-saves to localStorage
// and restores on next mount/session. Used for chip/toggle/year/sector
// selectors across all module views so user settings survive refresh + logout.
//
// Usage:
//   const sectorFilter = useSavedFilter<string>("dashboard.sector", "");
//   const lens = useSavedFilter<"all"|"income"|"expenses">("bp.lens", "all");
//
// Storage key namespacing: prefix `uza_filter_` + caller-supplied module.field key.
// Reads happen once at mount; writes happen on every state change (deep watch).

import { ref, watch, type Ref, type UnwrapRef } from "vue";

const KEY_PREFIX = "uza_filter_";

function safeRead(storageKey: string): unknown {
  try {
    const raw = typeof localStorage === "undefined" ? null : localStorage.getItem(storageKey);
    if (raw === null) return undefined;
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function safeWrite(storageKey: string, value: unknown): void {
  try {
    if (typeof localStorage === "undefined") return;
    if (value === undefined) localStorage.removeItem(storageKey);
    else localStorage.setItem(storageKey, JSON.stringify(value));
  } catch {
    // Quota/SecurityError — silently ignore, fallback to in-memory only.
  }
}

export function useSavedFilter<T>(key: string, defaultValue: T): Ref<UnwrapRef<T>> {
  const storageKey = KEY_PREFIX + key;
  const stored = safeRead(storageKey);
  const initial = stored === undefined ? defaultValue : (stored as T);
  const state = ref<T>(initial);
  watch(
    state,
    (v) => safeWrite(storageKey, v),
    { deep: true },
  );
  return state;
}

/** Clear a single saved filter (use when user clicks "Reset filters"). */
export function clearSavedFilter(key: string): void {
  try { localStorage.removeItem(KEY_PREFIX + key); } catch { /* ignore */ }
}

/** Clear all uza_filter_* keys (full reset). */
export function clearAllSavedFilters(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(KEY_PREFIX)) keys.push(k);
    }
    keys.forEach((k) => localStorage.removeItem(k));
  } catch { /* ignore */ }
}
