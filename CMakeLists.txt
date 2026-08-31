cmake_minimum_required(VERSION 3.20)
project(MetroidPrimeHuntersRecomp VERSION 0.6.8 LANGUAGES C CXX)

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
# Tier-3 entry points observed while the ROM's own arm7.bin was resident at a
# base no bank declared (beads-lqa.9). Addresses only -- the alias bank images
# are recompiled from arm7.bin itself, so no captured bytes are involved and
# these seeds are safe to commit.
set(MPH_ARM7_ALIAS_SEEDS
    "${CMAKE_CURRENT_SOURCE_DIR}/coverage/arm7-alias-entry-points.json")

if(WIN32)
    set(_mph_venv_python "${CMAKE_CURRENT_SOURCE_DIR}/.venv/Scripts/python.exe")
else()
    set(_mph_venv_python "${CMAKE_CURRENT_SOURCE_DIR}/.venv/bin/python3")
endif()
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
    "${MPH_INPUT_DIR}/arm7_wram_alias.toml"
    "${MPH_INPUT_DIR}/arm7_mainram_alias.toml"
    "${MPH_INPUT_DIR}/overlays.json")
add_custom_command(
    OUTPUT ${MPH_PREP_OUTPUTS}
    COMMAND "${MPH_PYTHON}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_mph.py"
            --rom "${MPH_ROM}"
            --out "${MPH_INPUT_DIR}"
            --coverage "${MPH_COVERAGE_SEEDS}"
            --arm7-alias-coverage "${MPH_ARM7_ALIAS_SEEDS}"
    DEPENDS "${MPH_ROM}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_mph.py"
            "${MPH_COVERAGE_SEEDS}" "${MPH_ARM7_ALIAS_SEEDS}"
    COMMENT "Verifying AMHE0 and preparing main/overlay code images")
add_custom_target(mph_prepare DEPENDS ${MPH_PREP_OUTPUTS})

# The bot-match route observed these overlay-0 roots once per generation.
# Their guest addresses overlap other MPH overlays, so keep the promotion
# tied to the captured page identity instead of trusting addresses alone.
add_custom_target(mph_verify_ov000_root_provenance
    COMMAND "${MPH_PYTHON}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_overlay_root_provenance.py"
            --config "${CMAKE_CURRENT_SOURCE_DIR}/config/mph_arm9_ov000.toml"
            --overlays-json "${MPH_INPUT_DIR}/overlays.json"
            --overlays-dir "${MPH_INPUT_DIR}/overlays"
            --overlay-id 0
            --page 0x02131000
            --page-sha1 bfce0687499c4fa2615da81b193588ba89ba5bd7
            --root 0x02131A24 --root 0x02131A54 --root 0x02131A5C
    DEPENDS mph_prepare
            "${CMAKE_CURRENT_SOURCE_DIR}/config/mph_arm9_ov000.toml"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_overlay_root_provenance.py"
    COMMENT "Verifying overlay-0 promoted root provenance")

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

# ARM7 alias banks (beads-lqa.9): arm7.bin recompiled again at the two bases
# the guest actually relocates the module to. "<bank>:<config stem>:<shards>".
set(MPH_ARM7_ALIAS_BANKS
    "mph_arm7_wram_alias:arm7_wram_alias:2"
    "mph_arm7_mainram_alias:arm7_mainram_alias:2")
set(MPH_ARM7_ALIAS_SOURCES)
set(MPH_ARM7_ALIAS_STAMPS)

set(MPH_ARM9_STAMP "${MPH_RECOMP_DIR}/mph_arm9.stamp")
set(MPH_ARM7_STAMP "${MPH_RECOMP_DIR}/mph_arm7.stamp")
# The mph_arm9 / mph_arm7 generation commands live BELOW the runtime-bank
# loop: their superblock (--coalesce-fallthroughs) pass needs the coverage
# banks' dispatch tables as preceding rows, and those paths/stamps are
# collected by that loop.

