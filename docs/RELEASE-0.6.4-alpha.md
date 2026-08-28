# Metroid Prime Hunters Recomp v0.6.4-alpha

Performance patch. No new features; no gameplay or behavior changes.

## Less dispatch overhead again, plus a faster-built binary

Two changes, both aimed at the same cost:

1. **Direct linking.** A recompiled call to a known target used to go through
   a runtime dispatcher lookup on every single call. Those call sites now
   bind straight to their target after a one-time validation, so the lookup
   disappears from the hot path entirely: **~72% fewer dispatcher cache
   probes** in gameplay.
2. **Profile-guided runner build.** The shipped runner is now built with PGO,
   so the code around what is left of the dispatch path is laid out and
   inlined for how the game actually runs.

Measured on a fast development machine: **6.2% less emulation time per frame
in gameplay and 5.7% in the attract loop**, with every measured phase of both
routes improving and none regressing. As with v0.6.3, that development-machine
figure is the floor rather than the headline: these are dispatch-path savings,
and the field diagnostics show that machines which drop frames in busy scenes
are dispatch-bound, so the same cut lands on a much larger share of the frame
there. If v0.6.3 still dropped frames for you, please test this build and send
a new diagnostic either way.

The two changes are **not additive** - they attack the same dispatch path and
overlap almost entirely, so 6.2% is the combined figure, not 2% plus 6%.

## Threaded 2D renderer (opt-in, off by default)

The 2D scanline renderer can now run on worker threads. It ships **disabled**;
set `NDS_GPU2D_THREADED=1` to turn it on. It needs **4 or more CPU cores** to
be worth it - on a 2-core machine it is a measured slowdown, which is why it
is not on by default. Output is byte-identical either way.

## Faster on-device shard compilation

The background compiler that fills in code the shipped banks do not cover was
running at a fixed, deliberately conservative cadence and could never catch up
on machines that needed it most. It now:

- **adapts**: while there is a backlog it compiles more per batch and waits
  less between batches, then returns to the quiet cadence once drained;
- **orders by how hot the code actually is**, not by discovery order;
- **remembers its backlog across sessions** and starts draining at launch
  instead of rediscovering from scratch.

Measured on a real session: **+53% shard throughput**, and the queue now
actually converges to empty where it previously did not. Frame-time cost
during compile intervals is within session noise.

**If you copy your old install's `live-shard-cache` across, its shards will be
recompiled once.** The live bank ABI went from 5 to 6 in this release (direct
linking adds per-call-site link slots), so shards compiled by v0.6.3 no longer
match and are refused - safely, before anything in them is ever run. They are
left on disk rather than deleted, so you can simply delete the old
`live-shard-cache` folder if you want the space back. A normal install into a
fresh folder is unaffected: there is nothing to refuse, and the prebuilt cache
that ships with this release is already built against the new ABI.

## Broader shipped coverage from your diagnostics

The coverage bundles you sent were ingested into the shipped banks. Shipped
code banks go from **81 to 251**, driven almost entirely by field play that no
scripted development route reaches - later areas, deeper Celestial Archives,
multiplayer paths. Two overlays (5 and 6) are shipped natively for the first
time because player sessions proved them resident and no development route
ever had. The prebuilt shard cache grows from 42 to 59 shards.

Effect: **2-3% less interpreted code** on the routes that can be measured,
and more than that on the field paths that only your sessions exercise.

Thank you to everyone who sent a diagnostic bundle - this section exists
because of them. Please keep sending them. Diagnostics now also record basic
hardware information (CPU, core count, memory), so future reports can be
attributed to the kind of machine they came from instead of being averaged
together.

## Correctness

Unchanged, and proven rather than assumed. Guest state - both screens, both
CPUs' full register files, and every event counter - is byte-identical with
direct linking on versus off, and with the threaded 2D renderer on versus off,
at seven 100-million-instruction checkpoints each. A 4,242-frame audio soak
produces the identical fingerprint across all configurations. The enlarged
bank set was separately proven guest-invisible against the previous build at
the same seven checkpoints.

Everything else is v0.6.3-alpha.
