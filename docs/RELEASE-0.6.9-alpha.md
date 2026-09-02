# Metroid Prime Hunters Recomp v0.6.9-alpha

The performance release for machines that dip. v0.6.6 fixed the *guest*-side
cost of busy scenes; this one fixes the *host*-side cost that was left, and it
is the larger of the two on hardware that cannot already hold 60.

## The root cause

An always-on host CPU sampler was added to the runner and pointed at the
Kanden campaign fight — the worst scene we have. It said the emulation thread
was not spending its time emulating. It was spending it on **bookkeeping that
surrounded** the emulation: cycle-accounting helper calls made once per
retired instruction and once per transferred register, and a full second 2D
compositor pass run inline on the same thread that runs the scheduler.

That is why the slowdown never showed up in guest-side coverage work. There
was nothing left to compile; the cost was in the host.

## The four fixes

1. **Per-instruction code-fetch cost is now emitted inline.** The recompiler
   folds the code-fetch cycle term directly into generated code instead of
   calling back into the runner's bus for every retired instruction. (This is
   what moves the recompiler to codegen version 3 — see the upgrade note.)
2. **Memory accesses are timed in one fused operation.** The access and its
   cycle cost were two separate trips through the bus, once per transferred
   register; an `LDM` of 12 registers paid it 12 times. They are now one.
3. **CP15 cacheability is a page bitmap.** The data-cache region walk that ran
   on every access became a single bitmap lookup.
4. **The 2D compositor moved off the emulation thread.** Two distinct problems
   here. The scanline worker pool shipped in v0.6.4 was never actually
   switched on — 192 lines a frame were rendered inline — and it is now on by
   default. Separately, the adaptive/widescreen compositor (a second, complete
   2D pass, ~86k pixels per screen at internal resolution 2) was never
   threaded at all; it now runs across a band pool, bit-exact by construction
   because every write it performs is indexed by its own scanline.

## Measured

Interleaved A/B on the pinned Kanden fight savestate, same route, same
savestate, alternating legs, on a quiet box.

**At 50% host CPU clock** — the throttled configuration that stands in for a
slower machine:

| | fps (median) | emu ms/frame | audio underruns |
| --- | --- | --- | --- |
| v0.6.8 framework | 46.1 / 46.3 | 19.06 / 19.03 | 3435 / 3423 |
| v0.6.9 framework | **59.8 / 59.7** | **14.72 / 14.72** | 79 / 306 |

**At 100% clock**, both legs sit on the 60 fps cap, so fps cannot show the
win; the frame breakdown can. Pooled over four paired legs, 60 samples a side:

| metric | delta |
| --- | --- |
| emulation ms/frame | **-14.5%** (9.13 -> 7.81) |
| presentation ms/frame | **-36.9%** (1.16 -> 0.73) |
| adaptive compositor ms/frame | **-65%** (0.68 -> 0.24) |
| idle headroom per frame | +1.82 ms |

Direction was consistent in four of four paired legs on all three metrics.
Guest behaviour is unchanged: the presented-frame digest ring is identical
between the serial and threaded 2D paths.

## New: the performance governor

If the emulation thread cannot hold the frame budget, the runner now trades
visual work for frame rate on its own, in two stages, and gives it back when
the pressure is gone (`--performance-governor auto|off|stage1|stage2`, or
`NDS_PERFORMANCE_GOVERNOR`; default `auto`).

- **Stage 0** — nothing changed. This is what a machine that holds 60 stays
  on, and it is byte-for-byte the old behaviour.
- **Stage 1** — the host display's 3D readback is allowed to run a frame
  behind. Worth ~1.4-1.5 ms/frame on the emulation thread (~16%). Guest-
  visible display capture is unaffected; it still forces the same-frame path.
- **Stage 2** — additionally drops the runtime internal scale to 1x and skips
  the supersample/AA presentation pass.

On dev hardware at full clock the governor stays at stage 0 for the whole
fight with zero transitions, i.e. it is inert when it should be. At 50% clock
it engages within the first frames and holds stage 2.

## New: stale shard quarantine

Because the recompiler's codegen version moved to 3, every shard in a
`live-shard-cache` copied from v0.6.8 or earlier was produced by a different
code generator and must not be loaded. Rather than fail, the runner now
**quarantines** them: a shard whose producer codegen version is not exactly
the running runner's is refused as a whole bank, its DLL is moved to
`live-shard-cache/quarantine/nds-codegen-vN`, and the addresses it covered
fall back to Tier 3 where the live compiler rebuilds them under the current
identity. The rejection is counted and logged per bank
(`load_codegen_mismatch`), so a diagnostic bundle shows exactly what happened.

**Upgrade note:** you do not have to do anything. Copy your old
`live-shard-cache` across or don't — either way the stale shards are set aside
automatically and rebuilt. This is the first release where that is true; in
earlier releases a stale cache had to be deleted by hand.

## New: always-on host CPU sampler

The sampler that found the root cause above is **always on**, in the shipped
Release binary, including this one. It is a ring buffer: it records
continuously from process start and is dumped on request, so a diagnostic
bundle from a machine that dipped contains the window that dipped rather than
whatever happened after someone thought to start recording. Per-thread roles
are tagged (emulation, render, and both 2D pools), so work that moves between
threads stays visible instead of vanishing.

The performance log (`performance-*.jsonl` in a diagnostic bundle) now also
carries per-frame `governor` records and `hostprof` records alongside the
existing frame timing.

## Known issues

- **Savestates from earlier builds will not load.** Savestates are locked to
  the exact runner build that wrote them, and this release is a different
  build, so every v0.6.8 savestate is refused with a build-id mismatch
  notice. Your battery save (`.sav`) is unaffected — only the 12 savestate
  slots. This is tracked as **beads-yjp.66**; the format needs a real
  migration story before the next release strands another set.
- **Rare audio underrun bursts at full clock on threaded 2D.** Not
  reproducible on demand and not present in the paired A/B medians, but seen.
  If you hear intermittent crackle, a diagnostic bundle is the useful thing
  to send. Watch item, not a known regression.
- **Other titles on this framework:** the same framework change set has an
  open 21:9 regression on Mario Kart DS (**beads-q4q.5**) and edge culling
  glitches on Super Mario 64 DS (**beads-1z8.2**). Neither is part of this
  Prime Hunters release and neither reproduces here.

## Versions

- Game: v0.6.9-alpha
- Framework pin: 31a2675 (host CPU sampler, inline code-fetch cycles, fused
  timed memory access + CP15 page bitmap, threaded 2D compositor, performance
  governor, live-shard codegen quarantine)
- Recompiler: `arm-recomp-core` 705e71b, codegen version 3
- Banks: 251 shipped (249 declared + the two main closures; composition
  unchanged from v0.6.8, regenerated under codegen v3)
