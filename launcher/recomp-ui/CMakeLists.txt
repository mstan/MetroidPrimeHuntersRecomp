cmake_minimum_required(VERSION 3.24)
project(mph_recomp_ui_launcher C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(SDL2 CONFIG REQUIRED)
find_package(Python3 COMPONENTS Interpreter REQUIRED)

set(NDSRECOMP_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../ndsrecomp" CACHE PATH
    "Path to the ndsrecomp framework checkout (for the shared SHA-1 helper)")
set(MPH_LAUNCHER_ROM_SHA1
    "90164d1ac127ee5f9815ea4ae7de798c7b5fc629" CACHE STRING
    "Clean retail ROM SHA-1 metadata rendered for this profile-specific launcher")
set(MPH_LAUNCHER_REGION "USA" CACHE STRING
    "Region label shown by the profile-specific launcher")
set(MPH_LAUNCHER_DEFAULT_ROM "Metroid Prime Hunters.nds" CACHE STRING
    "Default ROM filename offered by this profile-specific launcher")

# launcher_main.cpp tracks the current upstream launcher, including HD Rendering
# and persistent firmware/WFC state. Generate a profile-specific TU with only
# the multi-ROM identity transformations layered on top. Runtime acceptance is
# deliberately NOT an exact whole-ROM SHA gate; nds_runner owns the
# executable-compatibility + actual-content decision.
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/launcher_main.cpp" MPH_LAUNCHER_SOURCE)

function(mph_launcher_replace_required old new description)
    string(FIND "${MPH_LAUNCHER_SOURCE}" "${old}" _mph_replace_pos)
    if(_mph_replace_pos EQUAL -1)
        message(FATAL_ERROR
            "launcher_main.cpp no longer contains ${description}")
    endif()
    string(REPLACE "${old}" "${new}"
        _mph_replaced_source "${MPH_LAUNCHER_SOURCE}")
    set(MPH_LAUNCHER_SOURCE "${_mph_replaced_source}" PARENT_SCOPE)
endfunction()

mph_launcher_replace_required(
    "90164d1ac127ee5f9815ea4ae7de798c7b5fc629"
    "${MPH_LAUNCHER_ROM_SHA1}"
    "the US1.0 clean SHA-1 metadata")
mph_launcher_replace_required(
    "game.known_sha1_hex = sha1;\n    game.num_known_sha1 = std::size(sha1);"
    "// MPH_MULTIROM_CONTENT_GATE: recomp-ui must not reject a modified ROM\n    // before nds_runner can apply the base/executable compatibility detector.\n    // The runner remains the authoritative fail-closed content gate.\n    game.known_sha1_hex = nullptr;\n    game.num_known_sha1 = 0;"
    "the recomp-ui whole-ROM SHA-1 gate")
mph_launcher_replace_required(
    "game.region = \"USA\";"
    "game.region = \"${MPH_LAUNCHER_REGION}\";"
    "the USA region baseline")
mph_launcher_replace_required(
    "exe / \"Metroid Prime Hunters.nds\";"
    "exe / \"${MPH_LAUNCHER_DEFAULT_ROM}\";"
    "the default MPH ROM filename")

set(MPH_PROFILE_LAUNCHER_SOURCE
    "${CMAKE_CURRENT_BINARY_DIR}/launcher_main_profile.cpp")
file(WRITE "${MPH_PROFILE_LAUNCHER_SOURCE}" "${MPH_LAUNCHER_SOURCE}")

add_executable(mph-recomp-ui "${MPH_PROFILE_LAUNCHER_SOURCE}"
    "${NDSRECOMP_ROOT}/recompiler/support/sha1.cpp")
target_include_directories(mph-recomp-ui PRIVATE
    "${NDSRECOMP_ROOT}/recompiler/support"
    "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(mph-recomp-ui PRIVATE SDL2::SDL2)

set(RECOMP_UI_ROOT "F:/Projects/recomp-ui" CACHE PATH
    "Path to the shared recomp-ui checkout")
option(MPH_PATCH_RECOMP_UI_MULTIROM
    "Patch pinned recomp-ui so fingerprint-free MPH ROMs show runtime-delegated validation"
    ON)
set(_mph_recomp_ui_imgui
    "${RECOMP_UI_ROOT}/src/common/backends/imgui/launcher_imgui.cpp")
if(MPH_PATCH_RECOMP_UI_MULTIROM AND EXISTS "${_mph_recomp_ui_imgui}")
    execute_process(
        COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/../../tools/patch_recomp_ui_mph_multirom.py"
            --recomp-ui-root "${RECOMP_UI_ROOT}"
        RESULT_VARIABLE _mph_recomp_ui_patch_result
        OUTPUT_VARIABLE _mph_recomp_ui_patch_stdout
        ERROR_VARIABLE _mph_recomp_ui_patch_stderr)
    if(NOT _mph_recomp_ui_patch_result EQUAL 0)
        message(FATAL_ERROR
            "Failed to apply MPH multi-ROM recomp-ui patch:\n"
            "${_mph_recomp_ui_patch_stdout}${_mph_recomp_ui_patch_stderr}")
    endif()
    message(STATUS "${_mph_recomp_ui_patch_stdout}")
elseif(MPH_PATCH_RECOMP_UI_MULTIROM)
    # Static launcher-profile tests intentionally provide a minimal recomp-ui
    # CMake stub and do not compile the UI backend. A real launcher build has
    # the pinned source above and must take the fail-closed patch path.
    message(STATUS
        "MPH recomp-ui presentation patch skipped: UI backend source is not present")
endif()

enable_testing()
add_executable(mph-mod-provider-test tests/launcher_mod_provider_test.cpp
    "${NDSRECOMP_ROOT}/recompiler/support/sha1.cpp")
# The test #includes launcher_main.cpp whole, so it needs ndsrecomp's sha1.h.
target_include_directories(mph-mod-provider-test PRIVATE
    "${NDSRECOMP_ROOT}/recompiler/support"
    "${CMAKE_CURRENT_SOURCE_DIR}"
    "${RECOMP_UI_ROOT}/src"
    "${RECOMP_UI_ROOT}/src/common")
target_compile_definitions(mph-mod-provider-test PRIVATE
    MPH_RECOMP_UI_NO_MAIN)

set(RECOMP_UI_SDL3 OFF)
set(RECOMP_UI_ENABLE_MODS ON CACHE BOOL "" FORCE)
include("${RECOMP_UI_ROOT}/recomp_ui.cmake")
recomp_target_launcher_ui(mph-recomp-ui CONSOLE nds
    BOXART "${CMAKE_CURRENT_SOURCE_DIR}/assets/boxart.tga")

add_test(NAME mph_mod_provider_test COMMAND mph-mod-provider-test)
