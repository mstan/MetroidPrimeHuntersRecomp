cmake_minimum_required(VERSION 3.20)
project(MetroidPrimeHuntersRecomp VERSION 0.3.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(NDSRECOMP_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../ndsrecomp" CACHE PATH
    "Path to the ndsrecomp framework checkout")
if(NOT EXISTS "${NDSRECOMP_ROOT}/recompiler/CMakeLists.txt")
    message(FATAL_ERROR
        "ndsrecomp framework not found at ${NDSRECOMP_ROOT}. "
        "Pass -DNDSRECOMP_ROOT=<path>.")
endif()

include("${NDSRECOMP_ROOT}/cmake/NdsCompilerCache.cmake")
include("${NDSRECOMP_ROOT}/cmake/NdsJobPools.cmake")
add_subdirectory(
    "${NDSRECOMP_ROOT}/recompiler"
    "${CMAKE_BINARY_DIR}/ndsrecomp-recompiler")

set(MPH_VERSION "US1_0" CACHE STRING
    "Metroid Prime Hunters retail revision profile")
set(MPH_PROFILE_FILE
    "${CMAKE_CURRENT_SOURCE_DIR}/config/mph_rom_profiles.json"
    CACHE FILEPATH "Metroid Prime Hunters ROM profile registry")
if(NOT EXISTS "${MPH_PROFILE_FILE}")
    message(FATAL_ERROR "MPH ROM profile registry not found: ${MPH_PROFILE_FILE}")
endif()
file(READ "${MPH_PROFILE_FILE}" MPH_PROFILES_JSON)
string(JSON MPH_PROFILE_COUNT LENGTH "${MPH_PROFILES_JSON}" profiles)
if(MPH_PROFILE_COUNT LESS 1)
    message(FATAL_ERROR "MPH ROM profile registry contains no profiles")
endif()
math(EXPR _mph_profile_last "${MPH_PROFILE_COUNT} - 1")
set(MPH_PROFILE_KEYS)
foreach(_mph_profile_index RANGE 0 ${_mph_profile_last})
    string(JSON _mph_profile_key MEMBER
        "${MPH_PROFILES_JSON}" profiles ${_mph_profile_index})
    list(APPEND MPH_PROFILE_KEYS "${_mph_profile_key}")
endforeach()
set_property(CACHE MPH_VERSION PROPERTY STRINGS ${MPH_PROFILE_KEYS})
list(FIND MPH_PROFILE_KEYS "${MPH_VERSION}" MPH_PROFILE_INDEX)
if(MPH_PROFILE_INDEX EQUAL -1)
    list(JOIN MPH_PROFILE_KEYS ", " _mph_profile_choices)
    message(FATAL_ERROR
        "Unknown MPH_VERSION '${MPH_VERSION}'. Configured profiles: "
        "${_mph_profile_choices}")
endif()

string(JSON MPH_PROFILE_NAME GET
    "${MPH_PROFILES_JSON}" profiles "${MPH_VERSION}" display_name)
string(JSON MPH_PROFILE_GAME_CODE GET
    "${MPH_PROFILES_JSON}" profiles "${MPH_VERSION}" game_code)
string(JSON MPH_PROFILE_REVISION GET
    "${MPH_PROFILES_JSON}" profiles "${MPH_VERSION}" revision)
string(JSON MPH_PROFILE_ROM_SIZE GET
    "${MPH_PROFILES_JSON}" profiles "${MPH_VERSION}" rom_size)
string(JSON MPH_PROFILE_SHA1 GET
    "${MPH_PROFILES_JSON}" profiles "${MPH_VERSION}" sha1)
string(JSON MPH_PROFILE_COVERAGE GET
    "${MPH_PROFILES_JSON}" profiles "${MPH_VERSION}" coverage)
string(JSON MPH_PROFILE_GAME_CONFIG GET
    "${MPH_PROFILES_JSON}" profiles "${MPH_VERSION}" game_config)
string(JSON MPH_PROFILE_FMV_RUNTIME GET
    "${MPH_PROFILES_JSON}" profiles "${MPH_VERSION}" fmv_runtime)
string(JSON MPH_PROFILE_FMV_RUNTIME_BANK GET
    "${MPH_PROFILES_JSON}" profiles "${MPH_VERSION}" fmv_runtime_bank)

set(MPH_ROM "${CMAKE_CURRENT_SOURCE_DIR}/Metroid Prime Hunters.nds"
    CACHE FILEPATH "Path to the verified ${MPH_PROFILE_NAME} ROM")
set(MPH_GENERATED_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/generated" CACHE PATH
    "Root for ignored generated Metroid Prime Hunters artifacts")
if(MPH_VERSION STREQUAL "US1_0")
    set(MPH_GENERATED_DIR "${MPH_GENERATED_ROOT}")
else()
    set(MPH_GENERATED_DIR "${MPH_GENERATED_ROOT}/${MPH_VERSION}")
endif()
set(MPH_INPUT_DIR "${MPH_GENERATED_DIR}/inputs")
set(MPH_RECOMP_DIR "${MPH_GENERATED_DIR}/recomp")
set(MPH_COVERAGE_SEEDS
    "${CMAKE_CURRENT_SOURCE_DIR}/${MPH_PROFILE_COVERAGE}")
if(NOT EXISTS "${MPH_COVERAGE_SEEDS}")
    message(FATAL_ERROR
        "Coverage seed file for ${MPH_VERSION} not found: ${MPH_COVERAGE_SEEDS}")
endif()

message(STATUS
    "MPH profile ${MPH_VERSION}: ${MPH_PROFILE_NAME}, "
    "${MPH_PROFILE_GAME_CODE} revision ${MPH_PROFILE_REVISION}, "
    "SHA-1 ${MPH_PROFILE_SHA1}")

set(_mph_venv_python "${CMAKE_CURRENT_SOURCE_DIR}/.venv/Scripts/python.exe")
if(EXISTS "${_mph_venv_python}")
    set(MPH_PYTHON "${_mph_venv_python}" CACHE FILEPATH
        "Python interpreter with ndspy installed")
else()
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    set(MPH_PYTHON "${Python3_EXECUTABLE}" CACHE FILEPATH
        "Python interpreter with ndspy installed")
endif()

set(MPH_PREP_OUTPUTS
    "${MPH_INPUT_DIR}/arm9.bin"
    "${MPH_INPUT_DIR}/arm7.bin"
    "${MPH_INPUT_DIR}/arm9.toml"
    "${MPH_INPUT_DIR}/arm7.toml"
    "${MPH_INPUT_DIR}/overlays.json")
add_custom_command(
    OUTPUT ${MPH_PREP_OUTPUTS}
    COMMAND "${MPH_PYTHON}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_mph.py"
            --rom "${MPH_ROM}"
            --out "${MPH_INPUT_DIR}"
            --coverage "${MPH_COVERAGE_SEEDS}"
            --version "${MPH_VERSION}"
            --profiles "${MPH_PROFILE_FILE}"
    DEPENDS "${MPH_ROM}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_mph.py"
            "${MPH_PROFILE_FILE}" "${MPH_COVERAGE_SEEDS}"
    COMMENT "Verifying ${MPH_VERSION} and preparing main/overlay code images")
add_custom_target(mph_prepare DEPENDS ${MPH_PREP_OUTPUTS})

set(MPH_ARM9_SOURCES)
foreach(shard RANGE 0 15)
    if(shard LESS 10)
        set(shard_name "0${shard}")
    else()
        set(shard_name "${shard}")
    endif()
    list(APPEND MPH_ARM9_SOURCES
        "${MPH_RECOMP_DIR}/mph_arm9_${shard_name}.c")
endforeach()
list(APPEND MPH_ARM9_SOURCES
    "${MPH_RECOMP_DIR}/mph_arm9_dispatch.c")

set(MPH_ARM7_SOURCES)
foreach(shard RANGE 0 3)
    set(shard_name "0${shard}")
    list(APPEND MPH_ARM7_SOURCES
        "${MPH_RECOMP_DIR}/mph_arm7_${shard_name}.c")
endforeach()
list(APPEND MPH_ARM7_SOURCES
    "${MPH_RECOMP_DIR}/mph_arm7_dispatch.c")

set(MPH_ARM9_STAMP "${MPH_RECOMP_DIR}/mph_arm9.stamp")
add_custom_command(
    OUTPUT "${MPH_ARM9_STAMP}"
    BYPRODUCTS ${MPH_ARM9_SOURCES} "${MPH_RECOMP_DIR}/mph_arm9.h"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${MPH_RECOMP_DIR}"
    COMMAND $<TARGET_FILE:nds_recompile>
            --config "${MPH_INPUT_DIR}/arm9.toml"
            --bin "${MPH_INPUT_DIR}/arm9.bin"
            --out "${MPH_RECOMP_DIR}"
            --bank mph_arm9
            --shards 16
            --stable-address-shards
            --max-function-bytes 512
            --validate-live-bytes
    COMMAND ${CMAKE_COMMAND} -E touch "${MPH_ARM9_STAMP}"
    DEPENDS nds_recompile ${MPH_PREP_OUTPUTS}
    COMMENT "Discovering and recompiling ${MPH_VERSION} ARM9 main closure")

set(MPH_ARM7_STAMP "${MPH_RECOMP_DIR}/mph_arm7.stamp")
add_custom_command(
    OUTPUT "${MPH_ARM7_STAMP}"
    BYPRODUCTS ${MPH_ARM7_SOURCES} "${MPH_RECOMP_DIR}/mph_arm7.h"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${MPH_RECOMP_DIR}"
    COMMAND $<TARGET_FILE:nds_recompile>
            --config "${MPH_INPUT_DIR}/arm7.toml"
            --bin "${MPH_INPUT_DIR}/arm7.bin"
            --out "${MPH_RECOMP_DIR}"
            --bank mph_arm7
            --shards 4
            --stable-address-shards
            --max-function-bytes 512
            --validate-live-bytes
    COMMAND ${CMAKE_COMMAND} -E touch "${MPH_ARM7_STAMP}"
    DEPENDS nds_recompile ${MPH_PREP_OUTPUTS}
    COMMENT "Discovering and recompiling ${MPH_VERSION} ARM7 initial closure")

set(MPH_FMV_RUNTIME_SOURCES)
set(MPH_FMV_RUNTIME_STAMP)
if(MPH_PROFILE_FMV_RUNTIME)
    set(MPH_FMV_RUNTIME_CONFIG
        "${CMAKE_CURRENT_SOURCE_DIR}/config/${MPH_PROFILE_FMV_RUNTIME_BANK}.toml")
    set(MPH_FMV_RUNTIME_IMAGE
        "${MPH_GENERATED_DIR}/capture/${MPH_PROFILE_FMV_RUNTIME_BANK}.bin"
        CACHE FILEPATH "Deterministic ${MPH_VERSION} FMV ITCM+main-RAM capture")
    if(EXISTS "${MPH_FMV_RUNTIME_CONFIG}" AND EXISTS "${MPH_FMV_RUNTIME_IMAGE}")
        foreach(shard RANGE 0 31)
            if(shard LESS 10)
                set(shard_name "0${shard}")
            else()
                set(shard_name "${shard}")
            endif()
            list(APPEND MPH_FMV_RUNTIME_SOURCES
                "${MPH_RECOMP_DIR}/${MPH_PROFILE_FMV_RUNTIME_BANK}_${shard_name}.c")
        endforeach()
        list(APPEND MPH_FMV_RUNTIME_SOURCES
            "${MPH_RECOMP_DIR}/${MPH_PROFILE_FMV_RUNTIME_BANK}_dispatch.c")
        set(MPH_FMV_RUNTIME_STAMP
            "${MPH_RECOMP_DIR}/${MPH_PROFILE_FMV_RUNTIME_BANK}.stamp")
        add_custom_command(
            OUTPUT "${MPH_FMV_RUNTIME_STAMP}"
            BYPRODUCTS ${MPH_FMV_RUNTIME_SOURCES}
                "${MPH_RECOMP_DIR}/${MPH_PROFILE_FMV_RUNTIME_BANK}.h"
            COMMAND $<TARGET_FILE:nds_recompile>
                    --config "${MPH_FMV_RUNTIME_CONFIG}"
                    --bin "${MPH_FMV_RUNTIME_IMAGE}"
                    --out "${MPH_RECOMP_DIR}"
                    --bank "${MPH_PROFILE_FMV_RUNTIME_BANK}"
                    --shards 32
                    --stable-address-shards
                    --max-function-bytes 512
                    --validate-live-bytes
            COMMAND ${CMAKE_COMMAND} -E touch "${MPH_FMV_RUNTIME_STAMP}"
            DEPENDS nds_recompile "${MPH_FMV_RUNTIME_CONFIG}"
                "${MPH_FMV_RUNTIME_IMAGE}"
            COMMENT "Recompiling content-validated ${MPH_VERSION} ARM9 FMV runtime code")
    else()
        message(STATUS
            "MPH FMV runtime bank disabled for ${MPH_VERSION}: expected "
            "${MPH_FMV_RUNTIME_CONFIG} and ${MPH_FMV_RUNTIME_IMAGE}")
    endif()
else()
    message(STATUS
        "MPH FMV runtime bank disabled for ${MPH_VERSION}: no revision-specific "
        "runtime capture has been validated")
endif()

add_custom_target(mph_generate_banks
    DEPENDS "${MPH_ARM9_STAMP}" "${MPH_ARM7_STAMP}"
        ${MPH_FMV_RUNTIME_STAMP})
add_library(mph_recompiled_banks STATIC
    ${MPH_ARM9_SOURCES} ${MPH_ARM7_SOURCES} ${MPH_FMV_RUNTIME_SOURCES})
add_dependencies(mph_recompiled_banks mph_generate_banks)
ndsrecomp_limit_generated_compiles(mph_recompiled_banks)
ndsrecomp_limit_link(mph_recompiled_banks)
set_source_files_properties(${MPH_ARM9_SOURCES} ${MPH_FMV_RUNTIME_SOURCES}
    PROPERTIES COMPILE_DEFINITIONS "NDS_STATIC_CPU=0")
set_source_files_properties(${MPH_ARM7_SOURCES}
    PROPERTIES COMPILE_DEFINITIONS "NDS_STATIC_CPU=1")
target_include_directories(mph_recompiled_banks PRIVATE
    "${MPH_RECOMP_DIR}"
    "${NDSRECOMP_ROOT}/recompiler/armv4t")
if(NOT MSVC)
    target_compile_options(mph_recompiled_banks PRIVATE -w -O0 -g0)
endif()

add_executable(mph_romcheck
    src/main.cpp
    "${NDSRECOMP_ROOT}/recompiler/support/sha1.cpp")
set_target_properties(mph_romcheck PROPERTIES
    OUTPUT_NAME "MetroidPrimeHuntersRecomp")
target_include_directories(mph_romcheck PRIVATE
    "${NDSRECOMP_ROOT}/recompiler/support")
target_compile_definitions(mph_romcheck PRIVATE
    MPH_BUILD_VERSION="${MPH_VERSION}"
    MPH_EXPECTED_SHA1="${MPH_PROFILE_SHA1}"
    MPH_EXPECTED_GAME_CODE="${MPH_PROFILE_GAME_CODE}"
    MPH_EXPECTED_REVISION=${MPH_PROFILE_REVISION}
    MPH_EXPECTED_SIZE=${MPH_PROFILE_ROM_SIZE})
if(NOT MSVC)
    target_compile_options(mph_romcheck PRIVATE -Wall -Wextra)
endif()

add_custom_target(metroidprimehuntersrecomp
    DEPENDS mph_romcheck mph_recompiled_banks)