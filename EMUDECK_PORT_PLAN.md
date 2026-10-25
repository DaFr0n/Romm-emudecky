# EmuDeck Port Plan for `decky-romm-sync`

> Target: fork `danielcopper/decky-romm-sync` so RomM Sync uses an existing EmuDeck installation instead of RetroDECK.
>
> Strategy: preserve the RomM, Steam shortcut, artwork, download queue, persistence, metadata, and UI architecture. Replace the host-emulation integration layer behind explicit adapters/resolvers. Ship ROM sync + launch first; defer full save-sync parity until emulator-specific save adapters exist.

---

## 1. Goal

Build an EmuDeck-backed fork that can:

1. Connect to RomM and sync selected platforms into Steam.
2. Download ROMs into the active EmuDeck `Emulation/roms/<system>` tree.
3. Download supported BIOS files into the active EmuDeck `Emulation/bios` tree.
4. Create/update Steam shortcuts using the plugin's existing shortcut management.
5. Launch games through EmuDeck-managed launcher scripts or validated emulator commands.
6. Preserve existing artwork, metadata, version switching, uninstall, and download-queue behavior.
7. Detect EmuDeck configuration and storage-path changes safely.
8. Add save sync incrementally after launch behavior is stable.

---

## 2. Scope

### MVP — required

- EmuDeck installation detection.
- `storagePath` parsing from `~/.config/EmuDeck/settings.json`.
- ROM root resolution.
- BIOS root resolution.
- RomM platform → EmuDeck system folder mapping.
- ROM download/install/uninstall.
- Steam shortcut generation.
- A launch resolver that uses EmuDeck-managed launchers.
- A health banner when EmuDeck is missing, configuration is unreadable, or the storage root is unavailable.
- Existing sync, metadata, artwork, download queue, and version switching kept functional.
- Unit tests for path resolution, launch resolution, and platform mapping.

### Post-MVP

- Per-platform emulator selection.
- Per-game emulator selection.
- Dynamic discovery from EmuDeck/SRM configuration.
- Full save-sync parity for standalone emulators.
- EmuDeck storage migration UX.
- Multi-device save-location normalization.
- Emulator-specific BIOS/firmware workflows beyond simple file placement.

### Explicit non-goals for the first release

- Reimplementing EmuDeck.
- Calling every emulator binary directly.
- Maintaining a second copy of EmuDeck's full emulator command database.
- Full save support for all standalone emulators on day one.
- Supporting Windows/macOS in the first EmuDeck fork release.

---

## 3. Architectural rule

Do not spread `if emudeck` checks throughout services.

The current project already has the right separation:

```text
services
  ↓ Protocols
adapters / host integration
  ↓
RetroDECK today
EmuDeck in the fork
```

Preserve that pattern.

The port should replace host-specific implementations at the composition root instead of rewriting business services.

Primary seam:

```text
py_modules/bootstrap.py
```

Current host-specific dependencies to replace or generalize include:

```text
py_modules/adapters/retrodeck_paths.py
py_modules/lib/retrodeck_health.py
py_modules/adapters/es_de_config.py
py_modules/adapters/retroarch_config.py
py_modules/adapters/retroarch_core_info.py
py_modules/domain/shortcut_data.py
py_modules/services/migration.py
py_modules/services/protocols/paths.py
main.py
```

---

## 4. Target design

### 4.1 Host paths

Create:

```text
py_modules/adapters/emudeck_paths.py
py_modules/lib/emudeck_health.py
```

Suggested interface:

```python
class EmuDeckPaths(Protocol):
    def emulation_root(self) -> str: ...
    def roms_path(self) -> str: ...
    def bios_path(self) -> str: ...
    def tools_path(self) -> str: ...
    def launchers_path(self) -> str: ...
    def config_path(self) -> str: ...
    def config_health(self) -> EmuDeckConfigHealth: ...
```

Resolution source:

```text
~/.config/EmuDeck/settings.json
```

Read:

```json
{
  "storagePath": "..."
}
```

Derive:

```text
<storagePath>/Emulation
<storagePath>/Emulation/roms
<storagePath>/Emulation/bios
<storagePath>/Emulation/tools
<storagePath>/Emulation/tools/launchers
```

