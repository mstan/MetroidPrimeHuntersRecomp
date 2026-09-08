# Metroid Prime Hunters Recomp v0.7.0-alpha

This release fixes a multiplayer Prime Controls bug reported after v0.6.10.

## Fixes

- Fixes multiplayer mouse and keyboard settings: players joining a lobby retain
  their controls, including mouse aiming.

## Packaging

- Windows package version: `0.7.0`
- GitHub release tag: `v0.7.0-alpha`
- Framework pin: `bfd7358f31460ee54dfa15935b8e958ae1a85bdf`
- The release package must pass the bank inventory gate before archiving.
- Prebuilt native shards are staged only when their provider identity matches
  the shipped runner, recompiler, headers, and compiler policy.

## Upgrade Notes

Existing `live-shard-cache` folders remain compatible unless the loader
quarantines a shard for a producer mismatch. The bundled cache is validated
against this exact release runner, and newly discovered runtime pages can still
be compiled by the bundled overlay toolchain.
