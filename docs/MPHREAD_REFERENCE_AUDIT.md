# MphRead Reference Audit

Reference: https://github.com/NoneGiven/MphRead

Pinned reference in `game.toml`: `26cd8a6fe93dc5e525d1a1bb304fe96001111e55`

MphRead is an MIT-licensed Metroid Prime Hunters recreation, renderer, model
viewer, parser, and exporter. It is useful as a semantic reference for MPH file
formats and game behavior. It is not a DS GPU pixel oracle and should not be
treated as a drop-in replacement for the recomp renderer.

## What We Can Use

- Archive and extraction knowledge: NDS filesystem extraction, LZ10 handling,
  and the MPH `SNDFILE` `.arc` layout.
- MPH file format knowledge: room metadata, model/material/texture parsing,
  entity layer formats, `wc01` collision, node data, and save/settings layout.
- Rendering semantics: texture alpha classification, DS clamp/repeat/mirror
  mapping, material alpha behavior, texture filtering choices, decal and
  translucent pass ordering, and HUD layer composition ideas.
- Room visibility semantics: portal traversal, room-part node references,
  per-node frustum tests, audible/visible room state, and places where entity
  logic depends on room visibility instead of only mesh drawing.
- Dev tooling: exports for room/model/texture inspection, useful for comparing
  expected placement, material behavior, and room contents against recomp
  captures.

## Repo Boundary

Shared `ndsrecomp` work should own generic DS or cross-title infrastructure:

- ROM filesystem extraction and extracted-root conventions.
- Generic compression/archive plumbing where the format is not MPH-specific.
- Renderer settings and diagnostics that apply to any title.
- Presentation behavior such as aspect preservation and renderer selection.
- Generic validation harnesses for comparing native framebuffer output,
  direct OpenGL presentation, and software fallback.

MetroidPrimeHuntersRecomp should own title-specific behavior:

- The AMHE0 MphRead pin and attribution.
- MPH room manifests, entity structs, collision interpretation, and room
  visibility research.
- MPH widescreen/culling patches and scene classifiers.
- Issue #30 triage, tester-facing release notes, and MPH-specific repro routes.

## Issue #30 Triage

The report should be treated as several separate items:

- AMD/Linux black 3D output in third-person or morph ball is actionable. First
  determine whether the native framebuffer is black or only the direct OpenGL
  presentation is black.
- Aspect lock feedback is valid for the direct presenter. Current ndsrecomp
  code letterboxes native-width frames and fills widened adaptive frames; any
  future stretch option should be explicit, not default.
- Supersampling feedback is partly valid. The old presentation supersampling
  scales already-rasterized native pixels. Internal 3D resolution is the setting
  that increases 3D sample density, and the UI/docs should keep those concepts
  separate.
- Resource-use feedback needs diagnostics, not debate. Compare guest execution,
  3D renderer, 2D composition, upload, draw, swap, and software fallback.
- Controls feedback may be stale relative to current releases, but future
  sensitivity and "native input" work should be framed as host input mapped into
  guest behavior unless a real game-code input replacement is implemented.

## Attribution Policy

MphRead is MIT licensed. If code is copied or adapted, include the upstream MIT
license text in the relevant third-party notice and add a source comment such
as:

`Portions adapted from MphRead by NoneGiven, MIT License.`

If MphRead is only consulted as a behavioral/file-format reference, credit it in
README/docs and keep the pinned commit in `game.toml`.
