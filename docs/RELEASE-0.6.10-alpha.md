# Metroid Prime Hunters Recomp v0.6.10-alpha

This release is a focused follow-up to v0.6.9-alpha. It keeps the v0.6.9
performance work, bank inventory, and live-shard policy, and fixes several
player-facing launcher/input/diagnostic issues reported after the release.

## Fixes

- The launcher's Linear filter toggle now persists between sessions.
- Prime Controls no longer binds gamepad D-pad left/right to touchscreen UI
  helpers by default. That leaves the D-pad available for normal game menu
  navigation on controllers such as the Xbox Elite Series 2 over Bluetooth.
- The Prime Controls Mods page now includes a Restore gamepad defaults action
  that resets gamepad bindings and gamepad aim sensitivity to the shipped
  defaults.
- Performance logs and automatic coverage manifests now share the same
  diagnostics run timestamp when diagnostics are enabled, so files from one
  run are easier to group.
- The framework debug pump shutdown path is guarded against regressing the
  Linux accept() unblock fix.

## Packaging

- Windows package version: `0.6.10`
- GitHub release tag: `v0.6.10-alpha`
- Framework pin: `aa40b57`
- The release package must pass the bank inventory gate and the lean shard
  basic validation before archiving.
- Prebuilt native shards are staged only when their provider identity matches
  the shipped runner, recompiler, headers, compiler policy, and performance
  gate.

## Upgrade Notes

Existing `live-shard-cache` folders remain compatible unless the loader
quarantines a shard for a producer mismatch. The bundled cache is validated
against this exact release runner, and newly discovered runtime pages can still
be compiled by the bundled overlay toolchain.
