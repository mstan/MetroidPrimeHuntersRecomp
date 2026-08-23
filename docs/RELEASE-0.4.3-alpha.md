# MetroidPrimeHuntersRecomp v0.4.3-alpha

Patch release after `v0.4.2-alpha`.

## Included

- Pins ndsrecomp to `9f2f8f3f531fb084a15f4d924e875334d9d8209d`.
- Passes the launcher Fullscreen setting through to the runner as
  `--fullscreen off|borderless|exclusive`.
- Honors the launcher's Stacked/Separate window setting instead of forcing
  separate windows whenever Adaptive Widescreen or Prime Controls are enabled.
- Guards the compute renderer's texture-size uniform update so Intel OpenGL
  drivers do not receive `InvTextureSize` writes while a no-texture raster
  program is current.
- Enables melonDS high-resolution vertex coordinates when internal resolution
  is above 1x, reducing native-grid wobble in HD rendering.
- Allows the direct OpenGL top-screen presenter for native-HD output even when
  Adaptive Widescreen is off.
- Keeps native-width direct-presenter output at 4:3 with black bars instead of
  stretching it across wide/fullscreen windows.
- Retains the v0.4.2 public Tab turbo default-off fix and the v0.4.1 Nintendo
  WFC reconnect and same-machine local Multi-Card runtime-bank fixes.

## Validated scope

- ndsrecomp Windows runner build succeeded; all 15 runner tests passed.
- ndsrecomp Linux runner build succeeded; all 15 runner tests passed.
- MPH launcher `mph_mod_provider_test` passed on Windows and Linux.
- Windows release package built with `tools/build-windows.ps1 -Version 0.4.3`.
- Linux AppImage built with `tools/build-linux.sh --version 0.4.3`; AppImage
  layout validation passed.

## Validation Needed

- Affected Intel OpenGL users should retest the startup crash / blank-screen
  path.
- HD-rendering users should visually compare native-HD upscaling, texture
  wobble, mission briefing/FMV aspect ratio, and Adaptive Widescreen behavior.
- Window-setting reporters should retest Stacked, Separate, Borderless
  fullscreen, and Exclusive fullscreen from the launcher.

## Known limits

- Steam Deck / older-glibc compatibility is not fixed by this release.
- European ROM support is not included.
- Online cross-machine play remains unvalidated.
- Local wireless has been validated on one machine only.
- Several renderer compatibility, adaptive-widescreen visibility, and
  performance issues remain under active investigation.

## Artifact

- `MetroidPrimeHuntersRecomp-windows-x64-v0.4.3.zip`
- SHA-256:
  `0684C524816CD8874571B5E54EC7BA1CED6594924C6CEED7877D34B883497018`
- `MetroidPrimeHuntersRecomp-linux-v0.4.3-x86_64.AppImage`
- SHA-256:
  `18d60c3fd26f2812aa808f64309f5b1e33614bcbcd62128561d4cbe486d9fb0e`
