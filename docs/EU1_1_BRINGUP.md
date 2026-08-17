# Metroid Prime Hunters Multi-ROM / EU1.1 Bring-up

This document describes the current multi-ROM architecture in this branch.
It supersedes the earlier SHA-1-driven runtime-profile design.

## 1. Status

Runtime address layouts are statically prepared for all seven retail MPH base
revisions:

| Runtime base | Game code | Revision | Morph / Alt Form | Aim X | Aim Y |
|---|---|---:|---:|---:|---:|
| `US1_0` | `AMHE` | 0 | `0x020DA818` | `0x020DE526` | `0x020DE52E` |
| `US1_1` | `AMHE` | 1 | `0x020DB098` | `0x020DEDA6` | `0x020DEDAE` |
| `EU1_0` | `AMHP` | 0 | `0x020DB0B8` | `0x020DEDC6` | `0x020DEDCE` |
| `EU1_1` | `AMHP` | 1 | `0x020DB138` | `0x020DEE46` | `0x020DEE4E` |
| `JP1_0` | `AMHJ` | 0 | `0x020DC6D8` | `0x020E03E6` | `0x020E03EE` |
| `JP1_1` | `AMHJ` | 1 | `0x020DC698` | `0x020E03A6` | `0x020E03AE` |
| `KR1_0` | `AMHK` | 0 | `0x020D3EE4` | `0x020D7C0E` | `0x020D7C16` |

Exact build/capture content profiles currently exist for:

- `US1_0` clean retail ROM
- `EU1_1` clean retail ROM

The other retail revisions and individual modified ROMs still require their own
exact-content build/capture profile, coverage and generated artifacts before
they can be called fully supported.

## 2. Sources of truth

Runtime detection and addresses intentionally follow melonPrimeDS
`develop_hud`:

- detector: `src/frontend/qt_sdl/MelonPrimeGameRomDetect.cpp`
- address table: `src/frontend/qt_sdl/MelonPrimeGameRomAddrTable.h`
- executable checksum algorithm: `src/NDSCart/CartCommon.cpp`, `CartCommon::Checksum()`
- CRC32 implementation: `src/CRC32.cpp`

Repository:

`https://github.com/ag-advania/melonPrimeDS/tree/develop_hud`

The project registry records these source locations in
`config/mph_rom_profiles.json`.

## 3. Identity model

The old design coupled runtime RAM addresses to an exact whole-ROM SHA-1.
That is intentionally no longer the design.

There are three separate identities.

### 3.1 Runtime Base Profile

A runtime base profile is one of the seven region/revision layouts above. It
owns revision-specific host RAM addresses such as Aim X/Y and Morph / Alt Form.

The runtime detector uses:

1. melonPrimeDS-compatible executable checksum, then
2. exact NDS header `gameCode + revision` fallback.

NDS header offsets:

- game code: `0x0C..0x0F`
- ROM revision/version: `0x1E`

The Recomp detector is deliberately stricter than melonPrimeDS's generic
`revision != 0 -> 1.1` fallback. Only the seven explicitly supported tuples are
accepted. A hypothetical rev2+ is unknown.

### 3.2 Executable Compatibility Identity

melonPrimeDS `CartCommon::Checksum()` is reproduced exactly:

1. CRC32 over ROM header bytes `0x00..0x3F`
2. continue CRC32 over the ARM9 ROM image
3. continue CRC32 over the ARM7 ROM image

A hit in the audited melonPrimeDS checksum table is authoritative for the base
runtime layout and may enable host-side Aim/Morph RAM access.

A header-only match is weaker. It identifies a candidate base profile, but it
**does not authorize host RAM reads/writes**. Unknown executable content remains
fail-closed.

This prevents a modified ROM that merely preserves `AMHE` revision 0 from being
blindly treated as memory-compatible US1.0.

### 3.3 Actual Content Identity

