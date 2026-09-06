# Metroid Prime Hunters Recomp v0.6.10-linux.1

This Linux packaging patch addresses [#43](https://github.com/mstan/MetroidPrimeHuntersRecomp/issues/43):
the v0.6.10 AppImage could fail before opening the launcher on SteamOS with:

```text
/bin/sh: symbol lookup error: /bin/sh: undefined symbol: rl_trim_arg_from_keyseq
```

The AppImage now keeps its bundled Python/Readline libraries scoped to the
packaged programs. Host shell processes use the host's libraries. The bundled
Python extensions and compiler helpers retain relative library paths, and
packaging tests cover startup, cache seeding, and Python spawning a host shell.

## Download and upgrade

- Linux x86_64 / Steam Deck:
  `MetroidPrimeHuntersRecomp-linux-v0.6.10-linux.1-x86_64.AppImage`
- Verify the download with the accompanying `.AppImage.sha256` file.
- Put the patched AppImage beside your existing ROM and user-data folders,
  mark it executable if needed, and launch it. Update any Steam shortcut to
  point to the new filename.
- Windows users should continue using
  [v0.6.10-alpha](https://github.com/mstan/MetroidPrimeHuntersRecomp/releases/tag/v0.6.10-alpha).

This is a packaging revision of v0.6.10: the runner, launcher, and prebuilt
shards are retained. It does not change game behavior or renderer upscaling.
No ROM, retail BIOS, firmware, or save is included; supply your own supported
Metroid Prime Hunters USA revision-0 ROM.

## Validation and remaining limitations

The exact original shell error was reproduced using Arch Linux inside WSL2.
The repaired AppImage passed startup and cache seeding, clean-environment
Python imports and host-shell execution, paths containing spaces, and an
Ubuntu virtual-display launcher smoke test. Physical Steam Deck confirmation
remains outstanding.

An existing TinyCC live-compilation fallback limitation on Arch-like hosts
remains separate: its Ubuntu CRT search paths can fail to find `crti.o` and
`crtn.o`. This was reproduced with both the original and patched package;
the shipped prebuilt shard cache is retained. See the
[validation report](https://github.com/mstan/MetroidPrimeHuntersRecomp/blob/v0.6.10-linux.1/docs/ISSUE-43-steamos-validation.md) for details.

SHA-256:
`186ceab57887e921673ec31e644f1bfbcdadd13325083c37a337660a1daa2c6e`
