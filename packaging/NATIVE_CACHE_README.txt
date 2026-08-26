Native code cache (live-shard-cache)
====================================

Metroid Prime Hunters builds a lot of its hottest code in RAM while it runs, so
that code cannot be converted ahead of time when this build is made. It is
handled while you play instead.

The live-shard-cache folder that ships with this release already contains
pre-converted native code for the areas covered so far. Those run at full speed
from your very first visit -- you do not have to do anything.

As you play, areas that are not covered yet are recorded, converted in the
background by the small compiler toolchain bundled in overlay_toolchain, and
added to live-shard-cache automatically. The first minute or two in a brand new
area may therefore be slower than the second visit. Everything happens on your
machine; nothing is uploaded anywhere.

If you ever want to start over, delete live-shard-cache. The game will refill
it as you play.

PRIVACY / SHARING
-----------------
live-shard-cache\snapshots\*.json and any coverage manifest written into the
diagnostics folder contain snapshots of the game's own code, read out of YOUR
copy of the cartridge. Do NOT post them publicly or attach them to bug reports.
The converted .dll files under live-shard-cache\gcc and live-shard-cache\tcc
are derived from the same material, so treat the whole folder as private too.
