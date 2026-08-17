#!/usr/bin/env python3
"""Layer profile-aware MPH 21:9 projection/culling patches onto ndsrecomp.

Addresses and guards mirror melonPrimeDS MelonPrimePatchAspectRatio.cpp and
MelonPrimeGameRomAddrTable.h, cross-checked against mphCodex Widescreen.md.
Only an authoritative executable checksum may enable these host code/data
writes. Header-only fallback detection remains fail-closed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED_KEYS = {"US1_0", "US1_1", "EU1_0", "EU1_1", "JP1_0", "JP1_1", "KR1_0"}
FIELDS = ("scale_patch_addr1", "scale_patch_addr2", "scale_value_addr")
RAM_MIN = 0x02000000
RAM_MAX = 0x023FFFFF


def parse_addr(value: object, where: str) -> int:
    if not isinstance(value, str):
        raise SystemExit(f"{where}: expected hex string")
    try:
        address = int(value, 0)
    except ValueError as exc:
        raise SystemExit(f"{where}: invalid address {value!r}") from exc
    if not RAM_MIN <= address <= RAM_MAX:
        raise SystemExit(f"{where}: 0x{address:08X} outside DS main RAM")
    return address


def load_profiles(path: Path) -> list[dict[str, object]]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    profiles = registry.get("runtime_profiles")
    if not isinstance(profiles, dict) or set(profiles) != EXPECTED_KEYS:
        raise SystemExit("runtime_profiles must contain exactly the seven MPH base revisions")
    result: list[dict[str, object]] = []
    for key, item in profiles.items():
        if not isinstance(item, dict) or not isinstance(item.get("runtime"), dict):
            raise SystemExit(f"{key}: missing runtime object")
        runtime = item["runtime"]
        row: dict[str, object] = {"key": key}
        for field in FIELDS:
            row[field] = parse_addr(runtime.get(field), f"{key}.runtime.{field}")
        if int(row["scale_value_addr"]) & 3:
            raise SystemExit(f"{key}.runtime.scale_value_addr must be word-aligned")
        result.append(row)
    return result


def header_text(profiles: list[dict[str, object]]) -> str:
    rows = "\n".join(
        '    {"%s", 0x%08Xu, 0x%08Xu, 0x%08Xu},'
        % (
            p["key"], p["scale_patch_addr1"], p["scale_patch_addr2"],
            p["scale_value_addr"],
        )
        for p in profiles
    )
    return f'''#pragma once

#include <array>
#include <cstdint>

// Generated from config/mph_rom_profiles.json.
// Source of truth: melonPrimeDS MelonPrimeGameRomAddrTable.h.
struct NdsMphWidescreenProfile {{
    const char* key;
    uint32_t scale_patch_addr1;
    uint32_t scale_patch_addr2;
    uint32_t scale_value_addr;
}};

inline constexpr std::array<NdsMphWidescreenProfile, {len(profiles)}> kNdsMphWidescreenProfiles{{{{
{rows}
}}}};
'''


def patch_once(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    if old not in text:
        raise SystemExit(
            f"Refusing to patch {path}: expected pinned ndsrecomp preimage "
            f"for {marker!r} was not found"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch(framework: Path, registry: Path) -> None:
    src = framework / "runner" / "src"
    title_h = src / "title_patches.h"
    title_cpp = src / "title_patches.cpp"
    main_cpp = src / "main.cpp"
    for path in (title_h, title_cpp, main_cpp):
        if not path.is_file():
            raise SystemExit(f"runner source missing: {path}")

    profiles = load_profiles(registry)
    (src / "mph_widescreen_profiles.generated.h").write_text(
        header_text(profiles), encoding="utf-8"
    )

    patch_once(
        title_h,
        "bool nds_title_patches_mph_in_ball();\n",
        "bool nds_title_patches_mph_in_ball();\n"
        "// MPH_MULTIROM_WIDESCREEN: profile-aware 21:9 projection/culling patch.\n"
        "bool nds_title_patches_mph_detected();\n"
        "void nds_title_patches_set_mph_adaptive(bool enabled);\n",
        "MPH_MULTIROM_WIDESCREEN",
    )
    patch_once(
        title_cpp,
        '#include "mph_runtime_profiles.generated.h"  // MPH_MULTIROM_PROFILE_HEADER\n',
        '#include "mph_runtime_profiles.generated.h"  // MPH_MULTIROM_PROFILE_HEADER\n'
        '#include "mph_widescreen_profiles.generated.h"  // MPH_MULTIROM_WIDESCREEN_HEADER\n',
        "MPH_MULTIROM_WIDESCREEN_HEADER",
    )
    patch_once(
        title_cpp,
        "bool g_mph_allow_rom_sha1_mismatch = false;\n",
        "bool g_mph_allow_rom_sha1_mismatch = false;\n"
        "// MPH_MULTIROM_WIDESCREEN_STATE\n"
        "bool g_mph_adaptive = false;\n"
        "bool g_mph_aspect_ratio_applied = false;\n"
        "constexpr uint32_t kMphScaleOrig1 = 0xE5991664u;\n"
        "constexpr uint32_t kMphScaleOrig2 = 0xE59A1664u;\n"
        "constexpr uint32_t kMphScale21x9Instr = 0xE3A0106Du;\n"
        "constexpr uint16_t kMphScaleOrigValue = 0x1555u;\n"
        "constexpr uint16_t kMphScale21x9Value = 0x2555u;\n",
        "MPH_MULTIROM_WIDESCREEN_STATE",
    )
    patch_once(
        title_cpp,
        "\n}  // namespace\n\nvoid nds_title_patches_set_sm64ds_adaptive(bool enabled) {\n",
        "\nconst NdsMphWidescreenProfile* mph_widescreen_profile() {\n"
        "    if (!g_mph_runtime_profile) return nullptr;\n"
        "    for (const auto& profile : kNdsMphWidescreenProfiles)\n"
        "        if (std::strcmp(profile.key, g_mph_runtime_profile->key) == 0)\n"
        "            return &profile;\n"
        "    return nullptr;\n"
        "}\n\n"
        "void patch_mph_aspect_ratio() {\n"
        "    if (!g_mph_adaptive || g_mph_aspect_ratio_applied ||\n"
        "        !g_mph_runtime_profile || !g_mph_host_writes_compatible)\n"
        "        return;\n"
        "    const auto* wide = mph_widescreen_profile();\n"
        "    if (!wide) return;\n"
        "    int32_t first = 0, second = 0, scale_word = 0;\n"
        "    if (!read_main_ram32(wide->scale_patch_addr1, &first) ||\n"
        "        !read_main_ram32(wide->scale_patch_addr2, &second) ||\n"
        "        !read_main_ram32(wide->scale_value_addr, &scale_word))\n"
        "        return;\n"
        "    // Fail closed before doing any partial write. These are the exact\n"
        "    // guards used by melonPrimeDS for the three MPH widescreen patches.\n"
        "    if (static_cast<uint32_t>(first) != kMphScaleOrig1 ||\n"
        "        static_cast<uint32_t>(second) != kMphScaleOrig2 ||\n"
        "        (static_cast<uint32_t>(scale_word) & 0xFFFFu) != kMphScaleOrigValue)\n"
        "        return;\n"
        "    bus_write_u32_slow(wide->scale_patch_addr1, kMphScale21x9Instr);\n"
        "    bus_write_u32_slow(wide->scale_patch_addr2, kMphScale21x9Instr);\n"
        "    const uint32_t patched_scale =\n"
        "        (static_cast<uint32_t>(scale_word) & 0xFFFF0000u) | kMphScale21x9Value;\n"
        "    bus_write_u32_slow(wide->scale_value_addr, patched_scale);\n"
        "    g_mph_aspect_ratio_applied = true;\n"
        "    std::fprintf(stderr,\n"
        "                 \"[mph] adaptive 21:9 projection/culling enabled for %s\\n\",\n"
        "                 g_mph_runtime_profile->key);\n"
        "}\n\n"
        "}  // namespace\n\nvoid nds_title_patches_set_sm64ds_adaptive(bool enabled) {\n",
        "patch_mph_aspect_ratio()",
    )
    patch_once(
        title_cpp,
        "    g_mph_allow_rom_sha1_mismatch = false;\n"
        "    if (!rom_data || !rom_sha1 || !expected_rom_sha1 || rom_size <= 0x1Eu)\n",
        "    g_mph_allow_rom_sha1_mismatch = false;\n"
        "    g_mph_adaptive = false;\n"
        "    g_mph_aspect_ratio_applied = false;\n"
        "    if (!rom_data || !rom_sha1 || !expected_rom_sha1 || rom_size <= 0x1Eu)\n",
        "g_mph_aspect_ratio_applied = false",
    )
    patch_once(
        title_cpp,
        "bool nds_title_patches_mph_host_writes_compatible() {\n",
        "bool nds_title_patches_mph_detected() {\n"
        "    return g_mph_runtime_profile != nullptr;\n"
        "}\n\n"
        "void nds_title_patches_set_mph_adaptive(bool enabled) {\n"
        "    g_mph_adaptive = enabled && g_mph_runtime_profile &&\n"
        "                     g_mph_host_writes_compatible;\n"
        "    if (!g_mph_adaptive) g_mph_aspect_ratio_applied = false;\n"
        "}\n\n"
        "bool nds_title_patches_mph_host_writes_compatible() {\n",
        "nds_title_patches_mph_detected()",
    )
    patch_once(
        title_cpp,
        "void nds_title_patches_start_frame() {\n"
        "    if (g_sm64ds_adaptive) patch_sm64ds_clipper();\n"
        "}\n",
        "void nds_title_patches_start_frame() {\n"
        "    if (g_sm64ds_adaptive) patch_sm64ds_clipper();\n"
        "    if (g_mph_adaptive) patch_mph_aspect_ratio();\n"
        "}\n",
        "if (g_mph_adaptive) patch_mph_aspect_ratio();",
    )

    patch_once(
        main_cpp,
        "        sm64ds_wide_policy = true;\n"
        "    }\n"
        "#endif\n"
        "    if (interactive &&\n",
        "        sm64ds_wide_policy = true;\n"
        "    }\n"
        "#endif\n"
        "    // MPH_MULTIROM_WIDESCREEN_GATE: a header-only base-profile hint is\n"
        "    // insufficient for host code/data writes. Keep the UI option visible,\n"
        "    // but force native presentation when executable compatibility is unknown.\n"
        "    if (nds_title_patches_mph_detected() &&\n"
        "        !nds_title_patches_mph_host_writes_compatible()) {\n"
        "        if ((frontend_options.adaptive_screens & NDS_ADAPTIVE_TOP) != 0u)\n"
        "            std::fprintf(stderr,\n"
        "                         \"[mph] adaptive widescreen disabled: unknown executable checksum\\n\");\n"
        "        frontend_options.adaptive_screens &= ~NDS_ADAPTIVE_TOP;\n"
        "        frontend_options.adaptive_hud_anchor = false;\n"
        "    }\n"
        "    if (interactive &&\n",
        "MPH_MULTIROM_WIDESCREEN_GATE",
    )
    patch_once(
        main_cpp,
        "    nds_title_patches_set_sm64ds_adaptive(\n"
        "        sm64ds_wide_policy &&\n"
        "        (frontend_options.adaptive_screens & NDS_ADAPTIVE_TOP) != 0u);\n"
        "    nds_title_patches_set_mph_mouse_aim(mph_mouse_aim_policy);\n",
        "    nds_title_patches_set_sm64ds_adaptive(\n"
        "        sm64ds_wide_policy &&\n"
        "        (frontend_options.adaptive_screens & NDS_ADAPTIVE_TOP) != 0u);\n"
        "    nds_title_patches_set_mph_adaptive(\n"
        "        nds_title_patches_mph_host_writes_compatible() &&\n"
        "        (frontend_options.adaptive_screens & NDS_ADAPTIVE_TOP) != 0u);\n"
        "    nds_title_patches_set_mph_mouse_aim(mph_mouse_aim_policy);\n",
        "nds_title_patches_set_mph_adaptive(",
    )

    print("Patched MPH adaptive 21:9 runtime profiles: " +
          ", ".join(str(p["key"]) for p in profiles))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    args = parser.parse_args()
    patch(args.framework_root.resolve(), args.profiles.resolve())


if __name__ == "__main__":
    main()
