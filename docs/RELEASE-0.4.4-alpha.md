# MetroidPrimeHuntersRecomp v0.4.4-alpha

Patch release after `v0.4.3-alpha`.

## Included

- Builds against ndsrecomp main plus the MPH HD/compute renderer fixes.
- Keeps tutorial and transmission overlays on the HD 3D presenter when their
  OBJ-window masks disable color effects but leave BG0/3D visible.
- Builds the Linux AppImage in an Ubuntu 22.04 container, lowering the packaged
  glibc requirement for Steam Deck / older Linux distributions.
- Keeps the v0.4.3 launcher Fullscreen and Stacked/Separate window setting
  persistence and forwarding fixes.
- Retains the v0.4.2 public Tab turbo default-off fix and the v0.4.1 Nintendo
  WFC reconnect and same-machine local Multi-Card runtime-bank fixes.

## Validated scope

- MPH launcher `mph_mod_provider_test` passed on Windows.
- ndsrecomp Windows runner build succeeded; all 15 runner tests passed.
- Windows release package built with `tools/build-windows.ps1 -Version 0.4.4`.
- Linux title, runner, and launcher compile succeeded in the Ubuntu 22.04
  Steam Deck build container.
- Linux AppImage built with `tools/build-linux-steamdeck.ps1 -Version 0.4.4`;
  AppImage layout validation passed.
- Container build reported `nds_runner` requiring `GLIBC_2.35` and
  `mph-recomp-ui` requiring `GLIBC_2.34`.

## Validation Needed

- Steam Deck / older Linux users should retest the AppImage launch path.
- Window-setting reporters should retest Stacked, Separate, Borderless
  fullscreen, and Exclusive fullscreen from the launcher.
- Users who reported performance issues should retest against this build.
- Tutorial, transmission, and modal screen-routing flows still need local
  validation.

## Known limits

- European ROM support is not included.
- Online cross-machine play remains unvalidated.
- Local wireless has been validated on one machine only.
- Several renderer compatibility, adaptive-widescreen visibility, and
  performance issues remain under active investigation.

## Artifact

- `MetroidPrimeHuntersRecomp-windows-x64-v0.4.4.zip`
- SHA-256:
  `D375DBECBF4E6912BFD39F0EFBC5A0F5119E58802EB820FC44B3EC173DA83CFF`
- `MetroidPrimeHuntersRecomp-linux-v0.4.4-x86_64.AppImage`
- SHA-256:
  `8998D539E2DC194B5D03D32521A81224898D248E5DA2823E05E6097125850C90`