# The ARM7 module is declared once at its ROM-header base (0x02380000) but the
# guest relocates and executes it from 0x037F7E50 (ARM7 WRAM window) and
# 0x027CFBC4 (a main-RAM window). Code reached at those addresses matched no
# bank and fell to the Tier-3 interpreter permanently. These banks recompile
# the SAME arm7.bin at those bases -- no dumped bytes are needed, and
# --validate-live-bytes still gates every function against the live guest image
# before dispatch, so a base the guest is not currently using simply never
# validates. Seeds come from coverage/arm7-alias-entry-points.json, so the
# configs are reproducible from the ROM plus committed addresses alone; these
# banks are therefore NOT part of MPH_RUNTIME_BANKS (which require a
# git-ignored generated/capture/<bank>.bin image).
# Each bank name below is passed to the recompiler as a LITERAL, not through a
# loop variable: tools/verify_bank_inventory.ps1/.sh derive the expected bank
# inventory of a linked runner by scanning this file for literal bank-flag
# arguments plus the MPH_*_BANKS list entries, so a loop-generated bank name
# would be invisible to the release inventory gate. (For the same reason, never
# write that flag followed by a word in a comment here: the scanner would count
# the comment as a declared bank.)
foreach(_alias_spec IN LISTS MPH_ARM7_ALIAS_BANKS)
    string(REPLACE ":" ";" _alias_spec "${_alias_spec}")
    list(GET _alias_spec 0 _alias_bank)
    list(GET _alias_spec 2 _alias_shards)
    set(_alias_sources)
    math(EXPR _alias_last_shard "${_alias_shards} - 1")
    foreach(shard RANGE 0 ${_alias_last_shard})
        list(APPEND _alias_sources
            "${MPH_RECOMP_DIR}/${_alias_bank}_0${shard}.c")
    endforeach()
    list(APPEND _alias_sources "${MPH_RECOMP_DIR}/${_alias_bank}_dispatch.c")
    set(MPH_${_alias_bank}_SOURCES ${_alias_sources})
    list(APPEND MPH_ARM7_ALIAS_SOURCES ${_alias_sources})
    list(APPEND MPH_ARM7_ALIAS_STAMPS "${MPH_RECOMP_DIR}/${_alias_bank}.stamp")
endforeach()
# Snapshot the main-closure-only list before alias sources are appended:
# the relocated mph_arm7 generation command below claims ONLY these as
# byproducts (the alias commands own their own files).
set(MPH_ARM7_MAIN_SOURCES ${MPH_ARM7_SOURCES})
list(APPEND MPH_ARM7_SOURCES ${MPH_ARM7_ALIAS_SOURCES})

# The two ARM7 alias-bank generation commands also live below the
# runtime-bank loop (same reason: superblock preceding-dispatch inputs).

# A production release build is PERFORMANT and OPTIMIZED: every bank this
# project declares MUST be compiled in. Releases v0.4.12/v0.4.13/v0.5.0
# shipped without the 63 ingested coverage banks because the bank loops
# below silently skipped any bank whose config or capture image was absent
# (a STATUS message nobody reads). By default a missing bank is a loud
# WARNING plus an end-of-configure summary so a fresh public clone (which
# has no private capture store; run tools/fetch_bank_artifacts.ps1 to pull
# it when you have access) still builds a partial dev runner. Release
# builds MUST configure with -DMPH_ALLOW_MISSING_BANKS=OFF to make any
# omission a hard configure failure, and the release packagers
# independently refuse to stage a runner that fails the full bank
# inventory check (tools/verify_bank_inventory.ps1/.sh), so an incomplete
# runner can never ship either way.
option(MPH_ALLOW_MISSING_BANKS
    "Allow configuring with declared banks missing (dev default -- produces \
a non-release, non-performant runner; release builds set OFF)" ON)
set(MPH_SKIPPED_BANKS)

