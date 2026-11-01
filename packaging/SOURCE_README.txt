Metroid Prime Hunters Recomp v0.7.12-alpha - source and build notes
=================================================================

Title source: https://github.com/mstan/MetroidPrimeHuntersRecomp
Declared matching release ref: v0.7.12-alpha.
Before that tag is published, use branch fix/launcher-bindings-20261031 (PR49).

Public source revisions:
  Engine: https://github.com/RetroPortingToolKit/ndsrecomp
    release/native-hle-v0.6.11 at 179ac63d9e4055e1218d61b3fd03c34a94880a6e
  Shared UI: https://github.com/mstan/recomp-ui
    3f1d6f122a58823614abce14f5b86f4d165a629c
  ARM core: the engine's external/arm-recomp-core submodule
    90b6c510a7471c9c7146c0e8c8f5d9e6d7b13e57
  FreeBIOS: the engine's third_party/freebios submodule
    6d6cfb4953924e4abdaa130aedf71826a055508e

The runner links vendored melonDS and is a GPL-3.0-or-later combined work.
See LICENSE-GPL, licenses/ndsrecomp-ATTRIBUTION.md and licenses/ for the full
notices. Other components retain their respective licenses.

Native SDK source: https://github.com/lioncash/dynarmic at
  a41c380246d3d9f9874f0f792d234dc0cc17c180
Apply the four patches tracked in the selected engine's runner/cmake, in order:
  dynarmic-readonly-pages.patch
  dynarmic-cold-register-allocation.patch
  dynarmic-prepared-blocks.patch
  dynarmic-published-stores.patch
Use this patched source as NDS_ARM9_DYNARMIC_ROOT. The selected SDK archive
SHA-256 is 6a843c4287f5b6519cd27de38d26e1593ccad8a9c6329e5cf52cfd0867f576b8;
its dependency licenses are included. The archive is a build input, not a
replacement for the corresponding public source and patchset.

Build requirements: Windows x64 MinGW-w64 GCC 15.2, CMake/Ninja, SDL and Python,
plus your own supported cartridge dump. Generate title/system banks with the
title tools and the engine bios/ instructions. Retail ROM or BIOS/firmware
dumps, saves, private captured pages and generated title C are not distributed.
For your own build omit NDS_PREBUILT_BANK_ARCHIVE and compile locally generated
banks. The release retains verified O2 title banks; it does not select bank O3.

Selected native runner profile (engine runner/CMakeLists.txt):
  CMAKE_BUILD_TYPE=Release; NDS_SDL_BACKEND=SDL3
  NDS_ACCELERATED_RENDERER=OPENGL; NDS_ENABLE_COMPUTE_RENDERER=ON
  NDS_CORE_IPO=OFF; NDS_PGO_MODE=OFF
  NDS_MPH_PERFORMANCE=ON
  NDS_MPH_MATH_IMPLEMENTATION=HLE; NDS_MPH_SUBMIT_IMPLEMENTATION=HLE
  NDS_ARM7_NATIVE=ON; NDS_NATIVE_CONTROL=ON
  NDS_NATIVE_PRECISE_WRITES=ON; NDS_NATIVE_PUBLISHED_STORES=ON
  NDS_MKDS_PERFORMANCE=OFF; NDS_MKDS_IMPLEMENTATION=LLE
  NDS_MKDS_STREAM_IMPLEMENTATION=LLE; NDS_MKDS_CARD_PIO_IMPLEMENTATION=LLE
  NDS_GX_COMMAND_CACHE=ON; NDS_BOOTSTRAP_FIRMWARE=ON
  NDS_CAPTURE_VIEW_REUSE=ON; NDS_LEAN_DIAGNOSTICS=ON
  NDS_TITLE_VERSION=v0.7.12-alpha
  NDS_TITLE_ROM_SHA1=90164d1ac127ee5f9815ea4ae7de798c7b5fc629
  NDS_TITLE_BANK_DIR=<your generated title banks>
  NDS_RECOMP_UI_ROOT=<shared UI source above>
The selected O2 bank archive SHA-256 is
0f1528fd878a494fb2224ec0a0d98091f9cc50203963023791666d5254504707.
MPH remains serial; the MKDS CPU/render handoff profile is not admitted.

Use tools/build-windows.ps1 -Version 0.7.12 -PerformanceBackend ON
-DynarmicRoot <patched SDK> for the supported generation/build pipeline,
with the explicit runner CMake profile above. The portable reference remains
available with PerformanceBackend OFF and the retained LLE service choices.
Build launcher/recomp-ui with NDSRECOMP_ROOT=<selected engine>,
RECOMP_UI_ROOT=<selected UI>, MPH_LAUNCHER_SDL_BACKEND=SDL3,
MPH_NATIVE_PERFORMANCE=ON and MPH_NATIVE_GL_PREVIEW=ON.

Build the selected engine's recompiler for the bundled overlay toolchain.
tools/make_release.ps1 -Version 0.7.12 -RunnerBuildDir <runner>
-LauncherBuildDir <launcher> -NdsrecompRoot <engine> -RecompUiRoot <UI>
-RecompilerBuildDir recompiler/build -ShardCacheDir <compatible cache>
-SdlBackend SDL3 packages the full toolchain and compatible native shard cache.
Do not use SkipOverlayToolchain or AllowNoShardCache for this release.
The selected recompiler uses codegen v3; the cache provider identity is
9111767316e24b622941, with 7 GCC shards. The package includes the pinned
CPython 3.13.1/TCC0.9.27 toolchain, runtime headers and dependency notices.

Graphics default to 4x internal 3D resolution and 8-sample supersample AA.
Native resolution, AA Off and Software remain selectable. Prime/stylus/device
settings are preserved. Save states are build-specific; native in-game save
progress is a separate preserved contract. Online play remains experimental.
