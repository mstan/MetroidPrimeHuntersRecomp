# SDL3 first-target adoption

## Goal

Metroid Prime Hunters is the first title worktree consuming the ndsrecomp SDL3
default. The title build should use SDL3 for both the shared runner and the
recomp-ui launcher unless a developer explicitly selects SDL2.

## Build contract

- `tools/build-windows.ps1` defaults `-SdlBackend SDL3`.
- `tools/build-linux.sh` defaults `--sdl-backend SDL3`.
- The launcher CMake option is `MPH_LAUNCHER_SDL_BACKEND=SDL3|SDL2`.
- The runner option remains the framework-level `NDS_SDL_BACKEND=SDL3|SDL2`.
- Windows packaging stages `SDL3.dll` by default and stages `SDL2.dll` only
  when `-SdlBackend SDL2` is selected.
- The Steam Deck AppImage container remains on Ubuntu 22.04 for the older
  glibc floor and builds a pinned SDL3 from source; `libsdl2-dev` remains
  installed for explicit SDL2 fallback builds.

## Validation target

The first practical validation is the standalone launcher CMake target because
it exercises recomp-ui's SDL3 backend without requiring the private ROM or
generated title-bank artifacts:

```powershell
& C:\msys64\mingw64\bin\cmake.exe -G Ninja `
  -S F:\Projects\ndsrecomp\worktrees\mph-sdl3-default\launcher\recomp-ui `
  -B F:\Projects\ndsrecomp\worktrees\mph-sdl3-default\launcher\recomp-ui\build-sdl3-default `
  -DCMAKE_BUILD_TYPE=Release `
  -DNDSRECOMP_ROOT=F:\Projects\ndsrecomp\worktrees\ndsrecomp-sdl3-default `
  -DRECOMP_UI_ROOT=F:\Projects\recomp-ui `
  -DCMAKE_PREFIX_PATH=C:\msys64\mingw64\lib\cmake
& C:\msys64\mingw64\bin\cmake.exe --build `
  F:\Projects\ndsrecomp\worktrees\mph-sdl3-default\launcher\recomp-ui\build-sdl3-default `
  --target mph-recomp-ui -j 12
```
