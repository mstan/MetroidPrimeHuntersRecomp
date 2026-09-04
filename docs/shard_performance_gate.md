# MPH shard validation release gate

`tools/shard_performance_gate.py` is the acceptance test for the player-facing
shard policy. A DLL/SO count is not evidence of acceleration. A release cache
passes only when the exact packaged runner loads the prebuilt cache, records
native hits on the committed bot-match route, and proves the bundled runtime
TCC path can produce and hit a shard from a cold cache.

The release gate is intentionally small: two fresh processes, one cold
runtime-TCC run and one warm prebuilt-GCC cache run. The broader four-mode
matrix in `tools/shard_performance_gate.py run` is a diagnostic tool, not the
release path.

## Windows field gate

First build an unarchived candidate. It contains the exact runner, selected
cache projection, and bundled TCC toolchain, but cannot produce a release ZIP:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build-windows.ps1 `
  -Version 0.6.10 -StageForShardPerformanceGate
```

Then run the basic release gate. Use `mp_bots_blank` when no calibrated profile
save is available. ROM, BIOS, saves, and output stay outside Git.

```powershell
$candidate = 'release-stage\MetroidPrimeHuntersRecomp-windows-x64-v0.6.10'
py -3 tools\shard_performance_gate.py basic `
  --runner "$candidate\nds_runner.exe" `
  --bios ..\ndsrecomp\bios `
  --rom 'Metroid Prime Hunters.nds' `
  --config "$candidate\game.toml" `
  --prebuilt-cache "$candidate\live-shard-cache" `
  --route mp_bots_blank `
  --output perf-results\0.6.10-shard-basic-gate
Copy-Item perf-results\0.6.10-shard-basic-gate\basic-validation.json `
  release-shard-cache\performance-gate.json
```

The default `--runtime-tcc-command @bundled` exercises the packaged toolchain
beside `nds_runner.exe`. Do not substitute a developer GCC command for that
leg. A nonzero exit means the release candidate failed.

Package only after the gate passes. The packager verifies both the runner hash
and native shard inventory hash, so a rebuilt runner or changed cache requires
a new field run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build-windows.ps1 `
  -Version 0.6.10 `
  -ShardPerformanceGate release-shard-cache\performance-gate.json
```

## Linux field gate

The Linux flow is equivalent and produces a persistent candidate directory:

```bash
bash tools/build-linux.sh --version 0.6.10 \
  --stage-for-shard-performance-gate
candidate=release-linux/shard-performance-candidate/usr/bin
python3 tools/shard_performance_gate.py basic \
  --runner "$candidate/nds_runner" --bios ../ndsrecomp/bios \
  --rom 'Metroid Prime Hunters.nds' --config "$candidate/game.toml" \
  --prebuilt-cache "$candidate/prebuilt-live-shard-cache" \
  --route mp_bots_blank \
  --output perf-results/0.6.10-linux-shard-basic-gate
cp perf-results/0.6.10-linux-shard-basic-gate/basic-validation.json \
  release-shard-cache-linux/performance-gate.json
bash tools/build-linux.sh --version 0.6.10 \
  --shard-performance-gate \
  release-shard-cache-linux/performance-gate.json
```

Run the Windows and Linux gates separately. Native shard binaries and runner
hashes are platform-specific; a Windows pass cannot authorize an AppImage.

## Kanden gate

The bot route is the immediate release gate because it is committed and
automatable. Kanden campaign combat remains a second required field scenario
once the full save-state route exists. Do not relabel bot-route results as
Kanden coverage.
