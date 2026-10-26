import { getAppIdRomIdMap, getInstalledRom, getVersionList, startDownload, logError } from "../api/backend";

/** Opt-in for the next sync only; never persisted across plugin reloads. */
let enabled = false;
let pending = false;
let running = false;

export function getAutoDownloadEnabled(): boolean {
  return enabled;
}
export function setAutoDownloadEnabled(value: boolean): void {
  enabled = value;
}
export function armAutoDownloadSync(): void {
  pending = enabled;
}
export function disarmAutoDownloadSync(): void {
  pending = false;
}

/** Include all currently bound shortcuts, even when incremental sync skipped unchanged platforms. */
export async function downloadSyncedDefaults(appIds: number[], cancelled: boolean): Promise<void> {
  if (!pending) return;
  pending = false;
  if (cancelled || running) return;
  running = true;
  try {
    const bindings = await getAppIdRomIdMap();
    const seen = new Set<number>();
    const boundAppIds = Object.keys(bindings).map(Number).filter(Number.isSafeInteger);
    for (const appId of new Set([...appIds, ...boundAppIds])) {
      const boundRomId = bindings[String(appId)];
      if (!boundRomId) continue;
      try {
        const versions = await getVersionList(appId);
        if (versions.server_query_failed) {
          logError(`Auto-download: skipped app ${appId}, version lookup incomplete`);
          continue;
        }
        const available = versions.versions ?? [];
        // Never fetch a non-default sibling, even if it is the active shortcut.
        const chosen = available.length
          ? available.find((version) => version.is_default && version.synced && version.active)
          : null;
        if (available.length && !chosen) continue;
        const romId = available.length ? chosen!.rom_id : Number(boundRomId);
        if (!Number.isSafeInteger(romId) || seen.has(romId)) continue;
        seen.add(romId);
        // Skip any existing install. start_download can remove installed siblings.
        if (await getInstalledRom(romId)) continue;
        if (available.some((version) => version.installed)) continue;
        const result = await startDownload(romId);
        if (!result.success) logError(`Auto-download: ROM ${romId}: ${result.message}`);
      } catch (error) {
        logError(`Auto-download: app ${appId}: ${String(error)}`);
      }
    }
  } finally {
    running = false;
  }
}
