# MetroidPrimeHuntersRecomp

> **Public alpha - bugs are expected.** This is an early Metroid Prime Hunters
> recompilation release built on [ndsrecomp](https://github.com/mstan/ndsrecomp).
> It is not a finished port. Expect rough edges, crashes, hangs, rendering or
> audio issues, input quirks, networking failures, and possible desyncs. Testing,
> issues, and PRs are welcome.

MetroidPrimeHuntersRecomp runs **Metroid Prime Hunters** as an ndsrecomp target.
Runtime base-version detection supports the known US1.0, US1.1, EU1.0, EU1.1,
JP1.0, JP1.1, and KR1.0 layouts using executable-compatible detection rather
than using whole-ROM SHA-1 as the base-profile selector. You provide your own
legally obtained ROM. No Nintendo ROM, BIOS, firmware, save data, or generated
ROM-derived source is distributed.

## Gameplay Preview

[![Metroid Prime Hunters Recomp gameplay preview](docs/media/prime-hunters-video-preview.jpg)](https://www.youtube.com/watch?v=tvqnW6J6KU0)

Click the image to watch the gameplay preview on YouTube.

## Current Release

The project version is **v0.4.0-alpha**. Development Nightly builds are produced
from `develop` under the fixed `nightly-release` prerelease tag after the
Windows and Linux build workflows and release-payload safety checks succeed.

The Nightly build path is deliberately **ROM-free**: GitHub Actions never needs
or downloads a Metroid Prime Hunters ROM, private ROM URL, proprietary BIOS or
firmware dump, save file, or ROM-derived MPH title bank. Users supply their ROM
at runtime. In the current Nightly architecture, title code without a linked
content-specific native bank executes through ndsrecomp Tier-3. This is a safe
correctness fallback and may be slower than an optimized tagged build.

The package reserves a portable optimization-cache root beside the executable
or AppImage at `cache/banks/<content-sha1>/`. The current Nightly does not yet
generate native title banks there. The intended next step is a compiler-free
local optimization/JIT cache; see [`docs/LOCAL_BANK_CACHE.md`](docs/LOCAL_BANK_CACHE.md).

## Quick Start

Windows:

1. Download and fully extract the Windows ZIP.
2. Put your own Metroid Prime Hunters `.nds` ROM next to
   `MetroidPrimeHuntersRecomp.exe`, or select it in the launcher.
3. Run `MetroidPrimeHuntersRecomp.exe` and press Play.

Linux:

1. Download the AppImage and make it executable if required by your desktop.
2. Put your own Metroid Prime Hunters `.nds` ROM next to the AppImage.
3. Run the AppImage.

The current release can use the built-in FreeBIOS + generated firmware path, so
retail DS BIOS and firmware dumps are not required for the default no-dump
startup path. The ROM-free Nightly generates its native FreeBIOS banks only
from the redistributable BSD-2-Clause FreeBIOS source path at build time.

## ROM identity and multi-ROM behavior

Three identity layers are kept separate:

1. **Runtime base profile:** executable checksum / exact supported header tuple.
2. **Executable compatibility:** determines whether dangerous host RAM/code
   writes such as Aim/Morph/Adaptive Widescreen patches are authorized.
3. **Exact content identity:** whole-ROM SHA-1 for provenance, generated banks,
   captures, and the future local optimization-cache namespace.

Whole-ROM SHA-1 therefore does not decide that a modified ROM is US1.0 or EU1.1.
Unknown or ambiguous executable content never silently falls back to US1.0, and
host writes fail closed unless executable compatibility is authoritative.

Exact clean-content profiles currently validated in the repository include the
US1.0 and EU1.1 bring-up tracks. Other base layouts are prepared at runtime, but
full per-ROM extraction, coverage, gameplay validation, and optimized bank work
must still be completed before they should be described as equally validated
release targets.

## Enhancements

### Adaptive Widescreen

The launcher exposes an adaptive 21:9 upper-screen mode. The implementation
combines ndsrecomp's widened host renderer/compositor and HUD anchoring with
profile-aware Metroid Prime Hunters projection/culling corrections derived from
the audited melonPrimeDS/mphCodex address tables. Unsupported/unsafe runtime
identity falls back rather than applying guessed guest writes.

### Prime Controls

Prime-style keyboard/mouse controls and remappable gamepad bindings are exposed
through the launcher. Defaults include WASD movement, mouse aim, Mouse 1 fire,
and the existing touch-helper mappings.

### HD Rendering

HD Rendering is opt-in. It raises the 3D engine above native DS sample density
(up to the supported internal-resolution choices) and can upscale decoded
textures. The native 2D path remains the reference and HD Rendering is off by
default.

## Online Play

Nintendo WFC / Wiimmfi support remains experimental. The launcher persists the
console firmware profile in the user's application-data location so Wi-Fi
settings, console/game-card pairing, and WFC updates survive later launches.
Online play may still fail to connect, disconnect, or desync.

The Wi-Fi implementation is built on
[melonDS](https://github.com/melonDS-emu/melonDS)'s Wi-Fi work in the shared
ndsrecomp runner. Full credit to the melonDS team for the Wi-Fi controller,
emulated access point, and network backend foundation.

## Known Limits

- This is an alpha. Bugs, crashes, hangs, graphical issues, audio issues, and
  gameplay problems are expected.
- Gameplay coverage is incomplete across the seven base layouts.
- The ROM-free Nightly's Tier-3 title fallback can be substantially slower than
  a build with validated native MPH optimization banks, especially in known hot
  paths such as opening movies.
- The local `cache/banks/<content-sha1>/` directory is currently a reserved
  cache contract; dynamic native/JIT bank generation is not implemented yet.
- Widescreen still requires sustained gameplay auditing across scenes, effects,
  HUD placement, movies, fades, and screen routing.
- Online play is experimental.
- Save behavior and settings remain part of early release testing. Keep backups
  of anything you care about.

## Credits

- [melonDS](https://github.com/melonDS-emu/melonDS): Wi-Fi implementation
  foundation used by the shared ndsrecomp runner.
- [melonPrimeDS](https://github.com/ag-advania/melonPrimeDS): reference for
  Prime-style controls, ROM/version address tables, and aspect-ratio research.
- [mphCodex](https://github.com/Zection6V/mphCodex): game-code/disassembly and
  Metroid Prime Hunters behavior research.
- [MphRead](https://github.com/NoneGiven/MphRead): Metroid Prime Hunters file
  format and behavior reference.

See the ndsrecomp `THIRD_PARTY_ATTRIBUTION.md` for shared-runtime provenance and
licensing details.

## Developers

Bring-up and validation notes live under [`docs/`](docs/). The ROM-free Nightly
and local-cache direction is documented in
[`docs/LOCAL_BANK_CACHE.md`](docs/LOCAL_BANK_CACHE.md).

The original code in this repository is MIT licensed. Metroid Prime Hunters,
Nintendo DS firmware/BIOS images, ROMs, saves, and all derived game data remain
the property of their respective copyright holders and are not distributed.
