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

The clean interpreter baseline boots through the authentic firmware/cartridge
path, starts both game CPUs, displays the ActImagine splash, and advances into
the opening cinematic without a terminal dispatch miss. ROM-gated static
ARM9/ARM7 banks now reach VBlank 3600, well into the hunter-introduction
sequence, with both CPUs alive.

The first cross-title framework defect is already isolated and fixed in the
paired `../ndsrecomp-mph` worktree: an SM64DS ARM7 bank was registered for
every cartridge. Prime Hunters shares the standard ARM7 load address, so the
wrong title's code ran against Prime Hunters memory and corrupted execution.
Title banks are now gated by exact ROM identity.

The second cross-title assumption was the save device: the runner instantiated
SM64DS's 8 KiB EEPROM for every cartridge. AMHE is a 256 KiB flash title, so
save type/capacity now come from `game.toml` and the shared runtime implements
the corresponding flash command path.

Full attract-mode completion is not yet claimed. The next gates are recorded
in [`docs/BRINGUP.md`](docs/BRINGUP.md).

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
  --targets 300 900 2400 3600
```

The same tool accepts `--oracle <ndsref.exe>` in place of `--runner`; it
creates an ignored private firmware copy with Automatic Slot-1 startup so the
two backends traverse the same path. Compare matching images with
`tools/compare_mph_checkpoints.py`.

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
