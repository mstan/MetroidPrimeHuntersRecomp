# Metroid Prime Hunters Recomp v0.6.6-alpha

Performance release targeting the reported enemy-area slowdown, plus an
emulation-timing correctness fix and a lower default mouse-aim sensitivity.

## The enemy-area slowdown fix

v0.6.5 diagnostics from the field pinned the slowdown precisely: in busy
scenes, large stretches of game code were executing through leftover
two-instruction fragments instead of the real compiled functions, paying a
full dispatcher round-trip every couple of instructions. On the reporting
machine, dispatcher traffic tripled (13k to 45k round-trips per frame) exactly
in the slow rooms.

Fixed two ways, together:

1. **The dispatcher now picks the best code, not the newest.** When several
   compiled banks validly claim the same address, the one covering the largest
   verified span wins. Previously the last-registered bank won, which let the
   fragments shadow full functions.
2. **~122,000 redundant fragment entries are gone from the shipped banks**
   entirely, pruned at generation time.

Measured on dev hardware (which never dips): ARM9 dispatcher traffic **-20%**,
emulation time **-3%** on the standard route — and the same fix cut ARM7
dispatcher traffic ~76% in local multiplayer. On machines that actually dip in
enemy rooms the effect should be much larger; that is exactly what we ask you
to test. **Play the rooms that slowed down before and send a diagnostic bundle
either way.**

## The last interpreted code is now compiled

Code the static analysis could never find (reached only through computed
jumps) ran in an interpreter and showed up as background cost. Those regions
are now discovered from field diagnostics and compiled: on our test route the
interpreter's work dropped from ~128k instructions per interval to **zero**.

## Emulation timing fix

A halted ARM7 could wake up to one scheduling round early, drifting the whole
ARM7 timeline from real-hardware behavior (audible as subtle audio
divergence). Fixed at the root; our firmware-accuracy gate went from 0/8
scenarios passing to 6/8 (the remaining two share a separate, known cause).

## Lower default mouse-aim sensitivity

The default Prime-controls mouse aim sensitivity drops from 0.20x to
**0.13x** (a new selectable step). If you are on the old 0.20x default your
setting migrates automatically; if you chose a custom value it is left alone.

## Housekeeping

- Prebuilt shard cache: still not shipped (see v0.6.5 notes) - and with this
  release's fixes the on-device compiler also has almost nothing left to do.
  Copied `live-shard-cache` folders from older installs keep working.
- Cache identity no longer invalidates on toolchain rebuilds, so future
  releases can carry prebuilt caches forward when there is one worth carrying.

## Versions

- Game: v0.6.6-alpha
- Framework pin: 04edcb7 (dispatch ranking + capture-bank pruning +
  interpreted-span promotion + ARM7 halt-wake fix + shard identity rework)
- Banks: 251 shipped (ARM9 capture banks pruned; +339 field-derived seeds)
