# MetroidPrimeHuntersRecomp

Early Metroid Prime Hunters static-recompilation target for
[ndsrecomp](https://github.com/mstan/ndsrecomp). The project is pinned to the
USA revision-0 game and is being used to turn the initial SM64DS-oriented
framework into a multi-title Nintendo DS recompilation ecosystem.

## Verified local target

| field | value |
|---|---|
| file | `Metroid Prime Hunters.nds` (Git-ignored) |
| title | `MP HUNTERS` |
| game code | `AMHE` |
| revision | 0 |
| size | 64 MiB |
| SHA-1 | `90164d1ac127ee5f9815ea4ae7de798c7b5fc629` |
| SHA-256 | `7d0a98ff98e1b7c985d1f3d89b01730af1b2115061a4dfea847612d217a8b855` |

Never commit the ROM, extracted code/data, generated recompilation output,
screenshots, saves, or other Nintendo material.

## Current boundary

The ROM-gated static ARM9/ARM7 main banks boot through the authentic
firmware/cartridge path and complete the game's no-input attract loop with
interpreter fallback for code that is not compiled yet. The run reaches the
title at VBlank 7800, continues its title animation at VBlank 8400, returns to
the hunter reel by VBlank 9000, and remains alive through VBlank 12000 without
a terminal dispatch miss.

The deterministic `scenarios/adventure_start.json` replay now continues from
that title through Adventure Mode, creates mission file A, skips the opening
briefing, lands at Celestial Archives, and reaches the live first-person HUD.
The minimized replay reaches gameplay at VBlank 10859 without relying on
host-time input sleeps. All 15 native checkpoints in the route are
byte-identical to ndsref across both physical screens.

Native and ndsref scheduler/event counts agree through the loop. Captures of
both physical screens at title and post-title checkpoints are byte-identical
after correcting two shared reset/presentation assumptions: the runner now
starts from the retail `POWCNT1 = 0x820F` state, and screen routing is applied
as scanlines are produced rather than retroactively when a completed frame is
read.

The paired `../ndsrecomp-mph` worktree also removes two SM64DS-specific
cross-title assumptions. Static title banks are now registered only for the
exact ROM they were generated from—important because both games use the
standard ARM7 load address—and cartridge backup type/capacity are game-owned
configuration. AMHE declares its 256 KiB flash instead of inheriting SM64DS's
8 KiB EEPROM.

This proves campaign entry, not gameplay completeness. Runtime ARM7 code,
ARM9 overlay generations, sustained traversal/combat scenarios, and packaging
remain explicit next gates in
[`docs/BRINGUP.md`](docs/BRINGUP.md).

The exact-ROM `game.toml` now opts the upper screen into the shared 448x192
(21:9) adaptive renderer. The lower touchscreen stays native 256x192. This is
an enhancement bring-up baseline: projection, game-side culling, HUD anchoring,
movies, fades, and screen routing still need sustained gameplay auditing.

An MPH-specific recomp-ui development launcher lives in
`launcher/recomp-ui`. Its Adaptive Widescreen mod is enabled by default and
maps to the same runner CLI used by the SM64DS preview.

## Project shape

The structure follows the sibling SM64DS project while adopting patterns from
the more mature SNESRecomp and PSXRecomp game repositories:

- `game.toml` owns exact game identity and host-facing defaults.
- `tools/prepare_mph.py` verifies the ROM, extracts/decompresses both main CPU
  images, extracts all 18 ARM9 overlays, and emits ignored ndsrecomp configs.
- `generated/` contains every ROM-derived input and output and stays ignored.
- `ndsrecomp.pin` records the framework base; development currently uses the
  isolated sibling worktree at `../ndsrecomp-mph`.
- `mphread.pin` records the reverse-engineering reference used for AMHE0
  metadata. MphRead is a recreation/file-format project, not a matching
  disassembly.

## Setup and build

Create the local Python environment:

```powershell
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Place the verified ROM at `Metroid Prime Hunters.nds`, then configure and
build from a MinGW64 shell:

```bash
cmake -G Ninja -S . -B build \
  -DNDSRECOMP_ROOT=../ndsrecomp-mph
cmake --build build --target metroidprimehuntersrecomp
```

The build verifies the ROM, expands the compressed ARM9, extracts overlay
metadata/images, generates the initial ARM9 and ARM7 static closures, compiles
the generated banks, and builds the ROM identity checker.

Build the runner with these generated banks and launch the authentic
firmware/card path:

```bash
cmake -G Ninja -S ../ndsrecomp-mph/runner \
  -B ../ndsrecomp-mph/runner/build-mph-title \
  -DNDS_BOOTSTRAP_FIRMWARE=ON \
  -DNDS_TITLE_BANK_DIR="$PWD/generated/recomp" \
  -DNDS_TITLE_ROM_SHA1=90164d1ac127ee5f9815ea4ae7de798c7b5fc629
cmake --build ../ndsrecomp-mph/runner/build-mph-title

../ndsrecomp-mph/runner/build-mph-title/nds_runner \
  ../ndsrecomp/bios --interactive \
  --rom "Metroid Prime Hunters.nds" --config game.toml
```

For deterministic headless checkpoints:

```bash
./.venv/Scripts/python.exe tools/capture_mph_checkpoints.py \
  --runner ../ndsrecomp-mph/runner/build-mph-title/nds_runner.exe \
  --bios ../ndsrecomp/bios --rom "Metroid Prime Hunters.nds" \
  --config game.toml --out generated/captures/checkpoints \
  --targets 300 900 2400 3600 6000 7200 7800 8400 9000 12000
```

The same tool accepts `--oracle <ndsref.exe>` in place of `--runner`; it
creates an ignored private firmware copy with Automatic Slot-1 startup so the
two backends traverse the same path. Long targets transparently continue
across the debug server's per-command safety-round limit and refuse to save a
mislabeled checkpoint if the machine stalls. Compare matching images with
`tools/compare_mph_checkpoints.py`.

## Gameplay input discovery and replay

`tools/fuzz_mph_gameplay.py` performs seeded touch/button exploration after
the title screen. Every action is followed by an absolute-VBlank checkpoint,
physical-screen capture, perceptual signature, and machine-readable
`trace.json`, so a lucky path can be minimized and replayed.

Run the minimized Adventure trace against the native runner:

```bash
./.venv/Scripts/python.exe tools/fuzz_mph_gameplay.py \
  --runner ../ndsrecomp-mph/runner/build-mph-title/nds_runner.exe \
  --bios ../ndsrecomp/bios --rom "Metroid Prime Hunters.nds" \
  --config game.toml --out generated/fuzz/native-adventure \
  --actions scenarios/adventure_start.json --steps 0
```

Replace `--runner` with `--oracle ../ndsref/build-native/ndsref.exe` to
produce the independent reference trace. Add `--steps 100 --seed <number>`
to continue deterministic exploration after the scripted prefix.
Compare the complete action routes with:

```bash
./.venv/Scripts/python.exe tools/compare_mph_checkpoints.py \
  --native generated/fuzz/native-adventure \
  --oracle generated/fuzz/oracle-adventure --pattern "0*.png"
```

To inspect the verified cartridge without launching it:

```powershell
./build/MetroidPrimeHuntersRecomp --rom "Metroid Prime Hunters.nds"
```

## Reverse-engineering reference

[`NoneGiven/MphRead`](https://github.com/NoneGiven/MphRead) is pinned at
`26cd8a6fe93dc5e525d1a1bb304fe96001111e55`. It explicitly supports AMHE0 and
documents or recreates substantial game behavior and data formats. No public
matching Prime Hunters disassembly was found during initial research.

The original code in this repository is MIT licensed. The game, ROM, and
derived data remain the property of their respective copyright holders and
are not distributed.
