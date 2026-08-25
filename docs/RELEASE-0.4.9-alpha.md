# MetroidPrimeHuntersRecomp v0.4.9-alpha

Patch release after `v0.4.8-alpha`.

## Changes

- Centers low-polygon map, overworld, tutorial, and cinematic transition views
  that can otherwise expose split widened side content.
- Preserves adaptive widescreen during normal gameplay.
- Keeps the default-on `Diagnostics` option from `v0.4.8-alpha`, which writes
  coverage, performance, and dispatch-miss logs together in the launcher
  `diagnostics` folder.
- Pins ndsrecomp to `c185356962eb42fd94e98593e90c8ec2cfe4f2ef`.

## Validation

- ndsrecomp `gpu2d_window_test` passed.
- ndsrecomp `frontend_config_test` passed.
- Live MPH debug-framebuffer validation: a 31-polygon Celestial Archives
  prompt frame centered with black side bands.
- Live MPH debug-framebuffer validation: a later 1131-polygon gameplay frame
  kept populated adaptive-wide side bands.
- Windows ZIP package built successfully.
- Linux AppImage package built successfully and passed the AppImage layout
  test.

## Download

Attach your legally obtained Metroid Prime Hunters USA revision-0 ROM. No ROM,
BIOS, firmware, save data, or generated ROM-derived source is included.

- `MetroidPrimeHuntersRecomp-windows-x64-v0.4.9.zip`
- SHA256: `4855C4D5142947E8D96608FFA591B28F614DCCD51416ACF061488DB440F3BFAB`

- `MetroidPrimeHuntersRecomp-linux-v0.4.9-x86_64.AppImage`
- SHA256: `F868095937ED3A5CFC927AEF3CDAA7DE039B2A70C91E6F0EB07F813BECB07349`
