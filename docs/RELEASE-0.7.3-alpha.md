# Metroid Prime Hunters Recomp v0.7.3-alpha

This patch release fixes two Prime Controls and widescreen issues reported
against the 0.7.x line:

- Alternate-form mouse camera is restored for all hunters while preserving
  Samus boost charging.
- Imperialist sniper zoom keeps the selected widescreen aspect when aiming
  into nearby walls instead of falling back to the narrow low-polygon scene
  layout.

It retains the v0.7.2 in-game Escape settings menu, the v0.7.1 multiplayer
aiming fixes, and the v0.7.0 multiplayer mouse and keyboard settings fix for
players joining a lobby.

This release updates the runner savestate minor version to 12.2 so the new
rendered-polygon projection metadata survives save/load. Older compatible
savestates still load; savestates written by this build may not load in older
0.7.x runners.

Release metadata:

- Windows package version: `0.7.3`
- Linux package version: `0.7.3`
- GitHub release tag: `v0.7.3-alpha`
- Framework pin: `56ed6c964e1ec3be0991116ff7f4abd296d6c457`
