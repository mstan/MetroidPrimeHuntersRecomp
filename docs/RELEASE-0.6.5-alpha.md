# Metroid Prime Hunters Recomp v0.6.5-alpha

Diagnostics and background-compiler correctness patch. No new features; no
gameplay or behavior changes. This is the build to run if you have been
sending us performance diagnostics — its logs answer questions the v0.6.4
logs could not.

## Frame time is now fully attributed in the diagnostics

v0.6.4 diagnostics could account for only a fraction of where a slow frame's
time actually went; on a frame that dropped below 60 FPS, most of the cost was
invisible. The runner now carries an always-on, near-zero-cost (~0.1%)
partition of emulation time — guest ARM9/ARM7 code execution, the interpreter,
the CPU-side geometry engine, DMA, the 2D and 3D renderers, scheduler
machinery, and bus slow paths — written to the same performance log every
session. On our validation runs the unaccounted share of a busy frame fell
from roughly two thirds to under 10%.

**If busy areas still slow down for you, please play a few minutes in exactly
the area where it bites, then send a fresh diagnostic bundle.** One capture
from a real slowdown now tells us precisely what to optimize next.

## The background shard compiler stops wasting its time

Three coupled defects in the live-overlay pipeline are fixed:

1. **Phantom work orders.** The interpreter recorded a "gap" for every call
   target it branched to — including targets a shipped native bank already
   served. In field logs ~93% of recorded coverage entries were phantom, and
   the on-device compiler dutifully re-compiled pages that were already
   native. Coverage is now recorded only when the takeover check confirms no
   bank owns the target.
2. **Silently discarded shards.** A newly compiled shard for a page could
   unregister the resident shard for that page even when the newcomer covered
   *fewer* entry points, permanently losing coverage with no trace in any
   counter. In the field this silently dropped 25 of the 58 shipped shards.
   Replacement now happens only when the newcomer actually covers at least
   everything the resident covered; otherwise both stay registered.
3. **Unanswerable reject logs.** The single aggregate reject counter could not
   say *why* anything was rejected. The performance log now carries 32 named
   per-cause counters (per session and per interval), so a field bundle can
   answer this class of question outright.

Shipped shard caches and existing installs are unaffected; no ABI change in
this release (live bank ABI stays at 6, so a copied `live-shard-cache` from
v0.6.4 keeps working).

**Prebuilt cache note:** this package ships WITHOUT a prebuilt shard cache.
With the phantom-work fix, a clean-cache rebuild produces no shards — every
address those shards covered is already owned by a shipped static bank, so
there is no legitimate work list to build one from. **If you are upgrading,
copy your existing `live-shard-cache` folder across: your shards keep loading
and working (ABI unchanged).** A fresh install simply runs on the static
banks alone; if busy areas feel worse than v0.6.4 on a fresh install, that is
exactly the signal we are instrumenting for — please send a diagnostic. The
underlying static-bank code-layout issue is tracked and is the target of the
next performance release.

## Coverage corpus

The 2026-08-28 field captures were ingested and verified: they add one overlay
entry point. The interesting result was negative — everything else they
reported was already covered (see phantom work orders above), which is exactly
what the fixes in this release address at the source.

## Versions

- Game: v0.6.5-alpha
- Framework pin: c6122bd (bank-reject fixes + emu-time attribution merged onto
  the v0.6.4 line)
- Banks: 251 shipped (unchanged composition from v0.6.4 plus one ov000 entry)
