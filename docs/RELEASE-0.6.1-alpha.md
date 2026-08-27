# Metroid Prime Hunters Recomp v0.6.1-alpha

Launcher-only follow-up to v0.6.0-alpha. The game runner, compiled code
banks, and native shard cache are byte-identical to v0.6.0 — if the game
itself runs fine for you on v0.6.0, this changes nothing in-game.

## Fixed: launcher fits small displays (issue #33)

The launcher window now fits displays like 1366x768 instead of opening
larger than the screen, which could leave the Play button unreachable
("can't even get into the game"). If v0.6.0's launcher didn't fit your
screen, this release is for you.

Everything else is v0.6.0-alpha: restored + expanded native code banks,
prebuilt native shard cache, on-device shard compilation for new areas,
SDL3 frontend, and the Frame Interpolation mod (still unavailable in
split-screen mode with the OpenGL renderer).
