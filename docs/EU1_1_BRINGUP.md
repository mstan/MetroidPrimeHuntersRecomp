# Metroid Prime Hunters Recomp - EU1.1 Bring-up

作成日: 2026-08-17
更新日: 2026-08-17

## 1. 目的

`MetroidPrimeHuntersRecomp` を USA revision 0 (`AMHE`, revision 0) 固定から
multi-ROM化し、最初の追加対象として Europe revision 1 (`AMHP`, revision 1)
を安全にbring-upする。

現在はROM実体なしで実装・検証できる範囲を進め、次まで完了している。

1. ROM identityを版別profileとして管理する。
2. EU1.1 ROMからARM9 / ARM7 / ARM9 overlayを直接抽出するprofile-driven prepare経路を持つ。
3. EU1.1専用bankをUS1.0生成物から分離する。
4. US1.0のcoverage seedやFMV runtime captureをEU1.1へ流用しない。
5. exact ROM SHA-1でrunner側のbankとhost-side runtime address profileをgateする。
6. Prime ControlsのMorph判定とDirect Mouse AimをEU1.1固有RAMアドレスへ対応させる。
7. EU1.1専用ROM identity / default ROM filename / feature policyを持つlauncherを同一launcher sourceから生成する。
8. EU1.1では未検証のAdaptive Widescreenをlauncher UIから隠し、persisted stateとlaunch commandの両方でも強制OFFにする。
9. Windows/Linux build入口をprofile-awareにする。
10. ROM不要CIでmelonPrimeDS address tableとの照合、pinned ndsrecomp patch、runner C++ compile、exact-ROM runtime dispatchを検証する。
11. ROM不要CIでUS1.0/EU1.1のlauncher generated sourceを生成し、identityとfeature policyを直接検証する。

未完了なのは、EU1.1実ROMと実行環境を必要とするruntime validation、
EU1.1固有coverageの拡張、必要に応じたEU1.1固有FMV runtime captureである。

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

`config/mph_rom_profiles.json` は現在schema 2で、US1.0とEU1.1を同じ構造で管理する。

Profileには次を持たせる。

- `game_code`
- `revision`
- `rom_size`
- `sha1`
- `program_id`
- `coverage`
- `game_config`
- `fmv_runtime`
- `launcher_default_rom`
- `adaptive_widescreen`
- `runtime.morph_state`
- `runtime.aim_x`
- `runtime.aim_y`

host-side runtime addressのsource of truthは以下に固定する。

```text
https://github.com/ag-advania/melonPrimeDS/blob/main/src/frontend/qt_sdl/MelonPrimeGameRomAddrTable.h
```

Aim/Morphアドレスはglobal relocation deltaから推測せず、このmelonPrimeDS address tableを正として扱う。

`tools/check_mph_multirom_profiles.py` はprofileと各versionの`game.toml`、coverage seed、launcher policyを静的照合する。特に `adaptive_widescreen=false` のprofileでgame config側がadaptiveを有効化していた場合はfailする。

## 4. melonPrimeDSから確定したEU1.1 runtime addresses

`MelonPrimeGameRomAddrTable.h` の `RomGroup` は次の順序である。

```text
JP1_0, JP1_1, US1_0, US1_1, EU1_0, EU1_1, KR1_0
```

Recomp runnerで現在必要なフィールドは以下である。

| Semantic | melonPrimeDS field | US1.0 | EU1.1 |
|---|---|---:|---:|
| Morph / Alt Form state | `baseIsAltForm` | `0x020DA818` | `0x020DB138` |
| Direct Aim X | `baseAimX` | `0x020DE526` | `0x020DEE46` |
| Direct Aim Y | `baseAimY` | `0x020DE52E` | `0x020DEE4E` |

これらは `config/mph_rom_profiles.json` の `runtime` に登録済みである。

CIはmelonPrimeDS `main` の実ファイルを取得し、`RomGroup`と上記3フィールドをparserで読み取り、profileと自動照合する。値が変化した場合はCIで検出する。

## 5. pinned ndsrecompのUS1.0固定を除去する方法

pinned framework revision:

```text
46b12e6c18dea47f87d2c1f98c3054149dcbca5d
```

このrevisionのrunnerには元々、

```text
frontend.cpp:
  kMphUs10MorphState = 0x020DA818

title_patches.cpp:
  kMphUs10AimX = 0x020DE526
  kMphUs10AimY = 0x020DE52E

main.cpp:
  Prime Controls policy = exact US1.0 SHA-1 only
```

というUS1.0固定が存在する。

プロジェクト側の `tools/patch_ndsrecomp_mph_runtime.py` がbuild前にpinned `ndsrecomp` checkoutへ小さなprofile-selection shimを適用する。

パッチ後は概念的に次の経路になる。

