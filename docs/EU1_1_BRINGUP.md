# Metroid Prime Hunters Multi-ROM / EU1.1 Bring-up

This document describes the current multi-ROM architecture in this branch.
It supersedes the earlier whole-ROM-SHA-1-driven runtime-profile design and
includes the upstream Wi-Fi firmware-state persistence work integrated from
`mstan/MetroidPrimeHuntersRecomp` commit
`5abcfee6187d572e752985ede2364f165d62dd6a`.

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

Adaptive Widescreen is also statically address-mapped for all seven base
revisions. It is no longer hidden for EU1.1. Actual guest code/data writes are
still fail-closed and require an authoritative executable checksum.

Exact build/capture content profiles currently exist for:

- `US1_0` clean retail ROM
- `EU1_1` clean retail ROM

The other retail revisions and individual modified ROMs still require their own
exact-content build/capture profile, coverage and generated artifacts before
they can be called fully supported.

## 2. Sources of truth

Runtime detection and Aim/Morph addresses intentionally follow melonPrimeDS
`develop_hud`:

- detector: `src/frontend/qt_sdl/MelonPrimeGameRomDetect.cpp`
- address table: `src/frontend/qt_sdl/MelonPrimeGameRomAddrTable.h`
- executable checksum algorithm: `src/NDSCart/CartCommon.cpp`, `CartCommon::Checksum()`
- CRC32 implementation: `src/CRC32.cpp`

Adaptive Widescreen additionally uses:

- melonPrimeDS `main/src/frontend/qt_sdl/MelonPrimePatchAspectRatio.cpp`
- melonPrimeDS `main/src/frontend/qt_sdl/MelonPrimeGameRomAddrTable.h`
- mphCodex `mnt/data/analysis/mphAnalysis/_Commons/Widescreen.md`

The registry records these source locations in
`config/mph_rom_profiles.json`.

## 3. Identity model

The old design coupled runtime RAM addresses to an exact whole-ROM SHA-1. That
is intentionally no longer the design.

There are three separate identities.

### 3.1 Runtime Base Profile

A runtime base profile is one of the seven region/revision layouts above. It
owns revision-specific host addresses for Aim, Morph and Adaptive Widescreen.

The runtime detector uses:

1. melonPrimeDS-compatible executable checksum, then
2. exact NDS header `gameCode + revision` fallback.

NDS header offsets:

- game code: `0x0C..0x0F`
- ROM revision/version: `0x1E`

The Recomp fallback is deliberately stricter than melonPrimeDS's generic
`revision != 0 -> 1.1` fallback. Only the seven explicitly supported tuples are
accepted. A hypothetical rev2+ is unknown.

### 3.2 Executable Compatibility Identity

melonPrimeDS `CartCommon::Checksum()` is reproduced exactly:

1. CRC32 over ROM header bytes `0x00..0x3F`
2. continue CRC32 over the ARM9 ROM image
3. continue CRC32 over the ARM7 ROM image

A hit in the audited melonPrimeDS checksum table is authoritative for the base
runtime layout and may enable host-side Aim/Morph/Adaptive-Widescreen RAM/code
access.

A header-only match is weaker. It identifies a candidate base profile, but it
**does not authorize host RAM/code reads or writes**. Unknown executable content
remains fail-closed.

This prevents a modified ROM that merely preserves `AMHE` revision 0 from being
blindly treated as executable-compatible US1.0.

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

## 4. Current authoritative executable checksum table

The registry mirrors the current `develop_hud` detector table. CI downloads the
detector on every run and fails if the local registry drifts.

Current entries include:

- all seven clean retail revisions
- encrypted variants for all seven revisions
- EU1.1 Balanced
- EU1.1 Balanced v1.2.11
- EU1.1 Russian

The current EU1.1 Russian executable checksum is `0x9E20F3A8`.

A known checksum establishes the runtime layout. It does **not** by itself mean
the clean recomp build is byte-compatible with that modified executable.

For example, a known code-modified EU1.1 executable may use EU1.1 runtime host
addresses, while still requiring a separate exact content profile, coverage and
generated banks.