# Report a declared bank whose inputs are absent. FATAL by default; a
# warning (recorded for the end-of-configure summary) under the explicit
# MPH_ALLOW_MISSING_BANKS developer opt-out.
macro(mph_bank_input_missing _mb_kind _mb_bank _mb_path)
    if(MPH_ALLOW_MISSING_BANKS)
        message(WARNING
            "MPH ${_mb_kind} bank ${_mb_bank} DISABLED: missing "
            "${_mb_path}\n"
            "  This code will fall back to the Tier-3 interpreter. The "
            "resulting runner is NOT a release build.")
        list(APPEND MPH_SKIPPED_BANKS "${_mb_bank}")
    else()
        message(FATAL_ERROR
            "MPH ${_mb_kind} bank ${_mb_bank} cannot be built: missing "
            "${_mb_path}\n"
            "  Every declared bank must be present -- a release build "
            "never silently omits generated content.\n"
            "  Obtain the missing image from the private artifact store "
            "(tools/fetch_bank_artifacts.ps1; generated/capture/ is "
            "git-ignored and is NOT part of the "
            "checkout), or regenerate it: capture the bank live and run "
            "tools/promote_mph_runtime_coverage.py / "
            "tools/promote_runtime_coverage.py (ingested coverage_arm* "
            "banks come from tools/ingest_coverage_manifests.py).\n"
            "  If you knowingly want a partial, non-release tree, "
            "reconfigure with -DMPH_ALLOW_MISSING_BANKS=ON.")
    endif()
endmacro()

set(MPH_OVERLAY_BANKS
    "mph_arm9_ov000:32:000"
    "mph_arm9_ov001:4:001"
    "mph_arm9_ov002:32:002"
    "mph_arm9_ov003:4:003"
    "mph_arm9_ov004:32:004"
    # Overlays 5 and 6 share the 0x0219DC20 base and were undeclared until the
    # 2026-08-27 field ingest: no dev route had ever proved either resident, so
    # tools/seed_overlay_from_coverage.py had nothing to attribute and
    # tools/prepare_mph.py emits overlay configs with no entry points. Player
    # manifests supplied 10 and 314 generation-proven entries respectively, so
    # both are now real banks instead of interpreted address space.
    "mph_arm9_ov005:4:005"
    "mph_arm9_ov006:16:006"
    "mph_arm9_ov008:4:008"
    "mph_arm9_ov009:16:009"
    "mph_arm9_ov010:16:010"
    "mph_arm9_ov011:4:011"
    "mph_arm9_ov015:8:015")
set(MPH_OVERLAY_BANK_SOURCES)
set(MPH_OVERLAY_BANK_STAMPS)
foreach(_bank_spec IN LISTS MPH_OVERLAY_BANKS)
    string(REPLACE ":" ";" _bank_spec "${_bank_spec}")
    list(GET _bank_spec 0 _bank)
    list(GET _bank_spec 1 _bank_shards)
    list(GET _bank_spec 2 _overlay_id)
    set(_bank_config "${CMAKE_CURRENT_SOURCE_DIR}/config/${_bank}.toml")
    set(_bank_image
        "${MPH_INPUT_DIR}/overlays/arm9_overlay_${_overlay_id}.bin")
    # NOTE: _bank_image is produced by mph_prepare at build time, so it is
    # deliberately not checked here -- only the committed config is a
    # configure-time input.
    if(NOT EXISTS "${_bank_config}")
        mph_bank_input_missing(overlay "${_bank}" "${_bank_config}")
        continue()
    endif()
    set(_bank_sources)
    if(_bank_shards EQUAL 1)
        list(APPEND _bank_sources "${MPH_RECOMP_DIR}/${_bank}.c")
    else()
        math(EXPR _bank_last_shard "${_bank_shards} - 1")
        foreach(shard RANGE 0 ${_bank_last_shard})
            if(shard LESS 10)
                set(shard_name "0${shard}")
            else()
                set(shard_name "${shard}")
            endif()
            list(APPEND _bank_sources
                "${MPH_RECOMP_DIR}/${_bank}_${shard_name}.c")
        endforeach()
    endif()
    list(APPEND _bank_sources "${MPH_RECOMP_DIR}/${_bank}_dispatch.c")
    set(_bank_stamp "${MPH_RECOMP_DIR}/${_bank}.stamp")
    add_custom_command(
        OUTPUT "${_bank_stamp}"
        BYPRODUCTS ${_bank_sources} "${MPH_RECOMP_DIR}/${_bank}.h"
        COMMAND $<TARGET_FILE:nds_recompile>
                --config "${_bank_config}"
                --bin "${_bank_image}"
                --out "${MPH_RECOMP_DIR}"
                --bank "${_bank}"
                --shards ${_bank_shards}
                --stable-address-shards
                --max-function-bytes 512
                --validate-live-bytes
        COMMAND ${CMAKE_COMMAND} -E touch "${_bank_stamp}"
        DEPENDS nds_recompile mph_prepare "${_bank_config}"
        COMMENT "Recompiling content-validated AMHE0 overlay bank ${_bank}")
    list(APPEND MPH_OVERLAY_BANK_SOURCES ${_bank_sources})
    list(APPEND MPH_OVERLAY_BANK_STAMPS "${_bank_stamp}")
