# MetroidPrimeHuntersRecomp

> MetroidPrimeHuntersRecomp is a byproduct of developing
> [ndsrecomp](https://github.com/mstan/ndsrecomp): the games are the proving
> ground, and the framework is the long-term goal. This is an in-development
> preview, not a finished port. Expect rough edges, crashes, hangs,
> visual/audio issues, networking problems, desyncs, and game-specific bugs. My
> time for any one title is limited, so I ask for patience. Testing, issues,
> and PRs to the game or framework are welcome and will help accelerate polish.

Early Metroid Prime Hunters static-recompilation target for
[ndsrecomp](https://github.com/mstan/ndsrecomp). The project is pinned to the
USA revision-0 game and is part of the first wave of Nintendo DS recompilation
bring-up.

## Release status

Version 0.1.0 is an early alpha and the first release in the ndsrecomp
ecosystem. Instability and bugs are expected. This release is for testers and
developers who are comfortable with incomplete gameplay validation, early input
support, rudimentary controller support, and experimental networking.

The Windows ZIP targets the exact USA revision-0 ROM identified below. It
contains a portable launcher, the title runner with the content-validated FMV
bank compiled in, launcher assets, configuration, and required runtime
libraries. No Nintendo ROM, BIOS, firmware, save data, raw capture, or
generated source is distributed.

## Quick start

1. Download and fully extract
   `MetroidPrimeHuntersRecomp-windows-x64-v0.1.0.zip` from Releases.
2. Copy your own `biosnds9.rom`, `biosnds7.rom`, and `firmware.bin` dumps into
   the extracted `bios` folder. `bios/README.txt` lists the required hashes.
3. Run `MetroidPrimeHuntersRecomp.exe` and select your legally obtained
   Metroid Prime Hunters (USA revision 0) ROM when prompted.

The launcher remembers the ROM selection. The runner independently verifies
the ROM, both BIOS images, and firmware before executing any title bank.

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

That replay also drives reproducible static-coverage promotion. The native
debug endpoint records Tier-3 call and indirect targets when the fuzz helper's
`--capture-static-coverage` mode enables `--discover-static-misses`;
`tools/promote_mph_static_coverage.py`
keeps only immutable main-image PCs and excludes slice resumes, overlays, and
runtime RAM. The committed route contributes 567 ARM9 seeds, expanding the
generated main bank from 4,335 to 7,115 functions. Replaying the same route
reduced ARM9 Tier-3 entries by 10.98% and interpreted instructions by 5.91%,
with all 13 action checkpoints retaining identical event counts and RGB
hashes. This is a coverage improvement, not yet a wall-clock performance
claim; generated banks still compile with the bring-up `-O0` policy.

The opening FMVs have a separate, measured runtime bank. A static-only
interactive run falls from 59.8 FPS to 26-28 FPS after VBlank 2400 because
the video decoder executes roughly 620,000 ARM9 Tier-3 instructions per
frame from ITCM and the active overlay. The content-validated
`mph_arm9_fmv_runtime` bank compiles the call/indirect closure observed only
between VBlanks 2400 and 3000. On canonical `ndsrecomp` main, a complete
VBlank 2400-4800 run sustains 59.73-59.84 FPS at 8.37-9.31 ms emulation per
frame with zero audio underruns. The optimized and static-only runners retain
identical CPU/event counts and zero differing pixels on both screens at
VBlanks 2400, 3000, 3600, 4200, and 4800.

The runtime capture is ROM-derived and remains under ignored `generated/`.
Release builds compile its content-validated generated bank into
`nds_runner.exe`, matching the ROM-free executable model used by the sibling
SNES recompilation releases; neither the raw capture nor generated C is placed
in the release ZIP.
To reproduce it, first build a static-only title runner, then capture the
pre-FMV and FMV endpoints and regenerate the committed config:

```powershell
./.venv/Scripts/python.exe tools/benchmark_mph_fmv.py `
  --runner ../ndsrecomp/runner/build-mph-main-integration/nds_runner.exe `
  --bios ../ndsrecomp/bios --rom "Metroid Prime Hunters.nds" `
  --config game.toml --out generated/perf/fmv-pre --targets 2400 `
  --discover-static-misses
./.venv/Scripts/python.exe tools/benchmark_mph_fmv.py `
  --runner ../ndsrecomp/runner/build-mph-main-integration/nds_runner.exe `
  --bios ../ndsrecomp/bios --rom "Metroid Prime Hunters.nds" `
  --config game.toml --out generated/perf/fmv-capture `
  --targets 2400 3000 --discover-static-misses `
  --capture-runtime generated/capture/mph_arm9_fmv_runtime.bin
./.venv/Scripts/python.exe tools/promote_mph_runtime_coverage.py `
  --benchmark generated/perf/fmv-capture/benchmark.json `
  --before-benchmark generated/perf/fmv-pre/benchmark.json `
  --image generated/capture/mph_arm9_fmv_runtime.bin `
  --out config/mph_arm9_fmv_runtime.toml
```

Reconfigure the game build after the capture exists, generate the banks, and
then reconfigure/rebuild the title runner. The capture must hash to
`2f4a2ba36886fb9152781f5829dedfd4b836a73b`; dispatch still compares every
compiled function with the guest's live bytes, so later overlay generations
fall through safely.

Native and ndsref scheduler/event counts agree through the loop. Captures of
both physical screens at title and post-title checkpoints are byte-identical
after correcting two shared reset/presentation assumptions: the runner now
starts from the retail `POWCNT1 = 0x820F` state, and screen routing is applied
as scanlines are produced rather than retroactively when a completed frame is
read.

The canonical `../ndsrecomp` framework also removes two cross-title
assumptions. Static title banks are now registered only for the exact ROM they
were generated from, and cartridge backup type/capacity are game-owned
configuration. AMHE declares its 256 KiB flash explicitly.

This proves campaign entry, not gameplay completeness. Runtime ARM7 code,
the remaining ARM9 overlay generations, sustained traversal/combat scenarios,
and future release polish remain explicit next gates in
[`docs/BRINGUP.md`](docs/BRINGUP.md).

The exact-ROM `game.toml` now opts the upper screen into the shared 448x192
(21:9) adaptive renderer. The lower touchscreen stays native 256x192. This is
an enhancement bring-up baseline: projection, game-side culling, HUD anchoring,
movies, fades, and screen routing still need sustained gameplay auditing.

An MPH-specific recomp-ui development launcher lives in
`launcher/recomp-ui`. Its Adaptive Widescreen and Prime Controls mods are
enabled by default and map to the shared ndsrecomp runner CLI.
Prime Controls owns both mouse aim and the melonPrimeDS keyboard/mouse layout:
click the top window to capture the cursor, move the mouse for unbounded
relative aim, and use the configured bindings for movement, weapons, and
touchscreen helpers. `Escape`, changing focus, or closing a window safely
releases the cursor and any held fire input; the bottom window remains an
ordinary clickable touchscreen. Aim sensitivity defaults to `0.30x`, virtual
stylus sensitivity defaults to `0.20x`, and both are editable from the MODS
page along with inverted-Y and every Prime Controls binding. Settings persist
in `%APPDATA%\MetroidPrimeHuntersRecomp\mods.ini`. Binding defaults are `WASD`
move, `Space` jump, `Left Ctrl` morph ball, `Left Shift` boost/map zoom, `C`
scan visor, `F` OK, `Q/E` scan-message arrows, `V` menu, Mouse 1/2
fire/scan-fire, Mouse 4 missiles, Mouse 5 beam, number keys `1` through `6`
for subweapons, and `Tab` for the virtual stylus.

Rudimentary gamepad support is implemented as a controller alternative: the
left stick moves (it maps to the D-pad everywhere, including menus), the right
stick aims the camera, and every Prime Controls action has its own gamepad
binding, shown and remappable in the launcher's MODS page under **Gamepad**
alongside the keyboard rows. Defaults: `RT` shoot, `LT` scan-fire, `A` jump,
`B` morph ball, `X` missile, `Y` UI OK, `LB` beam, `RB` boost/zoom, `R3` scan
visor, D-pad left/right scan-message arrows, `Start` menu; subweapons 1-6
start unbound. Aiming engages as soon as the right stick, a trigger, or a bound
pad button is used and idles back out when released, so the touchscreen and
menus keep working while the sticks rest. Pad aim sensitivity sits on the same
page (also `--mph-pad-aim-sensitivity 10..400` /
`controls.prime.pad_aim_sensitivity`, default `100`); per-action flags are
`--mph-pad-bind-<action>` / `controls.prime.pad_bindings.<action>`.

melonPrimeDS itself ships no gamepad bindings for its Metroid controls
(keyboard and mouse only), so this controller layout is this project's own
dual-stick adaptation of its scheme.

Credit where it is due:
[makinori/melonPrimeDS](https://github.com/makinori/melonPrimeDS) is the
reference this Prime Controls reimplementation follows - its keyboard/mouse
layout, touchscreen-helper mappings, and sensitivity defaults were worked
out there first, and this project reimplements that scheme on the
recompiled runner's native input path.

## Networking and Wiimmfi

Nintendo WFC / Wiimmfi support is experimental. Current validation shows
Metroid Prime Hunters can authenticate through Wiimmfi and reach a Friends and
Rivals lobby where one locally driven instance can see another hosted game.
In-game online play is ultimately untested. There is no guarantee that a match
will connect, remain connected, or avoid desync.

The Wi-Fi implementation is built on
[melonDS](https://github.com/melonDS-emu/melonDS)'s Wi-Fi work in the shared
ndsrecomp runner: its DS Wi-Fi controller model, emulated access point, and
network backend are the foundation for Wiimmfi connectivity. Full credit to the
melonDS team. See the ndsrecomp
[`THIRD_PARTY_ATTRIBUTION.md`](https://github.com/mstan/ndsrecomp/blob/main/THIRD_PARTY_ATTRIBUTION.md)
for provenance and licensing details.

## Project shape

The structure follows the sibling recomp game repositories while adopting
patterns from the more mature SNESRecomp and PSXRecomp projects:

- `game.toml` owns exact game identity and host-facing defaults.
- `tools/prepare_mph.py` verifies the ROM, extracts/decompresses both main CPU
  images, extracts all 18 ARM9 overlays, and emits ignored ndsrecomp configs
  seeded by `coverage/adventure-main-entry-points.json`.
- `generated/` contains every ROM-derived input and output and stays ignored.
- `ndsrecomp.pin` records the exact framework commit on canonical `main`.
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
  -DNDSRECOMP_ROOT=../ndsrecomp
cmake --build build --target metroidprimehuntersrecomp
```

The build verifies the ROM, expands the compressed ARM9, extracts overlay
metadata/images, generates the initial ARM9 and ARM7 static closures, compiles
the generated banks, and builds the ROM identity checker.

## Release packaging

The supported Windows packaging path builds the ROM-free runner and launcher,
then stages the portable ZIP:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  tools\build-windows.ps1 -Version 0.1.0
```

On Linux, build the runner-first AppImage from source:

```bash
bash tools/build-linux.sh --version 0.1.0
```

The packagers refuse a runner that does not contain the FMV runtime bank,
stage only explicit safe payloads, and reject unsafe names or
ROM/save/BIOS/firmware/generated material. The AppImage starts `nds_runner`
directly because the current title launcher is Windows-only; place the `.nds`
ROM and a `bios/` folder containing your verified DS dumps beside the
AppImage.

Build the runner with these generated banks and launch the authentic
firmware/card path:

```bash
cmake -G Ninja -S ../ndsrecomp/runner \
  -B ../ndsrecomp/runner/build-mph-title \
  -DNDS_BOOTSTRAP_FIRMWARE=ON \
  -DNDS_TITLE_BANK_DIR="$PWD/generated/recomp" \
  -DNDS_TITLE_ROM_SHA1=90164d1ac127ee5f9815ea4ae7de798c7b5fc629
cmake --build ../ndsrecomp/runner/build-mph-title

../ndsrecomp/runner/build-mph-title/nds_runner \
  ../ndsrecomp/bios --interactive \
  --rom "Metroid Prime Hunters.nds" --config game.toml
```

For deterministic headless checkpoints:

```bash
./.venv/Scripts/python.exe tools/capture_mph_checkpoints.py \
  --runner ../ndsrecomp/runner/build-mph-title/nds_runner.exe \
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
  --runner ../ndsrecomp/runner/build-mph-title/nds_runner.exe \
  --bios ../ndsrecomp/bios --rom "Metroid Prime Hunters.nds" \
  --config game.toml --out generated/fuzz/native-adventure \
  --actions scenarios/adventure_start.json --steps 0
```

Replace `--runner` with `--oracle ../ndsref/build-native/ndsref.exe` to
produce the independent reference trace. Add `--steps 100 --seed <number>`
to continue deterministic exploration after the scripted prefix. For a
native coverage run, add `--capture-static-coverage`, then pass its ignored
`trace.json` to `tools/promote_mph_static_coverage.py`; review and commit the
filtered metadata, never the ROM-derived generated banks.
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
