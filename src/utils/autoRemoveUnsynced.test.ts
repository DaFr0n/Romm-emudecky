import { beforeEach, describe, expect, it, vi } from "vitest";
import * as backend from "../api/backend";
import {
  armAutoRemoveUnsynced,
  disarmAutoRemoveUnsynced,
  recordUnsyncedRom,
  removeUnsyncedRomFiles,
  setAutoRemoveUnsyncedEnabled,
} from "./autoRemoveUnsynced";

describe("guarded ROM cleanup", () => {
  beforeEach(() => {
    disarmAutoRemoveUnsynced();
    setAutoRemoveUnsyncedEnabled(false);
    vi.mocked(backend.getAppIdRomIdMap).mockReset().mockResolvedValue({});
    vi.mocked(backend.getDownloadQueue).mockReset().mockResolvedValue({ downloads: [] });
    vi.mocked(backend.getInstalledRom)
      .mockReset()
      .mockResolvedValue({ file_path: "/roms/game.zip" } as never);
    vi.mocked(backend.removeRom).mockReset().mockResolvedValue({ success: true, message: "removed" });
  });

  it("does not remove files unless opted in", async () => {
    armAutoRemoveUnsynced();
    recordUnsyncedRom(10);
    await removeUnsyncedRomFiles(false);
    expect(backend.removeRom).not.toHaveBeenCalled();
  });

  it("removes a stale installed ROM after a completed sync", async () => {
    setAutoRemoveUnsyncedEnabled(true);
    armAutoRemoveUnsynced();
    recordUnsyncedRom(10);
    await removeUnsyncedRomFiles(false);
    expect(backend.removeRom).toHaveBeenCalledWith(10);
  });

  it("never removes files after cancellation", async () => {
    setAutoRemoveUnsyncedEnabled(true);
    armAutoRemoveUnsynced();
    recordUnsyncedRom(10);
    await removeUnsyncedRomFiles(true);
    expect(backend.removeRom).not.toHaveBeenCalled();
  });

  it("disabling the toggle clears pending deletions", async () => {
    setAutoRemoveUnsyncedEnabled(true);
    armAutoRemoveUnsynced();
    recordUnsyncedRom(10);
    setAutoRemoveUnsyncedEnabled(false);
    await removeUnsyncedRomFiles(false);
    expect(backend.removeRom).not.toHaveBeenCalled();
  });

  it("keeps a ROM still bound to another shortcut", async () => {
    vi.mocked(backend.getAppIdRomIdMap).mockResolvedValue({ "123": 10 });
    setAutoRemoveUnsyncedEnabled(true);
    armAutoRemoveUnsynced();
    recordUnsyncedRom(10);
    await removeUnsyncedRomFiles(false);
    expect(backend.removeRom).not.toHaveBeenCalled();
  });

  it.each(["queued", "downloading", "extracting", "paused"])("keeps ROMs with %s downloads", async (status) => {
    vi.mocked(backend.getDownloadQueue).mockResolvedValue({ downloads: [{ rom_id: 10, status }] as never });
    setAutoRemoveUnsyncedEnabled(true);
    armAutoRemoveUnsynced();
    recordUnsyncedRom(10);
    await removeUnsyncedRomFiles(false);
    expect(backend.removeRom).not.toHaveBeenCalled();
  });

  it("keeps ROMs that are already absent", async () => {
    vi.mocked(backend.getInstalledRom).mockResolvedValue(null);
    setAutoRemoveUnsyncedEnabled(true);
    armAutoRemoveUnsynced();
    recordUnsyncedRom(10);
    await removeUnsyncedRomFiles(false);
    expect(backend.removeRom).not.toHaveBeenCalled();
  });

  it("fails closed when a safety check fails", async () => {
    vi.mocked(backend.getAppIdRomIdMap).mockRejectedValue(new Error("unavailable"));
    setAutoRemoveUnsyncedEnabled(true);
    armAutoRemoveUnsynced();
    recordUnsyncedRom(10);
    await removeUnsyncedRomFiles(false);
    expect(backend.removeRom).not.toHaveBeenCalled();
  });

  it("does not remove the same ROM twice", async () => {
    setAutoRemoveUnsyncedEnabled(true);
    armAutoRemoveUnsynced();
    recordUnsyncedRom(10);
    recordUnsyncedRom(10);
    await removeUnsyncedRomFiles(false);
    await removeUnsyncedRomFiles(false);
    expect(backend.removeRom).toHaveBeenCalledTimes(1);
  });

  it("ignores invalid IDs", async () => {
    setAutoRemoveUnsyncedEnabled(true);
    armAutoRemoveUnsynced();
    recordUnsyncedRom(0);
    recordUnsyncedRom(-1);
    recordUnsyncedRom(Number.NaN);
    await removeUnsyncedRomFiles(false);
    expect(backend.removeRom).not.toHaveBeenCalled();
  });

  it("continues after one failed deletion", async () => {
    vi.mocked(backend.removeRom)
      .mockRejectedValueOnce(new Error("filesystem error"))
      .mockResolvedValueOnce({ success: true, message: "removed" });
    setAutoRemoveUnsyncedEnabled(true);
    armAutoRemoveUnsynced();
    recordUnsyncedRom(10);
    recordUnsyncedRom(11);
    await removeUnsyncedRomFiles(false);
    expect(backend.removeRom).toHaveBeenCalledWith(11);
  });
});