Whole-ROM SHA-1 identifies the exact content used to generate or validate:

- build inputs
- recomp banks
- static coverage
- runtime coverage
- checkpoints
- FMV/runtime captures

This identity is not the runtime-address selector.

Generated title banks remain registered against the actual ROM SHA-1. A bank
captured/generated for clean ROM or MOD A is therefore not silently reused for
MOD B.

## 4. Known melonPrimeDS executable checksums

The current registry mirrors the audited `develop_hud` detector table,
including:

- all seven clean retail revisions
- encrypted variants
- EU1.1 Balanced variants
- EU1.1 Russian variant (`0x9E20F3A8`)

A known checksum establishes the runtime RAM layout. It does **not** by itself
mean the clean recomp build is byte-compatible with that modified executable.

For example, the known EU1.1 Russian executable can use the EU1.1 Aim/Morph RAM
layout, but because its executable checksum differs from canonical clean EU1.1,
it still requires a mod-specific exact build/capture content profile.

`Last Raven` is not present in the current audited `develop_hud` checksum table.
It therefore remains fail-closed for host Aim/Morph access until its executable
checksum/layout is explicitly validated.

## 5. Clean ROM versus modified ROM startup

The recomp-ui launcher intentionally does not enforce the clean whole-ROM SHA.
The launcher passes the selected `.nds` file to the runner, where the stronger
multi-layer detector can decide safely.

The runner rules are:

- exact expected whole-ROM SHA: normal exact-content build
- different whole-ROM SHA + canonical clean header/ARM9/ARM7 checksum of the
  expected base: clean build may be reused for a data-only variant
- code-modified executable checksum: exact clean SHA gate is not bypassed;
  prepare a mod-specific build/capture profile
- unknown checksum + supported header: candidate base may be identified, but
  host Aim/Morph RAM access and clean-build SHA bypass stay disabled
- unknown game code/revision or malformed ARM image ranges: reject/fail closed

The launcher SHA check is disabled specifically so it cannot reject a mod before
these runner rules execute.

## 6. Content profiles and `base_profile`

`config/mph_rom_profiles.json` schema 5 separates content identity from runtime
base identity.

Canonical clean profiles reserve the seven base keys. Example:

```json
"US1_0": {
  "base_profile": "US1_0",
  "known_clean": true,
  "game_code": "AMHE",
  "revision": 0,
  "sha1": "...exact clean whole-ROM SHA-1..."
}
```

A future exact mod profile must use a distinct key and reference the compatible
base layout:

```json
"US1_0_LAST_RAVEN": {
  "base_profile": "US1_0",
  "known_clean": false,
  "game_code": "AMHE",
  "revision": 0,
  "sha1": "...exact Last Raven whole-ROM SHA-1...",
  "program_id": "mph_amhe0_last_raven",
  "coverage": "coverage/last-raven-entry-points.json",
  "game_config": "config/game-last-raven.toml",
  "fmv_runtime": false,
  "fmv_runtime_bank": "mph_amhe0_last_raven_arm9_fmv_runtime",
  "launcher_default_rom": "Metroid Prime Hunters - Last Raven.nds",
  "adaptive_widescreen": false
}
```

The example is architectural only. Do not add a Last Raven profile until its
actual SHA-1, executable checksum, game config and generated/captured artifacts
are known and validated.

The static checker enforces that a mod cannot overwrite a canonical clean key.

## 7. EU1.1 current exact-content identity

Current clean EU1.1 profile:

- profile: `EU1_1`
- base profile: `EU1_1`
- game code: `AMHP`
- revision: `1`
- whole-ROM SHA-1: `bdcd1dea293e24c98d4c481430e90d21198985a5`
- default launcher ROM: `Metroid Prime Hunters (Europe Rev 1).nds`
- Adaptive Widescreen: disabled until validated
- FMV runtime bank: disabled until an EU1.1-specific capture is validated

Reserved EU1.1 runtime bank identity:

