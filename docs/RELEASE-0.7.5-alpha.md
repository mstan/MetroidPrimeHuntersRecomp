# Metroid Prime Hunters Recomp v0.7.5-alpha

This release adds broad campaign coverage and fixes Omega Cannon selection
reported in [issue 44](https://github.com/mstan/MetroidPrimeHuntersRecomp/issues/44).

- Adds compiled code discovered while visiting all 66 campaign room IDs,
  including late-game areas, both Gorea fights, transformation and ending paths.
- Includes two previously missing boss overlays and 13 additional captured
  runtime banks. The runner's required inventory is now 266 banks.
- Keeps the Omega Cannon when Prime Controls special-weapon shortcuts are used
  during Gorea phase two. Power Beam and missile selection remain available.
- Retains the existing controller, widescreen and in-game settings fixes.

The coverage investigation added 2,756 main/overlay entry seeds, plus runtime
bank seeds. Its final focused Gorea checks covered 1,099 VBlanks with zero
ARM9/ARM7 interpreter entries or instructions. This is coverage evidence, not
a claimed FPS gain or exhaustive full-game validation. The interpreter floor
and focused input/save-state checks also passed during the investigation.
See [the investigation](ISSUE-44-COVERAGE.md) for the exact scope and limits.

No HLE performance replacement is included in this release. The persistent
graphics-quality reduction reported in issue 44 remains under investigation;
the adaptive performance governor is a plausible mechanism, not a confirmed
fix. Existing gameplay evidence is reused under the project validation policy;
release validation covers builds, versions, bank inventory, packaging and
private-payload exclusion, without new gameplay or benchmark matrices.

Release metadata:

- Windows and Linux package version: `0.7.5`
- GitHub release tag: `v0.7.5-alpha`
- Framework pin: `13213eeb336fa45eb79264f9dcea8274acec54fb`
- recomp-ui pin: `e45e1f3062731abc188e351cad3608730b01fa12`

Supply your own AMHE USA revision-0 ROM. ROMs, raw runtime captures, BIOS and
firmware dumps, saves, and generated source are excluded from release assets.
