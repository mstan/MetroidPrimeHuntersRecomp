# MetroidPrimeHuntersRecomp v0.4.8-alpha

Patch release after `v0.4.7-alpha`.

## Changes

- Adds a default-on `Diagnostics` option on the Mods page.
- When diagnostics are enabled, the launcher keeps coverage manifests,
  performance JSONL logs, and dispatch-miss logs together in its `diagnostics`
  folder.
- Disabling `Diagnostics` suppresses those generated diagnostic files.
- Pins ndsrecomp to `ecd565509ac5f4bf4e36defbfbc2fe73a02aae96`.

## Validation

- ndsrecomp `frontend_config_test` and `relative_mouse_touch_test` passed.
- Metroid Prime Hunters launcher `mph-mod-provider-test` passed.
- Runner smoke test with diagnostics on wrote both coverage and performance
  logs into the diagnostics directory.
- Runner smoke test with diagnostics off wrote no diagnostic files.
- Windows ZIP package built successfully.
- Linux AppImage package built successfully and passed the AppImage layout test.

## Download

Attach your legally obtained Metroid Prime Hunters USA revision-0 ROM. No ROM,
BIOS, firmware, save data, or generated ROM-derived source is included.

- `MetroidPrimeHuntersRecomp-windows-x64-v0.4.8.zip`
- SHA256: `43D11A896FB75003A4329013FBFD1F2C47BD16D274827B149DD29618BBE1663A`

- `MetroidPrimeHuntersRecomp-linux-v0.4.8-x86_64.AppImage`
- SHA256: `63918021B4F6BBED355B0D13B07C1A227F09C392AE6AA67BBE2720A86E111D9E`
