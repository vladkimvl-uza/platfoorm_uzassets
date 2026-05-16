/**
 * Anti-loss editor protocol — Phase 1: localStorage draft backup.
 *
 *
 *   stash()            — instant snapshot on any input/blur (debounced)
 *   readBackup()       — read latest draft for this report (returns null if none)
 *   clearBackup()      — call after successful save
 *   listOrphans()      — find old drafts (>cleanupAfterDays) and clean them
 *   keyFor()           — key namespace: uz_fin_backup_{report_id}
 *
 * Drafts are written under `uz_fin_backup_{report_id}` and contain:
 *   {
 *     savedAt: ISO timestamp,
 *     payload: FinancialReportSavePayload,
 *     baseChecksum: string  // checksum at the time editing started
 *   }
 */

const PREFIX = "uz_fin_backup_";
const CLEANUP_AFTER_DAYS = 7;

export interface DraftEnvelope {
  savedAt: string;     // ISO
  payload: any;
  baseChecksum: string | null;
  reportLabel?: string;
}

export function keyFor(reportId: string): string {
  return `${PREFIX}${reportId}`;
}

/** Write backup synchronously to localStorage. Never throws. */
export function stash(reportId: string, env: DraftEnvelope): boolean {
  try {
    localStorage.setItem(keyFor(reportId), JSON.stringify(env));
    return true;
  } catch (e) {
    // Quota exceeded or storage disabled — log and continue
    console.warn("[anti-loss] stash failed", e);
    return false;
  }
}

/** Read backup if it exists. Returns null on missing or malformed JSON. */
export function readBackup(reportId: string): DraftEnvelope | null {
  try {
    const raw = localStorage.getItem(keyFor(reportId));
    if (!raw) return null;
    return JSON.parse(raw) as DraftEnvelope;
  } catch {
    return null;
  }
}

/** Remove backup. Called after successful save. */
export function clearBackup(reportId: string): void {
  try {
    localStorage.removeItem(keyFor(reportId));
  } catch { /* ignore */ }
}

/** Scan all `uz_fin_backup_*` keys, drop ones older than CLEANUP_AFTER_DAYS. */
export function listOrphans(): { key: string; ageDays: number; envelope: DraftEnvelope }[] {
  const out: { key: string; ageDays: number; envelope: DraftEnvelope }[] = [];
  const cutoff = Date.now() - CLEANUP_AFTER_DAYS * 24 * 60 * 60 * 1000;
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (!k || !k.startsWith(PREFIX)) continue;
    try {
      const env = JSON.parse(localStorage.getItem(k)!) as DraftEnvelope;
      const ts = new Date(env.savedAt).getTime();
      if (Number.isFinite(ts) && ts < cutoff) {
        out.push({
          key: k,
          ageDays: Math.floor((Date.now() - ts) / (24 * 60 * 60 * 1000)),
          envelope: env,
        });
      }
    } catch { /* skip malformed */ }
  }
  return out;
}

/** Auto-cleanup at app init: remove drafts older than 7 days. */
export function autoCleanupOrphans(): number {
  const orphans = listOrphans();
  for (const o of orphans) {
    try { localStorage.removeItem(o.key); } catch { /* ignore */ }
  }
  return orphans.length;
}

/** All current backups (any age) — for the recovery UI listing. */
export function allBackups(): { reportId: string; envelope: DraftEnvelope }[] {
  const out: { reportId: string; envelope: DraftEnvelope }[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (!k || !k.startsWith(PREFIX)) continue;
    try {
      const env = JSON.parse(localStorage.getItem(k)!) as DraftEnvelope;
      out.push({ reportId: k.substring(PREFIX.length), envelope: env });
    } catch { /* skip malformed */ }
  }
  return out;
}
