# MPH shard performance release gate

`tools/shard_performance_gate.py` is the acceptance test for the player-facing
shard policy. A DLL/SO count is not evidence of acceleration. A release cache
passes only when the exact packaged runner loads it and records native hits on
the committed bot-match route.

## Controlled matrix

Each repetition is a fresh process and gets one of four isolated cache states:

1. overlay disabled;
2. overlay enabled, empty cache, no compiler;
3. a fresh copy of the exact prebuilt GCC cache being packaged;
4. overlay enabled with runtime TCC and a fresh empty cache.

The driver rotates leg order between repetitions. The evaluator rejects a
matrix unless executable, ROM, config, save, framework revision, title
revision, renderer settings, host, route actions, and phase landmarks match.
Do not combine diagnostics from different releases or different gameplay
sessions. Dispatch-band summaries are supporting controls, not a license to
compare unmatched routes.

The report includes emulation and overlay-poll milliseconds per frame, ARM9
and ARM7 execution attribution, Tier-3 instruction counts, native hits,
loaded/registered banks, dispatch rates, and CRS hit/miss rates. Runtime TCC
may hitch during compilation, but it must be idle, drained, registered, and
receiving native hits by the final steady phase.

## Windows field gate

First build an unarchived candidate. It contains the exact runner, selected
cache projection, and bundled TCC toolchain, but cannot produce a release ZIP:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build-windows.ps1 `
  -Version 0.6.9-alpha -StageForShardPerformanceGate
```

Then run the matrix. Use `mp_bots_blank` when no calibrated profile save is
available. ROM, BIOS, saves, and output stay outside Git.

```powershell
$candidate = 'release-stage\MetroidPrimeHuntersRecomp-windows-x64-v0.6.9-alpha'
py -3 tools\shard_performance_gate.py run `
  --runner "$candidate\nds_runner.exe" `
  --bios ..\ndsrecomp\bios `
  --rom 'Metroid Prime Hunters.nds' `
  --config "$candidate\game.toml" `
  --prebuilt-cache "$candidate\live-shard-cache" `
  --route mp_bots_blank --repetitions 3 `
  --output perf-results\0.6.9-shard-field-gate
Copy-Item perf-results\0.6.9-shard-field-gate\performance-gate.json `
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
  -Version 0.6.9-alpha `
  -ShardPerformanceGate release-shard-cache\performance-gate.json
```

## Linux field gate

The Linux flow is equivalent and produces a persistent candidate directory:

```bash
bash tools/build-linux.sh --version 0.6.9-alpha \
  --stage-for-shard-performance-gate
candidate=release-linux/shard-performance-candidate/usr/bin
python3 tools/shard_performance_gate.py run \
  --runner "$candidate/nds_runner" --bios ../ndsrecomp/bios \
  --rom 'Metroid Prime Hunters.nds' --config "$candidate/game.toml" \
  --prebuilt-cache "$candidate/prebuilt-live-shard-cache" \
  --route mp_bots_blank --repetitions 3 \
  --output perf-results/0.6.9-linux-shard-field-gate
cp perf-results/0.6.9-linux-shard-field-gate/performance-gate.json \
  release-shard-cache-linux/performance-gate.json
bash tools/build-linux.sh --version 0.6.9-alpha \
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
