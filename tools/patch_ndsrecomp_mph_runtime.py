#!/usr/bin/env python3
"""Apply the MPH multi-ROM runtime-profile shim to the pinned ndsrecomp runner.

Runtime address selection follows melonPrimeDS's two-stage detector:

1. authoritative executable checksum (CRC32 of header[0:0x40], ARM9, ARM7),
2. exact NDS gameCode @0x0C + supported revision @0x1E as a fallback.

The fallback identifies a base profile but is *not* sufficient evidence for
host-side Aim/Morph RAM accesses. Those writes are enabled only for a checksum
explicitly known by the melonPrimeDS detector. This keeps unknown mods
fail-closed instead of guessing that a matching header implies compatible RAM.

Whole-ROM SHA-1 has a separate role. It remains the actual-content identity
used by generated banks/captures. A clean build may accept a different whole-
ROM SHA only when the actual ROM has the canonical executable checksum of that
same clean base profile (for example, a data-only mod outside header/ARM9/ARM7).
Code-modified variants still require their own exact build/capture identity.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
CHECKSUM_RE = re.compile(r"^0x[0-9A-F]{8}$")
MAIN_RAM_MIN = 0x02000000
MAIN_RAM_MAX = 0x023FFFFF
EXPECTED_RUNTIME_KEYS = {
    "US1_0", "US1_1", "EU1_0", "EU1_1", "JP1_0", "JP1_1", "KR1_0"
}


def parse_address(value: object, *, profile: str, field: str) -> int:
    if not isinstance(value, str):
        raise SystemExit(f"{profile}.{field}: expected a hex string")
    try:
        address = int(value, 0)
    except ValueError as exc:
        raise SystemExit(f"{profile}.{field}: invalid address {value!r}") from exc
    if not MAIN_RAM_MIN <= address <= MAIN_RAM_MAX:
        raise SystemExit(
            f"{profile}.{field}: 0x{address:08X} is outside DS main RAM"
        )
    return address


def parse_checksum(value: object, *, where: str) -> int:
    if not isinstance(value, str) or not CHECKSUM_RE.fullmatch(value):
        raise SystemExit(f"{where}: expected uppercase 0xXXXXXXXX checksum")
    return int(value, 16)


def load_runtime_registry(
    registry_path: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    runtime_profiles = registry.get("runtime_profiles")
    if not isinstance(runtime_profiles, dict) or not runtime_profiles:
        raise SystemExit("ROM profile registry has no runtime_profiles")

    actual_keys = set(runtime_profiles)
    if actual_keys != EXPECTED_RUNTIME_KEYS:
        missing = ", ".join(sorted(EXPECTED_RUNTIME_KEYS - actual_keys)) or "none"
        extra = ", ".join(sorted(actual_keys - EXPECTED_RUNTIME_KEYS)) or "none"
        raise SystemExit(
            "runtime profile set must be exactly the seven supported retail "
            f"profiles (missing: {missing}; extra: {extra})"
        )

    build_profiles = registry.get("profiles")
    if not isinstance(build_profiles, dict):
        raise SystemExit("ROM profile registry has no build profiles")

    result: list[dict[str, object]] = []
    seen_identity: set[tuple[str, int]] = set()
    seen_base_checksum: set[int] = set()
    seen_clean_sha1: set[str] = set()

    for key, profile in runtime_profiles.items():
        if not isinstance(profile, dict):
            raise SystemExit(f"{key}: runtime profile must be an object")
        game_code = profile.get("game_code")
        revision = profile.get("revision")
        runtime = profile.get("runtime")
        if (
            not isinstance(game_code, str)
            or len(game_code) != 4
            or not game_code.isascii()
        ):
            raise SystemExit(f"{key}.game_code must be exactly four ASCII bytes")
        if not isinstance(revision, int) or revision not in (0, 1):
            raise SystemExit(f"{key}.revision must be an explicitly supported 0/1")
        if not isinstance(runtime, dict):
            raise SystemExit(f"{key}.runtime must be an object")

        identity = (game_code, revision)
        if identity in seen_identity:
            raise SystemExit(
                f"duplicate runtime cartridge identity: {game_code} rev {revision}"
            )
        seen_identity.add(identity)

        base_checksum = parse_checksum(
            profile.get("base_checksum"), where=f"{key}.base_checksum"
        )
        if base_checksum in seen_base_checksum:
            raise SystemExit(f"duplicate canonical executable checksum for {key}")
        seen_base_checksum.add(base_checksum)

        known_clean_sha1 = ""
        clean = build_profiles.get(key)
        if clean is not None:
            if not isinstance(clean, dict):
                raise SystemExit(f"{key}: build profile must be an object")
            if clean.get("game_code") != game_code or clean.get("revision") != revision:
                raise SystemExit(
                    f"{key}: clean build identity disagrees with runtime profile"
                )
            sha1 = clean.get("sha1")
            if not isinstance(sha1, str) or not SHA1_RE.fullmatch(sha1):
                raise SystemExit(f"{key}.sha1 must be 40 lowercase hex digits")
            if sha1 in seen_clean_sha1:
                raise SystemExit(f"duplicate known-clean SHA-1: {sha1}")
            seen_clean_sha1.add(sha1)
            known_clean_sha1 = sha1

        result.append(
            {
                "key": key,
                "game_code": game_code,
                "revision": revision,
                "base_checksum": base_checksum,
                "known_clean_sha1": known_clean_sha1,
                "morph_state": parse_address(
                    runtime.get("morph_state"), profile=key, field="morph_state"
                ),
                "aim_x": parse_address(
                    runtime.get("aim_x"), profile=key, field="aim_x"
                ),
                "aim_y": parse_address(
                    runtime.get("aim_y"), profile=key, field="aim_y"
                ),
            }
        )

    checksums_obj = registry.get("runtime_checksums")
    if not isinstance(checksums_obj, list) or not checksums_obj:
        raise SystemExit("ROM profile registry has no runtime_checksums")
    checksums: list[dict[str, object]] = []
    seen_checksums: set[int] = set()
    canonical_seen: set[str] = set()
    for index, item in enumerate(checksums_obj):
        if not isinstance(item, dict):
            raise SystemExit(f"runtime_checksums[{index}] must be an object")
        checksum = parse_checksum(
            item.get("crc32"), where=f"runtime_checksums[{index}].crc32"
        )
        profile_key = item.get("profile")
        name = item.get("name")
        if profile_key not in EXPECTED_RUNTIME_KEYS:
            raise SystemExit(
                f"runtime_checksums[{index}].profile is unknown: {profile_key!r}"
            )
        if not isinstance(name, str) or not name:
            raise SystemExit(f"runtime_checksums[{index}].name must be non-empty")
        if checksum in seen_checksums:
            raise SystemExit(f"duplicate runtime checksum 0x{checksum:08X}")
        seen_checksums.add(checksum)
        profile = next(p for p in result if p["key"] == profile_key)
        if checksum == profile["base_checksum"]:
            canonical_seen.add(str(profile_key))
        checksums.append(
            {"crc32": checksum, "profile": profile_key, "name": name}
        )

    if canonical_seen != EXPECTED_RUNTIME_KEYS:
        missing = ", ".join(sorted(EXPECTED_RUNTIME_KEYS - canonical_seen))
        raise SystemExit(
            f"runtime_checksums is missing canonical entries for: {missing}"
        )
    return result, checksums


def generated_header(
    profiles: list[dict[str, object]], checksums: list[dict[str, object]]
) -> str:
    profile_rows: list[str] = []
    for profile in profiles:
        profile_rows.append(
            '    {"%s", "%s", %du, "%s", 0x%08Xu, 0x%08Xu, 0x%08Xu, 0x%08Xu},  // %s'
            % (
                profile["key"],
                profile["game_code"],
                profile["revision"],
                profile["known_clean_sha1"],
                profile["base_checksum"],
                profile["morph_state"],
                profile["aim_x"],
                profile["aim_y"],
                profile["key"],
            )
        )
    checksum_rows = [
        '    {0x%08Xu, "%s", "%s"},'
        % (item["crc32"], item["profile"], item["name"])
        for item in checksums
    ]
    return """#pragma once

