# Metroid Prime Hunters Recomp - EU1.1 Bring-up

作成日: 2026-08-17
更新日: 2026-08-17

## 1. 目的

`MetroidPrimeHuntersRecomp` を USA revision 0 (`AMHE`, revision 0) 固定からmulti-ROM化し、最初の追加対象として Europe revision 1 (`AMHP`, revision 1) を安全にbring-upする。

ROMなしで可能な基盤実装は完了しており、現在の残件はEU1.1実ROMを使うruntime validation、EU1.1固有coverage、必要に応じたEU1.1固有FMV runtime captureである。

## 2. EU1.1 identity

| Field | EU1.1 |
|---|---|
| Profile key | `EU1_1` |
| Game Code | `AMHP` |
| Revision | `1` |
| ROM size | `0x04000000` / 64 MiB |
| SHA-1 | `bdcd1dea293e24c98d4c481430e90d21198985a5` |
| Program ID prefix | `mph_amhp1` |
| Game config | `config/game-eu11.toml` |
| Launcher default ROM | `Metroid Prime Hunters (Europe Rev 1).nds` |
| Adaptive Widescreen | disabled until EU1.1 validation |
| FMV runtime bank | disabled until EU1.1 capture exists |

identityと版別policyは `config/mph_rom_profiles.json` に集約する。

## 3. ROM profile registry

schema 2 profileは少なくとも以下を管理する。

- `game_code`, `revision`, `rom_size`, `sha1`, `program_id`
- `coverage`, `game_config`, `fmv_runtime`
- `launcher_default_rom`, `adaptive_widescreen`
- `runtime.morph_state`, `runtime.aim_x`, `runtime.aim_y`

host-side runtime addressのsource of truth:

```text
https://github.com/ag-advania/melonPrimeDS/blob/main/src/frontend/qt_sdl/MelonPrimeGameRomAddrTable.h
```

Aim/Morphアドレスはglobal relocation deltaから推測しない。

## 4. melonPrimeDSから確定したEU1.1 runtime addresses

| Semantic | melonPrimeDS field | US1.0 | EU1.1 |
|---|---|---:|---:|
| Morph / Alt Form state | `baseIsAltForm` | `0x020DA818` | `0x020DB138` |
| Direct Aim X | `baseAimX` | `0x020DE526` | `0x020DEE46` |
| Direct Aim Y | `baseAimY` | `0x020DE52E` | `0x020DEE4E` |

CIはmelonPrimeDS `main` の実ファイルを取得してprofileと自動照合する。

## 5. pinned ndsrecomp runtime profile shim

pinned framework:

```text
46b12e6c18dea47f87d2c1f98c3054149dcbca5d
```

元runnerのUS1.0固定Morph/Aim addressとUS1.0-only Prime Controls policyは `tools/patch_ndsrecomp_mph_runtime.py` でexact-ROM profile選択へ変換する。

```text
ROM SHA-1
  -> NdsMphRuntimeProfile
      -> morph_state
      -> aim_x
      -> aim_y
  -> known profileのみPrime Controls / Direct Mouse Aimを許可
  -> unknown ROMはfail-closed
```

patcherはexact source preimageを要求し、idempotentで、profile切替時にold direct-aim enable stateをclearする。

`tools/tests/mph_runtime_profile_test.cpp` はpatched `title_patches.cpp` を実際にリンクして以下を検証する。

- unknown SHA-1でAim write / Morph readなし
- US1.0 address regressionなし
- EU1.1は `0x020DB138 / 0x020DEE46 / 0x020DEE4E` のみ使用
- profile切替後のstale stateなし

## 6. EU1.1 coverage bootstrap

`coverage/eu11-bootstrap-entry-points.json` は追加ARM9/ARM7 rootを空にする。ROM header entry PCは `prepare_mph.py` がseedし、未コンパイル領域はInterpreter fallbackへ送る。

US1.0 absolute PCはEU1.1へコピーしない。EU1.1自身のtraceからのみcoverageを拡張する。

## 7. Generated tree separation

US1.0:

```text
generated/inputs/
generated/recomp/
generated/capture/
```

EU1.1:

```text
generated/EU1_1/inputs/
generated/EU1_1/recomp/
```

## 8. Launcher identity / feature policy separation

`launcher/recomp-ui/CMakeLists.txt` はbaseline `launcher_main.cpp` からprofile-specific generated TUを作る。

反映項目:

- exact ROM SHA-1
- Region
- default ROM filename
- Adaptive Widescreen availability/default

EU1.1 generated launcher:

```text
SHA-1: bdcd1dea293e24c98d4c481430e90d21198985a5
Region: Europe
Default ROM: Metroid Prime Hunters (Europe Rev 1).nds
Adaptive Widescreen: disabled / UI hidden
```

EU1.1 Adaptive Widescreenは三重にfail-closed:

1. mod listから非表示
2. persisted `adaptive_widescreen=true` をload後にfalseへ戻す
3. `launch_runner()` 最終段でもprofile capabilityとANDする

Prime ControlsはEU1.1でも表示する。必要なMorph/Aim address routingはROMなしunit testで固定済みだが、ゲーム内semantic correctnessは実ROMで確認する。

