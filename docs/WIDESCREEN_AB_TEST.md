# Widescreen modes

The launcher exposes two alternative widescreen implementations:

- **Adaptive Widescreen** — the original ndsrecomp host-side 448px renderer / compositor / HUD anchoring path.
- **Game Aspect Ratio Patch** — the MPH guest-side 21:9 projection/culling patch derived from melonPrimeDS and mphCodex.

They are **mutually exclusive**. Turning either widescreen feature ON immediately turns the other one OFF. Both may be OFF for native 4:3 output, but both may not be ON at the same time.

The game-side patch defaults **OFF**, so the original ndsrecomp Adaptive Widescreen implementation remains the default widescreen path.

## Valid combinations

| Adaptive Widescreen | Game Aspect Ratio Patch | Result |
|---|---|---|
| OFF | OFF | Native 4:3 / 256x192 |
| ON | OFF | Original ndsrecomp host widescreen only |
| OFF | ON | Guest projection/culling patch; native 256x192 top image is stretched to 448x192 only at final presentation |
| ON | ON | **Invalid state** — the launcher automatically switches one side OFF |

When only the guest patch is enabled, the DS-native render surface remains 256x192. The final 256-to-448 stretch is required because the game-side patch produces projection geometry for a 21:9 target; displaying the resulting native surface unchanged as 4:3 would make it appear horizontally compressed.

Legacy `mods.ini` files from the comparison build may contain both values as `true`. The loader resolves that state while parsing and the next save writes a valid mutually-exclusive pair. The final process-launch argument construction also refuses to pass both widescreen mechanisms to the runner even if an invalid state is somehow introduced later.

The runner logs the selected guest policy. Guest-side code/data writes remain fail-closed and require an authoritative supported MPH executable checksum; header-only fallback never authorizes the aspect-ratio patch.

## Validation

The separate host-only / guest-only presentation paths and the nearest-only Supersampling presentation fix were visually tested with MPH before mutual exclusion was enabled. The current launcher policy then passed the full ROM-free Windows/Linux build and static regression suite at head `50271f43a4d0be9fe4c02a87c278bec80f4a4a47`.