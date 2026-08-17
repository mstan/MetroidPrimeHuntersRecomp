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

# recomp-ui treats any non-empty initial ROM string as selected before it tries
# to open the file.  A release package intentionally contains no ROM, so do not
# feed the conventional filename to the model unless that file really exists.
# This preserves the useful portable behavior where a player may deliberately
# place a ROM with the conventional name beside the executable, while a fresh
# extraction correctly starts at "No ROM loaded".
mph_launcher_replace_required(
    "    char selected_rom[1024]{};\n    const int result = recomp_launcher_run_window("
    "    std::error_code initial_rom_error;\n    const std::string initial_rom =\n        std::filesystem::is_regular_file(default_rom, initial_rom_error)\n            ? default_rom.string()\n            : std::string();\n    char selected_rom[1024]{};\n    const int result = recomp_launcher_run_window("
    "the initial ROM selection block")
mph_launcher_replace_required(
    "exe.string().c_str(), default_rom.string().c_str(),"
    "exe.string().c_str(), initial_rom.c_str(),"
    "the launcher initial ROM argument")

set(MPH_PROFILE_LAUNCHER_SOURCE
    "${CMAKE_CURRENT_BINARY_DIR}/launcher_main_profile.cpp")
file(WRITE "${MPH_PROFILE_LAUNCHER_SOURCE}" "${MPH_LAUNCHER_SOURCE}")

# MPH display policy layer. Keep the upstream-tracking launcher source simple,
# but expose the melonPrimeDS/mphCodex game-side projection/culling patch as a
# separate Mods item in the generated launcher. It defaults OFF; the existing
# Adaptive Widescreen feature remains the original host-side ndsrecomp path.
# The two features are radio-button-like: enabling either disables the other.
execute_process(
    COMMAND "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/../../tools/patch_mph_launcher_aspect_mod.py"
        --source "${MPH_PROFILE_LAUNCHER_SOURCE}"
    RESULT_VARIABLE _mph_aspect_mod_result
    OUTPUT_VARIABLE _mph_aspect_mod_stdout
    ERROR_VARIABLE _mph_aspect_mod_stderr)
if(NOT _mph_aspect_mod_result EQUAL 0)
    message(FATAL_ERROR
        "Failed to add MPH launcher aspect-ratio mod:\n"
        "${_mph_aspect_mod_stdout}${_mph_aspect_mod_stderr}")
endif()
message(STATUS "${_mph_aspect_mod_stdout}")
file(READ "${MPH_PROFILE_LAUNCHER_SOURCE}" MPH_LAUNCHER_SOURCE)

# Configure-time regression guards for the generated launcher. The release must
# start without a fake ROM selection, and the two widescreen mechanisms must
# remain separately addressable while never being enabled together.
string(FIND "${MPH_LAUNCHER_SOURCE}"
    "std::filesystem::is_regular_file(default_rom, initial_rom_error)"
    _mph_initial_rom_exists_guard)
if(_mph_initial_rom_exists_guard EQUAL -1)
    message(FATAL_ERROR "generated launcher lost the default-ROM existence guard")
endif()
string(FIND "${MPH_LAUNCHER_SOURCE}"
    "exe.string().c_str(), initial_rom.c_str(),"
    _mph_initial_rom_argument_guard)
if(_mph_initial_rom_argument_guard EQUAL -1)
    message(FATAL_ERROR "generated launcher still passes the unconditional default ROM path")
endif()
string(FIND "${MPH_LAUNCHER_SOURCE}"
    "mph-game-aspect-ratio-patch"
    _mph_aspect_mod_feature_guard)
if(_mph_aspect_mod_feature_guard EQUAL -1)
    message(FATAL_ERROR "generated launcher lost the Game Aspect Ratio Patch Mods feature")
endif()
string(FIND "${MPH_LAUNCHER_SOURCE}"
    "--mph-aspect-ratio-patch"
    _mph_aspect_mod_arg_guard)
if(_mph_aspect_mod_arg_guard EQUAL -1)
    message(FATAL_ERROR "generated launcher does not pass the guest aspect-ratio policy to nds_runner")
endif()
string(FIND "${MPH_LAUNCHER_SOURCE}"
    "bool aspect_ratio_patch = false;"
    _mph_aspect_mod_default_guard)
if(_mph_aspect_mod_default_guard EQUAL -1)
    message(FATAL_ERROR "Game Aspect Ratio Patch must remain opt-in by default")
endif()
string(FIND "${MPH_LAUNCHER_SOURCE}"
    "MPH_WIDESCREEN_MUTUAL_EXCLUSION"
    _mph_widescreen_exclusion_guard)
if(_mph_widescreen_exclusion_guard EQUAL -1)
    message(FATAL_ERROR "generated launcher lost widescreen mutual-exclusion logic")
endif()
string(FIND "${MPH_LAUNCHER_SOURCE}"
    "if (state->adaptive_widescreen) state->aspect_ratio_patch = false;"
    _mph_adaptive_disables_guest_guard)
if(_mph_adaptive_disables_guest_guard EQUAL -1)
    message(FATAL_ERROR "Adaptive Widescreen no longer disables Game Aspect Ratio Patch")
endif()
string(FIND "${MPH_LAUNCHER_SOURCE}"
    "if (state->aspect_ratio_patch) state->adaptive_widescreen = false;"
    _mph_guest_disables_adaptive_guard)
if(_mph_guest_disables_adaptive_guard EQUAL -1)
    message(FATAL_ERROR "Game Aspect Ratio Patch no longer disables Adaptive Widescreen")
endif()
string(FIND "${MPH_LAUNCHER_SOURCE}"
    "((adaptive && !mods.aspect_ratio_patch) ? L\"top\" : L\"none\")"
    _mph_runner_exclusion_guard)
if(_mph_runner_exclusion_guard EQUAL -1)
    message(FATAL_ERROR "runner launch path can pass both widescreen implementations")
endif()

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
# The baseline provider test still covers the upstream-tracking source. The
# generated launcher itself is compiled above and guarded for the additional
# MPH aspect-ratio feature at configure time.
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