```text
ROM SHA-1
  -> NdsMphRuntimeProfile選択
      -> morph_state
      -> aim_x
      -> aim_y
  -> exact profileがある場合のみPrime Controls / Direct Mouse Aimを許可
  -> 未登録SHA-1ではhost hookを無効化
```

生成されるframework側header:

```text
runner/src/mph_runtime_profiles.generated.h
```

このheaderは直接編集せず、`config/mph_rom_profiles.json` から生成する。

パッチャーは以下の性質を持つ。

- exact pinned source preimageを要求する。
- upstream sourceが想定外に変わった場合はguessせず失敗する。
- 同じcheckoutへ複数回適用しても結果が変わらない。
- profile切替時にDirect Aim enable stateをclearする。
- 未知ROMはfail-closedになる。
- runtime addressはDS main RAM範囲内か検証する。

さらに `tools/tests/mph_runtime_profile_test.cpp` は実際のpatched `title_patches.cpp` をリンクして、ROMなしで次を実行検証する。

- unknown SHA-1ではAim writeもMorph readも行わない。
- US1.0は従来の3アドレスを維持する。
- EU1.1は `0x020DB138 / 0x020DEE46 / 0x020DEE4E` のみを使う。
- US1.0からEU1.1へprofile切替した際にold enable stateを引き継がない。
- valid profileの後にunknown SHA-1を選択した場合もstale addressを保持しない。

## 6. EU1.1 coverage bootstrap

`coverage/eu11-bootstrap-entry-points.json`

初期状態ではARM9 / ARM7の追加coverage rootを空にする。

これは意図的である。

`prepare_mph.py` はROM headerのARM9/ARM7 entry PCを必ずseedするため、EU1.1はまずそのrootからstatic discoveryを行い、未コンパイル領域はruntime Interpreterへfallbackする。

US1.0の `coverage/adventure-main-entry-points.json` に入っているabsolute PCをEU1.1へコピーしてはいけない。

EU1.1自身を実行したtraceからのみEU1.1 coverageを拡張する。

## 7. Generated tree separation

US1.0は後方互換性のため従来通り:

```text
generated/
  inputs/
  recomp/
  capture/
```

EU1.1は:

```text
generated/
  EU1_1/
    inputs/
    recomp/
```

とする。

これにより異なるROM由来のbankやbinaryが同じパスへ混ざらない。

## 8. Launcher identity / feature policy separation

launcherの大きなsourceをROM revisionごとに複製しない。

`launcher/recomp-ui/CMakeLists.txt` はconfigure時にbaseline `launcher_main.cpp` を読み、選択profileの次の項目を反映したgenerated translation unitをbuild directoryへ作る。

- exact ROM SHA-1
- Region
- default ROM filename
- Adaptive Widescreen availability/default

```text
launcher_main.cpp
  -> configure-time guarded transform
  -> launcher_main_profile.cpp
  -> mph-recomp-ui
```

各replaceはbaseline preimageを要求する。launcher sourceが将来変わって想定文字列が消えた場合は、stale transformを続行せずCMake configureを失敗させる。

US1.0は従来挙動を維持する。

```text
SHA-1: 90164d1ac127ee5f9815ea4ae7de798c7b5fc629
Region: USA
Default ROM: Metroid Prime Hunters.nds
Adaptive Widescreen: enabled / UI exposed
```

EU1.1 buildは次になる。

```text
SHA-1: bdcd1dea293e24c98d4c481430e90d21198985a5
Region: Europe
Default ROM: Metroid Prime Hunters (Europe Rev 1).nds
Adaptive Widescreen: disabled / UI hidden
```

EU1.1のAdaptive Widescreenは三重にfail-closedにする。

1. launcher mod listからAdaptive Widescreen項目を隠す。
2. 旧/shared `mods.ini` に `adaptive_widescreen=true` が残っていてもload後にfalseへ戻す。
3. `launch_runner()` の最終段でもprofile capabilityとANDし、EU1.1では `--adaptive-widescreen top` を生成できないようにする。

Prime ControlsはEU1.1でも表示する。これはMorph/Aimの必要アドレスをmelonPrimeDS tableからexact profile化し、ROMなしunit testでaddress dispatchまで固定できたためである。ただし実ゲーム内でのsemantic correctnessは実ROM Gate Dで別途確認する。

## 9. FMV runtime bank

US1.0の

```text
config/mph_arm9_fmv_runtime.toml
generated/capture/mph_arm9_fmv_runtime.bin
```

はUS1.0 runtime bytesとobserved PCsに対するbankである。

EU1.1 profileは:

```text
fmv_runtime = false
```

とし、このbankを絶対に登録しない。

