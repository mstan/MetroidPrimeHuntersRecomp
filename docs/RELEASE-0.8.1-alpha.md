# Metroid Prime Hunters Recomp v0.8.1-alpha

Windows and Linux update addressing the remaining
[issue #44](https://github.com/mstan/MetroidPrimeHuntersRecomp/issues/44)
reports.

## Fixes

- **Graphics no longer drop to low quality.** Automatic Quality has been
  removed. It lowered the internal resolution and supersampling during room
  and door loads, and could hold the reduction for the rest of the session.
  Your selected graphics quality now always applies. Saved Automatic Quality
  settings from earlier versions are ignored.
- **Sound effects are back (Windows).** Shots, damage and other effects were silent in
  v0.7.16 and v0.8.0, while music still played. The enhanced engine's native
  sound service now plays the instrument type the game uses for its effects.
- **Morph ball looks correct again (Windows).** Since v0.7.16, the enhanced engine's
  native geometry tiled the ball's reflective shell texture 16 times. It now
  matches the original look.
- **Widescreen visor filler stays steady.** The extended frame at the top of
  the visor no longer flickers between colours while you aim.

The sound and morph ball problems affected only the Windows enhanced engine;
the Linux build uses the portable profile and was not affected.

## Online play

- **Wireless & online play is now on by default** and uses the same enhanced
  engine as offline play. The separate Reference engine is no longer needed
  for online play.
- If you previously turned the option off, that choice is kept.
- The Reference engine is still included as a portable fallback.

Online play remains experimental.

## Notes

- Provide your own supported (USA, revision 0) ROM.
- No ROM, BIOS, firmware, saves or private captures are included.
- Execution snapshots (savestates) remain build-specific.
