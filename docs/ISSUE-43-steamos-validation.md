# Issue 43: SteamOS AppImage startup

Validated 2026-09-06 against the local v0.5.0 and v0.6.10 release AppImages.
Public report: [issue 43](https://github.com/mstan/MetroidPrimeHuntersRecomp/issues/43).

## Cause and fix

v0.6.10 bundles Python's Readline extension and its older `libreadline.so.8`.
`AppRun` previously exported the AppImage's entire `usr/lib` directory through
`LD_LIBRARY_PATH`. On a host whose `/bin/sh` is a newer Bash linked to Readline,
the shell loaded the incompatible packaged library. The Python wrapper used
for initial shard-cache seeding then failed before the launcher opened:

```text
/bin/sh: symbol lookup error: /bin/sh: undefined symbol: rl_trim_arg_from_keyseq
```

v0.5.0 has no bundled Readline and passes the same host-shell probe.

`tools/fix_linux_appdir_runtime.sh` removes that global export and gives
packaged executables and the original nested Python extensions relative ELF
library paths. Host child processes inherit the original caller environment.
Paths are calculated from each ELF directory rather than hardcoded by depth.
The helper refreshes TinyCC's wrapper identity after modifying its binary and
skips already-correct library paths. Packaging invokes it before staging and
after linuxdeploy; the Steam Deck build container now installs `patchelf`.

Removing only the global export is insufficient: linuxdeploy had patched
copies of Python extensions under `usr/lib`, while Python imports the original
copies under `overlay_toolchain/python/lib/python3.10/lib-dynload`.

## Independent validation

Tests ran through WSL2 Ubuntu 24.04.1. The Arch shell test used official
`archlinux:base`, image digest
`sha256:82b1b08faae9d61e3e7e13d562f4d09114d939105b0d59ff34140f3bd418593a`,
with Bash 5.3.15 and `/bin/sh -> /usr/bin/bash`. This exercises the reported
library mismatch; it is not a physical Steam Deck or a full SteamOS image.

| Check | Result |
| --- | --- |
| Host shell with original v0.5.0 `usr/lib` | Passed |
| Host shell with original v0.6.10 `usr/lib` | Exact reported error, exit 127 |
| Original v0.6.10 `AppRun --help` in Arch | Exact error during cache seed, exit 1 |
| Repaired `AppRun --help`, empty environment, AppDir/state paths with spaces | Passed; cache and BIOS README seeded |
| Bundled Python: Readline, curses, SSL, SQLite, bz2, lzma, ctypes, zlib | All imported in Arch without `LD_LIBRARY_PATH` |
| Bundled Python spawning host `/bin/sh` | Passed; `/proc/self/maps` confirmed Python itself used bundled Readline |
| Recompiler codegen identity | Passed (`nds-codegen-v3`) |
| WSL `tools/test_appimage_layout.sh` | Passed |
| Updated layout test against untouched v0.6.10 | Rejected missing nested RPATH as expected |
| No-toolchain repair with no `patchelf` on PATH | Passed |
| Bash syntax checks and `tools/test_linux_release_shards.py` | Passed |
| Real launcher in Ubuntu 22.04 builder with Xvfb | Remained running for 8 seconds; intentional timeout 124; cache/BIOS seeded |
| Helper applied twice to real release AppDir | Entire file-hash inventory unchanged on second application |
| Main runner and launcher hashes before/after repair | Unchanged |
| Repacked AppImage, Arch `--appimage-extract-and-run --help`, path with spaces | Passed; cache/BIOS seeded |

GPT-5.5 implementation and review agents were independently challenged by the
parent. Review required nested-extension paths and both startup branches,
checked identity refresh ordering, and corrected an initially suggested
off-by-one relative path before accepting computed paths.

## Local test artifact

`release-linux-steamdeck/MetroidPrimeHuntersRecomp-linux-v0.6.10-issue43-x86_64.AppImage`

SHA-256:
`186ceab57887e921673ec31e644f1bfbcdadd13325083c37a337660a1daa2c6e`

This is the actual local v0.6.10 release repacked with the runtime-path repair,
using its original AppImage runtime. The game/launcher binaries and prebuilt
shards are retained; it is not a newly compiled game release. A companion
`.sha256` file is beside it. No release was published and no GitHub comment or
issue state was changed. Steam Deck hardware confirmation remains outstanding.

## Separate existing TinyCC limitation

A minimal TinyCC `-shared` compile on Arch fails to locate `crti.o`/`crtn.o`
with **both** the untouched and repaired v0.6.10 runtime. Arch provides them
in `/usr/lib`, while the bundled Ubuntu compiler expects different CRT search
paths. A minimal `-nostdlib` probe succeeds for both; that does not validate
actual live-shard compilation and is not a shipped workaround. The same
normal compile smoke passes under WSL Ubuntu.

This does not cause the reported startup failure. Track live-compilation
portability separately as central Beads `beads-lqa.45`; startup work is
`beads-lqa.43`. Central Beads updates were saved locally, but `bd dolt push`
failed because the configured remote Dolt ref was not found.