`Last Raven` is not present in the currently audited `develop_hud` checksum
table. It therefore remains fail-closed for Aim/Morph/Widescreen host writes
until its executable checksum and layout compatibility are explicitly
validated.

## 5. Adaptive Widescreen across all seven revisions

The previous EU1.1 bring-up temporarily disabled Adaptive Widescreen because the
US1.0 game-side projection/culling addresses were not known for other revisions.
That limitation is removed.

melonPrimeDS and mphCodex identify three revision-specific locations:

| Runtime base | Projection patch 1 | Projection patch 2 | Q12 culling aspect |
|---|---:|---:|---:|
| `US1_0` | `0x02110FFC` | `0x0211C638` | `0x02110820` |
| `US1_1` | `0x02111ABC` | `0x0211D168` | `0x021112E0` |
| `EU1_0` | `0x02111ADC` | `0x0211D114` | `0x02111300` |
| `EU1_1` | `0x02111B5C` | `0x0211D208` | `0x02111380` |
| `JP1_0` | `0x0211313C` | `0x0211E7E8` | `0x02112960` |
| `JP1_1` | `0x021130FC` | `0x0211E7A8` | `0x02112920` |
| `KR1_0` | `0x02109B64` | `0x02114838` | `0x021091A4` |

For 21:9 the runner mirrors melonPrimeDS's guarded patch semantics:

- projection 1 preimage: `0xE5991664`
- projection 2 preimage: `0xE59A1664`
- culling-aspect preimage: `0x1555`
- 21:9 projection instruction: `0xE3A0106D`
- 21:9 Q12 aspect: `0x2555`

All three preimages are verified before the first write. If any guard does not
match, no partial aspect-ratio patch is applied.

The UI may expose Adaptive Widescreen for a supported content profile, but the
runner is authoritative:

- known executable checksum + compatible base profile: enable profile-specific
  projection/culling patch and adaptive top-screen rendering
- header-only fallback: keep runtime base identification, but force the actual
  adaptive top-screen patch path off because executable compatibility has not
  been established
- unknown/non-MPH identity: normal fail-closed behavior

The patch checks the guarded guest words again on later frames, so an in-process
guest reset that restores the stock instructions can be patched again safely.

## 6. Clean ROM versus modified ROM startup

The recomp-ui launcher intentionally does not enforce the clean whole-ROM SHA.
The launcher passes the selected `.nds` file to the runner, where the stronger
multi-layer detector decides safely.

The runner rules are:

- exact expected whole-ROM SHA: normal exact-content build
- different whole-ROM SHA + canonical clean header/ARM9/ARM7 checksum of the
  expected base: clean build may be reused for a data-only variant
- known code-modified executable checksum: runtime layout may be trusted, but
  the clean exact-content build is not automatically reused
- unknown checksum + supported header: candidate base may be identified, but
  Aim/Morph/Widescreen host access and clean-build SHA bypass stay disabled
- unknown game code/revision or malformed ARM image ranges: reject/fail closed

The launcher SHA check is disabled specifically so it cannot reject a mod before
these runner rules execute.

