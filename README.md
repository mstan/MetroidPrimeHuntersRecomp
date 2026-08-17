# MetroidPrimeHuntersRecomp

> **Public alpha - bugs are expected.** This is an early Metroid Prime Hunters
> recompilation release built on [ndsrecomp](https://github.com/mstan/ndsrecomp).
> It is not a finished port. Expect rough edges, crashes, hangs, rendering or
> audio issues, input quirks, networking failures, and possible desyncs. Testing,
> issues, and PRs are welcome.

MetroidPrimeHuntersRecomp currently ships generated content profiles for the
validated ROM revisions tracked by this branch. Runtime base detection is
prepared for all seven retail Metroid Prime Hunters revisions and uses
melonPrimeDS-compatible executable checksums; whole-ROM SHA-1 is content
provenance, not the runtime address selector. You provide your own legally
obtained ROM. No Nintendo ROM, BIOS, firmware, save data, or generated
ROM-derived source is distributed.

## Gameplay Preview

[![Metroid Prime Hunters Recomp gameplay preview](docs/media/prime-hunters-video-preview.jpg)](https://www.youtube.com/watch?v=tvqnW6J6KU0)

Click the image to watch the gameplay preview on YouTube.

## Current Release

Latest upstream release:
**[v0.4.0-alpha](https://github.com/mstan/MetroidPrimeHuntersRecomp/releases/tag/v0.4.0-alpha)**.

Downloads:

- Windows:
  `MetroidPrimeHuntersRecomp-windows-x64-v0.4.0.zip`
- Linux:
  `MetroidPrimeHuntersRecomp-linux-x86_64-v0.4.0.AppImage`

This is an early ndsrecomp title and should still be treated as an alpha test
build rather than a polished game release.

New in upstream v0.4.0 is an opt-in **HD Rendering** mod on the launcher Mods
page. It can raise the internal 3D resolution up to 4x and optionally upscale
decoded textures. It is disabled by default; native rendering remains the
reference path. This branch keeps that upstream feature alongside the
multi-ROM-safe Adaptive Widescreen and Prime Controls work.

## Quick Start

Windows:

1. Download and fully extract the Windows ZIP.
2. Put your own supported Metroid Prime Hunters `.nds` ROM next to the launcher.
3. Run `MetroidPrimeHuntersRecomp.exe` and press Play.

Linux:

1. Download the AppImage.
2. Put your own supported Metroid Prime Hunters `.nds` ROM next to the AppImage.
3. Run the AppImage.

The current release can use the built-in FreeBIOS + generated firmware path, so
retail DS BIOS and firmware dumps are not required for the default no-dump
startup path. If you choose to use your own BIOS/firmware dumps, they must be
from hardware you own and must match the hashes listed in the release's
`bios/README.txt`.

## ROM identity and multi-ROM support

Runtime address selection does **not** use whole-ROM SHA-1. The runner first
uses the melonPrimeDS executable checksum (CRC32 over header + ARM9 + ARM7),
then uses exact game code + supported revision only as a fallback base-profile
hint. Header-only matches never authorize host RAM/code writes.

Known compatible executable checksums can use the revision-specific Prime
Controls and Adaptive Widescreen addresses. Whole-ROM SHA-1 remains the exact
content identity for generated banks, coverage, checkpoints and capture data,
so one modified ROM cannot silently reuse another modified ROM's generated
content.

The current branch has runtime address profiles for US1.0, US1.1, EU1.0,
EU1.1, JP1.0, JP1.1 and KR1.0. A revision still needs its own generated
content/capture coverage before it is considered fully brought up.

## What Works

- Boots supported content profiles through the ndsrecomp runner.
- Reaches Metroid Prime Hunters gameplay in tested routes.
- Includes an adaptive 21:9 upper-screen widescreen option using per-revision
  projection/culling addresses from melonPrimeDS/mphCodex.
- Includes Prime-style keyboard and mouse controls.
- Includes full remappable gamepad bindings in the launcher.
- Includes upstream HD Rendering controls for internal resolution and texture
  upscaling.
- Supports mouse-driven touchscreen input.
- Can authenticate through Wiimmfi and reach a Friends and Rivals lobby in
  validated flows.
- Persists mutable firmware/WFC state between launches through the upstream
  firmware-state path.

## Known Limits

- This is an alpha. Bugs, crashes, hangs, graphical issues, audio issues, and
  gameplay problems are expected.
- Gameplay coverage is incomplete. Do not assume the campaign is fully
  validated from start to finish.
- Widescreen is still being audited. Some scenes, effects, HUD placement,
  movies, fades, or screen-routing behavior may be wrong.
- HD texture upscaling remains opt-in and should not be treated as the native
  reference rendering path.
- Online play is experimental. Wiimmfi can reach the lobby in validated flows,
  but in-game play is ultimately untested. There is no guarantee that a match
  will connect, stay connected, or avoid desync.
- Save behavior and settings are still part of early release testing. Keep
  backups of anything you care about.

## Controls

Prime Controls are enabled by default.

Keyboard and mouse defaults:

- `WASD`: move
- Mouse: aim
- Mouse 1 / Mouse 2: fire / scan-fire
- `Space`: jump
- `Left Ctrl`: morph ball
- `Left Shift`: boost / map zoom
- `C`: scan visor
- `F`: OK
- `Q` / `E`: scan-message arrows
- `V`: menu
- Mouse 4: missiles
- Mouse 5: beam
- `1` through `6`: subweapons
- `Tab`: virtual stylus

Gamepad defaults:

- Left stick: move and menu D-pad
- Right stick: aim
- `RT` / `LT`: shoot / scan-fire
- `A`: jump
- `B`: morph ball
- `X`: missile
- `Y`: UI OK
- `LB` / `RB`: beam / boost or zoom
- `R3`: scan visor
- D-pad left/right: scan-message arrows
- `Start`: menu

Keyboard, mouse, and gamepad bindings are editable from the launcher Mods page.

## Online Play

Nintendo WFC / Wiimmfi support is experimental. The current validated state is
lobby connectivity: Metroid Prime Hunters can authenticate through Wiimmfi and
reach a Friends and Rivals lobby where a locally hosted game is visible.

The launcher keeps the console firmware profile in
`%APPDATA%\MetroidPrimeHuntersRecomp`. Wi-Fi settings, console/game-card
pairing, and WFC updates survive both the in-game system shutdown flow and a
normal window close. Confirming the WFC settings shutdown prompt closes the
application automatically.

Actually joining a match and playing in-game online is not guaranteed. It may
fail to connect, disconnect, or desync.

The Wi-Fi implementation is built on
[melonDS](https://github.com/melonDS-emu/melonDS)'s Wi-Fi work in the shared
ndsrecomp runner. Full credit to the melonDS team for the Wi-Fi controller,
emulated access point, and network backend foundation.

## Credits

- [melonDS](https://github.com/melonDS-emu/melonDS): Wi-Fi implementation
  foundation used by the shared ndsrecomp runner.
- [melonPrimeDS](https://github.com/ag-advania/melonPrimeDS): runtime-version
  detection, Prime-style controls, and per-version aspect-ratio patch reference.
- [mphCodex](https://github.com/Zection6V/mphCodex): MPH game-code analysis,
  including the seven-version widescreen projection/culling mapping.
- [MphRead](https://github.com/NoneGiven/MphRead): Metroid Prime Hunters file
  format and behavior reference.

See the ndsrecomp
[`THIRD_PARTY_ATTRIBUTION.md`](https://github.com/mstan/ndsrecomp/blob/main/THIRD_PARTY_ATTRIBUTION.md)
for provenance and licensing details for shared runtime components.

## Developers

This README is intentionally player-facing. Development notes, validation
history, and bring-up details live in [`docs/BRINGUP.md`](docs/BRINGUP.md).

The original code in this repository is MIT licensed. Metroid Prime Hunters,
Nintendo DS firmware/BIOS images, ROMs, saves, and all derived game data remain
the property of their respective copyright holders and are not distributed.
