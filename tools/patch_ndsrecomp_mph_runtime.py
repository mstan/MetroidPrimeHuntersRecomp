#!/usr/bin/env python3
"""Apply the MPH multi-ROM runtime-profile shim to the pinned ndsrecomp runner.

The upstream runner currently hard-codes Metroid Prime Hunters USA rev-0 RAM
addresses for Prime Controls and direct mouse aim. Runtime address selection
must follow the base game/revision, not the whole-ROM hash, so modified ROMs
that preserve a supported MPH cartridge identity can use the correct layout.

The detector mirrors melonPrimeDS's fallback identity:
NDS gameCode @0x0C + ROM revision @0x1E. Unlike melonPrimeDS, revisions outside
the seven explicitly supported retail profiles fail closed instead of mapping
all non-zero revisions to 1.1.

Whole-ROM SHA-1 remains a clean-content/provenance identity. If a SHA-1 is one
of the configured known-clean ROMs, its profile must agree with the header;
an impossible clean-hash/header mismatch is rejected. An unknown SHA-1 does
not by itself reject a recognized base profile.

Runtime address values are generated from config/mph_rom_profiles.json and
cross-checked in CI against melonPrimeDS's MelonPrimeGameRomAddrTable.h.

The source patch is intentionally small, idempotent, and fail-closed. If the
pinned ndsrecomp source changes enough that the expected preimages are absent,
this script stops instead of guessing a patch against unknown code.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
MAIN_RAM_MIN = 0x02000000
MAIN_RAM_MAX = 0x023FFFFF


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


def load_runtime_profiles(registry_path: Path) -> list[dict[str, object]]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    runtime_profiles = registry.get("runtime_profiles")
    if not isinstance(runtime_profiles, dict) or not runtime_profiles:
        raise SystemExit("ROM profile registry has no runtime_profiles")

    build_profiles = registry.get("profiles")
    if not isinstance(build_profiles, dict):
        raise SystemExit("ROM profile registry has no build profiles")

    result: list[dict[str, object]] = []
    seen_identity: set[tuple[str, int]] = set()
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

    expected = {
        "US1_0", "US1_1", "EU1_0", "EU1_1", "JP1_0", "JP1_1", "KR1_0"
    }
    actual = {str(profile["key"]) for profile in result}
    if actual != expected:
        missing = ", ".join(sorted(expected - actual)) or "none"
        extra = ", ".join(sorted(actual - expected)) or "none"
        raise SystemExit(
            f"runtime profile set must be exactly the seven supported retail "
            f"profiles (missing: {missing}; extra: {extra})"
        )
    return result


def generated_header(profiles: list[dict[str, object]]) -> str:
    rows = []
    for profile in profiles:
        rows.append(
            '    {"%s", "%s", %du, "%s", 0x%08Xu, 0x%08Xu, 0x%08Xu},'
            "  // %s"
            % (
                profile["key"],
                profile["game_code"],
                profile["revision"],
                profile["known_clean_sha1"],
                profile["morph_state"],
                profile["aim_x"],
                profile["aim_y"],
                profile["key"],
            )
        )
    return """#pragma once

#include <array>
#include <cstdint>

// Generated by MetroidPrimeHuntersRecomp/tools/patch_ndsrecomp_mph_runtime.py.
// Do not edit in the ndsrecomp checkout; edit config/mph_rom_profiles.json.
//
// game_code + revision selects the base runtime layout. known_clean_sha1 is
// provenance/consistency metadata only; an unknown SHA-1 is a supported variant
// when its exact header identity matches one of these seven profiles.
struct NdsMphRuntimeProfile {
    const char* key;
    const char* game_code;
    uint8_t revision;
    const char* known_clean_sha1;
    uint32_t morph_state;
    uint32_t aim_x;
    uint32_t aim_y;
};