## 9. FMV runtime bank

US1.0 runtime captureはEU1.1へ流用しない。EU1.1は現在 `fmv_runtime=false`。必要な場合のみEU1.1自身からcaptureし、live-byte validation付きbankを作る。

## 10. Build

### Windows

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  tools\build-windows.ps1 `
  -Version 0.3.0 `
  -MphVersion EU1_1 `
  -RomPath 'D:\ROMs\Metroid Prime Hunters (Europe) (Rev 1).nds'
```

`-RomPath`省略時はprofileの `launcher_default_rom` を使う。

WindowsはEU1.1 identity verify -> extraction -> static bank -> runtime-profile patch -> exact EU SHA runner -> profile-specific launcher -> EU game config packagingまで一貫して行う。

### Linux

```bash
tools/build-linux.sh \
  --mph-version EU1_1 \
  --rom '/path/to/Metroid Prime Hunters (Europe) (Rev 1).nds'
```

`--rom`省略時はEU1.1 profileのdefault ROM filenameをrepository rootから探す。AppRunはprofile別 `game.toml` をrunnerへ渡し、`--adaptive-widescreen` 等でtitle policyを上書きしない。

## 11. ROM不要static CI

`.github/workflows/mph-multirom-static.yml` は以下を検証する。

1. Python / shell / PowerShell syntax
2. profile / coverage / game config / launcher policy整合性
3. melonPrimeDS `MelonPrimeGameRomAddrTable.h` とのAim/Morph照合
4. exact `ndsrecomp.pin` fetch
5. US1.0/EU1.1 launcher generated source renderとidentity/policy確認
6. Linux AppRunのprofile-owned config policy確認
7. ndsrecomp runtime patchのidempotency
8. US1.0固定Aim/Morph symbol除去確認
9. patched runnerの `title_patches.cpp` / `frontend.cpp` / `main.cpp` compile
10. exact-ROM runtime dispatch unit test実行
11. US1.0/EU1.1 `mph_romcheck` compile
12. `git diff --check`

ROM、BIOS、firmware dumpはCIで取得しない。

## 12. mphCodexの役割

Aim X/Y/MorphはmelonPrimeDS tableをsource of truthとする。その他Recomp固有host enhancementのcross-version semantic調査にはmphCodexを利用する。

| Semantic | US1.0 | EU1.1 |
|---|---:|---:|
| Current Camera Sequence | `0x020D9CB0` | `0x020DA5D0` |
| Game Mode | `0x020E78FC` | `0x020E845C` |
| Upper HUD function | `0x0202F600` | `0x0202F5E0` |
| Crosshair callsite | `0x0202F934` | `0x0202F904` |
| Crosshair renderer | `0x020393D4` | `0x02039338` |
| Local Player Pointer | `0x020BCA70` | `0x020BD370` |
| HUD suppression storage | `0x020DE748` | `0x020DF068` |

単一delta変換は使用しない。

## 13. 実ROMで残るvalidation gates

### Gate A - extraction / bank generation

EU1.1 identity accept、ARM9 decompress、ARM7 extraction、overlay列挙、EU1.1 bank生成、US1.0 artifact非混入。

### Gate B - boot

firmware boot、cartridge handoff、opening logos/FMV、title、attract loop。

### Gate C - gameplay

Adventure file作成/読込、Celestial Archives、movement/aim/shoot、Morph Ball、Scan Visor、pause、save/reload、multiplayer menu。

### Gate D - Prime Controls / Direct Mouse Aim semantics

address routingはunit test済み。実ROMではnormal/Morph touch behavior、camera aim、menu/touch復帰、keyboard/gamepad操作を確認する。

### Gate E - Adaptive Widescreen

現在EU1.1では意図的に無効。基本対応の必須条件ではない。将来有効化する場合のみprojection、culling、HUD anchoring、touchscreen、特殊camera/visor sceneをEU1.1実ROMで検証し、profileとgame configを同時にenableする。

### Gate F - deterministic coverage

EU1.1自身のexecution traceからのみcoverageを昇格する。

### Gate G - FMV runtime optimization

必要な場合のみEU1.1 captureを作り、content validationとperformanceを確認してから `fmv_runtime=true` にする。

## 14. Supported判定

EU1.1をruntime検証済みsupportedと宣言するには、exact identity、EU1.1 ARM9/ARM7 banks、title/gameplay/save/load、Prime Controls/Direct Aim semantic validation、native/reference checkpoint比較、US1.0 regressionなしが必要である。

Adaptive WidescreenとEU1.1 FMV runtime bankは基本correctnessの必須条件ではない。未検証機能はfail-closedを維持する。

## 15. 現在の判定

### Code / infrastructure

**READY FOR EU1.1 ROM VALIDATION**

ROMなしで可能なprofile、extraction routing、bank isolation、runtime address selection、launcher identity/feature gating、Windows/Linux packaging、static CIまで実装済み。

### Runtime correctness

**NOT YET CLAIMED**

EU1.1実ROMによるboot/gameplay/reference validationは別途必要である。
