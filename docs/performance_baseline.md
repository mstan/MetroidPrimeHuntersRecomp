# MPH performance baseline

Date: 2026-08-25
Host: Intel Core i9-9900K, Windows 10 19045
Target: MetroidPrimeHuntersRecomp `d325004` (v0.5.0) + perf-worktree bank
completeness fixes; framework ndsrecomp `a4a6f9e`.

This is a measurement baseline, not an optimization conclusion. It exists so
every optimization ships with before/after numbers (beads-fly).

## Harness

`tools/measure_mph_scenario.py` (new this date; generic machinery shared in
ndsrecomp `tools/scenario_bench.py`, mirroring the SM64DS
`measure_sm64ds_scenario.py` discipline): fresh-process repetitions, routes
replayed from `scenarios/*.json` over the debug TCP surface, phases anchored
to guest VBlank windows (attract) and cumulative ARM9 instruction counts
(gameplay) so guest work is invariant as builds get faster. Per phase it
records FPS, `phase_ms_per_frame` {emu, present, audio_drain}, audio
underruns, Tier-3 deltas (`static_coverage`), and dispatch-composition deltas
(`dispatch_stats`). Boot mode is `direct` — LLE firmware boot currently hangs
on MPH builds (beads-lqa.35).

Routes measured: `attract` (boot → title/FMV, seven 600-VBlank windows) and
`adventure` (scripted 13-step navigation into Celestial Archives gameplay:
settle, walk, steady phases at 5M/40M/125M cumulative insn9). Story
progression beyond this is not automatable (owner call, 2026-08-25); the
deeper benchmark route is multiplayer-vs-bots (stand/walk), pending save
calibration.

## Binaries compared

- **shipped-050**: the published v0.5.0-alpha runner
  (`build-mph-release-050`, SHA-256 `c39781dc…`), which shipped with **0 of
  63 coverage banks** (beads-lqa.33).
- **banked**: identical v0.5.0 code rebuilt with all 67 bank capture images
  present (`build-mph-perf-banked`, SHA-256 `5246f3e5…`, 169,309,087 bytes),
  banks still at `-O0` like every release to date.

## Canonical result (3 fresh-process reps, medians)

Adventure route:

| Phase | banked FPS / emu ms | shipped-050 FPS / emu ms | t3 insns9 (banked/050) |
|---|---|---|---|
| adventure_settle | 59.04 / 5.14 | 59.38 / 4.98 | 9.6k / 9.9k |
| adventure_walk | 59.74 / 5.44 | 59.75 / 5.46 | 71.6k / 70.6k |
| adventure_steady | 59.86 / 6.73 | 59.76 / 6.62 | 183.1k / 183.4k |

Attract route (banked → 050 medians): boot 55.02/54.86 FPS at ~4.9 ms; all
six title/FMV windows 59.4–59.9 FPS at 4.9–11.5 ms emu. Zero audio underruns
in every phase of every rep, both binaries.

## Load-bearing observations

1. **On this host, both binaries hold ~60 FPS with 5–11 ms emu/frame** on
   the automatable routes. The user-reported 30–40 FPS (GitHub #21,
   beads-lqa.23) does not reproduce here in early campaign/attract —
   consistent with the affected population being lower-end hosts and/or
   deeper content (first artifact, multiplayer), where per-frame emu cost
   crosses their 16.7 ms budget even though it is ~5–7 ms here.
2. **The 63 coverage banks are not exercised on these early routes**:
   Tier-3 deltas are near-identical banked vs 050 (they originate from
   player sessions deeper in campaign and in multiplayer). Their impact must
   be shown on the mp-bots route once calibrated. The bank regression fix is
   correct regardless (shipped code must include all declared banks).
3. Residual Tier-3 on these routes is small but nonzero (9.6k–213k ARM9
   insns per phase window) — closure candidates once the mp-bots route is
   calibrated.
4. attract_boot presents ~55 FPS (pacing, not emu cost — emu is 4.9 ms);
   the 2400–4200 VBlank FMV windows are the emu-heaviest at 9.3–11.5 ms.

## Reproduction

```powershell
# from metroidprimehuntersrecomp-mph-perf
py -3 tools/measure_mph_scenario.py --route adventure --repetitions 3 --exe <exe> --tag <tag>
py -3 tools/measure_mph_scenario.py --route attract   --repetitions 3 --exe <exe> --tag <tag>
# worst-phase RIP profile
py -3 tools/profile_mph_worst_phase.py --route attract --phase attract_3000_3600 --exe <exe>
```

Artifacts: `perf-results/baseline-{adventure,attract}-{banked,050}/`
(report.json per leg; run logs and screenshots alongside).

## Ledger

- 2026-08-25 **bank completeness** (beads-lqa.33): v0.4.12+/v0.5.0 shipped
  0/63 coverage banks; rebuilt complete; release pipeline now hard-gates
  inventory at packaging (verify_bank_inventory) with strict-configure for
  releases. Early-route timing impact on this host: none measurable (see
  observation 2); correctness/coverage fix, not yet a measured perf win.
- 2026-08-25 **-O2 generated banks**: DISPROVED as a new optimization — the
  runner has always compiled title bank sources at `-O2`
  (`ndsrecomp/runner/CMakeLists.txt` hardcodes `-w;-O2;-g0` on
  `TITLE_BANK_SOURCES`; shipped v0.5.0 build.ninja confirms). The famous
  "-O0" applies only to the MPH project's standalone compile-validation
  static lib, which nothing links (BRINGUP.md:75 was misleading). No A/B
  run — the candidate and baseline binaries contain identical code.
  `MPH_BANK_OPT_LEVEL` cache var added to the validation lib for
  consistency.
- 2026-08-25 **ARM7 alias banks + seed refresh** (beads-lqa.9): in
  progress — recompile arm7.bin at the two observed runtime bases
  (0x037F7E50 WRAM, 0x027CFBC4 main RAM; 1,988 + 702 ingested entry
  targets from 11 player manifests).
