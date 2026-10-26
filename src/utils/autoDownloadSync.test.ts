import { beforeEach, describe, expect, it, vi } from "vitest";
import * as backend from "../api/backend";
import {
  armAutoDownloadSync,
  disarmAutoDownloadSync,
  downloadSyncedDefaults,
  getAutoDownloadEnabled,
  setAutoDownloadEnabled,
} from "./autoDownloadSync";

const version = (rom_id: number, changes: Record<string, unknown> = {}) => ({
  rom_id,
  name: "Game",
  label: "Game",
  regions: [],
  languages: [],
  revision: "",
  tags: [],
  synced: true,
  installed: false,
  active: true,
  is_default: true,
  switchable: true,
  ...changes,
});

describe("auto-download default ROMs", () => {
  beforeEach(() => {
    setAutoDownloadEnabled(false);
    disarmAutoDownloadSync();
    vi.mocked(backend.getAppIdRomIdMap).mockReset().mockResolvedValue({ "100": 10 });
    vi.mocked(backend.getVersionList).mockReset().mockResolvedValue({
      multi_version: false,
      versions: [version(10)],
    });
    vi.mocked(backend.getInstalledRom).mockReset().mockResolvedValue(null);
    vi.mocked(backend.startDownload).mockReset().mockResolvedValue({ success: true, message: "queued" });
    vi.spyOn(backend, "logError").mockImplementation(() => undefined);
  });

  it("is off by default", async () => {
    expect(getAutoDownloadEnabled()).toBe(false);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    expect(backend.startDownload).not.toHaveBeenCalled();
  });

  it("downloads the default version after successful sync", async () => {
    setAutoDownloadEnabled(true);
    expect(getAutoDownloadEnabled()).toBe(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    expect(backend.startDownload).toHaveBeenCalledWith(10);
  });

  it("does not download after cancellation", async () => {
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], true);
    expect(backend.startDownload).not.toHaveBeenCalled();
  });

  it("disarm prevents downloads", async () => {
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    disarmAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    expect(backend.startDownload).not.toHaveBeenCalled();
  });

  it("handles unchanged platforms through existing bindings", async () => {
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([], false);
    expect(backend.startDownload).toHaveBeenCalledWith(10);
  });

  it("skips an installed ROM", async () => {
    vi.mocked(backend.getInstalledRom).mockResolvedValue({ file_path: "/roms/game.zip" } as never);
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    expect(backend.startDownload).not.toHaveBeenCalled();
  });

  it("skips a ROM when a sibling is installed", async () => {
    vi.mocked(backend.getVersionList).mockResolvedValue({
      multi_version: true,
      versions: [version(10), version(11, { installed: true, active: false, is_default: false })],
    });
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    expect(backend.startDownload).not.toHaveBeenCalled();
  });

  const invalidDefaultFlags = [{ is_default: false }, { synced: false }, { active: false }];

  it.each(invalidDefaultFlags)("skips bad flags: %j", async (changes) => {
    vi.mocked(backend.getVersionList).mockResolvedValue({
      multi_version: true,
      versions: [version(10, changes)],
    });
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    expect(backend.startDownload).not.toHaveBeenCalled();
  });

  it("skips partial server version lookups", async () => {
    vi.mocked(backend.getVersionList).mockResolvedValue({
      multi_version: true,
      server_query_failed: true,
      versions: [version(10)],
    });
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    expect(backend.startDownload).not.toHaveBeenCalled();
    expect(backend.logError).toHaveBeenCalled();
  });

  it("uses the bound ROM when version list is empty", async () => {
    vi.mocked(backend.getVersionList).mockResolvedValue({ multi_version: false, versions: [] });
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    expect(backend.startDownload).toHaveBeenCalledWith(10);
  });

  it("avoids duplicate downloads", async () => {
    vi.mocked(backend.getAppIdRomIdMap).mockResolvedValue({ "100": 10, "101": 10 });
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100, 101], false);
    expect(backend.startDownload).toHaveBeenCalledTimes(1);
  });

  it("ignores unbound app IDs", async () => {
    vi.mocked(backend.getAppIdRomIdMap).mockResolvedValue({});
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    expect(backend.startDownload).not.toHaveBeenCalled();
  });

  it("reports failed download requests", async () => {
    vi.mocked(backend.startDownload).mockResolvedValue({ success: false, message: "offline" });
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    expect(backend.logError).toHaveBeenCalled();
  });

  it("catches version lookup errors", async () => {
    vi.mocked(backend.getVersionList).mockRejectedValue(new Error("offline"));
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    expect(backend.logError).toHaveBeenCalled();
  });

  it("runs only once per completed sync", async () => {
    setAutoDownloadEnabled(true);
    armAutoDownloadSync();
    await downloadSyncedDefaults([100], false);
    await downloadSyncedDefaults([100], false);
    expect(backend.startDownload).toHaveBeenCalledTimes(1);
  });
});
