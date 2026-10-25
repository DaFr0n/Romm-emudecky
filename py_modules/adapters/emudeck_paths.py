"""EmuDeck paths adapter — reads ``~/.config/EmuDeck/settings.json`` for path resolution.

Provides path resolution for saves, ROMs, BIOS, the EmuDeck-managed
launcher directory, and the Emulation root. The adapter reads EmuDeck's
``settings.json`` (its configurator output) once and caches the result
for 30 seconds — long enough to amortize repeated reads during a sync
run, short enough to pick up edits made via the EmuDeck configurator
within a single plugin session.

Path getters are best-effort and never raise: a missing, unreadable, or
malformed ``settings.json`` (or a missing/empty ``storagePath`` key)
falls back to ``<user_home>/Emulation/*`` (the conventional EmuDeck
internal-storage layout). The SD-card / external-storage case relies on
the loud signal ``main.py`` surfaces to the frontend banner —
:meth:`EmuDeckPathsAdapter.config_health` is what catches an
unavailable root before the getters' best-effort fallback is ever used.

Implements service-facing Protocols (:class:`services.protocols.paths.RetroDeckPaths`)
under the transitional naming policy of the EmuDeck port plan §12:
method names are preserved (so ``retrodeck_home`` returns the Emulation
root), with host-specific paths resolved against
``<storagePath>/Emulation``. The two extra getters
(:meth:`tools_path` and :meth:`launchers_path`) are the new surface the
launcher adapter (Phase A) will consume; they are not part of the
existing Protocol today.
"""

from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING, Any

from lib.emudeck_health import EmuDeckConfigHealth

if TYPE_CHECKING:
    import logging


