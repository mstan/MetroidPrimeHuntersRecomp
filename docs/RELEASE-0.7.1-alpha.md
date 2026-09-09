# Metroid Prime Hunters Recomp v0.7.1-alpha

This release fixes Prime Controls aiming interruptions reported in v0.7.0.

## Fixes

- Fixes multiplayer aiming when another player enters morph ball; each client
  now checks its own player state before releasing mouse aim.
- Fixes scan visor and weapon hotkey actions so mouse aiming continues while
  those controls are pressed.
- Retains the v0.7.0 multiplayer mouse and keyboard settings fix for players
  joining a lobby.

## Packaging

- Windows package version: `0.7.1`
- GitHub release tag: `v0.7.1-alpha`
- Framework pin: `5cefd9f557ceb4c9656b3dfdcf7f0c5e3e3d74fe`
- Windows runner SHA-256: `3cc47f0e7b0ebf279741ea4486066b84315f227314bf0ffbbfbcb652c4ad64fb`

## Validation Notes

- Bank inventory passed for the Windows runner: 251 banks verified.
- Package integrity checks cover dependency closure and private-payload
  exclusion before archiving.
- One campaign session checked the scan visor and weapon hotkey aiming path.
- The new multiplayer morph-ball behavior was not rerun in a live multiplayer
  match before packaging.