endforeach()

# Content-validated runtime banks: code the guest copies into RAM at run
# time (ITCM mirrors, the local-wireless ARM7 driver, ...), captured live,
# promoted via tools/promote_runtime_coverage.py, and validated against live
# guest bytes before dispatch. Each entry is "<bank>:<shards>"; the bank's
# config lives at config/<bank>.toml and its (git-ignored) capture image at
# generated/capture/<bank>.bin. A bank whose capture image is absent is a
# hard configure error unless MPH_ALLOW_MISSING_BANKS=ON, because the code
# then falls back to the Tier-3 interpreter (e.g. local multiplayer drops
# from ~60 to ~40 FPS without the two ARM7 MP banks) and that must never
# happen silently in a release.
set(MPH_RUNTIME_BANKS
    "mph_arm9_fmv_runtime:64"
    "mph_arm9_mp_runtime:96"
    "mph_arm7_mp_wram_runtime:4"
    "mph_arm7_mp_mainram_runtime:4")
file(GLOB MPH_INGESTED_RUNTIME_BANK_CONFIGS CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/config/coverage_arm*.toml")
foreach(_bank_config IN LISTS MPH_INGESTED_RUNTIME_BANK_CONFIGS)
    get_filename_component(_bank "${_bank_config}" NAME_WE)
    list(APPEND MPH_RUNTIME_BANKS "${_bank}:2")
endforeach()
set(MPH_RUNTIME_BANK_SOURCES)
set(MPH_RUNTIME_BANK_STAMPS)
# Stamps of the runtime banks generated BEFORE the main closures. The two ARM9
# capture banks are deliberately absent: they are generated after mph_arm9 (see
# the deferred list below), so the closures cannot depend on them.
set(MPH_RUNTIME_BANK_STAMPS_PRE)
set(MPH_RUNTIME_ARM9_SOURCES)
set(MPH_RUNTIME_ARM7_SOURCES)
# beads-lqa.40: capture-derived ARM9 banks whose dispatch rows must be pruned
# against the main closure. tools/promote_mph_runtime_coverage.py seeds them
# from every call target the Tier-3 interpreter observed inside the ARM9 main
# image, so they re-translate code mph_arm9 already owns -- as two-instruction
# landing pads that co-validate with the closure's whole-function rows on ~88k
# addresses. Their generation therefore runs AFTER mph_arm9 and consumes its
# dispatch table, so the redundant rows are never emitted in the first place.
set(MPH_ARM9_CAPTURE_BANKS
    "mph_arm9_fmv_runtime"
    "mph_arm9_mp_runtime")
set(MPH_DEFERRED_ARM9_CAPTURE_SPECS)
# Dispatch tables of the ingested coverage banks, per CPU. These are the
# banks that sort BEFORE the main closures in the runner's alphabetical
# *_dispatch.c registration glob, so they are the (only) preceding rows the
# superblock pass below must respect for mph_arm9 / mph_arm7 / the aliases.
set(MPH_COVERAGE_ARM9_DISPATCH)
set(MPH_COVERAGE_ARM7_DISPATCH)
foreach(_bank_spec IN LISTS MPH_RUNTIME_BANKS)
    string(REPLACE ":" ";" _bank_spec "${_bank_spec}")
    list(GET _bank_spec 0 _bank)
    list(GET _bank_spec 1 _bank_shards)
    set(_bank_config "${CMAKE_CURRENT_SOURCE_DIR}/config/${_bank}.toml")
    set(_bank_image "${MPH_GENERATED_DIR}/capture/${_bank}.bin")
    if(NOT EXISTS "${_bank_config}")
        mph_bank_input_missing(runtime "${_bank}" "${_bank_config}")
        continue()
    endif()
    if(NOT EXISTS "${_bank_image}")
        mph_bank_input_missing(runtime "${_bank}" "${_bank_image}")
        continue()
    endif()
    set(_bank_sources)
    if(_bank_shards EQUAL 1)
        list(APPEND _bank_sources "${MPH_RECOMP_DIR}/${_bank}.c")
    else()
        math(EXPR _bank_last_shard "${_bank_shards} - 1")
        foreach(shard RANGE 0 ${_bank_last_shard})
            if(shard LESS 10)
                set(shard_name "0${shard}")
            else()
                set(shard_name "${shard}")
            endif()
            list(APPEND _bank_sources
                "${MPH_RECOMP_DIR}/${_bank}_${shard_name}.c")
        endforeach()
    endif()
    list(APPEND _bank_sources "${MPH_RECOMP_DIR}/${_bank}_dispatch.c")
    set(MPH_${_bank}_SOURCES ${_bank_sources})
    set(_bank_stamp "${MPH_RECOMP_DIR}/${_bank}.stamp")
    list(FIND MPH_ARM9_CAPTURE_BANKS "${_bank}" _capture_index)
    if(_capture_index EQUAL -1)
        add_custom_command(
            OUTPUT "${_bank_stamp}"
            BYPRODUCTS ${_bank_sources} "${MPH_RECOMP_DIR}/${_bank}.h"
            COMMAND $<TARGET_FILE:nds_recompile>
                    --config "${_bank_config}"
                    --bin "${_bank_image}"
                    --out "${MPH_RECOMP_DIR}"
                    --bank "${_bank}"
                    --shards ${_bank_shards}
                    --stable-address-shards
                    --max-function-bytes 512
                    --validate-live-bytes
            COMMAND ${CMAKE_COMMAND} -E touch "${_bank_stamp}"
            DEPENDS nds_recompile "${_bank_config}" "${_bank_image}"
            COMMENT "Recompiling content-validated AMHE0 runtime bank ${_bank}")
        list(APPEND MPH_RUNTIME_BANK_STAMPS_PRE "${_bank_stamp}")
    else()
        # Generated below, once mph_arm9_dispatch.c exists to prune against.
        list(APPEND MPH_DEFERRED_ARM9_CAPTURE_SPECS
            "${_bank}|${_bank_config}|${_bank_image}|${_bank_shards}")
    endif()
    list(APPEND MPH_RUNTIME_BANK_SOURCES ${_bank_sources})
    list(APPEND MPH_RUNTIME_BANK_STAMPS "${_bank_stamp}")
    if(_bank MATCHES "_arm9_")
        list(APPEND MPH_RUNTIME_ARM9_SOURCES ${_bank_sources})
    else()
        list(APPEND MPH_RUNTIME_ARM7_SOURCES ${_bank_sources})
    endif()
    if(_bank MATCHES "^coverage_arm9")
        list(APPEND MPH_COVERAGE_ARM9_DISPATCH
            "${MPH_RECOMP_DIR}/${_bank}_dispatch.c")
    elseif(_bank MATCHES "^coverage_arm7")
        list(APPEND MPH_COVERAGE_ARM7_DISPATCH
            "${MPH_RECOMP_DIR}/${_bank}_dispatch.c")
    elseif(_bank MATCHES "^mph_arm7_mp_")
        list(APPEND MPH_ARM7_MP_RUNTIME_DISPATCH
            "${MPH_RECOMP_DIR}/${_bank}_dispatch.c")
    endif()
endforeach()

# ---- Main closures + ARM7 alias banks, with superblock coalescing ----------
# Field evidence (beads-0vo, v0.6.2 player diag): slow scenes are dispatch
# bound -- ARM7 24.9k dispatches/frame (79 percent artificial fallthrough),
# ARM9 23.7k. These four banks carry those flows and, unlike SM64DS's banks,
# never received the retained D1 superblock pass (--coalesce-fallthroughs was
# simply never passed here). Preceding-dispatch lists mirror the runner's
# ALPHABETICAL *_dispatch.c registration order per CPU, so a coalesced
# interior row can never shadow a bank registered ahead of it; windows that
# cannot overlap are still listed -- a superfluous preceding row only
# suppresses a merge, never correctness.
function(mph_preceding_args out_var)
    set(_args)
    foreach(_p IN LISTS ARGN)
        list(APPEND _args --preceding-dispatch "${_p}")
    endforeach()
    set(${out_var} "${_args}" PARENT_SCOPE)
endfunction()

mph_preceding_args(MPH_ARM9_PRECEDING ${MPH_COVERAGE_ARM9_DISPATCH})
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
            --coalesce-fallthroughs
            ${MPH_ARM9_PRECEDING}
    COMMAND ${CMAKE_COMMAND} -E touch "${MPH_ARM9_STAMP}"
    DEPENDS nds_recompile ${MPH_PREP_OUTPUTS} ${MPH_RUNTIME_BANK_STAMPS_PRE}
    COMMENT "Recompiling the AMHE0 ARM9 main closure (superblocks)")