## 7. Content profiles and `base_profile`

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
  "adaptive_widescreen": true
}
```

The example is architectural only. Setting `adaptive_widescreen` true exposes
the feature in the content profile; it does **not** bypass the executable
compatibility gate. Until Last Raven has an explicitly registered compatible
checksum, its host projection/Aim/Morph writes remain disabled.

## 8. EU1.1 exact-content identity

Current clean EU1.1 profile:

- profile: `EU1_1`
- base profile: `EU1_1`
- game code: `AMHP`
- revision: `1`
- whole-ROM SHA-1: `bdcd1dea293e24c98d4c481430e90d21198985a5`
- default launcher ROM: `Metroid Prime Hunters (Europe Rev 1).nds`
- Adaptive Widescreen: exposed and revision-aware
- FMV runtime bank: disabled until an EU1.1-specific capture is validated

Reserved EU1.1 runtime bank identity:

- config: `config/mph_amhp1_arm9_fmv_runtime.toml`
- capture: `generated/EU1_1/capture/mph_amhp1_arm9_fmv_runtime.bin`
- bank: `mph_amhp1_arm9_fmv_runtime`

No US1.0 FMV runtime capture is reused for EU1.1.

## 9. Upstream Wi-Fi firmware-state persistence

The branch integrates the upstream `5abcfee` Wi-Fi persistence behavior while
preserving the multi-ROM launcher generation and SHA policy.

The launcher now assigns mutable firmware state under:

`%APPDATA%\MetroidPrimeHuntersRecomp`

using separate files for generated and retail firmware modes:

- `firmware-generated.bin`
- `firmware-retail.bin`

The selected state file is passed to the runner through
`--firmware-state-path`. Wi-Fi settings, WFC updates and console/game-card
pairing can therefore persist across normal launches and guest shutdowns.

The dashboard console-MAC display prefers the persisted mutable firmware state
after it exists, falling back to the generated installation identity on the
first generated-firmware launch.

This required updating the pinned ndsrecomp revision to:

`6c6a03bdcf99093f64555c4d05d16e522dc58634`

The new upstream runner still contains old US1.0 SHA/address assumptions in its
baseline source, so the local multi-ROM patch stack remains authoritative and
replaces them during the build.

## 10. Preparing an exact content profile

The preparation path intentionally remains exact-content gated. This protects
generated code provenance; it is not the runtime selector.

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

It then extracts ARM9, ARM7 and overlays and emits content-specific seed
configs.

## 11. Coverage and capture safety

Static and runtime promotion is profile/content aware.

For non-US content, traces carry both:

- content profile key
- exact whole-ROM SHA-1

Main-image geometry is derived from the selected prepared ARM9/ARM7 configs,
not reused from US1.0 constants.

FMV/runtime capture promotion verifies exact content provenance. A capture from
one content SHA must not be promoted into another content profile.

## 12. CI and runtime safety tests

CI downloads the current melonPrimeDS `develop_hud` detector/address table and
checks the registry against them, then fetches the exact pinned ndsrecomp
revision and applies the patch stack twice to verify idempotency.

The runtime harness uses synthetic, non-copyrighted ROM images constructed to
produce the canonical melonPrimeDS executable checksums. It verifies:

- all seven runtime profiles dispatch the correct Aim/Morph addresses
- authoritative checksums allow host accesses
- header-only fallback does not allow host RAM/code access
- unsupported revisions fail closed
- malformed ARM image ranges fail closed
- known-clean SHA/header contradictions fail closed
- canonical executable-equivalent data variants may pass the clean SHA gate
- known code-modified variants receive the correct runtime base but cannot
  automatically reuse the clean exact-content build
- Adaptive Widescreen address triples match melonPrimeDS for all seven revisions
- patched `title_patches.cpp`, `frontend.cpp` and `main.cpp` compile against the
  pinned runner
- US1.0/EU1.1 launcher generation and exact-content ROM checkers compile

At the time of this update, `MPH Multi-ROM Static Checks` run #72 passes every
main validation step.

## 13. Remaining work for full multi-ROM support

The detector/address architecture is prepared for all seven base revisions, but
full player-facing support still requires exact content work per ROM:

1. add verified clean content profiles for US1.1, EU1.0, JP1.0, JP1.1 and KR1.0
2. prepare/extract each exact ROM
3. capture deterministic coverage and promote it under that exact SHA
4. generate revision-specific ARM9/ARM7/overlay banks
5. validate boot, Adventure, pause, save/load and multiplayer-menu paths
6. validate Prime Controls, Direct Mouse Aim and Adaptive Widescreen semantics
   on real execution
7. compare checkpoints against reference/native execution
8. capture revision-specific FMV runtime code only where interpreter fallback
   needs optimization
9. regression-test US1.0 after each new profile

For a modified ROM, additionally:

1. compute the exact whole-ROM SHA-1
2. compute the melonPrimeDS-compatible header+ARM9+ARM7 CRC32
3. determine and validate its runtime base layout
4. if code-modified, register the executable checksum only after Aim/Morph/
   Widescreen address compatibility is established
5. add a distinct content profile with `base_profile`
6. generate/promote coverage and banks under that mod's exact content identity

Do not guess an unknown mod as US1.0 simply because its filename, region or
header resembles US1.0.
