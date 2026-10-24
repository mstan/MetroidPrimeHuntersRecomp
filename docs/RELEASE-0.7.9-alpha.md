# Metroid Prime Hunters v0.7.9-alpha (Windows)

Integrates the retained shared ndsrecomp host-work improvements into main:
reduced unarmed diagnostic work, immutable graphics capture reuse, MPH native
math/submission HLE and guarded geometry-command/projection reuse. Keeps the
native OpenGL presenter, Prime Controls, adaptive display, full declared bank
inventory and live-overlay toolchain.

The MKDS-specific native CPU backend is not enabled for MPH. MKDS's new race
result is not an MPH speedup claim. Existing v0.7.8 matched older-host and owner
gameplay evidence is reused, supplemented by focused artifact checks.
Native saves remain supported; snapshots are build-specific. Live Wiimmfi
was not retested and remains experimental/unverified for this update.
