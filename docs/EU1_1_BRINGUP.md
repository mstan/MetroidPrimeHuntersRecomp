# Metroid Prime Hunters Recomp - EU1.1 Bring-up

作成日: 2026-08-17

## 1. 目的

`MetroidPrimeHuntersRecomp` を USA revision 0 (`AMHE`, revision 0) 固定から段階的に
multi-ROM化し、最初の追加対象として Europe revision 1 (`AMHP`, revision 1)
を安全にbring-upする。

この段階は「EU1.1を正式対応済みにする」ものではない。
まず以下を成立させる。

1. ROM identityを版別profileとして管理する。
2. EU1.1 ROMからARM9 / ARM7 / ARM9 overlayを直接抽出できる。
3. EU1.1専用bankをUS1.0生成物から分離して生成できる。
4. US1.0のcoverage seedやFMV runtime captureをEU1.1へ流用しない。
5. exact ROM SHA-1でrunner側のbank登録をgateする。
6. EU1.1固有の未解析箇所はInterpreter fallbackへ安全に落とす。

## 2. EU1.1 identity

| Field | EU1.1 |
|---|---|
| Profile key | `EU1_1` |
| Game Code | `AMHP` |
| Revision | `1` |
| ROM size | `0x04000000` / 64 MiB |
| SHA-1 | `bdcd1dea293e24c98d4c481430e90d21198985a5` |
| Program ID prefix | `mph_amhp1` |

identityは `config/mph_rom_profiles.json` に集約する。

## 3. 今回追加するbootstrap構造

### 3.1 Profile registry

`config/mph_rom_profiles.json`

US1.0とEU1.1を同一schemaで管理する。

Profileには最低限、

- `game_code`
- `revision`
- `rom_size`
- `sha1`
- `program_id`
- `coverage`
- `game_config`
- `fmv_runtime`

を持たせる。

### 3.2 EU1.1 coverage seed

`coverage/eu11-bootstrap-entry-points.json`

初期状態ではARM9 / ARM7の追加coverage rootを空にする。

これは意図的である。

`prepare_mph.py` はROM headerのARM9/ARM7 entry PCを必ずseedするため、
EU1.1はまずそのrootからstatic discoveryを行い、未コンパイル領域は
runtime Interpreterへfallbackする。

US1.0の `coverage/adventure-main-entry-points.json` に入っているアドレスを
EU1.1へそのままコピーしてはいけない。

### 3.3 Generated tree separation

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

## 4. mphCodexで確認済みのEU1.1差分例

AllVersions調査ではEU1.1に次の対応が確認されている。

| Semantic | US1.0 | EU1.1 |
|---|---:|---:|
| Current Camera Sequence | `0x020D9CB0` | `0x020DA5D0` |
| Game Mode | `0x020E78FC` | `0x020E845C` |
| Upper HUD function | `0x0202F600` | `0x0202F5E0` |
| Crosshair callsite | `0x0202F934` | `0x0202F904` |
| Crosshair renderer | `0x020393D4` | `0x02039338` |
| Local Player Pointer | `0x020BCA70` | `0x020BD370` |
| HUD suppression storage | `0x020DE748` | `0x020DF068` |

重要なのは、差分が単一の固定deltaではないことである。

したがって今後のtitle patch / enhancementは、

```text
US1.0 address + region offset
```

ではなく、

```text
ROM identity -> semantic runtime profile -> exact address
```

で管理する。

## 5. 現時点でEU1.1へ有効化しない機能

### 5.1 Prime Controls / Morph state

pinned `ndsrecomp` runnerのPrime ControlsにはUS1.0専用の

```text
0x020DA818
```

が直接使われている。

EU1.1側の同semanticアドレスを確認するまでは無効のままにする。

### 5.2 Direct Mouse Aim

`runner/src/title_patches.cpp` のDirect Mouse AimにはUS1.0専用の