EU1.1でopening FMV等がInterpreter fallbackでは遅い場合でも、US1.0 captureを流用してはいけない。EU1.1自身からITCM + main RAM captureを取得し、live-byte validation付きのEU1.1専用runtime bankを作る。

## 10. Build

### 10.1 Windows

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  tools\build-windows.ps1 `
  -Version 0.3.0 `
  -MphVersion EU1_1 `
  -RomPath 'D:\ROMs\Metroid Prime Hunters (Europe) (Rev 1).nds'
```

`-RomPath` を省略した場合は選択profileの `launcher_default_rom` を使う。EU1.1なら `Metroid Prime Hunters (Europe Rev 1).nds` になる。

現在のWindows buildはEU1.1についても以下まで一貫して行う。

1. EU1.1 ROM identity verify
2. EU1.1 ARM9/ARM7 extraction
3. EU1.1 static bank generation
4. pinned ndsrecomp runtime-profile patch
5. exact EU1.1 SHA-1 runner build
6. EU1.1 identity + feature policy launcher build
7. EU1.1 launcherでAdaptive Widescreenを非公開/強制OFF
8. `config/game-eu11.toml` をrelease内 `game.toml` としてpackage

EU1.1にはFMV runtime captureがまだないため、そのbankの存在はrelease gateにしない。

### 10.2 Linux

runnerまで:

```bash
tools/build-linux.sh \
  --mph-version EU1_1 \
  --rom '/path/to/Metroid Prime Hunters (Europe) (Rev 1).nds' \
  --no-package
```

AppImageまで:

```bash
tools/build-linux.sh \
  --mph-version EU1_1 \
  --rom '/path/to/Metroid Prime Hunters (Europe) (Rev 1).nds'
```

EU1.1 package名には `EU1_1` suffixを付け、US1.0のhistorical filenameとは分離する。

Linux AppRunはprofile別 `game.toml` をrunnerへ渡し、launcherのようなUS1.0固定Adaptive Widescreen CLI overrideを行わない。EU1.1では `config/game-eu11.toml` のnative presentation policyがそのまま有効になることを維持する。

## 11. ROM不要static CI

`.github/workflows/mph-multirom-static.yml`

PRごとに以下を検証する。

1. `prepare_mph.py` / profile checker / framework patcherのPython syntax
2. Linux build scriptのshell syntax
3. Windows build/release scriptのPowerShell syntax
4. `config/mph_rom_profiles.json` とcoverage/game config/launcher policyの整合性
5. melonPrimeDS `main` の `MelonPrimeGameRomAddrTable.h` を取得
6. `baseIsAltForm` / `baseAimX` / `baseAimY` をprofileと自動照合
7. exact `ndsrecomp.pin` revisionを取得
8. fake SDL2 / recomp-ui CMake interfaceでUS1.0 launcher sourceを生成
9. fake SDL2 / recomp-ui CMake interfaceでEU1.1 launcher sourceを生成
10. generated EU1.1 launcherがEU SHA-1 / Europe / EU default ROM filenameを持つことを確認
11. generated EU1.1 launcherがAdaptive Widescreen default OFF / UI hidden / final launch gate OFFであることを確認
12. runtime-profile patchを適用
13. 同じpatchを2回適用し、対象ファイルhashが完全一致することを確認
14. US1.0固定Aim/Morph symbolがpatched runnerから除去されていることを確認
15. patched `title_patches.cpp` / `frontend.cpp` / `main.cpp` をpinned runnerの実CMake compile flagsでcompile
16. `tools/tests/mph_runtime_profile_test.cpp` をpatched `title_patches.cpp` とリンクして実行
17. US1.0/EU1.1それぞれの`mph_romcheck`をcompile
18. EU1.1 checkerにEU1.1 SHA-1/profile keyが埋め込まれていることを確認
19. `git diff --check`

このCIはROM、BIOS、firmware dumpを一切取得・保存しない。

2026-08-17時点の最新CIでは上記項目がすべてPASSしている。

## 12. mphCodexの役割

Aim X/Y/MorphについてはmelonPrimeDS address tableをsource of truthとする。

mphCodexは引き続き、今後Recomp固有のhost enhancementがsemantic stateを読む必要が出た場合のcross-version調査に利用する。

例:

| Semantic | US1.0 | EU1.1 |
|---|---:|---:|
| Current Camera Sequence | `0x020D9CB0` | `0x020DA5D0` |
| Game Mode | `0x020E78FC` | `0x020E845C` |
| Upper HUD function | `0x0202F600` | `0x0202F5E0` |
| Crosshair callsite | `0x0202F934` | `0x0202F904` |
| Crosshair renderer | `0x020393D4` | `0x02039338` |
| Local Player Pointer | `0x020BCA70` | `0x020BD370` |
| HUD suppression storage | `0x020DE748` | `0x020DF068` |