mph_preceding_args(MPH_ARM7_PRECEDING ${MPH_COVERAGE_ARM7_DISPATCH})
add_custom_command(
    OUTPUT "${MPH_ARM7_STAMP}"
    BYPRODUCTS ${MPH_ARM7_MAIN_SOURCES} "${MPH_RECOMP_DIR}/mph_arm7.h"
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
            --coalesce-fallthroughs
            ${MPH_ARM7_PRECEDING}
    COMMAND ${CMAKE_COMMAND} -E touch "${MPH_ARM7_STAMP}"
    DEPENDS nds_recompile ${MPH_PREP_OUTPUTS} ${MPH_RUNTIME_BANK_STAMPS_PRE}
    COMMENT "Recompiling the AMHE0 ARM7 initial closure (superblocks)")

# The WRAM alias registers FIRST among ARM7 banks (registration-order.txt
# below): with no preceding rows its whole-module adjacency coalesces
# freely instead of being suppressed by the 25 single-page coverage_arm7
# generation banks inside its window. Content validation still gates every
# row, so priority changes only which candidate is consulted first.
file(WRITE "${MPH_RECOMP_DIR}/registration-order.txt"
    "# beads-0vo: whole-module ARM7 alias precedes page-generation banks\n"
    "mph_arm7_wram_alias\n")