```text
Aim X: 0x020DE526
Aim Y: 0x020DE52E
```

が使われている。

これもEU1.1 mapping完了前には有効化しない。

### 5.3 USA FMV runtime bank

US1.0の

```text
config/mph_arm9_fmv_runtime.toml
generated/capture/mph_arm9_fmv_runtime.bin
```

はUS1.0のruntime bytesとobserved PCsに対するbankである。

EU1.1では `fmv_runtime=false` とし、絶対に登録しない。

EU1.1のFMV高速化はEU1.1実行から独立captureを作成した後に行う。

### 5.4 Launcherのsupported-ROM list

recomp-ui launcherのsupported SHA-1配列にはまだEU1.1を追加しない。

理由は、launcherがPrime Controls等を通常のplayer-facing featureとして有効化する
経路を持つためである。

EU1.1の基本bootとruntime profileが検証されるまで「正式対応」と表示しない。

## 6. Build

### Windows bring-up

EU1.1 ROMをrepo rootの

```text
Metroid Prime Hunters.nds
```

として配置した上で:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  tools\build-windows.ps1 `
  -MphVersion EU1_1
```

EU1.1ではtitle bankとrunnerまでをbuildし、launcher/release packagingは
意図的にskipする。

revision-specific runtime config:

```text
config/game-eu11.toml
```

### Linux bring-up

```bash
tools/build-linux.sh --mph-version EU1_1 --no-package
```

AppImage生成まで行う場合:

```bash
tools/build-linux.sh --mph-version EU1_1
```

package内の `game.toml` は `config/game-eu11.toml` から生成する。

## 7. ROMが手元にある段階で行う次工程

### Gate A - extraction / static bank

1. `prepare_mph.py` がEU1.1 identityをacceptする。
2. ARM9を正しくdecompressする。
3. ARM7を抽出する。
4. overlay tableを列挙する。
5. `generated/EU1_1/recomp/` にEU1.1専用bankを生成する。
6. US1.0 artifactを一切参照していないことを確認する。

### Gate B - interpreter bootstrap

EU1.1専用bankをexact SHA-1 gateでrunnerへ登録し、

- firmware boot
- cartridge handoff
- opening logos
- FMV
- title screen

まで進むか確認する。

最初から高static coverageを要求しない。
missはInterpreterへ落として正しさを優先する。

### Gate C - deterministic coverage

EU1.1で実行したtraceから、

- immutable ARM9 main-image call target
- immutable ARM9 main-image indirect target
- ARM7 main-image target

のみを抽出し、

```text
coverage/eu11-main-entry-points.json
```

へ昇格する。

US1.0のPCをアドレス変換して生成してはいけない。

### Gate D - FMV runtime bank

EU1.1自身からITCM + main RAM captureを作り、

- capture SHA-1
- live-byte validation
- observed call / indirect roots

をEU1.1専用configへ固定する。

### Gate E - runtime semantic profile

mphCodexを使い、

- morph state
- aim X/Y
- local player
- game mode
- HUD / camera state
- Scan Visor state
- Adventure camera state

をEU1.1へ対応させる。

ここまで完了して初めてPrime Controls / Direct Mouse Aim / adaptive HUD等を
EU1.1に段階的に解禁する。

## 8. 完了条件

EU1.1を「supported」とする条件は最低でも以下。

- exact EU1.1 ROM identity gate
- EU1.1 main ARM9 bank
- EU1.1 ARM7 bank
- interpreter fallbackでterminal dispatch missなし
- title到達
- Adventure gameplay到達
- save/load確認
- pause/reload確認
- title patchがUS1.0 addressを参照しない
- Prime Controls動作確認
- Direct Mouse Aim動作確認
- native/reference checkpoint比較
- US1.0 regressionなし

現時点の実装は、このうちROM実体なしで先に安全に整備できる
**profile / extraction / bank isolation / bootstrap build infrastructure**
までを対象とする。
