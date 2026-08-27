# Metroid Prime Hunters Recomp v0.6.2-alpha

Performance patch. No new features; no gameplay or behavior changes.

## ~19% faster emulation core

The emulation core used to run full bookkeeping (event checks, yield polls,
cycle accounting) on every single guest instruction. It now computes the next
moment anything can actually need service and, until then, each instruction
pays a single compare-and-add; the full checks run exactly at the moments
that matter. Measured on sustained gameplay: **18-20% less emulation time
per frame**, with the interpreter fallback path also ~5% faster.

This is aimed squarely at lower-end machines: if your frame time sat near
the 60 FPS budget and busy scenes dropped you into the 30-45 FPS range,
this patch buys back roughly a fifth of the CPU cost of every frame.

Correctness is unchanged by construction and by proof: the faithful path
remains in the binary (`NDS_CYCLE_FAST_LIMIT=0` forces it), and guest state
was verified byte-identical between both paths at seven 100-million
instruction checkpoints (framebuffers, full register files, event counts),
with identical audio/frame fingerprints over a 2,400-frame soak.

Also includes libiconv-2.dll in the package (hotfixed in-place on the
v0.6.0/v0.6.1 downloads earlier; carried properly here).

Everything else is v0.6.1-alpha: prebuilt native shard cache, on-device
shard compilation, SDL3 frontend, small-display launcher fix, and the
Frame Interpolation mod (still unavailable in split-screen mode with the
OpenGL renderer).
