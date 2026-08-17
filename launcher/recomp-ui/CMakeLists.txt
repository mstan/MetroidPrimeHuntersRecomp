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
    "Clean retail ROM SHA-1 metadata rendered for this profile-specific launcher")
set(MPH_LAUNCHER_REGION "USA" CACHE STRING
    "Region label shown by the profile-specific launcher")
set(MPH_LAUNCHER_DEFAULT_ROM "Metroid Prime Hunters.nds" CACHE STRING
    "Default ROM filename offered by this profile-specific launcher")
option(MPH_LAUNCHER_ADAPTIVE_WIDESCREEN
    "Expose and allow the title-specific adaptive widescreen enhancement" ON)

# Keep launcher_main.cpp as the readable US1.0 baseline, but compile a
# profile-specific generated TU. Every replacement below is preimage-guarded:
# if the baseline launcher changes, configure fails instead of silently
# applying a stale multi-ROM/upstream transformation.
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

if(MPH_LAUNCHER_ADAPTIVE_WIDESCREEN)
    set(_mph_adaptive_literal "true")
    set(_mph_mod_count "2")
else()
    set(_mph_adaptive_literal "false")
    set(_mph_mod_count "1")
endif()

mph_launcher_replace_required(
    "90164d1ac127ee5f9815ea4ae7de798c7b5fc629"
    "${MPH_LAUNCHER_ROM_SHA1}"
    "the US1.0 SHA-1 baseline")
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
mph_launcher_replace_required(
    "bool adaptive_widescreen = true;"
    "bool adaptive_widescreen = ${_mph_adaptive_literal};"
    "the adaptive-widescreen default")
mph_launcher_replace_required(
    "int mod_feature_count(void*) {\n    return 2;\n}"
    "int mod_feature_count(void*) {\n    return ${_mph_mod_count};\n}"
    "the two-feature mod count")
mph_launcher_replace_required(
    "if (!context || !output || index < 0 || index > 1) return 0;\n    const auto* state = static_cast<const ModState*>(context);"
    "if (!context || !output || index < 0 || index >= ${_mph_mod_count}) return 0;\n    if (!${_mph_adaptive_literal}) ++index;\n    const auto* state = static_cast<const ModState*>(context);"
    "the mod feature index guard")
mph_launcher_replace_required(
    "if (std::strcmp(package_id, \"mph-adaptive-widescreen\") == 0 &&\n        std::strcmp(feature_id, \"adaptive-widescreen\") == 0) {\n        state->adaptive_widescreen = enabled != 0;\n        return 1;\n    }"
    "if (std::strcmp(package_id, \"mph-adaptive-widescreen\") == 0 &&\n        std::strcmp(feature_id, \"adaptive-widescreen\") == 0) {\n        if (!${_mph_adaptive_literal}) {\n            state->adaptive_widescreen = false;\n            return 0;\n        }\n        state->adaptive_widescreen = enabled != 0;\n        return 1;\n    }"
    "the adaptive-widescreen enable handler")
mph_launcher_replace_required(
    "load_mod_state(mod_state);\n    RecompLauncherCModProvider mod_provider = make_mod_provider(&mod_state);"
    "load_mod_state(mod_state);\n    if (!${_mph_adaptive_literal}) mod_state.adaptive_widescreen = false;\n    RecompLauncherCModProvider mod_provider = make_mod_provider(&mod_state);"
    "the post-load mod-state initialization")
mph_launcher_replace_required(
    "const std::wstring rom_wide = widen(rom);\n    if (rom_wide.empty()) return false;"
    "const std::wstring rom_wide = widen(rom);\n    if (rom_wide.empty()) return false;\n    adaptive = adaptive && ${_mph_adaptive_literal};"
    "the runner launch profile gate")

