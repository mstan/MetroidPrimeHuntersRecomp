# MetroidPrimeHuntersRecomp v0.4.1-alpha

Patch release after `v0.4.0-alpha`.

## Included

- Fixes Nintendo WFC error 52200 on reconnect by clearing the stale AMHE0 guest
  CRT errno word on every AP association.
- Adds `tools/probe_mph_wfc_reconnect.py`, an automated connect/disconnect/
  reconnect regression probe with per-cycle network deltas and guest DWC state
  sampling.
- Adds same-machine local Multi-Card launch tooling in
  `tools/launch_local_play_pair.ps1` and documents the current validation path
  in `docs/HANDOFF_MPH_LOCAL_PLAY.md`.
- Promotes live local-multiplayer runtime code into three content-validated
  banks: `mph_arm9_mp_runtime`, `mph_arm7_mp_wram_runtime`, and
  `mph_arm7_mp_mainram_runtime`.
- Reads schema-4 coverage manifests in overlay seeding and reporting tools.
- Pins ndsrecomp to the static relocation discovery framework build, which
  discovers ARM7 WRAM/main-RAM and ARM9 ITCM autoload aliases from ROM content.

## Validated scope

- WFC reconnect gate: three consecutive Nintendo WFC connect cycles reached NAS
  TLS in one launch with zero backend errors and zero TCP resets.
- Same-machine local Multi-Card play: host and guest sustained 59.7-59.9 FPS in
  a live Combat Hall match after the runtime-bank promotion.
- Standard MPH boot smoke passed on the pinned framework.
- Windows release package built with `tools/build-windows.ps1 -Version 0.4.1`;
  archive inspection found no ROM, BIOS, firmware, save, generated source, or
  unsafe ZIP entries.
- Linux AppImage built with `tools/build-linux.sh --version 0.4.1`; AppImage
  layout validation passed.
- Direct test execution passed for all 13 built runner test executables and the
  MPH launcher mod-provider test.
- The prior v0.4.0 scope remains unchanged: campaign entry, widescreen/HD
  rendering, Prime-style controls, gamepad support, Wiimmfi same-machine match
  evidence, and the FMV runtime bank remain included.

## Known limits

- Online cross-machine play remains unvalidated.
- Local wireless has been validated on one machine only.
- Campaign, traversal, combat, save reload, and widescreen presentation coverage
  are still incomplete.

## Artifact

- `MetroidPrimeHuntersRecomp-windows-x64-v0.4.1.zip`
- SHA-256:
  `4803963152BD90A1A631B7EBF53E7CE39DFBB4899D1B9650FBABE3B8A86A5A1F`
- `MetroidPrimeHuntersRecomp-linux-v0.4.1-x86_64.AppImage`
- SHA-256:
  `6f8ac20eb4178bf95e6570a0ed27cd8dbb6f6a40d18273980c4798d1dd17203a`