Required behavior:

- Cache settings briefly, similar to the current RetroDECK adapter.
- Expand `$HOME`, `~`, and environment variables.
- Distinguish:
  - config absent;
  - config unreadable;
  - `storagePath` missing;
  - Emulation root missing;
  - root unavailable/unmounted;
  - OK.
- Never silently write to a guessed path when a configured external/SD storage root is unavailable.

Suggested health enum:

```text
ABSENT
UNREADABLE
INVALID
ROOT_MISSING
OK
```

---

## 5. Platform mapping

Do not assume RomM platform slugs equal EmuDeck directory names.

Keep the existing normalization concept:

```text
RomM slug/fs_slug
        ↓
local system identity
        ↓
EmuDeck ROM subfolder
```

Refactor terminology where practical:

```text
resolve_system(...)
```

may remain as the public seam, but comments/docs should say "local system folder" rather than "RetroDECK system".

Audit:

```text
defaults/config.json
py_modules/adapters/romm/http.py
docs/adr/0010-normalize-romm-slug-to-retrodeck-system.md
```

Create a compatibility test table covering at least:

```text
dc                  -> dreamcast
psx                 -> psx
ps2                 -> ps2
ps3                 -> ps3
ngp                 -> ngp
neo-geo-pocket      -> ngp
gc                  -> gc
wii                 -> wii
n3ds                -> n3ds
nds                 -> nds
psp                 -> psp
saturn              -> saturn
snes                -> snes
gba                 -> gba
```

Acceptance rule:

> Every platform enabled in the UI must resolve to the exact EmuDeck ROM directory the installed EmuDeck setup expects.

Unknown platform behavior:

- Preserve the safe verbatim fallback only if it remains inside the ROM root.
- Keep the existing path traversal guard.

---

## 6. Launch architecture

This is the core porting task.

### Current model

The current implementation assumes one RetroDECK Flatpak invocation:

```text
flatpak run net.retrodeck.retrodeck ...
```

and can pass ES-DE emulator overrides into that sandbox.

That model must not survive in the EmuDeck fork.

### New model

Use an explicit host launch plan:

```python
@dataclass(frozen=True)
class EmulatorInvocation:
    kind: str
    label: str | None = None
    executable: str | None = None
    args: tuple[str, ...] = ()
```

Recommended `kind` values for MVP:

```text
emudeck_launcher
retroarch
standalone
```

Prefer:

```text
Emulation/tools/launchers/<launcher>.sh
```

when EmuDeck provides a launcher for the emulator.

Example conceptual launch:

```text
/path/to/Emulation/tools/launchers/pcsx2-qt.sh "/path/to/game.iso"
```

### New modules

Create:

```text
py_modules/adapters/emudeck_launchers.py
py_modules/domain/emudeck_launch.py
```

Suggested responsibilities:

#### `EmuDeckLauncherAdapter`

- Locate launcher directory from `EmuDeckPaths`.
- Check whether a launcher exists and is executable/readable.
- Resolve a logical emulator ID to a launcher path.
- Return structured data; do not build shell strings.

#### `domain/emudeck_launch.py`

- Build a safe argv-like launch description.
- Quote only at the final Steam launch-options boundary.
- Keep ROM paths data, not shell fragments.
- Never interpolate server-controlled names into trusted command text.

### MVP launcher mapping

Start with a small explicit table for common systems. Keep it isolated in one module/config file.

Example shape:

```python
SYSTEM_DEFAULT_LAUNCHERS = {
    "ps2": "pcsx2-qt.sh",
    "gc": "dolphin.sh",
    "wii": "dolphin.sh",
    "psp": "ppsspp.sh",
}
```

Do not commit guessed launcher names without verifying them on a real EmuDeck installation.

For systems using RetroArch, determine the most stable EmuDeck-provided launcher route and use that instead of hardcoding RetroArch Flatpak internals.

### Launch fallback order

For MVP:

```text
1. Per-game explicit launcher override, if valid
2. Per-platform launcher override, if valid
3. Verified system default launcher
4. Fail launch resolution visibly
```

Do not fall back to a RetroDECK command.

A missing launcher should produce a clear state such as:

```text
needs_setup
launcher_missing
```

---

