# Metroid Prime Hunters Recomp - EU1.1 Bring-up

作成日: 2026-08-17
更新日: 2026-08-17

## 1. 目的

`MetroidPrimeHuntersRecomp` を USA revision 0 (`AMHE`, revision 0) 固定からmulti-ROM化し、最初の追加対象として Europe revision 1 (`AMHP`, revision 1) を安全にbring-upする。

ROMなしで可能な基盤実装は完了しており、現在の残件はEU1.1実ROMを使うruntime validation、EU1.1固有coverageの実採取、必要に応じたEU1.1固有FMV runtime captureである。

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
| FMV runtime enabled | `false` |
| Reserved EU1.1 FMV bank ID | `mph_amhp1_arm9_fmv_runtime` |

identityと版別policyは `config/mph_rom_profiles.json` に集約する。

## 3. ROM profile registry

schema 2 profileは少なくとも以下を管理する。

- `game_code`, `revision`, `rom_size`, `sha1`, `program_id`
- `coverage`, `game_config`
- `fmv_runtime`, `fmv_runtime_bank`
- `launcher_default_rom`, `adaptive_widescreen`
- `runtime.morph_state`, `runtime.aim_x`, `runtime.aim_y`

host-side runtime addressのsource of truth:

```text
https://github.com/ag-advania/melonPrimeDS/blob/main/src/frontend/qt_sdl/MelonPrimeGameRomAddrTable.h
```

Aim/Morphアドレスはglobal relocation deltaから推測しない。

CMakeのprofile候補とWindows buildの `-MphVersion` validationもregistryから導出する。新しいrevisionをprofile registryへ追加するとき、`US1_0/EU1_1` の固定列挙を別途更新する必要はない。

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

## 6. EU1.1 static coverage pipeline

### 6.1 Bootstrap

`coverage/eu11-bootstrap-entry-points.json` は追加ARM9/ARM7 rootを空にする。ROM header entry PCは `prepare_mph.py` がseedし、未コンパイル領域はInterpreter fallbackへ送る。

US1.0の `coverage/adventure-main-entry-points.json` に含まれるabsolute PCはEU1.1へコピーしない。EU1.1自身のexecution traceからのみcoverageを拡張する。

### 6.2 US1.0固定rangeの除去

旧 `tools/promote_mph_static_coverage.py` はUS1.0固定の以下を内蔵していた。

```text
GAME_SHA1
ARM9 main-image start/end
ARM7 main-image start/end
ARM9/ARM7 existing entry PC
```

現在はこれらを持たない。

`prepare_mph.py` が選択ROMそのものから生成した

```text
generated/<profile>/inputs/arm9.toml
generated/<profile>/inputs/arm7.toml
```

の `[program].load_address`, `size`, `entry_pc`, `id` を読み、実ROM由来のimmutable main-image geometryをcoverage filterへ使用する。

EU1.1では既定で:

```text
generated/EU1_1/inputs/arm9.toml
generated/EU1_1/inputs/arm7.toml
```

を読む。

したがってEU1.1のARM9/ARM7終端アドレスをUS1.0から推測・変換する処理はない。

### 6.3 Trace provenance

`tools/fuzz_mph_gameplay.py` は現在profile-awareで、実行前にROMのsize/SHA-1/game code/revisionを検証する。

生成する `trace.json` には少なくとも以下を記録する。

```json
{
  "mph_profile": "EU1_1",
  "rom_sha1": "bdcd1dea293e24c98d4c481430e90d21198985a5",
  "scenario": "scenarios/adventure_start.json"
}
```

EU1.1のcoverage昇格では、このprofile/ROM identityが欠落した旧traceや出所不明traceを拒否する。

### 6.4 EU1.1 Adventure coverage採取

EU1.1 runnerをbuild済みとする。

```powershell
python tools\fuzz_mph_gameplay.py `
  --version EU1_1 `
  --runner ..\ndsrecomp\runner\build-mph-release-EU1_1\nds_runner.exe `
  --bios bios `
  --rom "Metroid Prime Hunters (Europe Rev 1).nds" `
  --out generated\EU1_1\capture\adventure-coverage `
  --actions scenarios\adventure_start.json `
  --steps 0 `
  --capture-static-coverage
```

`--capture-static-coverage` によりrunnerは `--discover-static-misses` 付きで起動し、最後に `static_coverage` と `tier3_coverage` をdebug serverから回収する。

### 6.5 EU1.1 static coverage昇格

runner/framework commitは実際に採取へ使ったrevisionを記録する。

```powershell
$runnerCommit = git -C ..\ndsrecomp rev-parse HEAD

python tools\promote_mph_static_coverage.py `
  --version EU1_1 `
  --trace generated\EU1_1\capture\adventure-coverage\trace.json `
  --out coverage\eu11-adventure-main-entry-points.json `
  --runner-commit $runnerCommit
```

昇格対象は以下のみ。

