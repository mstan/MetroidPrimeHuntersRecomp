# MetroidPrimeHuntersRecomp v0.7.11-alpha

Enables 4x internal 3D resolution and 8-sample supersample anti-aliasing
by default. The game now displays its higher-resolution 3D raster while
preserving native-resolution HUD text and DS window masks. Native
resolution and AA Off remain available in Mods; explicit saved settings
are retained. Adaptive widescreen remains enabled by default.

Fixes HD fallback in masked Mario Kart scenes and native-aspect views,
plus native GL HD red/blue channel transport. The owner accepted the
new game pictures, including MPH adaptive widescreen. Original textures
can still show diagonal aliasing; texture filtering is future work.

Retains the previous native ARM9/ARM7 and per-title HLE packages.
Quality settings increase graphics cost; no new speed claim or online
compatibility claim is made. Native saves are preserved; execution
snapshots remain build-specific. Validation reuses the owner playtests
and focused actual-GPU, compositor and launcher checks.

Engine pin: `2d9f4f3cb33daa78a724a1c17fdbcc2048580c2c`. Tracking: `beads-yjp.101`.