## 7. Shortcut generation changes

Primary file:

```text
py_modules/domain/shortcut_data.py
```

Tasks:

1. Remove:
   - `net.retrodeck.retrodeck`
   - `RETRODECK_INVOCATION`
   - RetroDECK sandbox core directory constants
   - `flatpak run --command=... net.retrodeck.retrodeck`
2. Replace the renderer with a host-neutral function.
3. Keep existing escaping/path safety guarantees.
4. Keep the existing `rom-launcher` wrapper unless a real reason is found to remove it.
5. Ensure version switching and reinstall paths re-bake launch options using the same resolver.

Required invariant:

> Every code path that creates or updates `launch_options` must use one shared EmuDeck launch resolver.

Search for all calls to:

```text
resolve_emulator_invocation
build_launch_options
launch_options
```

and route them through the same implementation.

---

## 8. Emulator discovery roadmap

### Phase A — fixed verified defaults

One launcher per supported system.

Goal: working ROM sync and launch.

### Phase B — discover installed launchers

Scan:

```text
Emulation/tools/launchers
```

Expose only installed/valid launchers.

Add a resolver table:

```text
system -> allowed emulator IDs -> launcher script
```

### Phase C — dynamic EmuDeck/SRM integration

Investigate using:

- EmuDeck settings;
- Steam ROM Manager parser definitions;
- EmuDeck-generated launcher metadata;
- installed emulator state.

Goal:

```text
system
  -> available emulator choices
  -> default emulator
  -> verified launch command
```

Only begin Phase C after the MVP launch path is stable.

---

## 9. BIOS plan

### MVP

Replace the BIOS root provider only.

Current services should receive:

```text
EmuDeckPaths.bios_path()
```

Audit all BIOS placement rules because EmuDeck has both:

```text
Emulation/bios
Emulation/bios/<system-specific-subdir>
```

Keep the existing separate BIOS vocabulary principle.

Do not reuse ROM-system normalization blindly for BIOS paths.

Test at least:

```text
PS1
PS2
Dreamcast
Nintendo DS
Switch-family special folders
```

For firmware that must be installed through an emulator UI or API, mark it unsupported in MVP rather than pretending that copying a file is sufficient.

---

## 10. Save sync plan

Do not block the MVP on complete save-sync parity.

### Step 1 — RetroArch only

Make existing RetroArch save support work against EmuDeck's RetroArch installation/configuration.

Change:

```text
py_modules/adapters/retroarch_config.py
py_modules/adapters/retroarch_core_info.py
```

to discover EmuDeck's actual RetroArch config/core metadata paths.

Acceptance criteria:

- active RetroArch save layout is read correctly;
- content-dir saves are detected;
- sort-by-content and sort-by-core behavior is respected;
- core canonical names resolve correctly.

### Step 2 — emulator-specific adapters

Introduce:

```python
class SaveLocationProvider(Protocol):
    def locations_for(self, system: str, emulator_id: str, rom: RomIdentity) -> list[SaveLocation]: ...
```

Then implement incrementally:

```text
RetroArchSaveLocationProvider
DolphinSaveLocationProvider
PCSX2SaveLocationProvider
PPSSPPSaveLocationProvider
RPCS3SaveLocationProvider
...
```

Each adapter needs tests with real EmuDeck path conventions.

### Safety rule

Until a provider exists for the active emulator:

- show save sync as unsupported for that game;
- do not guess;
- do not upload arbitrary emulator directories;
- do not silently use RetroArch rules for standalone emulators.

---

## 11. Migration and health behavior

### Migration MVP

Disable or remove RetroDECK-specific migration UX.

Replace the user-facing concept with:

```text
EmuDeck storage path changed
```

Track the last valid Emulation root.

Detect:

```text
old: /home/deck/Emulation
new: /run/media/.../Emulation
```

For the first release, prefer:

- detect and warn;
- verify existing installed ROM paths;
- offer rescan/rebind behavior;

before implementing automatic file movement.

Automatic movement is a later phase.

### Files to audit

```text
py_modules/services/migration.py
py_modules/domain/migration_paths.py
py_modules/adapters/migration_file.py
py_modules/lib/migration_gate.py
src/components/MigrationBlockedPage.tsx
src/components/MigrationBlockedCard.tsx
docs/user-guide/retrodeck-path-migration.md
```

