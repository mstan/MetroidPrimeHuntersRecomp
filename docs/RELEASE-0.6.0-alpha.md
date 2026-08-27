# Metroid Prime Hunters Recomp v0.6.0-alpha

Two headline changes on top of v0.5.2: the game now recompiles its own
overlay code while you play (tier-2 live overlays), and the whole runtime
moved to SDL3.

## New: tier-2 live overlays — the game recompiles itself as you play

Previously, code the game copies to RAM at runtime (overlays) could only be
covered by banks a developer had recompiled ahead of time from submitted
coverage. Anything not yet covered ran on the interpreter.

This release ships a real compiler with the game:

- **Bundled toolchain** (`overlay_toolchain/`, ~25 MB): an embedded CPython
  3.13.1 and TinyCC 0.9.27, SHA256-pinned, plus the recompiler and the
  runtime headers shards compile against. Nothing to install.
- **Prebuilt native cache** (`live-shard-cache/`): a gcc-optimized shard
  cache warmed by the developer over the benchmark routes and filtered to
  the exact provider identity of the shipped binaries, so common areas run
  native from the very first visit rather than being compiled on demand.
  A `shard-manifest.txt` lists what shipped; the release pipeline refuses
  to package a cache that does not match the shipped artifacts.
- **Background compilation**: uncovered overlay pages you actually execute
  are compiled with the bundled TinyCC in the background and hot-loaded.
  The first visit to a new area is interpreted; subsequent visits are not.

Hardening that landed with it: shard ABI checking (a shard built for a
different runner ABI is rejected rather than loaded), a reset guard, a
compile-thread pin, a locked shard index, and a *futility guard* — if a
compile run publishes shards and every newly examined one is rejected, the
runner logs one loud diagnostic naming the cause and stops re-running,
instead of burning a compile every cooldown forever.

The launcher's live-overlay wiring is now a single gate: if the bundled
`overlay_toolchain/` is present it always wins, the cache always sits at
`<game>/live-shard-cache`, and the runner synthesizes its own compile
command. Developer overrides are explicit opt-in
(`NDS_LIVE_OVERLAY_COMMAND` / `NDS_LIVE_OVERLAY_CACHE`).

## Changed: SDL3 is now the default frontend

Both the runner and the launcher build against SDL3 (only `SDL3.dll`
ships; `SDL2.dll` is gone from the package). SDL2 remains a supported
compatibility backend for anyone building from source
(`-DNDS_SDL_BACKEND=SDL2`, `-DMPH_LAUNCHER_SDL_BACKEND=SDL2`).

What this means in practice:

- Audio now goes through `SDL_AudioStream` instead of an SDL2 callback ring
  buffer. Same 32,768 Hz stereo path, same underrun accounting.
- Gamepads use SDL3's gamepad API, which generally means better controller
  detection and a larger built-in mapping database.
- Mouse/touch coordinates are converted through the renderer's logical
  presentation explicitly, and integer scaling is expressed as SDL3's
  `SDL_LOGICAL_PRESENTATION_INTEGER_SCALE`.
- Exclusive fullscreen currently maps to SDL3's fullscreen window state;
  true display-mode switching can be added later if a title needs it.

There is no intentional change to anything the game itself can observe —
guest timing, input sampling cadence, and the emulated hardware are
untouched, and the deterministic frame hashes are unchanged from v0.5.2.

## Carried forward from v0.5.2

### Frame Interpolation mod (experimental)

For 120 Hz+ displays: an opt-in mod on the Mods page that presents one
blended frame between finished DS frames, smoothing perceived motion.
Presentation-only — game logic, timing, input sampling, audio, and
multiplayer are completely unaffected. Off by default.

**Known limitation: does not work in split-screen (separate window) mode
with the OpenGL renderer** — that presenter draws the top screen directly
and needs an offscreen-texture refactor before frames can be blended
(planned). It also stays inert on 60 Hz displays. To use it today, switch
to the stacked screen layout, or select the Software renderer. Expect
slight ghosting on fast motion — that's inherent to blending; real motion
interpolation would need renderer-side motion data. Feedback welcome
(issue #32).

The refresh-rate gate now reads SDL3's floating-point refresh rate and
rounds to whole Hz, so the >= 100 Hz activation threshold behaves exactly
as it did under SDL2.

### Bank completeness

Releases v0.4.12, v0.4.13, and v0.5.0 were built from a checkout missing
the 63 player-coverage code banks that v0.4.10/v0.4.11 introduced, and the
build system skipped them silently. The release pipeline now verifies the
complete bank inventory inside the runner binary and refuses to package an
incomplete build. Every release ships with an auditable
`bank-manifest.txt` listing the banks compiled in (this release: 81).

### ARM7 code runs natively (two alias banks)

The game relocates its ARM7 module at boot and executes it from two
addresses no bank previously covered, so essentially all ARM7 work
(audio/system co-processor) ran on the interpreter. The module is now
recompiled at both runtime addresses, seeded with 2,690 entry points
merged from eleven player coverage submissions. On the automated
benchmark, ARM7 interpreter execution drops to zero in every measured
phase.

### Performance benchmark harness

`tools/measure_mph_scenario.py` measures reproducible routes (attract/FMV,
campaign entry) with per-phase FPS, emulation ms/frame, audio underruns,
and interpreter-fallback counts; `docs/performance_baseline.md` pins the
baseline.

## Notes

- The runner still writes optional coverage manifests; submitting them
  after playing (especially areas that feel slow) still drives what gets
  recompiled ahead of time. Live overlays reduce how much that matters,
  but a gcc-optimized prebuilt bank still beats an on-the-fly tcc shard.
- Known follow-up: the first player session can redundantly recompile
  pages already covered by the bundled cache (beads-yjp.29.2).