この表からも、US1.0 -> EU1.1を単一deltaで変換できないことが分かる。

## 13. 実ROMで残るvalidation gates

### Gate A - extraction / bank generation

EU1.1実ROMで次を確認する。

- `prepare_mph.py` がEU1.1 identityをaccept
- ARM9 decompress成功
- ARM7 extraction成功
- ARM9 overlay table列挙成功
- `generated/EU1_1/recomp/` にEU1.1専用bank生成
- US1.0 artifactが混入していない

### Gate B - boot / interpreter bootstrap

- firmware boot
- cartridge handoff
- opening logos
- opening FMV
- title screen
- attract loop

static missはInterpreterへfallbackさせ、最初はcorrectnessを優先する。

### Gate C - gameplay

最低限:

- Adventure file作成/読込
- Celestial Archives landing
- first-person gameplay
- movement
- aim
- shoot
- Morph Ball
- Scan Visor
- pause
- save/reload
- multiplayer menu

### Gate D - Prime Controls / Direct Mouse Aim semantic validation

ROM不要unit testによってaddress routing自体は既に固定済みである。

```text
Morph state = 0x020DB138
Aim X       = 0x020DEE46
Aim Y       = 0x020DEE4E
```

実ROM Gate Dでは「そのアドレスを使うか」ではなく、ゲーム内semanticが期待通りかを確認する。

- normal formでcenter touch保持
- Morph Ball時にcenter touchを解除
- mouse X/Y deltaでcamera aimが正しく変化
- menu/touch操作へ戻れる
- keyboard/gamepad Prime Controls
- profile切替・再起動後にstale stateが残らない

### Gate E - Adaptive Widescreen

EU1.1では現在意図的に無効である。EU1.1を基本対応とするための必須条件ではない。

将来EU1.1でも有効化する場合は、少なくとも次をEU1.1実ROMで確認する。

- 3D projection
- frustum/culling
- upper-screen HUD anchoring
- lower touchscreen native layout
- Adventure camera / Scan Visor等の特殊scene
- US1.0との差分があるsemantic addressを固定値で流用していないこと

検証後にのみ、

```json
"adaptive_widescreen": true
```

とEU1.1 `game.toml` の対応display設定を同時に有効化する。

### Gate F - EU1.1 deterministic coverage

EU1.1 execution traceから

- immutable ARM9 main-image call target
- immutable ARM9 main-image indirect target
- ARM7 main-image target

のみを抽出し、EU1.1専用coverageへ昇格する。

US1.0 absolute PCのaddress translationは行わない。

### Gate G - EU1.1 FMV runtime optimization

必要な場合だけEU1.1自身からcaptureを作る。

- capture SHA-1
- live-byte validation
- observed call targets
- observed indirect targets
- performance comparison

を固定してからEU1.1 profileの `fmv_runtime` をtrueへ変更する。

## 14. Supported判定

EU1.1をruntime検証済みsupportedと宣言する条件:

- exact EU1.1 ROM identity gate
- EU1.1 main ARM9 bank
- EU1.1 ARM7 bank
- interpreter fallbackでterminal dispatch missなし
- title到達
- Adventure gameplay到達
- save/load確認
- pause/reload確認
- host-side title patchがUS1.0 addressをEU1.1へ使用しない
- Prime Controls動作確認
- Direct Mouse Aim動作確認
- EU1.1未検証enhancementがfail-closedであること
- native/reference checkpoint比較
- US1.0 regressionなし

Adaptive WidescreenやEU1.1 FMV runtime bankは、基本的なEU1.1 correctnessを満たすための必須機能ではない。未検証のまま誤って有効化しないことを優先する。

## 15. 現在の判定

### Code / infrastructure

**READY FOR EU1.1 ROM VALIDATION**

ROMなしで可能なidentity/profile、extraction routing、bank isolation、runtime address selection、launcher identity、launcher feature gating、Windows/Linux packaging、static CIまで実装済み。

特に以下はROMなしで実行検証済みである。

- melonPrimeDS tableとEU1.1 Aim/Morph profileの一致
- runtime patchのidempotency
- patched runner C++ translation unitsのcompile
- unknown ROM fail-closed
- US1.0 runtime address regressionなし
- EU1.1 exact Aim/Morph dispatch
- US1.0/EU1.1 launcher generated sourceのprofile分離
- EU1.1 Adaptive WidescreenのUI/persisted state/launch command三重gate
- US1.0/EU1.1 ROM checker compile

### Runtime correctness

**NOT YET CLAIMED**

EU1.1実ROMによるboot/gameplay/reference validationは別途必要である。
このvalidationを通すまでは、コードがEU1.1を受理できることと、ゲーム動作が完全に検証済みであることを混同しない。