- ARM9/ARM7 immutable main image内
- Tier-3 `call`
- Tier-3 `indirect`

以下は除外する。

- slice-resume root
- main image範囲外runtime RAM
- reused overlay virtual ranges
- ROM header entry PCの重複

実ROM検証後に `config/mph_rom_profiles.json` のEU1.1 `coverage` をbootstrap JSONからこの昇格済みJSONへ切り替える。

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
generated/EU1_1/capture/
```

異なるROM revisionのprepared binary、coverage capture、runtime image、generated bankを同じディレクトリへ混在させない。

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

## 9. EU1.1 FMV runtime capture pipeline

### 9.1 US1.0 bankの非流用

US1.0の既存bank:

```text
config/mph_arm9_fmv_runtime.toml
generated/capture/mph_arm9_fmv_runtime.bin
bank id: mph_arm9_fmv_runtime
```

はEU1.1へ流用しない。

EU1.1用に予約しているidentity/path:

```text
config/mph_amhp1_arm9_fmv_runtime.toml
generated/EU1_1/capture/mph_amhp1_arm9_fmv_runtime.bin
bank id: mph_amhp1_arm9_fmv_runtime
```

現在 `fmv_runtime=false` なので、EU1.1 buildはこのbankを要求・登録しない。

### 9.2 FMV benchmark/captureのprofile化

`tools/benchmark_mph_fmv.py` は現在:

- `--version EU1_1` を受ける
- exact EU1.1 ROM identityを起動前に検証する
- `--config` 省略時は `config/game-eu11.toml` を選ぶ
- `--adaptive auto` が既定
- EU1.1ではprofile policyに従い `--adaptive-widescreen none`
- profileがAdaptive Widescreen未検証なら明示的な `--adaptive top` も拒否する
- `benchmark.json` に `mph_profile` と `rom_sha1` を保存する
- `--capture-runtime` 時はcapture SHA-1とbyte countも保存する

EU1.1を誤ってUS1.0のAdaptive Widescreen有効状態でbenchmark/coverage captureする経路はfail-closedにした。

### 9.3 Before window採取

例としてVBlank 2400までの累積coverageを取る。

```powershell
python tools\benchmark_mph_fmv.py `
  --version EU1_1 `
  --runner ..\ndsrecomp\runner\build-mph-release-EU1_1\nds_runner.exe `
  --bios bios `
  --rom "Metroid Prime Hunters (Europe Rev 1).nds" `
  --out generated\EU1_1\capture\fmv-before `
  --targets 2400 `
  --discover-static-misses
```

### 9.4 Target window + RAM capture

```powershell
python tools\benchmark_mph_fmv.py `
  --version EU1_1 `
  --runner ..\ndsrecomp\runner\build-mph-release-EU1_1\nds_runner.exe `
  --bios bios `
  --rom "Metroid Prime Hunters (Europe Rev 1).nds" `
  --out generated\EU1_1\capture\fmv-3000 `
  --targets 2400 3000 `
  --discover-static-misses `
  --capture-runtime generated\EU1_1\capture\mph_amhp1_arm9_fmv_runtime.bin
```

runtime imageはITCM + main RAMを連結した `0x00408000` bytes。

### 9.5 EU1.1 runtime bank config昇格

```powershell
python tools\promote_mph_runtime_coverage.py `
  --version EU1_1 `
  --before-benchmark generated\EU1_1\capture\fmv-before\benchmark.json `
  --benchmark generated\EU1_1\capture\fmv-3000\benchmark.json `
  --image generated\EU1_1\capture\mph_amhp1_arm9_fmv_runtime.bin `
  --out config\mph_amhp1_arm9_fmv_runtime.toml
```

EU1.1では昇格時に以下を全て要求する。

- benchmarkの `mph_profile == EU1_1`
- benchmarkの `rom_sha1 == EU1.1 SHA-1`
- before benchmarkも同じidentity
- benchmark内 `runtime_capture.sha1` と渡した`.bin`の実SHA-1が一致
- benchmark内capture byte countが `0x00408000`
- ARM9 runtime領域内のobserved call/indirect targetが存在

これらのどれかが不一致ならTOMLを生成しない。

実runtime validationとperformance確認後にのみ、EU1.1 profileの `fmv_runtime` を `true` へ変更する。

## 10. FMV runtime bank build/release routing

CMakeはFMV bank名を固定しない。profileの `fmv_runtime_bank` から以下を導出する。

```text
config/<fmv_runtime_bank>.toml
generated/<profile>/capture/<fmv_runtime_bank>.bin
generated/<profile>/recomp/<fmv_runtime_bank>_*.c
--bank <fmv_runtime_bank>
```

Windows/Linux release gateもprofileのbank IDをrunner内で確認する。

従って将来EU1.1で `fmv_runtime=true` にした場合も、US1.0の `mph_arm9_fmv_runtime` を誤要求しない。

## 11. Profile-aware checkpoint validation

`tools/capture_mph_checkpoints.py` もprofile-awareにした。

runner/oracleのどちらを使う場合も、起動前に選択ROMをprofileのsize/SHA-1/game code/revisionへ照合する。runner時は `--config` 省略でprofileのgame configを選び、config identityもROM profileへ照合する。

各capture directoryには `metadata.json` を追加し、以下を保存する。

```text
mph_profile
rom_sha1
display_name
backend
boot
targets
game_config
```

これによりUS1.0 native checkpointとEU1.1 oracle checkpoint等を誤って同一比較セットとして扱う前に、capture provenanceを確認できる。

EU1.1例:

```powershell
python tools\capture_mph_checkpoints.py `
  --version EU1_1 `
  --runner ..\ndsrecomp\runner\build-mph-release-EU1_1\nds_runner.exe `
  --bios bios `
  --rom "Metroid Prime Hunters (Europe Rev 1).nds" `
  --out generated\EU1_1\capture\checkpoints `
  --targets 300 600 900 1200