inline constexpr std::array<NdsMphRuntimeProfile, %d> kNdsMphRuntimeProfiles{{
%s
}};
""" % (len(rows), "\n".join(rows))


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

    profiles = load_runtime_profiles(registry_path)
    generated = runner_src / "mph_runtime_profiles.generated.h"
    generated.write_text(generated_header(profiles), encoding="utf-8")

    patch_once(
        title_h,
        "void nds_title_patches_set_mph_mouse_aim(bool enabled);\n"
        "bool nds_title_patches_apply_mph_mouse_delta(int32_t dx, int32_t dy);\n",
        "// MPH_MULTIROM_RUNTIME_PROFILE: base-profile detection from NDS header.\n"
        "bool nds_title_patches_select_mph_runtime_profile(\n"
        "    const uint8_t* rom_data, uint64_t rom_size, const char* rom_sha1);\n"
        "bool nds_title_patches_mph_in_ball();\n"
        "void nds_title_patches_set_mph_mouse_aim(bool enabled);\n"
        "bool nds_title_patches_apply_mph_mouse_delta(int32_t dx, int32_t dy);\n",
        "base-profile detection from NDS header",
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
        "// MPH_MULTIROM_RUNTIME_PROFILE: selected by exact gameCode + revision.\n"
        "const NdsMphRuntimeProfile* g_mph_runtime_profile = nullptr;\n",
        "selected by exact gameCode + revision",
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
        "    const uint8_t* rom_data, uint64_t rom_size, const char* rom_sha1) {\n"
        "    g_mph_mouse_aim = false;\n"
        "    g_mph_runtime_profile = nullptr;\n"
        "    // NDS header: game code @0x0C..0x0F, ROM version @0x1E.\n"
        "    if (!rom_data || rom_size <= 0x1Eu || !rom_sha1) return false;\n\n"
        "    const NdsMphRuntimeProfile* header_profile = nullptr;\n"
        "    for (const NdsMphRuntimeProfile& profile : kNdsMphRuntimeProfiles) {\n"
        "        if (std::memcmp(profile.game_code, rom_data + 0x0Cu, 4) == 0 &&\n"
        "            profile.revision == rom_data[0x1Eu]) {\n"
        "            if (header_profile) return false;  // ambiguous registry: fail closed\n"
        "            header_profile = &profile;\n"
        "        }\n"
        "    }\n"
        "    if (!header_profile) return false;\n\n"
        "    // Whole-ROM SHA-1 is clean identity/provenance, not the selector.\n"
        "    // If this content is a known clean dump, its header must agree with\n"
        "    // the corresponding base profile. Unknown hashes are mod variants.\n"
        "    const NdsMphRuntimeProfile* clean_profile = nullptr;\n"
        "    for (const NdsMphRuntimeProfile& profile : kNdsMphRuntimeProfiles) {\n"
        "        if (profile.known_clean_sha1[0] != '\\0' &&\n"
        "            std::strcmp(profile.known_clean_sha1, rom_sha1) == 0) {\n"
        "            clean_profile = &profile;\n"
        "            break;\n"
        "        }\n"
        "    }\n"
        "    if (clean_profile && clean_profile != header_profile) return false;\n\n"
        "    g_mph_runtime_profile = header_profile;\n"
        "    return true;\n"
        "}\n\n"
        "bool nds_title_patches_mph_in_ball() {\n"
        "    return g_mph_runtime_profile &&\n"
        "           bus_read_u8_slow(g_mph_runtime_profile->morph_state) == 0x02u;\n"
        "}\n\n"
        "void nds_title_patches_set_mph_mouse_aim(bool enabled) {\n"
        "    g_mph_mouse_aim = enabled && g_mph_runtime_profile;\n"
        "}\n\n"
        "bool nds_title_patches_apply_mph_mouse_delta(int32_t dx, int32_t dy) {\n"
        "    if (!g_mph_mouse_aim || !g_mph_runtime_profile ||\n"
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
        "    mph_mouse_aim_policy =\n"
        "        rom_sha1 == \"90164d1ac127ee5f9815ea4ae7de798c7b5fc629\" &&\n"
        "        frontend_options.relative_mouse_touch;\n",
        "    // MPH_MULTIROM_RUNTIME_PROFILE: select the base address layout from\n"
        "    // gameCode + revision. SHA-1 only checks known-clean consistency;\n"
        "    // modified ROMs with a supported exact header identity remain usable.\n"
        "    const bool mph_runtime_profile =\n"
        "        nds_title_patches_select_mph_runtime_profile(\n"
        "            rom.data(), static_cast<uint64_t>(rom.size()), rom_sha1.c_str());\n"
        "    mph_mouse_aim_policy =\n"
        "        mph_runtime_profile && frontend_options.relative_mouse_touch;\n",
        "SHA-1 only checks known-clean consistency",
    )

    print(
        f"Patched ndsrecomp MPH runtime base profiles: "
        + ", ".join(str(profile["key"]) for profile in profiles)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    args = parser.parse_args()
    patch_runner(args.framework_root.resolve(), args.profiles.resolve())


if __name__ == "__main__":
    main()