mph_preceding_args(MPH_ARM7_MAINRAM_ALIAS_PRECEDING
    ${MPH_COVERAGE_ARM7_DISPATCH}
    "${MPH_RECOMP_DIR}/mph_arm7_dispatch.c"
    "${MPH_RECOMP_DIR}/mph_arm7_wram_alias_dispatch.c")
add_custom_command(
    OUTPUT "${MPH_RECOMP_DIR}/mph_arm7_mainram_alias.stamp"
    BYPRODUCTS ${MPH_mph_arm7_mainram_alias_SOURCES}
               "${MPH_RECOMP_DIR}/mph_arm7_mainram_alias.h"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${MPH_RECOMP_DIR}"
    COMMAND $<TARGET_FILE:nds_recompile>
            --config "${MPH_INPUT_DIR}/arm7_mainram_alias.toml"
            --bin "${MPH_INPUT_DIR}/arm7.bin"
            --out "${MPH_RECOMP_DIR}"
            --bank mph_arm7_mainram_alias
            --shards 2
            --stable-address-shards
            --max-function-bytes 512
            --validate-live-bytes
            --coalesce-fallthroughs
            ${MPH_ARM7_MAINRAM_ALIAS_PRECEDING}
    COMMAND ${CMAKE_COMMAND} -E touch
            "${MPH_RECOMP_DIR}/mph_arm7_mainram_alias.stamp"
    DEPENDS nds_recompile ${MPH_PREP_OUTPUTS} ${MPH_RUNTIME_BANK_STAMPS_PRE}
            "${MPH_ARM7_STAMP}"
            "${MPH_RECOMP_DIR}/mph_arm7_wram_alias.stamp"
    COMMENT "Recompiling the AMHE0 ARM7 main-RAM alias (superblocks)")