```

## 12. Build

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

## 13. ROM不要static CI

`.github/workflows/mph-multirom-static.yml` は以下を検証する。

1. capture/promotion/checkpointを含むPython syntax
2. Linux shell / Windows PowerShell syntax
3. profile / coverage / game config / launcher / FMV bank policy整合性
4. CMake/Windowsがprofile keyを固定列挙しないこと
5. melonPrimeDS `MelonPrimeGameRomAddrTable.h` とのAim/Morph照合
6. fake EU1.1 prepared ARM9/ARM7 geometryからstatic coverageを昇格
7. main-image範囲外targetが除外されることを確認
8. fake EU1.1 runtime image + tagged benchmarkからEU1.1 FMV TOMLを生成
9. runtime image SHA/size metadata照合
10. EU1.1 TOMLへUSA runtime名が混入しないことを確認
11. CMake/Windows/Linuxがprofile-owned FMV bank IDを使用することを確認
12. exact `ndsrecomp.pin` fetch
13. US1.0/EU1.1 launcher generated source renderとidentity/policy確認
14. Linux AppRunのprofile-owned config policy確認
15. ndsrecomp runtime patchのidempotency
16. US1.0固定Aim/Morph symbol除去確認
17. patched runnerの `title_patches.cpp` / `frontend.cpp` / `main.cpp` compile
18. exact-ROM runtime dispatch unit test実行
19. US1.0/EU1.1 `mph_romcheck` compile
20. `git diff --check`

ROM、BIOS、firmware dumpはCIで取得しない。

## 14. mphCodexの役割

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

## 15. 実ROMで残るvalidation gates

### Gate A - extraction / bank generation

EU1.1 identity accept、ARM9 decompress、ARM7 extraction、overlay列挙、EU1.1 bank生成、US1.0 artifact非混入。

### Gate B - boot

firmware boot、cartridge handoff、opening logos/FMV、title、attract loop。

### Gate C - gameplay

Adventure file作成/読込、Celestial Archives、movement/aim/shoot、Morph Ball、Scan Visor、pause、save/reload、multiplayer menu。

### Gate D - Prime Controls / Direct Mouse Aim semantics

address routingはunit test済み。実ROMではnormal/Morph touch behavior、camera aim、menu/touch復帰、keyboard/gamepad操作を確認する。

### Gate E - deterministic coverage

EU1.1自身のprofile-tagged execution traceからcoverageを採取し、EU1.1 prepared main-image geometryでfilterして昇格する。

### Gate F - FMV runtime optimization

必要な場合のみEU1.1 captureを作り、capture identity、content validation、correctness、performanceを確認してから `fmv_runtime=true` にする。

### Gate G - Adaptive Widescreen

現在EU1.1では意図的に無効。基本対応の必須条件ではない。将来有効化する場合のみprojection、culling、HUD anchoring、touchscreen、特殊camera/visor sceneをEU1.1実ROMで検証し、profileとgame configを同時にenableする。

## 16. Supported判定

EU1.1をruntime検証済みsupportedと宣言するには、exact identity、EU1.1 ARM9/ARM7 banks、title/gameplay/save/load、Prime Controls/Direct Aim semantic validation、native/reference checkpoint比較、US1.0 regressionなしが必要である。

Adaptive WidescreenとEU1.1 FMV runtime bankは基本correctnessの必須条件ではない。未検証機能はfail-closedを維持する。

## 17. 現在の判定

### Code / infrastructure

**READY FOR EU1.1 ROM VALIDATION AND PROFILE-TAGGED COVERAGE CAPTURE**

ROMなしで可能なprofile、extraction routing、bank isolation、runtime address selection、launcher identity/feature gating、coverage capture metadata、static/runtime coverage promotion、profile-owned FMV bank routing、checkpoint identity validation、Windows/Linux packaging、static CIまで実装済み。

### Runtime correctness

**NOT YET CLAIMED**

EU1.1実ROMによるboot/gameplay/reference validationと実coverage/capture採取は別途必要である。
