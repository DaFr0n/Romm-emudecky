import { getAppIdRomIdMap, getDownloadQueue, getInstalledRom, logError, removeRom } from "../api/backend";

// Session-only, opt-in cleanup. Never delete files on a cancelled or failed sync.
let enabled = false;
let armed = false;
const staleRomIds = new Set<number>();

export function getAutoRemoveUnsyncedEnabled(): boolean {
  return enabled;
}

export function setAutoRemoveUnsyncedEnabled(value: boolean): void {
  enabled = value;
  if (!value) disarmAutoRemoveUnsynced();
}

export function armAutoRemoveUnsynced(): void {
  armed = enabled;
  staleRomIds.clear();
}

export function disarmAutoRemoveUnsynced(): void {
  armed = false;
  staleRomIds.clear();
}

export function recordUnsyncedRom(romId: number): void {
  if (armed && Number.isSafeInteger(romId) && romId > 0) staleRomIds.add(romId);
}

export async function removeUnsyncedRomFiles(cancelled: boolean): Promise<void> {
  if (!armed) return;
  armed = false;
  const candidates = [...staleRomIds];
  staleRomIds.clear();
  if (cancelled) return;

  for (const romId of candidates) {
    try {
      // Recheck live bindings, queued downloads and installation immediately before removal.
      const bindings = await getAppIdRomIdMap();
      if (Object.values(bindings).some((id) => Number(id) === romId)) continue;
      const queue = await getDownloadQueue();
      if (
        queue.downloads.some(
          (item) => item.rom_id === romId && ["queued", "downloading", "extracting", "paused"].includes(item.status),
        )
      ) continue;
      if (!(await getInstalledRom(romId))) continue;
      const result = await removeRom(romId);
      if (!result.success) logError(`Auto-remove: ROM ${romId}: ${result.message}`);
    } catch (error) {
      logError(`Auto-remove: skipped ROM ${romId}: ${String(error)}`);
    }
  }
}
