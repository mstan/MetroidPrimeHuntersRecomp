# MetroidPrimeHuntersRecomp v0.4.2-alpha

Patch release after `v0.4.1-alpha`.

## Included

- Pins ndsrecomp to `9ddd3a35a8d96d374acb39497e40e6bce46b99ea`.
- Disables the developer Tab turbo shortcut in public builds by default, so it
  no longer conflicts with MPH's default virtual-stylus binding.
- Keeps developer speed control available only by explicit runner opt-in with
  `--tab-turbo on` or through the debug-server turbo command.
- Clears any frontend Tab turbo latch on focus loss.
- Retains the v0.4.1 Nintendo WFC reconnect and same-machine local Multi-Card
  runtime-bank fixes.

## Validated scope

- ndsrecomp runner build succeeded at the pinned framework commit; all 15 runner
  tests passed.
- Windows release package built with `tools/build-windows.ps1 -Version 0.4.2`;
  archive inspection found no ROM, BIOS, firmware, save, generated source, or
  unsafe ZIP entries.
- Linux AppImage built with `tools/build-linux.sh --version 0.4.2`; AppImage
  layout validation passed.
- MPH launcher `mph_mod_provider_test` passed.
- Manual launch before this patch reproduced the public Tab turbo latch at
  elevated FPS; this patch removes that default public trigger.

## Known limits

- Online cross-machine play remains unvalidated.
- Local wireless has been validated on one machine only.
- Campaign, traversal, combat, save reload, and widescreen presentation coverage
  are still incomplete.
- Several renderer compatibility and HD presentation issues remain under active
  investigation.

## Artifact

- `MetroidPrimeHuntersRecomp-windows-x64-v0.4.2.zip`
- SHA-256:
  `FB236426EA7D37DD0881AD458C6969D5DB29A39C1310D419807CD85B4D991AFD`
- `MetroidPrimeHuntersRecomp-linux-v0.4.2-x86_64.AppImage`
- SHA-256:
  `63487a83428573286aa3f5630a3093443fed1032f15e9cb4a25bba6a4d5d61db`