---

## 12. Rename/generalize plan

Avoid a giant rename in the first commit.

### First pass

Introduce EmuDeck implementations while keeping service-facing protocol names temporarily if that reduces churn.

Example:

```text
RetroDeckPaths Protocol
```

can initially be replaced by:

```text
HostEmulationPaths
```

only after the adapter works.

### Recommended eventual terminology

```text
RetroDeckPaths        -> EmulationPaths
retrodeck_paths       -> emulation_paths
retrodeck_home        -> emulation_root
RetroDeckConfigHealth -> EmulationConfigHealth
```

Do terminology cleanup after behavior is covered by tests.

---

## 13. File-by-file worklist

### Create

```text
py_modules/adapters/emudeck_paths.py
py_modules/adapters/emudeck_launchers.py
py_modules/lib/emudeck_health.py
py_modules/domain/emudeck_launch.py

tests/adapters/test_emudeck_paths.py
tests/adapters/test_emudeck_launchers.py
tests/domain/test_emudeck_launch.py
tests/integration/test_emudeck_download_path.py
```

### Modify

```text
py_modules/bootstrap.py
py_modules/services/protocols/paths.py
py_modules/services/downloads.py
py_modules/services/rom_removal.py
py_modules/services/firmware.py
py_modules/domain/shortcut_data.py
py_modules/adapters/retroarch_config.py
py_modules/adapters/retroarch_core_info.py
main.py
src/api/backend.ts
src/utils/retrodeckHealth.ts
src/types/retrodeck.ts
src/types/index.ts
src/components/MainPage.tsx
src/components/DangerZone.tsx
README.md
plugin.json
```

### Audit before deciding to keep/replace

```text
py_modules/adapters/es_de_config.py
py_modules/domain/emulator_commands.py
py_modules/services/active_core_resolver.py
py_modules/services/cores.py
py_modules/services/relaunch_options_resolver.py
py_modules/services/version_switch.py
py_modules/services/saves/
py_modules/services/migration.py
```

### Remove or archive only after replacements exist

```text
py_modules/adapters/retrodeck_paths.py
py_modules/lib/retrodeck_health.py
docs/user-guide/retrodeck-path-migration.md
```

---

## 14. Milestones

## Milestone 0 — fork and baseline

Deliverables:

- fork builds unchanged;
- test suite passes before modifications;
- local Decky dev deployment works;
- create `emudeck-port` branch.

Exit criteria:

```text
baseline tests green
plugin loads
existing RetroDECK behavior reproducible
```

---

## Milestone 1 — EmuDeck path adapter

Deliverables:

- parse EmuDeck settings;
- resolve Emulation root;
- resolve ROM, BIOS, tools, launcher roots;
- health states;
- unit tests.

Exit criteria:

```text
EmuDeck internal storage detected
EmuDeck SD/external storage detected
missing settings handled
bad JSON handled
missing storagePath handled
unmounted root handled
no guessed write path used
```

---

## Milestone 2 — ROM download integration

Deliverables:

- downloads go to EmuDeck ROM folders;
- cleanup scans EmuDeck ROM/BIOS roots;
- uninstall removes only plugin-owned installs;
- installed path persistence works.

Exit criteria:

```text
single-file ROM download works
ZIP/multi-file ROM works
M3U path behavior still passes tests
cancel/pause/resume behavior still passes
uninstall works
path traversal tests remain green
```

---

## Milestone 3 — launch MVP

Deliverables:

- verified launcher mapping;
- EmuDeck launcher adapter;
- new launch renderer;
- Steam shortcuts launch real games.

Start with 3 systems:

```text
one RetroArch-backed system
one simple standalone emulator
one folder/multi-file-sensitive system
```

Suggested validation set:

```text
SNES or GBA
PS2
GameCube or Wii
```

Exit criteria:

```text
shortcut launches from Game Mode
paths with spaces work
special characters do not break argv handling
missing launcher is surfaced clearly
reinstall re-bakes launch command
version switch re-bakes launch command
```

---

## Milestone 4 — library UX cleanup

Deliverables:

