# Widescreen A/B test modes

The launcher exposes two independent display features:

- **Adaptive Widescreen** — the original ndsrecomp host-side 448px renderer / compositor / HUD anchoring path.
- **Game Aspect Ratio Patch** — the MPH guest-side 21:9 projection/culling patch derived from melonPrimeDS and mphCodex.

The game-side patch defaults **OFF** so the original ndsrecomp Adaptive Widescreen implementation remains the baseline and is not double-applied automatically.

## Four test combinations

| Adaptive Widescreen | Game Aspect Ratio Patch | Result |
|---|---|---|
| OFF | OFF | Native 4:3 / 256x192 |
| ON | OFF | Original ndsrecomp host widescreen only |
| OFF | ON | Guest projection/culling patch; native 256x192 top image is stretched to 448x192 only at final presentation |
| ON | ON | Both mechanisms enabled; intentionally reproduces the suspected double-application path |

When only the guest patch is enabled, the DS-native render surface remains 256x192. The final 256-to-448 stretch is required because the game-side patch produces projection geometry for a 21:9 target; displaying the resulting native surface unchanged as 4:3 would make it appear horizontally compressed.

The runner logs the selected guest policy. Guest-side code/data writes remain fail-closed and require an authoritative supported MPH executable checksum; header-only fallback never authorizes the aspect-ratio patch.