# ---- Capture-derived ARM9 banks, pruned against the main closure ----------
# beads-lqa.40. These run LAST of the generation commands: their preceding set
# is every ARM9 bank the runner registers ahead of them (the ingested coverage
# banks, then the mph_arm9 main closure), and --prune-preceding-owned drops
# every row those banks already own with an equal-or-larger proven span over
# byte-identical content. What survives is exactly what the capture uniquely
# contributes -- ITCM/relocated code and genuinely novel entry points.
mph_preceding_args(MPH_ARM9_CAPTURE_PRECEDING
    ${MPH_COVERAGE_ARM9_DISPATCH}
    "${MPH_RECOMP_DIR}/mph_arm9_dispatch.c")
foreach(_capture_spec IN LISTS MPH_DEFERRED_ARM9_CAPTURE_SPECS)
    string(REPLACE "|" ";" _capture_spec "${_capture_spec}")
    list(GET _capture_spec 0 _cap_bank)
    list(GET _capture_spec 1 _cap_config)
    list(GET _capture_spec 2 _cap_image)
    list(GET _capture_spec 3 _cap_shards)
    add_custom_command(
        OUTPUT "${MPH_RECOMP_DIR}/${_cap_bank}.stamp"
        BYPRODUCTS ${MPH_${_cap_bank}_SOURCES}
                   "${MPH_RECOMP_DIR}/${_cap_bank}.h"
        COMMAND $<TARGET_FILE:nds_recompile>
                --config "${_cap_config}"
                --bin "${_cap_image}"
                --out "${MPH_RECOMP_DIR}"
                --bank "${_cap_bank}"
                --shards ${_cap_shards}
                --stable-address-shards
                --max-function-bytes 512
                --validate-live-bytes
                --prune-preceding-owned
                ${MPH_ARM9_CAPTURE_PRECEDING}
        COMMAND ${CMAKE_COMMAND} -E touch
                "${MPH_RECOMP_DIR}/${_cap_bank}.stamp"
        DEPENDS nds_recompile "${_cap_config}" "${_cap_image}"
                "${MPH_ARM9_STAMP}" ${MPH_RUNTIME_BANK_STAMPS_PRE}
        COMMENT "Recompiling AMHE0 capture bank ${_cap_bank} (pruned against the ARM9 main closure)")
endforeach()

# First-registered ARM7 bank (registration-order.txt): no preceding rows.
set(MPH_ARM7_WRAM_ALIAS_PRECEDING)
add_custom_command(
    OUTPUT "${MPH_RECOMP_DIR}/mph_arm7_wram_alias.stamp"
    BYPRODUCTS ${MPH_mph_arm7_wram_alias_SOURCES}
               "${MPH_RECOMP_DIR}/mph_arm7_wram_alias.h"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${MPH_RECOMP_DIR}"
    COMMAND $<TARGET_FILE:nds_recompile>
            --config "${MPH_INPUT_DIR}/arm7_wram_alias.toml"
            --bin "${MPH_INPUT_DIR}/arm7.bin"
            --out "${MPH_RECOMP_DIR}"
            --bank mph_arm7_wram_alias
            --shards 2
            --stable-address-shards
            --max-function-bytes 512
            --validate-live-bytes
            --coalesce-fallthroughs
            ${MPH_ARM7_WRAM_ALIAS_PRECEDING}
    COMMAND ${CMAKE_COMMAND} -E touch
            "${MPH_RECOMP_DIR}/mph_arm7_wram_alias.stamp"
    DEPENDS nds_recompile ${MPH_PREP_OUTPUTS}
    COMMENT "Recompiling the AMHE0 ARM7 WRAM alias (superblocks, first-registered)")

