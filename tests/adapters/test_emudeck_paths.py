"""Tests for adapters.emudeck_paths.EmuDeckPathsAdapter."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from unittest.mock import patch

from adapters.emudeck_paths import EmuDeckPathsAdapter
from lib.emudeck_health import EmuDeckConfigHealth


def _make_adapter(tmp_path, config: dict[str, Any] | None = None, *, raw: str | None = None) -> EmuDeckPathsAdapter:
    """Create adapter with optional ``settings.json``.

    ``config`` writes a JSON dict; ``raw`` writes literal bytes (for the
    malformed-JSON case). The config lives at
    ``<home>/.config/EmuDeck/settings.json``.
    """
    user_home = str(tmp_path)
    config_dir = tmp_path / ".config" / "EmuDeck"
    config_dir.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (config_dir / "settings.json").write_text(json.dumps(config))
    elif raw is not None:
        (config_dir / "settings.json").write_text(raw)
    return EmuDeckPathsAdapter(user_home=user_home, logger=logging.getLogger("test"))


class TestPathResolution:
    def test_internal_storage_roots(self, tmp_path):
        storage = tmp_path / "internal"
        storage.mkdir()
        adapter = _make_adapter(tmp_path, {"storagePath": str(storage)})
        assert adapter.emulation_root() == str(storage / "Emulation")
        assert adapter.roms_path() == str(storage / "Emulation" / "roms")
        assert adapter.bios_path() == str(storage / "Emulation" / "bios")
        assert adapter.saves_path() == str(storage / "Emulation" / "saves")
        assert adapter.tools_path() == str(storage / "Emulation" / "tools")
        assert adapter.launchers_path() == str(storage / "Emulation" / "tools" / "launchers")
        assert adapter.retrodeck_home() == str(storage / "Emulation")

    def test_sd_external_storage_roots(self, tmp_path):
        sd_root = tmp_path / "run" / "media" / "deck" / "SDCARD"
        sd_root.mkdir(parents=True)
        emu_root = sd_root / "Emulation"
        emu_root.mkdir()
        adapter = _make_adapter(tmp_path, {"storagePath": str(sd_root)})
        assert adapter.roms_path() == str(sd_root / "Emulation" / "roms")
        assert adapter.emulation_root() == str(emu_root)

    def test_storage_path_with_tilde_expands(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        adapter = _make_adapter(tmp_path, {"storagePath": "~"})
        assert adapter.emulation_root() == os.path.join(str(tmp_path), "Emulation")
        assert adapter.roms_path() == os.path.join(str(tmp_path), "Emulation", "roms")

    def test_storage_path_with_home_env_var_expands(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        adapter = _make_adapter(tmp_path, {"storagePath": "$HOME"})
        assert adapter.emulation_root() == os.path.join(str(tmp_path), "Emulation")
        assert adapter.bios_path() == os.path.join(str(tmp_path), "Emulation", "bios")

    def test_storage_path_with_subpath_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MYSD", str(tmp_path / "sd"))
        (tmp_path / "sd" / "Emulation").mkdir(parents=True)
        adapter = _make_adapter(tmp_path, {"storagePath": "$MYSD"})
        assert adapter.roms_path() == os.path.join(str(tmp_path / "sd" / "Emulation" / "roms"))

    def test_missing_config_uses_fallback(self, tmp_path):
        adapter = EmuDeckPathsAdapter(user_home=str(tmp_path), logger=logging.getLogger("test"))
        expected_base = os.path.join(str(tmp_path), "Emulation")
        assert adapter.emulation_root() == expected_base
        assert adapter.roms_path() == os.path.join(expected_base, "roms")
        assert adapter.bios_path() == os.path.join(expected_base, "bios")
        assert adapter.saves_path() == os.path.join(expected_base, "saves")
        assert adapter.retrodeck_home() == expected_base

    def test_empty_storage_path_uses_fallback(self, tmp_path):
        adapter = _make_adapter(tmp_path, {"storagePath": ""})
        expected = os.path.join(str(tmp_path), "Emulation", "roms")
        assert adapter.roms_path() == expected

    def test_whitespace_storage_path_treated_as_missing(self, tmp_path):
        adapter = _make_adapter(tmp_path, {"storagePath": "   "})
        assert adapter.roms_path() == os.path.join(str(tmp_path), "Emulation", "roms")

    def test_missing_storage_path_key_uses_fallback(self, tmp_path):
        adapter = _make_adapter(tmp_path, {"other": "data"})
        assert adapter.bios_path() == os.path.join(str(tmp_path), "Emulation", "bios")

    def test_malformed_json_uses_fallback(self, tmp_path):
        adapter = _make_adapter(tmp_path, raw="not valid json")
        assert adapter.bios_path() == os.path.join(str(tmp_path), "Emulation", "bios")


class TestTTLCache:
    def test_cache_returns_same_value(self, tmp_path):
        adapter = _make_adapter(tmp_path, {"storagePath": "/first"})
        assert adapter.bios_path() == "/first/Emulation/bios"
        config_dir = tmp_path / ".config" / "EmuDeck"
        (config_dir / "settings.json").write_text(json.dumps({"storagePath": "/second"}))
        assert adapter.bios_path() == "/first/Emulation/bios"

    def test_cache_expires_after_ttl(self, tmp_path):
        adapter = _make_adapter(tmp_path, {"storagePath": "/first"})
        assert adapter.bios_path() == "/first/Emulation/bios"
        adapter._cache_time = time.monotonic() - 31
        config_dir = tmp_path / ".config" / "EmuDeck"
        (config_dir / "settings.json").write_text(json.dumps({"storagePath": "/second"}))
        assert adapter.bios_path() == "/second/Emulation/bios"

    def test_failed_load_retried_on_next_call(self, tmp_path):
        """A failed load is not cached — later successful loads are picked up immediately."""
        adapter = EmuDeckPathsAdapter(user_home=str(tmp_path), logger=logging.getLogger("test"))
        assert adapter.bios_path() == os.path.join(str(tmp_path), "Emulation", "bios")

        config_dir = tmp_path / ".config" / "EmuDeck"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "settings.json").write_text(json.dumps({"storagePath": "/picked/up"}))

        # No TTL wait required.
        assert adapter.bios_path() == "/picked/up/Emulation/bios"


class TestLoadConfigLogging:
    def test_load_config_logs_warning_on_json_error(self, tmp_path, caplog):
        adapter = _make_adapter(tmp_path, raw="not valid json")
        with caplog.at_level(logging.WARNING):
            adapter.bios_path()
        assert any("Failed to load EmuDeck config" in rec.message for rec in caplog.records)

    def test_load_config_logs_warning_on_permission_error(self, tmp_path, caplog):
        config_dir = tmp_path / ".config" / "EmuDeck"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "settings.json"
        config_file.write_text(json.dumps({"storagePath": "/should/not/be/read"}))

        real_open = open

        def fake_open(path, *args, **kwargs):
            if str(path) == str(config_file):
                raise PermissionError(f"denied: {path}")
            return real_open(path, *args, **kwargs)

        adapter = EmuDeckPathsAdapter(user_home=str(tmp_path), logger=logging.getLogger("test"))
        with patch("builtins.open", side_effect=fake_open), caplog.at_level(logging.WARNING):
            result = adapter.bios_path()
        assert result == os.path.join(str(tmp_path), "Emulation", "bios")
        assert any("Failed to load EmuDeck config" in rec.message for rec in caplog.records)

    def test_load_config_does_not_log_on_missing_file(self, tmp_path, caplog):
        adapter = EmuDeckPathsAdapter(user_home=str(tmp_path), logger=logging.getLogger("test"))
        with caplog.at_level(logging.WARNING):
            adapter.bios_path()
        assert not any("Failed to load EmuDeck config" in rec.message for rec in caplog.records)


class TestConfigPath:
    def test_config_path_points_at_emudeck_settings(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        assert adapter.config_path() == os.path.join(str(tmp_path), ".config", "EmuDeck", "settings.json")


class TestConfigHealth:
    def test_ok_when_config_present_and_root_exists(self, tmp_path):
        storage = tmp_path / "storage"
        (storage / "Emulation").mkdir(parents=True)
        adapter = _make_adapter(tmp_path, {"storagePath": str(storage)})
        assert adapter.config_health() is EmuDeckConfigHealth.OK

    def test_absent_when_no_config_file(self, tmp_path):
        adapter = EmuDeckPathsAdapter(user_home=str(tmp_path), logger=logging.getLogger("test"))
        assert adapter.config_health() is EmuDeckConfigHealth.ABSENT

    def test_absent_does_not_log(self, tmp_path, caplog):
        adapter = EmuDeckPathsAdapter(user_home=str(tmp_path), logger=logging.getLogger("test"))
        with caplog.at_level(logging.WARNING):
            assert adapter.config_health() is EmuDeckConfigHealth.ABSENT
        assert not any("Failed to load EmuDeck config" in rec.message for rec in caplog.records)

    def test_unreadable_on_malformed_json(self, tmp_path):
        adapter = _make_adapter(tmp_path, raw="not valid json")
        assert adapter.config_health() is EmuDeckConfigHealth.UNREADABLE

    def test_unreadable_on_permission_error(self, tmp_path):
        config_dir = tmp_path / ".config" / "EmuDeck"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "settings.json"
        config_file.write_text(json.dumps({"storagePath": "/whatever"}))

        real_open = open

        def fake_open(path, *args, **kwargs):
            if str(path) == str(config_file):
                raise PermissionError(f"denied: {path}")
            return real_open(path, *args, **kwargs)

        adapter = EmuDeckPathsAdapter(user_home=str(tmp_path), logger=logging.getLogger("test"))
        with patch("builtins.open", side_effect=fake_open):
            assert adapter.config_health() is EmuDeckConfigHealth.UNREADABLE

    def test_invalid_when_storage_path_missing(self, tmp_path):
        adapter = _make_adapter(tmp_path, {"other": "data"})
        assert adapter.config_health() is EmuDeckConfigHealth.INVALID

    def test_invalid_when_storage_path_empty(self, tmp_path):
        adapter = _make_adapter(tmp_path, {"storagePath": ""})
        assert adapter.config_health() is EmuDeckConfigHealth.INVALID

    def test_invalid_beats_disk_probe(self, tmp_path):
        """INVALID means storagePath is unusable; the disk probe never runs."""
        # Even though <user_home>/Emulation exists, missing storagePath
        # must NOT report OK or ROOT_MISSING — the config is unusable.
        (tmp_path / "Emulation").mkdir()
        adapter = _make_adapter(tmp_path, {"other": "data"})
        assert adapter.config_health() is EmuDeckConfigHealth.INVALID

    def test_root_missing_when_emulation_root_absent(self, tmp_path):
        """ROOT_MISSING: storagePath set but the Emulation dir is not on disk.

        Models the SD-card-ejected failure mode: the storage root was
        configured (and still set in settings.json) but the directory
        tree is gone.
        """
        adapter = _make_adapter(tmp_path, {"storagePath": str(tmp_path / "ejected-sd" / "deck")})
        assert adapter.config_health() is EmuDeckConfigHealth.ROOT_MISSING

    def test_root_missing_probes_emulation_root_not_storage(self, tmp_path):
        """ROOT_MISSING keys on the Emulation subdir, matching the real failure case.

        If <storage>/Emulation is gone but the parent storage dir still
        exists, that's still ROOT_MISSING — the ROMs/saves/bios subpaths
        all branch off Emulation.
        """
        storage = tmp_path / "storage"
        storage.mkdir()  # storage exists, but Emulation does not
        adapter = _make_adapter(tmp_path, {"storagePath": str(storage)})
        assert adapter.config_health() is EmuDeckConfigHealth.ROOT_MISSING

    def test_absent_wins_over_root_missing(self, tmp_path):
        """ABSENT must win even though the fallback Emulation root doesn't exist.

        With no ``settings.json`` the getters fall back to
        ``<user_home>/Emulation`` — which the tmp dir does not have. The
        disk probe must NOT run for ABSENT, so the result stays ABSENT
        (quiet) rather than ROOT_MISSING (loud).
        """
        adapter = EmuDeckPathsAdapter(user_home=str(tmp_path), logger=logging.getLogger("test"))
        assert not os.path.isdir(adapter.emulation_root())
        assert adapter.config_health() is EmuDeckConfigHealth.ABSENT

    def test_health_reuses_ttl_cache_no_second_read(self, tmp_path):
        storage = tmp_path / "storage"
        (storage / "Emulation").mkdir(parents=True)
        adapter = _make_adapter(tmp_path, {"storagePath": str(storage)})
        assert adapter.config_health() is EmuDeckConfigHealth.OK

        real_open = open
        opened: list[str] = []

        def tracking_open(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=tracking_open):
            assert adapter.config_health() is EmuDeckConfigHealth.OK

        assert opened == [], "config_health re-read settings.json within the TTL"

    def test_health_recovers_after_unmounted_storage_reinserted(self, tmp_path):
        """Reinserting the SD card flips ROOT_MISSING back to OK.

        ROOT_MISSING is not cached long-term — it re-probes the disk
        each time the TTL cache expires. This tests the recovery half:
        the directory appears and the health flips OK across a cache
        expiry. (Cache-expiry behavior is the same as the path-getter
        cache — see the TTL tests above.)
        """
        storage = tmp_path / "storage"
        adapter = _make_adapter(tmp_path, {"storagePath": str(storage)})
        assert adapter.config_health() is EmuDeckConfigHealth.ROOT_MISSING
        adapter._cache_time = time.monotonic() - 31
        (storage / "Emulation").mkdir(parents=True)
        assert adapter.config_health() is EmuDeckConfigHealth.OK


class TestNeverGuessesIntoUnavailableStorage:
    """The plan's hard rule: never silently write into internal storage
    when the configured external/SD storage root is unavailable.

    The adapter's contract is the health signal — the *download service*
    is the gate that must check ``config_health`` before writing. These
    tests pin that contract so a future refactor that swaps health for a
    silent internal fallback is caught.
    """

    def test_unmounted_sd_returns_root_missing_not_ok(self, tmp_path):
        adapter = _make_adapter(tmp_path, {"storagePath": "/run/media/deck/MISSING_CARD"})
        assert adapter.config_health() is EmuDeckConfigHealth.ROOT_MISSING

    def test_roms_path_does_not_falsely_point_at_internal(self, tmp_path):
        """When storagePath IS set, the roms path must point at that storage.

        Never silently fall through to ``<user_home>``.
        """
        adapter = _make_adapter(tmp_path, {"storagePath": "/run/media/deck/EXTERNAL/Emulation-root"})
        assert adapter.roms_path() == "/run/media/deck/EXTERNAL/Emulation-root/Emulation/roms"
        assert not adapter.roms_path().startswith(str(tmp_path))


class TestProtocolConformance:
    """The adapter implements the existing ``RetroDeckPaths`` Protocol
    under the transitional naming policy — same method names, EmuDeck paths."""

    def test_all_protocol_methods_present(self, tmp_path):
        adapter = _make_adapter(tmp_path)
        # Every Protocol method must resolve to a string (never raise).
        assert isinstance(adapter.saves_path(), str)
        assert isinstance(adapter.roms_path(), str)
        assert isinstance(adapter.bios_path(), str)
        assert isinstance(adapter.retrodeck_home(), str)
        assert isinstance(adapter.config_path(), str)
        assert adapter.config_health() in EmuDeckConfigHealth

    def test_retrodeck_home_returns_emulation_root(self, tmp_path):
        storage = tmp_path / "storage"
        adapter = _make_adapter(tmp_path, {"storagePath": str(storage)})
        assert adapter.retrodeck_home() == str(storage / "Emulation")