class EmuDeckPathsAdapter:
    """Adapter for reading EmuDeck path configuration from ``settings.json``.

    Path layout derived from EmuDeck's documented storage tree::

        <storagePath>/Emulation
        <storagePath>/Emulation/roms
        <storagePath>/Emulation/bios
        <storagePath>/Emulation/saves
        <storagePath>/Emulation/tools
        <storagePath>/Emulation/tools/launchers

    ``storagePath`` is read from ``~/.config/EmuDeck/settings.json``.
    ``~``, ``$HOME`` and other environment variables are expanded so the
    literal string ``"~/..."`` in the config works the same as on a
    deck where EmuDeck has written the home dir explicitly.
    """

    _CACHE_TTL = 30  # seconds
    _EMULATION_DIRNAME = "Emulation"

    def __init__(self, *, user_home: str, logger: logging.Logger) -> None:
        self._user_home = user_home
        self._logger = logger
        self._cached_config: dict[str, Any] | None = None
        self._cache_time = 0.0
        # Load outcome that distinguishes the four failure classifications.
        # The getters only need the dict-or-None; ``config_health`` needs
        # the reason.
        self._last_load_health: EmuDeckConfigHealth = EmuDeckConfigHealth.ABSENT

    def config_path(self) -> str:
        """Absolute path to ``settings.json`` that this adapter probes."""
        return os.path.join(self._user_home, ".config", "EmuDeck", "settings.json")

    def _load_config(self) -> dict[str, Any] | None:
        now = time.monotonic()
        if self._cached_config is not None and (now - self._cache_time) < self._CACHE_TTL:
            return self._cached_config
        config_path = self.config_path()
        try:
            with open(config_path) as f:
                config = json.load(f)
            self._cached_config = config
            self._cache_time = now
            self._last_load_health = EmuDeckConfigHealth.OK
            return config
        except FileNotFoundError:
            # Missing file is the expected pre-install state (no EmuDeck
            # yet) — don't spam the log on every read, and don't cache
            # the time so the next read picks up a created file
            # immediately.
            self._cached_config = None
            self._last_load_health = EmuDeckConfigHealth.ABSENT
            return None
        except (OSError, json.JSONDecodeError) as exc:
            self._logger.warning(f"Failed to load EmuDeck config at {config_path}: {exc}")
            self._cached_config = None
            self._cache_time = now
            self._last_load_health = EmuDeckConfigHealth.UNREADABLE
            return None

    def _expansion(self, raw: str) -> str:
        """Expand ``~``, ``$HOME`` and environment variables in ``raw``.

        ``expandvars`` first so e.g. ``$HOME/Emulation`` resolves, then
        ``expanduser`` so a bare ``~`` is treated as the home dir. Falls
        through unchanged when nothing matches either rule.
        """
        return os.path.expanduser(os.path.expandvars(raw))

    def _storage_path(self) -> str | None:
        """Resolved ``storagePath`` (expanded) or ``None`` when absent/empty."""
        config = self._load_config()
        if config is None:
            return None
        raw: str | None = config.get("storagePath")
        if not raw or not raw.strip():
            return None
        return self._expansion(raw)

    def _fallback(self, subdir: str) -> str:
        """Best-effort path when ``storagePath`` is unavailable.

        Mirrors the RetroDECK adapter's guarantee that the path getters
        never raise: a missing/unreadable config surfaces the right path
        under the conventional EmuDeck home location
        (``<user_home>/Emulation``). The health signal is what stops
        callers from writing to this guess when the real root has moved.
        """
        return os.path.join(self._user_home, self._EMULATION_DIRNAME, subdir)

    def _resolved_under_emulation(self, subdir: str) -> str:
        """Path under ``<storagePath>/Emulation`` with the safe fallback."""
        storage = self._storage_path()
        if storage is None:
            return self._fallback(subdir)
        return os.path.join(storage, self._EMULATION_DIRNAME, subdir)

    def emulation_root(self) -> str:
        storage = self._storage_path()
        if storage is None:
            return os.path.join(self._user_home, self._EMULATION_DIRNAME)
        return os.path.join(storage, self._EMULATION_DIRNAME)

    def roms_path(self) -> str:
        return self._resolved_under_emulation("roms")

    def bios_path(self) -> str:
        return self._resolved_under_emulation("bios")

    def saves_path(self) -> str:
        return self._resolved_under_emulation("saves")

    def tools_path(self) -> str:
        return self._resolved_under_emulation("tools")

    def launchers_path(self) -> str:
        return os.path.join(self._resolved_under_emulation("tools"), "launchers")

    def retrodeck_home(self) -> str:
        """Transitional Protocol seam — returns the Emulation root.

        The :class:`services.protocols.paths.RetroDeckPaths` Protocol
        names this method ``retrodeck_home`` historically; the EmuDeck
        port keeps the name during the transitional rename window
        (port plan §12) and returns ``<storagePath>/Emulation`` (the
        host-emulation analog). Consumers treat it as "the host
        emulation home directory" — migration/startup-healing use it as
        the probe target for "is the configured root mounted?".
        """
        return self.emulation_root()

    def config_health(self) -> EmuDeckConfigHealth:
        """Classify how trustworthy the resolved EmuDeck roots are.

        Reuses the 30-second TTL cache via :meth:`_load_config` — no
        second independent file read within the TTL. Five outcomes:

        - ``ABSENT``: ``settings.json`` not found — the expected
          pre-install state. Wins over ``ROOT_MISSING`` even when the
          ``<user_home>/Emulation`` fallback does not exist on disk,
          so it stays quiet.
        - ``UNREADABLE``: the file exists but could not be read/parsed.
        - ``INVALID``: the file read OK but ``storagePath`` is missing
          or empty — EmuDeck knows the user is configured but not where
          ROMs live.
        - ``ROOT_MISSING``: ``storagePath`` set but the resolved
          Emulation root does not exist on disk (e.g. SD card ejected).
        - ``OK``: read OK, ``storagePath`` set, and the resolved
          Emulation root exists.
        """
        self._load_config()
        # ABSENT and UNREADABLE win over the disk probe — a missing
        # config / parse error is the user's pre-install state, and a
        # missing fallback root is expected then, not a failure.
        if self._last_load_health in (
            EmuDeckConfigHealth.ABSENT,
            EmuDeckConfigHealth.UNREADABLE,
        ):
            return self._last_load_health
        # Config loaded. If storagePath is missing/empty this is
        # INVALID, not ROOT_MISSING — we know the config is unusable on
        # its face and shouldn't pretend the disk has anything to probe.
        storage = self._storage_path()
        if storage is None:
            return EmuDeckConfigHealth.INVALID
        # Probe only the Emulation root, matching the SD-card-ejected
        # failure mode EmuDeck users actually hit (the whole tree goes
        # away together, not just the roms subtree).
        if not os.path.isdir(self.emulation_root()):
            return EmuDeckConfigHealth.ROOT_MISSING
        return EmuDeckConfigHealth.OK
