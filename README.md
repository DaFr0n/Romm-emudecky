# EmuRomm Sync

> **Fork changes and AI assistance:** This fork adapts RomM Sync for EmuDeck. The merged work includes a launcher-path CI test correction ([PR #1](https://github.com/DaFr0n/Romm-emudecky/pull/1)), security hardening for BIOS registry reads, launcher paths and release downloads ([PR #2](https://github.com/DaFr0n/Romm-emudecky/pull/2)), and a Sonar test assertion fix ([PR #3](https://github.com/DaFr0n/Romm-emudecky/pull/3)). The experimental filesystem-probe changes in [PR #4](https://github.com/DaFr0n/Romm-emudecky/pull/4) were **not merged**. Four pre-existing SonarCloud filesystem-oracle findings remain under review.
>
> **AI disclosure:** OpenAI ChatGPT assisted with reviewing findings, proposing and editing changes, tests, CI/build troubleshooting, and documentation. The maintainer tested the installable Decky build and reported the changes working on a Legion Go S running SteamOS. AI assistance and a successful build do not guarantee that all issues are resolved.
>
> **EmuDeck fork** of [melikootje/Romm-emudecky](https://github.com/melikootje/Romm-emudecky), originally based on
> [danielcopper/decky-romm-sync](https://github.com/danielcopper/decky-romm-sync). This branch targets EmuDeck rather than RetroDECK.

A [Decky Loader](https://decky.xyz/) plugin that syncs your self-hosted [RomM](https://github.com/rommapp/romm) library
into Steam as non-steam shortcuts. Games appear directly in your Steam library, launch through EmuDeck, and keep their
saves in sync across devices through your RomM server.

## Features

- **Library sync** — Pulls platforms and ROMs from your RomM server and creates Steam shortcuts, complete with cover
  art, hero banners, and logos (with optional [SteamGridDB](https://www.steamgriddb.com/) artwork)
- **Save sync** — Keeps save files in sync across devices through your RomM server, with newest-wins conflict resolution
  and a manual override when you need it
- **ROM downloads** — Download ROMs on demand with progress tracking and a managed download queue
- **Optional auto-download during library sync** — Enable **Auto-download synced games** before syncing to queue missing ROMs automatically, including games whose Steam shortcuts already exist. No Force Full Sync required.
- **Default-version selection** — When a game has multiple RomM versions, only the synced, active **Default** version is eligible for automatic download. **Not Synced** alternatives are ignored; already-installed versions are left untouched. Multi-disc files belonging to the selected ROM use the existing downloader.
- **BIOS management** — Download firmware/BIOS files from RomM for systems that need them (PSX, Dreamcast, PS2, …)
- **Game detail page** — Install status, BIOS status, and download/uninstall actions right on each game's Steam page
- **Per-platform control** — Choose exactly which platforms get synced
- **Controller friendly** — Full gamepad navigation throughout the plugin UI
- **Steam Input config** — Per-shortcut Steam Input mode (Default / Force On / Force Off)
- **EmuDeck path migration** — Move your EmuDeck installation between storage locations without re-syncing
- **EmuDeck health diagnostics** — Detects misconfigured input drivers and EmuDeck configuration issues that break menu
  navigation

## Screenshots

|                                   QAM panel                                    |                                        Game detail page                                         |
| :----------------------------------------------------------------------------: | :---------------------------------------------------------------------------------------------: |
|               ![EmuRomm Sync QAM panel](assets/screenshot-qam.jpg)                |              ![Game detail page with metadata](assets/screenshot-game-detail.jpg)               |
|                              **BIOS management**                               |                                      **Per-game actions**                                       |
| ![BIOS status showing a required file to download](assets/screenshot-bios.jpg) | ![RomM actions menu: sync saves, download BIOS, refresh artwork](assets/screenshot-actions.jpg) |

## Current status

- **Pre-release test build:** Auto-download has been tested successfully by the maintainer when using Force Full Sync. The follow-up change to support existing shortcuts with ordinary incremental sync and the new display name **EmuRomm Sync** still need on-device verification before the first release.
- **Tested on Legion Go S (SteamOS):** the Decky plugin ZIP installs successfully, and the fork's merged changes have been tested by the maintainer.
- **Development branch:** [`emudeck-port`](https://github.com/DaFr0n/Romm-emudecky/tree/emudeck-port). The working changes from PRs #1–#3 are merged; the unsuccessful filesystem-probe experiment in PR #4 was not merged.
- **Security:** launcher-path containment checks and other hardening are included. Four inherited SonarCloud filesystem-oracle findings remain under review; passing a build does not establish that they are resolved.
- **Compatibility:** functionality can depend on installed EmuDeck launcher scripts and emulator configuration. Not every emulator or save-sync scenario has been verified.

## Requirements

- [Decky Loader](https://decky.xyz/) on your Steam Deck or Linux HTPC — the plugin lives in Steam's gamepad UI, so it
  works in the Deck's Game Mode **or** in Big Picture Mode on any Linux PC
- A running [RomM](https://github.com/rommapp/romm) server, **version 4.9.0 or newer** (the plugin stays inert against
  older servers)
- [EmuDeck](https://www.emudeck.com/) for launching games

## Installation

### Test build from GitHub Actions

This fork currently distributes **EmuRomm Sync** test builds through **GitHub Actions artifacts**, not GitHub Releases or the Decky Store.

1. Open the [Build EmuDeck Plugin ZIP workflow](https://github.com/DaFr0n/Romm-emudecky/actions/workflows/build-emudeck.yml).
2. Open the latest **successful** run for `emudeck-port`.
3. Under **Artifacts**, download `RomM-EmuDeck-Decky-Plugin` (GitHub login may be required).
4. **Extract the downloaded artifact ZIP**. It contains the actual Decky-installable plugin ZIP; do not submit the outer GitHub artifact archive or the repository's **Code → Download ZIP** source archive to Decky.
5. In Decky Loader, enable **Developer Mode**, then open **Settings → Developer → Install Plugin from ZIP** and select the **inner plugin ZIP**.
6. Back up existing plugin settings and saves before updating. Because the Decky display name changed from **RomM Sync** to **EmuRomm Sync**, verify that Decky has not retained a second old plugin entry. Do not delete plugin data or uninstall the previous build without backing up first.
7. Restart Decky Loader if necessary, then verify connection, paths, ROM downloads, shortcuts and saves.

A green workflow means the plugin was built and packaged successfully; it does not replace testing on the target device.

## Quick start

1. Open the Quick Access Menu and select **EmuRomm Sync**
2. In **Settings**, enter your RomM server URL and credentials, then hit **Test Connection**
3. In **Platforms**, enable the platforms you want to sync
4. Optionally enable **Auto-download synced games** before syncing; leave it off if you only want Steam shortcuts.
5. Hit **Sync Library** — your ROMs appear as non-Steam shortcuts. With auto-download enabled, missing default ROMs are queued after a successful sync, even for shortcuts already present.
6. **Skip Preview** applies changes immediately; otherwise review the preview and select **Apply Sync**. **Force Full Sync** clears the sync cache and re-fetches platform data; it should **not** be necessary just to auto-download games for existing shortcuts.

### Automatic downloads: what to expect

- The auto-download toggle is **off by default** and applies to the current plugin session. Enable it **before** starting a sync.
- The downloader checks both newly synced shortcuts and existing shortcut bindings. Incremental sync can report no shortcut changes and still queue missing ROMs.
- For multi-version games, only a ROM marked **Default** that is also the active synced shortcut version is eligible. Versions marked **Not Synced** are not downloaded.
- Existing installations are skipped, including a different version of the same game, to avoid overwriting a manually selected install.
- Downloads use the normal queue (up to two concurrent downloads). If you cancel the sync, automatic downloads are not started. Existing queued downloads remain managed by the normal Downloads screen.
- This feature is being tested ahead of the first release. If you notice unexpected version selection, disable auto-download and report the game and version labels.

See the [User Guide](https://melikootje.github.io/Romm-emudecky/user-guide/syncing-your-library/) for syncing details,
[save sync](https://melikootje.github.io/Romm-emudecky/user-guide/save-sync/), and
[BIOS management](https://melikootje.github.io/Romm-emudecky/user-guide/bios-management/).

## Contributing

Build from source, run the tests, and read the architecture reference on the documentation site:

- [Development setup](https://melikootje.github.io/Romm-emudecky/contributing/development/)
- [Frontend dev loop](https://melikootje.github.io/Romm-emudecky/contributing/frontend-dev-loop/) — live-reload the UI
  into a windowed Big Picture on the Deck, no Game Mode switching
- [Backend architecture](https://melikootje.github.io/Romm-emudecky/architecture/backend-architecture/)

## Acknowledgments

This plugin stands on the shoulders of some great projects:

- [melikootje/Romm-emudecky](https://github.com/melikootje/Romm-emudecky) — the direct upstream fork and EmuDeck codebase.
- [danielcopper/decky-romm-sync](https://github.com/danielcopper/decky-romm-sync) — the original RomM Sync project and foundation for the integration.
- [RomM](https://github.com/rommapp/romm) — the self-hosted ROM manager at the heart of this plugin. RomM provides the
  library, metadata, cover art, and save file storage that makes the entire sync experience possible
- [EmuDeck](https://www.emudeck.com/) — the all-in-one emulation solution for Steam Deck that bundles ES-DE, RetroArch,
  and standalone emulators with launcher scripts. Our entire launch chain runs through EmuDeck
- [Decky Loader](https://decky.xyz/) — the plugin framework that makes all of this possible
- [Valve](https://www.valvesoftware.com/) — for the Steam Deck, SteamOS, and an open enough platform to build on
- [Unifideck](https://github.com/ma3ke/unifideck) — inspiration for game detail page injection techniques and gamepad
  navigation patterns
- [MetaDeck](https://github.com/EmuDeck/MetaDeck) — inspiration for store patching patterns used in metadata display on
  non-Steam shortcuts
- [Argosy](https://github.com/rommapp/argosy-launcher) — RomM's Android device-sync client. Its baseline-anchored
  save-conflict handling — client-side detection layered over RomM's negotiate transport, with a keep-local/keep-remote
  prompt on genuine divergence — validated the posture this plugin's save sync takes
- [Grout](https://github.com/rommapp/grout) — RomM's Linux handheld client. Its 409-driven upload reconciliation (POST
  with overwrite=false, downgrading to a download when the local save is unchanged and surfacing a conflict when it
  diverged) informed this plugin's negotiate upload and conflict path

## License

GPL-3.0