- config: `config/mph_amhp1_arm9_fmv_runtime.toml`
- capture: `generated/EU1_1/capture/mph_amhp1_arm9_fmv_runtime.bin`
- bank: `mph_amhp1_arm9_fmv_runtime`

No US1.0 FMV runtime capture is reused for EU1.1.

## 8. Preparing a clean content profile

The preparation path intentionally remains exact-content gated. This is not the
runtime selector; it protects generated code provenance.

Example EU1.1 preparation:

```bash
python tools/prepare_mph.py \
  --version EU1_1 \
  --rom "/path/to/Metroid Prime Hunters (Europe Rev 1).nds" \
  --coverage coverage/eu11-bootstrap-entry-points.json \
  --out generated/EU1_1/inputs
```

`prepare_mph.py` checks:

- exact whole-ROM SHA-1
- expected ROM size
- game code at `0x0C`
- revision at `0x1E`
- coverage `game_sha1`

It then extracts ARM9, ARM7 and overlays and emits revision/content-specific
seed configs.

## 9. Building EU1.1

Typical CMake configuration:

```bash
cmake -S . -B build-eu11 \
  -DMPH_VERSION=EU1_1 \
  -DMPH_ROM="/path/to/Metroid Prime Hunters (Europe Rev 1).nds"
cmake --build build-eu11
```

Windows and Linux build helpers consume the same registry-owned profile data.
Profile choices are derived from `profiles`, not a hard-coded two-profile list.

## 10. Coverage and capture safety

Static and runtime promotion is profile/content aware.

For non-US content, traces carry both:

- content profile key
- exact whole-ROM SHA-1

Main-image geometry is derived from the selected prepared ARM9/ARM7 configs,
not reused from US1.0 constants.

FMV/runtime capture promotion verifies exact content provenance. A capture from
one content SHA must not be promoted into another content profile.

## 11. Runtime safety tests

CI patches the exact pinned ndsrecomp revision and compiles the patched runner
translation units.

The runtime harness uses synthetic, non-copyrighted ROM images constructed to
produce the canonical melonPrimeDS executable checksums. It verifies:

- all seven runtime profiles dispatch the correct Aim/Morph addresses
- checksum-authoritative profiles allow host Aim/Morph access
- header-only fallback does not allow host RAM access
- unsupported revisions fail closed
- malformed ARM image ranges fail closed
- known-clean SHA/header contradictions fail closed
- canonical executable-equivalent data variants may pass the clean SHA gate
- known code-modified EU1.1 Russian checksum gets EU1.1 RAM layout but cannot
  reuse the clean EU1.1 build identity
- runtime patching is idempotent
- patched runner source files compile

## 12. Remaining work for full multi-ROM support

The detector/address architecture is now prepared for all seven base revisions,
but full player-facing support still requires exact content work per ROM:

1. add verified clean content profiles for US1.1, EU1.0, JP1.0, JP1.1 and KR1.0
2. prepare/extract each exact ROM
3. capture deterministic coverage and promote it under that exact SHA
4. generate revision-specific ARM9/ARM7/overlay banks
5. validate boot, Adventure, pause, save/load and multiplayer-menu paths
6. validate Prime Controls / Direct Mouse Aim semantics on real execution
7. compare checkpoints against the reference/native execution path
8. capture revision-specific FMV runtime code only where interpreter fallback needs optimization
9. regression-test US1.0 after each new profile

For a modified ROM, additionally:

1. compute the exact whole-ROM SHA-1
2. compute the melonPrimeDS-compatible header+ARM9+ARM7 CRC32
3. determine/validate its runtime base layout
4. if code-modified, register the executable checksum only after address compatibility is established
5. add a distinct content profile with `base_profile`
6. generate/promote coverage and banks under that mod's exact content identity

Do not guess an unknown mod as US1.0 simply because its filename, region or
header resembles US1.0.