- RetroDECK wording removed from visible UI;
- EmuDeck health banner;
- requirements/docs updated;
- settings and danger-zone text updated.

Exit criteria:

```text
no visible RetroDECK requirement text
no RetroDECK health terminology
plugin clearly reports EmuDeck configuration failures
```

---

## Milestone 5 — BIOS MVP

Deliverables:

- BIOS root switched;
- placement rules audited;
- unsupported firmware types marked honestly.

Exit criteria:

```text
PS1 BIOS verified
PS2 BIOS verified
Dreamcast BIOS verified
special-subfolder test verified
```

---

## Milestone 6 — emulator selection

Deliverables:

- launcher discovery;
- per-platform launcher choice;
- per-game launcher choice;
- persisted labels/IDs survive restart.

Exit criteria:

```text
invalid launcher cannot be selected
missing launcher degrades visibly
platform choice fans out to shortcuts
game override wins over platform default
```

---

## Milestone 7 — save sync

Deliverables:

- RetroArch save sync first;
- standalone emulator providers incrementally.

Exit criteria per emulator:

```text
local path discovery test
upload test
download test
conflict test
multiple-slot test where applicable
storagePath relocation test
```

---

## 15. Testing strategy

### Unit tests

Cover:

- settings parsing;
- path expansion;
- health classification;
- system mapping;
- launcher mapping;
- launcher existence;
- launch option escaping;
- missing launcher behavior;
- ROM path safety;
- BIOS path resolution.

### Contract tests

Create fake implementations for:

```text
EmulationPaths
LauncherResolver
SaveLocationProvider
```

Run existing services against fakes so host integration stays isolated.

### Integration tests on a Steam Deck

Use a disposable RomM test library.

Test matrix:

| Case | Internal storage | SD/external |
|---|---:|---:|
| Detect EmuDeck | ✓ | ✓ |
| Download ROM | ✓ | ✓ |
| Launch RetroArch system | ✓ | ✓ |
| Launch standalone system | ✓ | ✓ |
| Uninstall | ✓ | ✓ |
| BIOS download | ✓ | ✓ |
| Storage unavailable | n/a | ✓ |
| Reinsert storage | n/a | ✓ |

### Regression requirement

Before merging each milestone:

```text
existing non-host-specific tests must stay green
```

---

## 16. Recommended commit sequence

Keep commits small enough to review and revert.

```text
1. test: lock baseline behavior before EmuDeck port
2. feat: add EmuDeck settings and path adapter
3. refactor: generalize host path protocol
4. feat: route ROM and BIOS roots through EmuDeck paths
5. test: add EmuDeck download destination coverage
6. feat: add EmuDeck launcher adapter
7. refactor: replace RetroDECK shortcut renderer
8. feat: add initial verified system launcher map
9. test: cover launch rebakes and version switching
10. feat: add EmuDeck config health surface
11. chore: remove RetroDECK user-facing wording
12. docs: add EmuDeck setup and supported-system matrix
```

Do not combine save-sync work into these commits.

---

## 17. Tomorrow: first working session

### Task 1 — baseline

```bash
git clone <your-fork-url>
cd decky-romm-sync
git checkout -b emudeck-port
```

Run the project's documented install, lint, type-check, and test commands.

Record:

```text
Python version
Node version
package manager version
test count
current failures, if any
```

Do not begin the port until the baseline is understood.

### Task 2 — build the path adapter first

Implement only:

```text
py_modules/adapters/emudeck_paths.py
py_modules/lib/emudeck_health.py
tests/adapters/test_emudeck_paths.py
```

Test fixtures:

```text
valid internal settings.json
valid SD-card settings.json
missing file
malformed JSON
storagePath missing
Emulation root missing
```

Do not touch launch logic on the first pass.

### Task 3 — wire paths in bootstrap

Replace construction of:

```text
RetroDeckPathsAdapter
```

with the new EmuDeck path implementation.

At this point, keep protocol renaming minimal.

### Task 4 — make one ROM download land correctly

Pick one simple single-file platform.

Success condition:

```text
RomM download
    ↓
<storagePath>/Emulation/roms/<system>/<rom file>
```

Verify:

- file exists;
- install record stores correct path;
- uninstall removes the file;
- unrelated ROMs remain untouched.

