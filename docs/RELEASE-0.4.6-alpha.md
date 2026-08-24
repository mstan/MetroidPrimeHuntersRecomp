# MetroidPrimeHuntersRecomp v0.4.6-alpha

Patch release after `v0.4.5-alpha`.

## Included

- Pins ndsrecomp to `2ce78376f419d62da59df1d9edcd34d75b7956da`.
- Fixes the Separate layout Prime Controls focus split reported by Wolfen
  during a multiplayer Wiimmfi match: focusing either game window now keeps
  mouse aiming and keyboard controls usable together.
- Keeps the v0.4.5 Linux AppImage in-app ROM picker fallback.
- Keeps the v0.4.4 Ubuntu 22.04 AppImage baseline for Steam Deck / older Linux
  distributions.
- Retains the v0.4.3 launcher fullscreen/layout forwarding and HD renderer
  fixes, the v0.4.2 public Tab turbo default-off fix, and the v0.4.1 Nintendo
  WFC reconnect and same-machine local Multi-Card runtime-bank fixes.

## Validated scope

- ndsrecomp `relative_mouse_touch_test` and `frontend_config_test` passed on
  Windows.
- ndsrecomp Windows `nds_runner` target built successfully.
- Windows release package built with `tools/build-windows.ps1 -Version 0.4.6`.
- Linux AppImage built with `tools/build-linux-steamdeck.ps1 -Version 0.4.6`;
  AppImage layout validation passed.
- Container build reported `nds_runner` requiring `GLIBC_2.35` and
  `mph-recomp-ui` requiring `GLIBC_2.34`.

## Validation Needed

- Mouse/keyboard Prime Controls users should retest Separate layout by focusing
  both the top and bottom windows.
- Wiimmfi multiplayer users should retest mouse aiming and keyboard movement in
  a real match.
- Steam Deck / older Linux users should continue testing AppImage launch and
  ROM selection.

## Known limits

- European ROM support is not included.
- Online cross-machine play remains early and needs wider testing.
- Several renderer compatibility, adaptive-widescreen visibility, and
  performance issues remain under active investigation.

## Artifact

- `MetroidPrimeHuntersRecomp-windows-x64-v0.4.6.zip`
- SHA-256:
  `26A8D342118D8F47D8B741251772B38A5038C6855FC8457DDB8C81BA3531E711`
- `MetroidPrimeHuntersRecomp-linux-v0.4.6-x86_64.AppImage`
- SHA-256:
  `8565CC9C0C2BA78AAA79F02A19F8953A6A9D19E854B80D14B36A5C866684983A`
