/**
 * Directions store — single source of truth for direction codes/labels/colors
 * across the platform. Replaces hardcoded DIRS_META scattered in components.
 *
 * On first access, fetches /directions and caches in memory. Mutations
 * (add/edit/delete) from CatalogsPage should call reload().
 */
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { directionsApi, type DirectionBrief } from "@/api/directions";

export const useDirectionsStore = defineStore("directions", () => {
  const items = ref<DirectionBrief[]>([]);
  const loaded = ref(false);
  const loading = ref(false);

  async function ensureLoaded(force = false): Promise<void> {
    if (loaded.value && !force) return;
    if (loading.value) return;
    loading.value = true;
    try {
      items.value = await directionsApi.list();
      loaded.value = true;
    } catch (e) {
      console.warn("[directions store] failed to load", e);
    } finally {
      loading.value = false;
    }
  }

  async function reload(): Promise<void> {
    await ensureLoaded(true);
  }

  /** code → {label, color} lookup. Returns undefined if direction not found. */
  const byCode = computed(() => {
    const map = new Map<string, DirectionBrief>();
    for (const d of items.value) map.set(d.code.toLowerCase(), d);
    return map;
  });

  /** label (lowercased) → code lookup. Used for normalizing free-text input. */
  const labelToCode = computed(() => {
    const map = new Map<string, string>();
    for (const d of items.value) {
      map.set(d.label.trim().toLowerCase(), d.code.toLowerCase());
    }
    return map;
  });

  function labelFor(code: string | null | undefined): string {
    if (!code) return "";
    return byCode.value.get(String(code).toLowerCase())?.label || String(code);
  }

  function colorFor(code: string | null | undefined): string {
    if (!code) return "#94A3B8";
    return byCode.value.get(String(code).toLowerCase())?.color || "#94A3B8";
  }

  function normalize(raw: string | null | undefined): string | null {
    if (!raw) return null;
    const s = String(raw).trim().toLowerCase();
    if (!s) return null;
    if (byCode.value.has(s)) return s;
    return labelToCode.value.get(s) || s;
  }

  return {
    items, loaded, loading,
    ensureLoaded, reload,
    byCode, labelToCode,
    labelFor, colorFor, normalize,
  };
});