# Upstream 5abcfee: persist mutable DS firmware/WFC state across launches.
# This is injected into the generated profile TU so the readable baseline can
# remain stable while all region launchers receive the same behavior.
mph_launcher_replace_required(
    "    return text;\n}\n\ntemplate <size_t N>\nvoid copy_text"
    "    return text;\n}\n\nstd::filesystem::path firmware_state_path(\n    const std::filesystem::path& settings_path, bool generated) {\n    return settings_path.parent_path() /\n        (generated ? \"firmware-generated.bin\" : \"firmware-retail.bin\");\n}\n\nstd::string read_firmware_state_mac(const std::filesystem::path& path) {\n    std::ifstream file(path, std::ios::binary);\n    if (!file) return {};\n    file.seekg(0x36, std::ios::beg);\n    unsigned char mac[6]{};\n    file.read(reinterpret_cast<char*>(mac), sizeof(mac));\n    if (file.gcount() != static_cast<std::streamsize>(sizeof(mac)) ||\n        (mac[0] & 0x01u))\n        return {};\n    char text[32];\n    std::snprintf(text, sizeof(text), \"%02X:%02X:%02X:%02X:%02X:%02X\",\n                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);\n    return text;\n}\n\ntemplate <size_t N>\nvoid copy_text"
    "the upstream firmware-state helper insertion point")
mph_launcher_replace_required(
    "    }\n\n    std::wstring command =\n        quote(runner.wstring())"
    "    }\n    const std::filesystem::path firmware_state = firmware_state_path(\n        mods.settings_path, no_dumps_mode);\n\n    std::wstring command =\n        quote(runner.wstring())"
    "the upstream firmware-state launch path")
mph_launcher_replace_required(
    "        L\" --network on --wfc on --wfc-provider wiimmfi\";\n    // beads-yjp.16:"
    "        L\" --network on --wfc on --wfc-provider wiimmfi\";\n    append_arg(command, L\"--firmware-state-path\", firmware_state.wstring());\n    // beads-yjp.16:"
    "the upstream firmware-state runner argument")
mph_launcher_replace_required(
    "    // Read-only identity detail for the dashboard ONLINE card. Captured once\n    // at startup: the MAC only changes on the first-ever no-dump launch.\n    const std::string identity_mac = read_identity_mac(\n        mod_state.bios_path.empty()\n            ? mod_state.default_bios_dir\n            : bios_dir_from_setting(mod_state.bios_path.c_str()));\n    const std::string identity_detail =\n        !identity_mac.empty()\n            ? \"Console MAC: \" + identity_mac + \" (generated identity)\"\n            : std::string(\"Console MAC: from the firmware dump, or created \"\n                          \"on the first no-dump launch.\");"
    "    // Read-only identity detail for the dashboard ONLINE card. Prefer the\n    // mutable profile once it has been seeded; generated mode falls back to\n    // the installation identity before that first launch.\n    const std::filesystem::path selected_bios =\n        mod_state.bios_path.empty()\n            ? mod_state.default_bios_dir\n            : bios_dir_from_setting(mod_state.bios_path.c_str());\n    bool generated_identity = false;\n    if (mod_state.bios_path.empty()) {\n        bool conventional_dumps = true;\n        for (const NdsDump& dump : kNdsDumps) {\n            if (!std::filesystem::is_regular_file(selected_bios / dump.file))\n                conventional_dumps = false;\n        }\n        generated_identity = !conventional_dumps;\n    }\n    std::string identity_mac = read_firmware_state_mac(firmware_state_path(\n        mod_state.settings_path, generated_identity));\n    if (identity_mac.empty() && generated_identity)\n        identity_mac = read_identity_mac(selected_bios);\n    const std::string identity_detail =\n        !identity_mac.empty()\n            ? \"Console MAC: \" + identity_mac +\n                  (generated_identity\n                       ? \" (generated identity)\" : \" (firmware profile)\")\n            : std::string(\"Console MAC: from the firmware dump, or created \"\n                          \"on the first no-dump launch.\");"
    "the upstream dashboard firmware identity block")

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

enable_testing()
add_executable(mph-mod-provider-test tests/launcher_mod_provider_test.cpp
    "${NDSRECOMP_ROOT}/recompiler/support/sha1.cpp")
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