add_custom_target(mph_generate_banks
    DEPENDS "${MPH_ARM9_STAMP}" "${MPH_ARM7_STAMP}"
        ${MPH_ARM7_ALIAS_STAMPS}
        ${MPH_OVERLAY_BANK_STAMPS} ${MPH_RUNTIME_BANK_STAMPS})
add_dependencies(mph_generate_banks mph_verify_ov000_root_provenance)
add_library(mph_recompiled_banks STATIC
    ${MPH_ARM9_SOURCES} ${MPH_ARM7_SOURCES} ${MPH_OVERLAY_BANK_SOURCES}
    ${MPH_RUNTIME_BANK_SOURCES})
add_dependencies(mph_recompiled_banks mph_generate_banks)
ndsrecomp_limit_generated_compiles(mph_recompiled_banks)
ndsrecomp_limit_link(mph_recompiled_banks)
set_source_files_properties(${MPH_ARM9_SOURCES} ${MPH_OVERLAY_BANK_SOURCES}
    ${MPH_RUNTIME_ARM9_SOURCES}
    PROPERTIES COMPILE_DEFINITIONS "NDS_STATIC_CPU=0")
set_source_files_properties(${MPH_ARM7_SOURCES} ${MPH_RUNTIME_ARM7_SOURCES}
    PROPERTIES COMPILE_DEFINITIONS "NDS_STATIC_CPU=1")
target_include_directories(mph_recompiled_banks PRIVATE
    "${MPH_RECOMP_DIR}"
    "${NDSRECOMP_ROOT}/recompiler/armv4t"
    "${NDSRECOMP_ROOT}/external/arm-recomp-core/common")
if(NOT MSVC)
    # Generated banks are optimized: shipped builds must be performant
    # (beads-lqa.33 / beads-fly). -O2 rather than -O3: the SM64DS C1
    # experiment showed -O3 on large shards makes build time explode
    # without a proven win. MPH_BANK_OPT_LEVEL exists so a dev tree can
    # drop back to -O0 for fast iteration.
    set(MPH_BANK_OPT_LEVEL "-O2" CACHE STRING
        "Optimization level for generated bank TUs (release: -O2)")
    target_compile_options(mph_recompiled_banks PRIVATE
        -w ${MPH_BANK_OPT_LEVEL} -g0)
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

# Bank inventory summary. tools/verify_bank_inventory.ps1 / .sh assert the
# same identities against the linked runner binary, so a release cannot ship
# with banks that were dropped here.
list(LENGTH MPH_OVERLAY_BANKS _mph_declared_overlay_banks)
list(LENGTH MPH_RUNTIME_BANKS _mph_declared_runtime_banks)
list(LENGTH MPH_ARM7_ALIAS_BANKS _mph_declared_alias_banks)
list(LENGTH MPH_SKIPPED_BANKS _mph_skipped_bank_count)
math(EXPR _mph_declared_banks
    "${_mph_declared_overlay_banks} + ${_mph_declared_runtime_banks} + ${_mph_declared_alias_banks}")
math(EXPR _mph_built_banks
    "${_mph_declared_banks} - ${_mph_skipped_bank_count}")
message(STATUS
    "MPH banks: ${_mph_built_banks}/${_mph_declared_banks} declared banks "
    "enabled (${_mph_declared_overlay_banks} overlay + "
    "${_mph_declared_runtime_banks} runtime/coverage + "
    "${_mph_declared_alias_banks} ARM7 alias), plus the mph_arm9 "
    "and mph_arm7 main closures")
if(_mph_skipped_bank_count GREATER 0)
    string(REPLACE ";" "\n    " _mph_skipped_pretty "${MPH_SKIPPED_BANKS}")
    message(WARNING
        "MPH_ALLOW_MISSING_BANKS=ON: ${_mph_skipped_bank_count} declared "
        "bank(s) were SKIPPED. This tree cannot produce a release build:\n"
        "    ${_mph_skipped_pretty}")
endif()
