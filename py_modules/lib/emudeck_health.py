"""Health classification for EmuDeck path resolution from ``settings.json``.

Cross-cutting enum shared by the adapter that reads
``~/.config/EmuDeck/settings.json`` (``adapters/emudeck_paths.py``), the
Protocol services depend on (``services/protocols/paths.py``), and the
``main.py`` callable that surfaces the state to the frontend banner. It
lives in ``lib/`` because all three layers must import it and
``import-linter`` forbids the adapter->service and service->adapter
directions; ``lib/`` is the only namespace importable from every layer.
"""

from __future__ import annotations

from enum import StrEnum


class EmuDeckConfigHealth(StrEnum):
    """How trustworthy the resolved EmuDeck roots are right now.

    The path getters are always best-effort and never raise; this enum
    is the loud signal that lets the frontend warn the user when the
    resolved roots are likely wrong.
    """

    OK = "ok"
    """``settings.json`` read successfully, ``storagePath`` is present.

    The resolved Emulation root exists on disk.
    """

    ABSENT = "absent"
    """``settings.json`` not found — EmuDeck is not installed or not yet configured.

    Stays quiet (the expected pre-install state).
    """

    UNREADABLE = "unreadable"
    """``settings.json`` exists but cannot be read or parsed.

    We know EmuDeck is configured but not where it stores ROMs. Loud.
    """

    INVALID = "invalid"
    """``settings.json`` read OK but the ``storagePath`` key is missing or empty.

    EmuDeck settings are present but unusable. Loud.
    """

    ROOT_MISSING = "root_missing"
    """``settings.json`` read OK and ``storagePath`` is set, but the resolved
    Emulation root is missing on disk (e.g. SD card ejected). Loud."""
