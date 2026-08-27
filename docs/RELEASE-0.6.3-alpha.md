# Metroid Prime Hunters Recomp v0.6.3-alpha

Performance patch. No new features; no gameplay or behavior changes.

## Less dispatch overhead, especially for lower-end machines

Two structural changes to how the recompiled code banks are generated:

1. **Superblock coalescing** for the main ARM9/ARM7 code banks and the ARM7
   alias banks: thousands of artificial "hand back to the dispatcher" seams
   between adjacent functions become plain jumps (17,000+ merged on ARM9,
   3,200 across the whole ARM7 module).
2. The whole-module ARM7 bank now takes **registration priority** over the
   per-page fallback banks inside its window, which is what makes the ARM7
   half of (1) effective.

Measured effect: **ARM7 dispatcher traffic drops ~26% in gameplay and ~59%
during boot** (the artificial fallthrough class drops 33-87%). On a fast
development machine this reads as a 2-4% emulation-time saving; on machines
where busy scenes push frame time over the 60 FPS budget - which the field
diagnostics show are dispatch-bound - the same cut applies to a much larger
share of the frame. If v0.6.2 still dropped frames for you in busy scenes,
please test this build and send a new diagnostic either way.

The runner binary is also **~16% smaller** than v0.6.2.

Correctness is unchanged and proven: guest state (both screens, both CPUs'
full register files, all event counters) verified byte-identical against
v0.6.2 at seven 100-million-instruction checkpoints, and the 2,400-frame
audio soak reproduces the exact reference fingerprint with zero underruns.

Everything else is v0.6.2-alpha.
