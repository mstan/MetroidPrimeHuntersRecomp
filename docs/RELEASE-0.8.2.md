# Metroid Prime Hunters Recomp v0.8.2

Windows and Linux release. It contains the
[issue #44](https://github.com/mstan/MetroidPrimeHuntersRecomp/issues/44)
fixes first published as v0.8.1-alpha, with the same game engine.

## Fixes

- **Graphics no longer drop to low quality.** Automatic Quality has been
  removed. It lowered the internal resolution and supersampling during room
  and door loads, and could hold the reduction for the rest of the session.
  Your selected graphics quality now always applies.
- **Sound effects are back (Windows).** Shots, damage and other effects were
  silent in v0.7.16 and v0.8.0, while music still played.
- **Morph ball looks correct again (Windows).** The enhanced engine's native
  geometry had been tiling the ball's reflective shell texture 16 times.
- **Widescreen visor filler stays steady.** The extended frame at the top of
  the visor no longer flickers between colours while you aim.

The sound and morph ball problems affected only the Windows enhanced engine.

## Online play

- **Wireless & online play is always on** and uses the same enhanced engine as
  offline play. It is no longer a setting.
- The Reference engine is still included as a portable fallback.

## Notes

- Provide your own supported (USA, revision 0) ROM.
- No ROM, BIOS, firmware, saves or private captures are included.
- Execution snapshots (savestates) remain build-specific.
