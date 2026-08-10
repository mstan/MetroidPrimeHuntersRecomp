cmake_minimum_required(VERSION 3.20)
project(MetroidPrimeHuntersRecomp VERSION 0.0.0 LANGUAGES C CXX)

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

set(MPH_ROM "${CMAKE_CURRENT_SOURCE_DIR}/Metroid Prime Hunters.nds"
    CACHE FILEPATH "Path to the verified USA AMHE revision-0 ROM")
set(MPH_GENERATED_DIR "${CMAKE_CURRENT_SOURCE_DIR}/generated")
set(MPH_INPUT_DIR "${MPH_GENERATED_DIR}/inputs")
set(MPH_RECOMP_DIR "${MPH_GENERATED_DIR}/recomp")
set(MPH_COVERAGE_SEEDS
    "${CMAKE_CURRENT_SOURCE_DIR}/coverage/adventure-main-entry-points.json")

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
    DEPENDS "${MPH_ROM}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_mph.py"
            "${MPH_COVERAGE_SEEDS}"
    COMMENT "Verifying AMHE0 and preparing main/overlay code images")
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
    COMMENT "Discovering and recompiling the AMHE0 ARM9 main closure")

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
    COMMENT "Discovering and recompiling the AMHE0 ARM7 initial closure")

add_custom_target(mph_generate_banks
    DEPENDS "${MPH_ARM9_STAMP}" "${MPH_ARM7_STAMP}")
add_library(mph_recompiled_banks STATIC
    ${MPH_ARM9_SOURCES} ${MPH_ARM7_SOURCES})
add_dependencies(mph_recompiled_banks mph_generate_banks)
ndsrecomp_limit_generated_compiles(mph_recompiled_banks)
ndsrecomp_limit_link(mph_recompiled_banks)
set_source_files_properties(${MPH_ARM9_SOURCES}
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
if(NOT MSVC)
    target_compile_options(mph_romcheck PRIVATE -Wall -Wextra)
endif()

add_custom_target(metroidprimehuntersrecomp
    DEPENDS mph_romcheck mph_recompiled_banks)
