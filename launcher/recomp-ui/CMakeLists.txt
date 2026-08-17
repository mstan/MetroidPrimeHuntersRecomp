cmake_minimum_required(VERSION 3.24)
project(mph_recomp_ui_launcher C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(SDL2 CONFIG REQUIRED)

set(NDSRECOMP_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../ndsrecomp" CACHE PATH
    "Path to the ndsrecomp framework checkout (for the shared SHA-1 helper)")
set(MPH_LAUNCHER_ROM_SHA1
    "90164d1ac127ee5f9815ea4ae7de798c7b5fc629" CACHE STRING
    "Exact retail ROM SHA-1 accepted by this profile-specific launcher")
set(MPH_LAUNCHER_REGION "USA" CACHE STRING
    "Region label shown by the profile-specific launcher")

add_executable(mph-recomp-ui launcher_main.cpp
    "${NDSRECOMP_ROOT}/recompiler/support/sha1.cpp")
target_include_directories(mph-recomp-ui PRIVATE
    "${NDSRECOMP_ROOT}/recompiler/support")
target_compile_definitions(mph-recomp-ui PRIVATE
    MPH_LAUNCHER_ROM_SHA1="${MPH_LAUNCHER_ROM_SHA1}"
    MPH_LAUNCHER_REGION="${MPH_LAUNCHER_REGION}")
target_link_libraries(mph-recomp-ui PRIVATE SDL2::SDL2)

set(RECOMP_UI_ROOT "F:/Projects/recomp-ui" CACHE PATH
    "Path to the shared recomp-ui checkout")

enable_testing()
add_executable(mph-mod-provider-test tests/launcher_mod_provider_test.cpp
    "${NDSRECOMP_ROOT}/recompiler/support/sha1.cpp")
# The test #includes launcher_main.cpp whole, so it needs the SAME sha1.h the
# launcher gets -- ndsrecomp's gba::sha1, not recomp-ui/src/common/sha1.h,
# which is a different API and would be picked up first from the include path
# below. Listed ahead of the recomp-ui directories for that reason.
target_include_directories(mph-mod-provider-test PRIVATE
    "${NDSRECOMP_ROOT}/recompiler/support"
    "${CMAKE_CURRENT_SOURCE_DIR}"
    "${RECOMP_UI_ROOT}/src"
    "${RECOMP_UI_ROOT}/src/common")
target_compile_definitions(mph-mod-provider-test PRIVATE
    MPH_RECOMP_UI_NO_MAIN
    MPH_LAUNCHER_ROM_SHA1="${MPH_LAUNCHER_ROM_SHA1}"
    MPH_LAUNCHER_REGION="${MPH_LAUNCHER_REGION}")

set(RECOMP_UI_SDL3 OFF)
set(RECOMP_UI_ENABLE_MODS ON CACHE BOOL "" FORCE)
include("${RECOMP_UI_ROOT}/recomp_ui.cmake")
recomp_target_launcher_ui(mph-recomp-ui CONSOLE nds
    BOXART "${CMAKE_CURRENT_SOURCE_DIR}/assets/boxart.tga")

add_test(NAME mph_mod_provider_test COMMAND mph-mod-provider-test)