### Task 5 — end the day with a narrow PR/commit

Ideal first-day result:

```text
EmuDeck settings detected
ROM root resolved
BIOS root resolved
health states tested
one ROM can download to the right folder
```

Do not start save-sync work on day one.

---

## 18. Definition of MVP done

The EmuDeck fork is MVP-ready when all of the following are true:

- Plugin starts without RetroDECK installed.
- Plugin requires and detects EmuDeck.
- Internal and SD/external `storagePath` layouts work.
- Library sync creates Steam entries.
- ROM downloads go to correct EmuDeck folders.
- At least the initially supported system matrix launches reliably from Game Mode.
- Uninstall removes only plugin-managed ROM installs.
- Artwork and metadata still work.
- Version switching still produces correct launch options.
- BIOS downloads work for the explicitly supported BIOS matrix.
- Unsupported save-sync cases are disabled or clearly marked, never guessed.
- CI is green.
- README contains an honest supported-system and supported-save-sync matrix.

---

## 19. Key design decisions to preserve

1. **One normalization boundary.** Convert RomM platform identity into local system identity once.
2. **One launch resolver.** Every shortcut creation/re-bake path uses the same resolver.
3. **No guessed paths.** Missing or unreadable EmuDeck config is a visible health failure.
4. **No guessed saves.** Save sync is enabled only when a verified provider exists.
5. **Reuse EmuDeck's launchers.** Do not duplicate emulator-specific boot logic unnecessarily.
6. **Keep services host-agnostic.** EmuDeck details belong in adapters/domain launch resolution.
7. **Ship narrow compatibility first.** A small verified system matrix is better than broad unreliable support.

---

## 20. First issues to create

### Issue 1 — EmuDeck path adapter

**Goal:** Read EmuDeck `storagePath` and expose Emulation roots with health classification.

### Issue 2 — Generalize host path protocol

**Goal:** Remove RetroDECK naming from service-facing path seams without changing service behavior.

### Issue 3 — EmuDeck download destinations

**Goal:** Route ROM and BIOS downloads to EmuDeck roots and preserve install/uninstall safety.

### Issue 4 — EmuDeck launcher resolver

**Goal:** Resolve supported systems to verified EmuDeck launcher scripts.

### Issue 5 — Replace RetroDECK launch rendering

**Goal:** Build Steam launch options from EmuDeck launcher invocations.

### Issue 6 — EmuDeck health UI

**Goal:** Replace RetroDECK config-health types, backend callables, and UI banner text.

### Issue 7 — RetroArch save support on EmuDeck

**Goal:** Discover EmuDeck RetroArch config/core metadata and restore RetroArch save-sync parity.

---

## 21. Stop conditions

Pause and redesign instead of adding hacks if any of these happen:

- launcher names differ unpredictably across EmuDeck versions;
- launcher scripts are regenerated in a way that invalidates stored paths;
- a service needs to know whether the host is RetroDECK or EmuDeck;
- multiple modules independently build emulator commands;
- save paths are being inferred from ROM system alone;
- external storage failure causes fallback writes into internal storage;
- Steam shortcut re-bake logic diverges between install, reinstall, core change, and version switch.

These are architecture failures, not edge cases.

---

## 22. Recommended first release support statement

Use an explicit matrix in the README:

```text
ROM library sync: supported
ROM downloads: supported
Steam shortcut creation: supported
Artwork/metadata: supported
BIOS download: supported for listed systems
Emulator selection: limited to listed systems/emulators
Save sync: RetroArch only initially
Standalone-emulator save sync: not yet supported
Automatic EmuDeck storage migration: not yet supported
```

That keeps the first release useful without claiming parity that has not been verified.

---

## 23. Immediate next implementation target

Start with this dependency chain:

```text
EmuDeck settings.json
        ↓
EmuDeckPathsAdapter
        ↓
bootstrap.py
        ↓
DownloadService
        ↓
one ROM written to correct EmuDeck system folder
```

Only after that works, continue with:

```text
EmuDeck launcher directory
        ↓
EmuDeckLauncherAdapter
        ↓
shared launch resolver
        ↓
shortcut_data.py
        ↓
one game launched successfully from Game Mode
```

That is the shortest path to proving the fork architecture.
