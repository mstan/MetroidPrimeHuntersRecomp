# Metroid Prime Hunters Recomp v0.7.0-alpha

This release fixes a multiplayer Prime Controls bug reported after v0.6.10.

## Fixes

- Fixes multiplayer mouse and keyboard settings: players joining a lobby retain
  their controls, including mouse aiming.

## Packaging

- Windows package version: `0.7.0`
- GitHub release tag: `v0.7.0-alpha`
- Framework pin: `bfd7358`
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
