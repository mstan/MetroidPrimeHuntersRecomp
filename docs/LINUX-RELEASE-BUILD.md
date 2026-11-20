# Linux release build: pinned toolchain and compiler cache

Linux release binaries are built in a container so they keep the Ubuntu 22.04
glibc floor. Rebuilding ~1,400 unchanged generated title-bank C files from
scratch takes hours, so the release container now uses a persistent ccache.

## Images

| file | role |
|---|---|
| `packaging/linux/steamdeck.Dockerfile` | Base toolchain recipe. Not run by release builds. |
| `packaging/linux/steamdeck-ccache.Dockerfile` | Release build image: `FROM` the built base, pinned by digest, plus ccache 4.5.1. |
| `packaging/linux/release-toolchain.sha256` | Pinned gcc/g++/cpp, cc1, cc1plus, collect2, lto1, as and ld bytes. |

The pinned base is `mph-linux-release14-builder:ubuntu22.04`
(`sha256:a1b72566cda16446328931505fcc596dcef6807837c95789c7fb8316ad0ccb1d`,
gcc 11.4.0-1ubuntu1~22.04.3, binutils 2.38-4ubuntu2.12). Building the ccache
layer fails if the base's compiler bytes differ from
`release-toolchain.sha256`, or if installing ccache changes any installed
package version or any of the 2,897 files of the toolchain packages.

Rebuilding `steamdeck.Dockerfile` resolves `ubuntu:22.04` and apt afresh, so
it yields a new compiler. Treat that as a deliberate toolchain change: build
and tag the new base, then update `BASE_IMAGE` in the ccache Dockerfile and
`release-toolchain.sha256` in the same change.

## Running builds

`tools/run-linux-release-container.ps1` defines the container once: the
image, the `/work/mph`, `/work/ndsrecomp` and `/work/recomp-ui` mounts, the
compiler cache, and extra read-only git mounts so the framework build id
(`NdsBuildIdScript.cmake`) resolves the real commit and clean state. Both
`tools/build-linux-steamdeck.ps1` and step-wise release scripts use it:

```powershell
tools\run-linux-release-container.ps1 -ScriptsDir <steps> -BiosDir <bios> `
  -Env JOBS=8 -Command bash,/scripts/build-title-banks.sh
```

Compiler cache options (both scripts): `-CompilerCacheDir` (default
`$env:MPH_LINUX_CCACHE_DIR`, else `F:\ccache-linux`; the system drive is
refused), `-CompilerCacheMaxSize` (default `40G`), `-NoCompilerCache`. The
container gets `CCACHE_DIR=/ccache`, `CCACHE_NOHASHDIR=1` and
`CCACHE_MAXSIZE`; each run zeroes and then prints the ccache statistics.

`CCACHE_BASEDIR` is deliberately not set. Every worktree is mounted at the
same `/work/...` paths, so cache keys are already worktree-independent.
Setting `base_dir=/work` makes ccache pass gcc relative paths, which changes
`__FILE__` strings (libslirp's `g_warn_if_fail`/`g_warn_if_reached`
messages) and therefore the runner bytes compared with an uncached build.
