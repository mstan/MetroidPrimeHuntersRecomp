# Windows native execution

The October26 candidate uses native ARM9 execution together with the existing
guarded math/submission HLE and NativeGL renderer. The normal dispatcher still
checks title code and resumable service continuations. Guest devices, interrupts,
sound and native cartridge saves remain modeled. Owner visual/play check passed.

On the i5-4670/GTX760 Windows NAS, two matched600-VBlank Gorea samples showed
20–29% less process CPU and22–39% greater uncapped throughput. The second pair
reversed order to resolve observed host variation. These are bounded gameplay
samples, not all-room or online guarantees. Native virtual timing differs from
Faithful, and snapshots remain build-specific. Live Wiimmfi was not qualified.

`tools/build-windows.ps1` defaults to this Windows profile. Supply
`-DynarmicRoot <patched pinned SDK source>` as documented by the shared engine's
native-backend setup. `-PerformanceBackend OFF` builds and launches portable
Faithful without the SDK. Math/submission HLE retain their separate build-time
LLE opt-outs. Native ARM7 is explicitly disabled for MPH; that package has only
been qualified for MKDS so far. Other-platform build paths remain portable.

Engine implementation841f033, subsequent ARM7 framework supporta5f8054;
isolated branch `perf/native-services-20261026`. Raw source/binary/settings and
per-game data are retained under
`G:/Temp/Codex/ndsrecomp/native-services-20261026/campaign-results.json`.
Tracking: `beads-ova0`, optimization campaign `beads-2wy8.1`.
