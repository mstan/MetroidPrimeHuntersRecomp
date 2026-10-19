Metroid Prime Hunters Recomp v0.7.7-alpha - source and build notes
================================================================

The matching source bundle is attached to the v0.7.7-alpha GitHub release:
https://github.com/mstan/MetroidPrimeHuntersRecomp/releases/tag/v0.7.7-alpha

Public source revisions:
  Title/launcher: mstan/MetroidPrimeHuntersRecomp tag v0.7.7-alpha
  Engine: RetroPortingToolKit/ndsrecomp
    f5f529b4a747e3b265db6f17bddb6f24d39d1297
  Shared UI: mstan/recomp-ui
    41c88ffea852b970af8d50312620b17404e455ad
  ARM core: the engine's external/arm-recomp-core submodule
    705e71b8aff3ad64fe78f77c3c94bd93158554dd
  FreeBIOS: the engine's third_party/freebios submodule
    6d6cfb4953924e4abdaa130aedf71826a055508e

The source bundle includes those trees and vendored melonDS sources/patches.
See framework/THIRD_PARTY_ATTRIBUTION.md for upstream provenance and licenses.
nds_runner is a GPL-3.0-or-later combined work; LICENSE-GPL and licenses/ are
included with the binaries. Other components retain their respective terms.

Build requirements: Windows x64, CMake/Ninja, MinGW-w64 GCC, SDL3, Python,
and a legally obtained US 1.0 cartridge dump (AMHE0), SHA-1:
90164d1ac127ee5f9815ea4ae7de798c7b5fc629
No retail ROM, BIOS/firmware dump, save, captured code page or generated C
source is included. See the title README and CMakeLists.txt for title bank
generation from your own dump and locally acquired coverage inputs.

Release runner settings (normal Release optimization; no PGO):
  NDS_ACCELERATED_RENDERER=OPENGL
  NDS_ENABLE_COMPUTE_RENDERER=ON (shared acceleration infrastructure)
  NDS_MPH_MATH_IMPLEMENTATION=HLE
  NDS_MPH_SUBMIT_IMPLEMENTATION=HLE
  NDS_PGO_MODE=OFF
  NDS_BOOTSTRAP_FIRMWARE=ON
  NDS_TITLE_VERSION=v0.7.7-alpha
  NDS_TITLE_BANK_DIR=<your generated title banks>
  NDS_TITLE_ROM_SHA1=<SHA-1 above>
  NDS_RECOMP_UI_ROOT=<shared UI source>

The release reuses the measured, unchanged generated bank archive after
checking its runtime headers, content hash and full linked bank inventory.
For your own build, omit NDS_PREBUILT_BANK_ARCHIVE and compile your banks.
The connected-region CPU experiment is not part of this release.

Launcher: build title/launcher/recomp-ui with NDSRECOMP_ROOT=<framework>,
RECOMP_UI_ROOT=<shared UI>, MPH_LAUNCHER_SDL_BACKEND=SDL3 and
MPH_NATIVE_GL_PREVIEW=ON. Build framework/recompiler for the overlay toolchain.
title/tools/make_release.ps1 packages the runner, launcher and compatible
prebuilt shard cache. The source bundle's BUILDING.txt gives example commands.

Software rendering remains selectable in the launcher. Developers can build
the LLE math/submission reference with the corresponding IMPLEMENTATION=LLE
settings; the reference paths and their tests remain in the source tree.
