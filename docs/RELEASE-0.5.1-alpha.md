# Metroid Prime Hunters Recomp v0.5.1-alpha

Performance-focused re-cut. If you saw lower FPS on v0.4.12 through v0.5.0
than on v0.4.11, this release is for you — please retest and report.

## Fixed: v0.4.12–v0.5.0 shipped without 63 recompiled code banks

Releases v0.4.12, v0.4.13, and v0.5.0 were built from a checkout missing the
63 player-coverage code banks that v0.4.10/v0.4.11 introduced, and the build
system skipped them silently. All the game code those banks cover ran on the
(slow) interpreter instead of natively — a direct performance regression for
campaign and multiplayer content, hitting lower-end machines hardest.

This can no longer happen: the release pipeline now verifies the complete
bank inventory inside the runner binary and refuses to package an incomplete
build. Every release ships with an auditable `bank-manifest.txt` listing the
banks compiled in (this release: 81).

## New: ARM7 code now runs natively (two alias banks)

The game relocates its ARM7 module at boot and executes it from two
addresses no bank previously covered, so essentially all ARM7 work
(audio/system co-processor) ran on the interpreter — billions of interpreted
instructions per play session, measured from player-submitted coverage.
The module is now recompiled at both runtime addresses, seeded with 2,690
entry points merged from eleven player coverage submissions. On the
automated benchmark, ARM7 interpreter execution drops to zero in every
measured phase.

## New: performance benchmark harness

`tools/measure_mph_scenario.py` measures reproducible routes (attract/FMV,
campaign entry) with per-phase FPS, emulation ms/frame, audio underruns, and
interpreter-fallback counts; `docs/performance_baseline.md` pins this
release's baseline. Future performance work lands with before/after numbers.

## Notes

- No gameplay/code changes otherwise; this is v0.5.0 plus bank completeness,
  the ARM7 alias banks, and build/packaging integrity.
- The runner still writes optional coverage manifests; submitting them after
  playing (especially areas that feel slow) directly drives what gets
  recompiled next.
