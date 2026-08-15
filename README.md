# MetroidPrimeHuntersRecomp

> **Public alpha - bugs are expected.** This is an early Metroid Prime Hunters
> recompilation release built on [ndsrecomp](https://github.com/mstan/ndsrecomp).
> It is not a finished port. Expect rough edges, crashes, hangs, rendering or
> audio issues, input quirks, networking failures, and possible desyncs. Testing,
> issues, and PRs are welcome.

MetroidPrimeHuntersRecomp runs the USA revision-0 release of **Metroid Prime
Hunters** as a native recompilation target. You provide your own legally
obtained ROM. No Nintendo ROM, BIOS, firmware, save data, or generated
ROM-derived source is distributed.

## Gameplay Preview

[![Metroid Prime Hunters Recomp gameplay preview](docs/media/prime-hunters-video-preview.jpg)](https://www.youtube.com/watch?v=tvqnW6J6KU0)

Click the image to watch the gameplay preview on YouTube.

## Current Release

Latest release:
**[v0.3.0-alpha](https://github.com/mstan/MetroidPrimeHuntersRecomp/releases/tag/v0.3.0-alpha)**.

Downloads:

- Windows:
  `MetroidPrimeHuntersRecomp-windows-x64-v0.3.0.zip`
- Linux:
  `MetroidPrimeHuntersRecomp-linux-x86_64-v0.3.0.AppImage`

This is the first release line in the ndsrecomp ecosystem and it is still very
early. Campaign entry, widescreen output, Prime-style controls, gamepad support,
and Wiimmfi lobby connectivity have all seen active bring-up, but this should
still be treated as an alpha test build rather than a polished game release.

## Quick Start

Windows:

1. Download and fully extract the `v0.3.0-alpha` Windows ZIP.
2. Put your own Metroid Prime Hunters USA revision-0 `.nds` ROM next to
   `MetroidPrimeHuntersRecomp.exe`.
3. Run `MetroidPrimeHuntersRecomp.exe` and press Play.

Linux:

1. Download the `v0.3.0-alpha` AppImage.
2. Put your own Metroid Prime Hunters USA revision-0 `.nds` ROM next to the
   AppImage.
3. Run the AppImage.

The current release can use the built-in FreeBIOS + generated firmware path, so
retail DS BIOS and firmware dumps are not required for the default no-dump
startup path. If you choose to use your own BIOS/firmware dumps, they must be
from hardware you own and must match the hashes listed in the release's
`bios/README.txt`.

## Required ROM

Only this ROM revision is supported:

| field | value |
|---|---|
| title | `MP HUNTERS` |
| game code | `AMHE` |
| region/revision | USA revision 0 |
| size | 64 MiB |
| SHA-1 | `90164d1ac127ee5f9815ea4ae7de798c7b5fc629` |
| SHA-256 | `7d0a98ff98e1b7c985d1f3d89b01730af1b2115061a4dfea847612d217a8b855` |

If your ROM does not match, the launcher/runner should reject it.

## What Works

- Boots the supported ROM through the ndsrecomp runner.
- Reaches Metroid Prime Hunters gameplay in tested routes.
- Includes an adaptive 21:9 upper-screen widescreen option.
- Includes Prime-style keyboard and mouse controls.
- Includes full remappable gamepad bindings in the launcher.
- Supports mouse-driven touchscreen input.
- Can authenticate through Wiimmfi and reach a Friends and Rivals lobby in
  validated flows.

## Known Limits

- This is an alpha. Bugs, crashes, hangs, graphical issues, audio issues, and
  gameplay problems are expected.
- Gameplay coverage is incomplete. Do not assume the campaign is fully
  validated from start to finish.
- Widescreen is still being audited. Some scenes, effects, HUD placement,
  movies, fades, or screen-routing behavior may be wrong.
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

Actually joining a match and playing in-game online is not guaranteed. It may
fail to connect, disconnect, or desync.

The Wi-Fi implementation is built on
[melonDS](https://github.com/melonDS-emu/melonDS)'s Wi-Fi work in the shared
ndsrecomp runner. Full credit to the melonDS team for the Wi-Fi controller,
emulated access point, and network backend foundation.

## Credits

- [melonDS](https://github.com/melonDS-emu/melonDS): Wi-Fi implementation
  foundation used by the shared ndsrecomp runner.
- [melonPrimeDS](https://github.com/makinori/melonPrimeDS): reference for the
  Prime-style keyboard/mouse controls and touchscreen-helper behavior.
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
