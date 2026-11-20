Metroid Prime Hunters Recomp v0.8.2 - source and build notes
================================================================

Title source: https://github.com/mstan/MetroidPrimeHuntersRecomp
Matching release ref: v0.8.2.

Public source revisions:
  Engine: https://github.com/RetroPortingToolKit/ndsrecomp
    369d3a0d39aa149e0b9abff0b2e4850faa6d8a4e
  Shared UI: https://github.com/RetroPortingToolKit/recomp-ui
    a8e6d5e6e673fa34db9104cc10c574c54c68082b
  ARM core: the engine's external/arm-recomp-core submodule
    90b6c510a7471c9c7146c0e8c8f5d9e6d7b13e57
  FreeBIOS: the engine's third_party/freebios submodule
    6d6cfb4953924e4abdaa130aedf71826a055508e

The runner links vendored melonDS and is a GPL-3.0-or-later combined work.
See LICENSE-GPL, licenses/ndsrecomp-ATTRIBUTION.md and licenses/ for the full
notices. Other components retain their respective licenses.

Native SDK source: https://github.com/lioncash/dynarmic at
  a41c380246d3d9f9874f0f792d234dc0cc17c180
Apply the selected engine's runner/cmake patches in this order:
  dynarmic-readonly-pages.patch
  dynarmic-cold-register-allocation.patch
  dynarmic-prepared-blocks.patch
  dynarmic-observation-callbacks.patch
Follow the selected engine docs/dynarmic-sdk.md for the public reproducible
recipe, expected patched tree and feature/ABI checks. Pass that isolated source
explicitly as -DynarmicRoot; no private commit is required. Published stores
remain OFF for this profile. Dependency notices ship with the package; the SDK
is absent from the separate Reference build.

Build requirements: Windows x64 MinGW-w64 GCC 15.2, CMake/Ninja, SDL and Python,
plus your own supported cartridge dump. Generate title/system banks with the
title tools and engine bios/ instructions. ROMs, BIOS/firmware dumps, saves,
private captures and generated title C are not distributed. Omit
NDS_PREBUILT_BANK_ARCHIVE when compiling your own generated banks.

Enhanced runner profile:
  CMAKE_BUILD_TYPE=Release; NDS_SDL_BACKEND=SDL3
  NDS_ACCELERATED_RENDERER=OPENGL; NDS_ENABLE_COMPUTE_RENDERER=ON
  NDS_3D_GEOMETRY=NATIVE; NDS_ARM9_OBSERVATION_SERVICE=ON
  NDS_OFFLINE_ARM7=ON; NDS_WHOLE_ASSETS=ON; NDS_NATIVE_PUBLISHED_STORES=OFF
  NDS_MPH_PERFORMANCE=ON
  NDS_MPH_MATH_IMPLEMENTATION=HLE; NDS_MPH_SUBMIT_IMPLEMENTATION=HLE
  NDS_GX_COMMAND_CACHE=ON; NDS_BOOTSTRAP_FIRMWARE=ON
  NDS_TITLE_ROM_SHA1=90164d1ac127ee5f9815ea4ae7de798c7b5fc629

Use tools/build-windows.ps1 -Version 0.8.2 -PerformanceBackend ON
-DynarmicRoot <SDK prepared using docs/dynarmic-sdk.md> with the matching engine/UI sources.
Build the separate Reference runner with -PerformanceBackend OFF; that forces
SDK, native geometry, ARM9 observation, native ARM7, whole-assets and title HLE
off. Its launcher uses NDS_RUNNER_FILENAME=nds_runner_lle.exe and native flags
OFF. The enhanced launcher uses the default runner filename and native flags ON.
Use -SkipPackage when building artifacts separately; then pass both enhanced
and Reference runner/launcher directories to tools/make_release.ps1.

Wireless & online play is always on; it is not a setting. Each launcher runs
its own engine online and offline (the enhanced engine keeps only the original
ARM7 wireless driver while connected). Both engines share ROM selection,
firmware, cartridge saves and launcher preferences. Graphics retain adaptive
Fit to screen and the selected graphics quality.
Save states are build-specific; native in-game save progress is preserved.
Online interoperability remains experimental.

The package intentionally omits old prebuilt shard caches. The matching
embedded CPython 3.13.1/TinyCC 0.9.27/recompiler provider, runtime headers and
dependency notices are bundled. Package with -AllowNoShardCache and do not
use -SkipOverlayToolchain. Player-generated cache state remains private.
TinyCC source: https://download.savannah.gnu.org/releases/tinycc/tcc-0.9.27.tar.bz2
Its full matching COPYING is included beside the bundled compiler.

Bundled live-overlay recompiler is the retained separately qualified tool from
engine source 85811e5776e4c2bcbfac132a19164fb5f4e9aeff, codegen identity
nds-codegen-v3. Its executable SHA-256 is
c3afd4279572be5802f6f125a8e4bf7dadc8beb8ad8342bb801fcd0eb8c42639.
It uses the matching runtime_arm.h shipped alongside it; the later engine
merge does not change that runtime interface or regenerate title banks.