#include <array>
#include <cstdint>

// Generated by MetroidPrimeHuntersRecomp/tools/patch_ndsrecomp_mph_runtime.py.
// Do not edit in the ndsrecomp checkout; edit config/mph_rom_profiles.json.
//
// The executable checksum mirrors melonPrimeDS CartCommon::Checksum(): CRC32 of
// header[0:0x40], then ARM9, then ARM7. A checksum hit is authoritative for the
// runtime layout. Header gameCode+revision is only a fail-closed fallback hint.
struct NdsMphRuntimeProfile {
    const char* key;
    const char* game_code;
    uint8_t revision;
    const char* known_clean_sha1;
    uint32_t base_checksum;
    uint32_t morph_state;
    uint32_t aim_x;
    uint32_t aim_y;
};

struct NdsMphRuntimeChecksum {
    uint32_t checksum;
    const char* profile_key;
    const char* name;
};

inline constexpr std::array<NdsMphRuntimeProfile, %d> kNdsMphRuntimeProfiles{{
%s
}};

inline constexpr std::array<NdsMphRuntimeChecksum, %d> kNdsMphRuntimeChecksums{{
%s
}};
""" % (
        len(profile_rows),
        "\n".join(profile_rows),
        len(checksum_rows),
        "\n".join(checksum_rows),
    )


def patch_once(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    if old not in text:
        raise SystemExit(
            f"Refusing to patch {path}: expected pinned ndsrecomp preimage "
            f"for marker {marker!r} was not found"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_runner(framework_root: Path, registry_path: Path) -> None:
    runner_src = framework_root / "runner" / "src"
    title_h = runner_src / "title_patches.h"
    title_cpp = runner_src / "title_patches.cpp"
    frontend_cpp = runner_src / "frontend.cpp"
    main_cpp = runner_src / "main.cpp"
    for path in (title_h, title_cpp, frontend_cpp, main_cpp):
        if not path.is_file():
            raise SystemExit(f"Pinned ndsrecomp runner file not found: {path}")

    profiles, checksums = load_runtime_registry(registry_path)
    generated = runner_src / "mph_runtime_profiles.generated.h"
    generated.write_text(generated_header(profiles, checksums), encoding="utf-8")

    patch_once(
        title_h,
        "void nds_title_patches_set_mph_mouse_aim(bool enabled);\n"
        "bool nds_title_patches_apply_mph_mouse_delta(int32_t dx, int32_t dy);\n",
        "// MPH_MULTIROM_RUNTIME_PROFILE: melonPrimeDS-compatible base detector.\n"
        "bool nds_title_patches_select_mph_runtime_profile(\n"
        "    const uint8_t* rom_data, uint64_t rom_size, const char* rom_sha1,\n"
        "    const char* expected_rom_sha1);\n"
        "bool nds_title_patches_mph_host_writes_compatible();\n"
        "bool nds_title_patches_mph_allows_rom_sha1_mismatch();\n"
        "bool nds_title_patches_mph_in_ball();\n"
        "void nds_title_patches_set_mph_mouse_aim(bool enabled);\n"
        "bool nds_title_patches_apply_mph_mouse_delta(int32_t dx, int32_t dy);\n",
        "melonPrimeDS-compatible base detector",
    )

    patch_once(
        title_cpp,
        '#include "title_patches.h"\n',
        '#include "title_patches.h"\n'
        '#include "mph_runtime_profiles.generated.h"  // MPH_MULTIROM_PROFILE_HEADER\n',
        "MPH_MULTIROM_PROFILE_HEADER",
    )
    patch_once(
        title_cpp,
        "// AMHE0's native touch-look routine consumes these signed, per-frame fields.\n"
        "// Feeding deltas here while holding the stylus at center preserves the game\n"
        "// path but removes the finite physical touchscreen edge.\n"
        "constexpr uint32_t kMphUs10AimX = 0x020DE526u;\n"
        "constexpr uint32_t kMphUs10AimY = 0x020DE52Eu;\n",
        "// MPH_MULTIROM_RUNTIME_PROFILE: runtime identity and safety state.\n"
        "const NdsMphRuntimeProfile* g_mph_runtime_profile = nullptr;\n"
        "bool g_mph_host_writes_compatible = false;\n"
        "bool g_mph_allow_rom_sha1_mismatch = false;\n\n"
        "uint32_t mph_read_le32(const uint8_t* p) {\n"
        "    return static_cast<uint32_t>(p[0]) |\n"
        "           (static_cast<uint32_t>(p[1]) << 8) |\n"
        "           (static_cast<uint32_t>(p[2]) << 16) |\n"
        "           (static_cast<uint32_t>(p[3]) << 24);\n"
        "}\n\n"
        "uint32_t mph_crc32(const uint8_t* data, uint32_t len, uint32_t start) {\n"
        "    uint32_t crc = start ^ 0xFFFFFFFFu;\n"
        "    for (uint32_t i = 0; i < len; ++i) {\n"
        "        crc ^= data[i];\n"
        "        for (int bit = 0; bit < 8; ++bit)\n"
        "            crc = (crc >> 1) ^\n"
        "                  (0xEDB88320u & (0u - (crc & 1u)));\n"
        "    }\n"
        "    return crc ^ 0xFFFFFFFFu;\n"
        "}\n\n"
        "bool mph_compute_executable_checksum(\n"
        "    const uint8_t* rom, uint64_t rom_size, uint32_t* out) {\n"
        "    if (!rom || !out || rom_size < 0x40u) return false;\n"
        "    const uint32_t arm9_offset = mph_read_le32(rom + 0x20u);\n"
        "    const uint32_t arm9_size = mph_read_le32(rom + 0x2Cu);\n"
        "    const uint32_t arm7_offset = mph_read_le32(rom + 0x30u);\n"
        "    const uint32_t arm7_size = mph_read_le32(rom + 0x3Cu);\n"
        "    if (static_cast<uint64_t>(arm9_offset) + arm9_size > rom_size ||\n"
        "        static_cast<uint64_t>(arm7_offset) + arm7_size > rom_size)\n"
        "        return false;\n"
        "    uint32_t crc = mph_crc32(rom, 0x40u, 0u);\n"
        "    crc = mph_crc32(rom + arm9_offset, arm9_size, crc);\n"
        "    crc = mph_crc32(rom + arm7_offset, arm7_size, crc);\n"
        "    *out = crc;\n"
        "    return true;\n"
        "}\n\n"
        "const NdsMphRuntimeProfile* mph_find_profile_by_key(const char* key) {\n"
        "    for (const auto& profile : kNdsMphRuntimeProfiles)\n"
        "        if (std::strcmp(profile.key, key) == 0) return &profile;\n"
        "    return nullptr;\n"
        "}\n\n"
        "const NdsMphRuntimeProfile* mph_find_clean_sha1(const char* sha1) {\n"
        "    if (!sha1 || sha1[0] == '\\0') return nullptr;\n"
        "    for (const auto& profile : kNdsMphRuntimeProfiles) {\n"
        "        if (profile.known_clean_sha1[0] != '\\0' &&\n"
        "            std::strcmp(profile.known_clean_sha1, sha1) == 0)\n"
        "            return &profile;\n"
        "    }\n"
        "    return nullptr;\n"
        "}\n",
        "runtime identity and safety state",
    )
    patch_once(
        title_cpp,
        "void nds_title_patches_set_mph_mouse_aim(bool enabled) {\n"
        "    g_mph_mouse_aim = enabled;\n"
        "}\n\n"
        "bool nds_title_patches_apply_mph_mouse_delta(int32_t dx, int32_t dy) {\n"
        "    if (!g_mph_mouse_aim || (dx == 0 && dy == 0)) return false;\n"
        "    if (dx != 0)\n"
        "        bus_write_u32_slow(kMphUs10AimX, static_cast<uint32_t>(dx));\n"
        "    if (dy != 0)\n"
        "        bus_write_u32_slow(kMphUs10AimY, static_cast<uint32_t>(dy));\n"
        "    return true;\n"
        "}\n",
        "bool nds_title_patches_select_mph_runtime_profile(\n"
        "    const uint8_t* rom_data, uint64_t rom_size, const char* rom_sha1,\n"
        "    const char* expected_rom_sha1) {\n"
        "    g_mph_mouse_aim = false;\n"
        "    g_mph_runtime_profile = nullptr;\n"
        "    g_mph_host_writes_compatible = false;\n"
        "    g_mph_allow_rom_sha1_mismatch = false;\n"
        "    if (!rom_data || !rom_sha1 || !expected_rom_sha1 || rom_size <= 0x1Eu)\n"
        "        return false;\n\n"
        "    uint32_t checksum = 0;\n"
        "    if (!mph_compute_executable_checksum(rom_data, rom_size, &checksum))\n"
        "        return false;\n\n"
        "    const NdsMphRuntimeChecksum* checksum_hit = nullptr;\n"
        "    const NdsMphRuntimeProfile* profile = nullptr;\n"
        "    for (const auto& entry : kNdsMphRuntimeChecksums) {\n"
        "        if (entry.checksum == checksum) {\n"
        "            checksum_hit = &entry;\n"
        "            profile = mph_find_profile_by_key(entry.profile_key);\n"
        "            break;\n"
        "        }\n"
        "    }\n\n"
        "    if (!profile) {\n"
        "        // melonPrimeDS fallback, tightened to exact supported revisions.\n"
        "        for (const auto& candidate : kNdsMphRuntimeProfiles) {\n"
        "            if (std::memcmp(candidate.game_code, rom_data + 0x0Cu, 4) == 0 &&\n"
        "                candidate.revision == rom_data[0x1Eu]) {\n"
        "                if (profile) return false;  // ambiguous registry: fail closed\n"
        "                profile = &candidate;\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "    if (!profile) return false;\n\n"
        "    // A known clean whole-ROM hash can only describe its own base profile.\n"
        "    const NdsMphRuntimeProfile* actual_clean = mph_find_clean_sha1(rom_sha1);\n"
        "    if (actual_clean && actual_clean != profile) return false;\n\n"
        "    g_mph_runtime_profile = profile;\n"
        "    // Unknown checksum + matching header is only a base-profile hint.\n"
        "    // Do not perform host RAM reads/writes until the executable checksum\n"
        "    // is explicitly represented by melonPrimeDS's authoritative table.\n"
        "    g_mph_host_writes_compatible = checksum_hit != nullptr;\n\n"
        "    // Whole-ROM mismatch may be relaxed only for a clean build whose\n"
        "    // executable identity is byte-for-byte equivalent to the canonical\n"
        "    // header+ARM9+ARM7 checksum. Code-modified known variants therefore\n"
        "    // still require an exact mod-specific build/capture SHA.\n"
        "    const NdsMphRuntimeProfile* expected_clean =\n"
        "        mph_find_clean_sha1(expected_rom_sha1);\n"
        "    g_mph_allow_rom_sha1_mismatch =\n"
        "        std::strcmp(rom_sha1, expected_rom_sha1) != 0 &&\n"
        "        expected_clean == profile && checksum == profile->base_checksum;\n"
        "    return true;\n"
        "}\n\n"
        "bool nds_title_patches_mph_host_writes_compatible() {\n"
        "    return g_mph_runtime_profile && g_mph_host_writes_compatible;\n"
        "}\n\n"
        "bool nds_title_patches_mph_allows_rom_sha1_mismatch() {\n"
        "    return g_mph_runtime_profile && g_mph_allow_rom_sha1_mismatch;\n"
        "}\n\n"
        "bool nds_title_patches_mph_in_ball() {\n"
        "    return nds_title_patches_mph_host_writes_compatible() &&\n"
        "           bus_read_u8_slow(g_mph_runtime_profile->morph_state) == 0x02u;\n"
        "}\n\n"
        "void nds_title_patches_set_mph_mouse_aim(bool enabled) {\n"
        "    g_mph_mouse_aim =\n"
        "        enabled && nds_title_patches_mph_host_writes_compatible();\n"
        "}\n\n"
        "bool nds_title_patches_apply_mph_mouse_delta(int32_t dx, int32_t dy) {\n"
        "    if (!g_mph_mouse_aim || !nds_title_patches_mph_host_writes_compatible() ||\n"
        "        (dx == 0 && dy == 0)) return false;\n"
        "    if (dx != 0)\n"
        "        bus_write_u32_slow(g_mph_runtime_profile->aim_x,\n"
        "                           static_cast<uint32_t>(dx));\n"
        "    if (dy != 0)\n"
        "        bus_write_u32_slow(g_mph_runtime_profile->aim_y,\n"
        "                           static_cast<uint32_t>(dy));\n"
        "    return true;\n"
        "}\n",
        "nds_title_patches_select_mph_runtime_profile",
    )

    patch_once(
        frontend_cpp,
        "constexpr uint32_t kMphUs10MorphState = 0x020DA818u;\n",
        "// MPH_MULTIROM_RUNTIME_PROFILE: morph address comes from the base ROM profile.\n",
        "morph address comes from the base ROM profile",
    )
    patch_once(
        frontend_cpp,
        "                const bool in_ball =\n"
        "                    bus_read_u8_slow(kMphUs10MorphState) == 0x02u;\n",
        "                const bool in_ball = nds_title_patches_mph_in_ball();\n",
        "nds_title_patches_mph_in_ball()",
    )

    patch_once(
        main_cpp,
        "        rom_sha1 = gba::sha1(rom.data(), rom.size()).hex();\n"
        "        std::fprintf(stderr, \"[load] cartridge: %zu bytes, SHA-1 %s\\n\",\n"
        "                     rom.size(), rom_sha1.c_str());\n"
        "        if (!frontend_options.expected_rom_sha1.empty() &&\n"
        "            rom_sha1 != frontend_options.expected_rom_sha1) {\n"
        "            std::fprintf(stderr,\n"
        "                         \"refusing to start: game config expects ROM SHA-1 \"\n"
        "                         \"%s, got %s\\n\",\n"
        "                         frontend_options.expected_rom_sha1.c_str(),\n"
        "                         rom_sha1.c_str());\n"
        "            return 1;\n"
        "        }\n",
        "        rom_sha1 = gba::sha1(rom.data(), rom.size()).hex();\n"
        "        std::fprintf(stderr, \"[load] cartridge: %zu bytes, SHA-1 %s\\n\",\n"
        "                     rom.size(), rom_sha1.c_str());\n"
        "        // MPH_MULTIROM_CONTENT_GATE: choose a base layout before the\n"
        "        // generic exact-SHA gate. The whole-ROM hash still identifies\n"
        "        // generated content; only canonical executable-equivalent data\n"
        "        // variants may reuse a clean build.\n"
        "        nds_title_patches_select_mph_runtime_profile(\n"
        "            rom.data(), static_cast<uint64_t>(rom.size()), rom_sha1.c_str(),\n"
        "            frontend_options.expected_rom_sha1.c_str());\n"
        "        if (!frontend_options.expected_rom_sha1.empty() &&\n"
        "            rom_sha1 != frontend_options.expected_rom_sha1 &&\n"
        "            !nds_title_patches_mph_allows_rom_sha1_mismatch()) {\n"
        "            std::fprintf(stderr,\n"
        "                         \"refusing to start: game config expects ROM SHA-1 \"\n"
        "                         \"%s, got %s\\n\",\n"
        "                         frontend_options.expected_rom_sha1.c_str(),\n"
        "                         rom_sha1.c_str());\n"
        "            return 1;\n"
        "        }\n",
        "MPH_MULTIROM_CONTENT_GATE",
    )
    patch_once(
        main_cpp,
        "    mph_mouse_aim_policy =\n"
        "        rom_sha1 == \"90164d1ac127ee5f9815ea4ae7de798c7b5fc629\" &&\n"
        "        frontend_options.relative_mouse_touch;\n",
        "    // MPH_MULTIROM_HOST_WRITE_GATE: header fallback alone never enables\n"
        "    // direct host RAM writes; an authoritative executable checksum is required.\n"
        "    mph_mouse_aim_policy =\n"
        "        nds_title_patches_mph_host_writes_compatible() &&\n"
        "        frontend_options.relative_mouse_touch;\n",
        "MPH_MULTIROM_HOST_WRITE_GATE",
    )

    print(
        f"Patched ndsrecomp MPH runtime base profiles: "
        + ", ".join(str(profile["key"]) for profile in profiles)
        + f" ({len(checksums)} authoritative executable checksums)"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    args = parser.parse_args()
    patch_runner(args.framework_root.resolve(), args.profiles.resolve())


if __name__ == "__main__":
    main()
