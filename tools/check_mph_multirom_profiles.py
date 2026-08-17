#!/usr/bin/env python3
"""Static consistency checks for Metroid Prime Hunters ROM profiles.

Build/capture profiles describe exact clean-content identities and generated
artifacts. Runtime profiles separately describe the seven supported base ROM
layouts. This separation is intentional: whole-ROM SHA-1 is provenance, while
runtime Aim/Morph address selection follows gameCode + revision.

When --melonprime-table is provided, every runtime Aim/Morph address is
cross-checked against melonPrimeDS's MelonPrimeGameRomAddrTable.h.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from typing import NoReturn


SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
BANK_RE = re.compile(r"^[A-Za-z0-9_]+$")
HEX_RE = re.compile(r"0x[0-9A-Fa-f]+u?")
REQUIRED_RUNTIME_FIELDS = {
    "morph_state": "baseIsAltForm",
    "aim_x": "baseAimX",
    "aim_y": "baseAimY",
}
EXPECTED_RUNTIME_PROFILES = {
    "US1_0": ("AMHE", 0),
    "US1_1": ("AMHE", 1),
    "EU1_0": ("AMHP", 0),
    "EU1_1": ("AMHP", 1),
    "JP1_0": ("AMHJ", 0),
    "JP1_1": ("AMHJ", 1),
    "KR1_0": ("AMHK", 0),
}


def die(message: str) -> NoReturn:
    raise SystemExit(f"ERROR: {message}")


def parse_hex(value: object, where: str) -> int:
    if not isinstance(value, str):
        die(f"{where} must be a hex string")
    try:
        return int(value, 0)
    except ValueError:
        die(f"{where} has invalid hex value {value!r}")


def load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_melonprime_table(path: Path) -> dict[str, dict[str, int]]:
    text = path.read_text(encoding="utf-8")
    enum_match = re.search(
        r"enum\s+class\s+RomGroup\s*:\s*int\s*\{([^}]*)\}", text, re.S
    )
    if not enum_match:
        die(f"could not parse RomGroup from {path}")
    groups: list[str] = []
    for raw in enum_match.group(1).split(","):
        token = raw.strip().split("=")[0].strip()
        if token and token != "COUNT":
            groups.append(token)
    if not groups:
        die(f"RomGroup has no revisions in {path}")

    wanted = set(REQUIRED_RUNTIME_FIELDS.values())
    fields: dict[str, list[int]] = {}
    row_re = re.compile(
        r"X\(ADDR,\s*([A-Za-z0-9_]+),\s*[A-Za-z0-9_]+,\s*([^)]*)\)"
    )
    for match in row_re.finditer(text):
        field = match.group(1)
        if field not in wanted:
            continue
        values = [
            int(token.rstrip("uU"), 16)
            for token in HEX_RE.findall(match.group(2))
        ]
        if len(values) != len(groups):
            die(
                f"{field} in {path} has {len(values)} values; "
                f"RomGroup has {len(groups)} revisions"
            )
        fields[field] = values

    missing = wanted - fields.keys()
    if missing:
        die(f"missing melonPrimeDS fields: {', '.join(sorted(missing))}")

    result: dict[str, dict[str, int]] = {}
    for index, group in enumerate(groups):
        result[group] = {field: values[index] for field, values in fields.items()}
    return result


def validate_runtime_profiles(
    registry: dict[str, object],
    melon: dict[str, dict[str, int]] | None,
) -> dict[str, dict[str, object]]:
    runtime_profiles = registry.get("runtime_profiles")
    if not isinstance(runtime_profiles, dict):
        die("ROM profile registry has no object-valued runtime_profiles")

    actual_keys = set(runtime_profiles)
    expected_keys = set(EXPECTED_RUNTIME_PROFILES)
    if actual_keys != expected_keys:
        missing = ", ".join(sorted(expected_keys - actual_keys)) or "none"
        extra = ", ".join(sorted(actual_keys - expected_keys)) or "none"
        die(
            "runtime_profiles must contain exactly the seven supported retail "
            f"profiles (missing: {missing}; extra: {extra})"
        )

    seen_identity: set[tuple[str, int]] = set()
    validated: dict[str, dict[str, object]] = {}
    for key, expected_identity in EXPECTED_RUNTIME_PROFILES.items():
        profile = runtime_profiles.get(key)
        if not isinstance(profile, dict):
            die(f"runtime profile {key} must be an object")

        game_code = profile.get("game_code")
        revision = profile.get("revision")
        if (game_code, revision) != expected_identity:
            die(
                f"{key} runtime identity is {(game_code, revision)!r}; "
                f"expected {expected_identity!r}"
            )
        if not isinstance(game_code, str) or len(game_code) != 4 or not game_code.isascii():
            die(f"{key}.game_code must be exactly four ASCII characters")
        if not isinstance(revision, int) or revision not in (0, 1):
            die(f"{key}.revision is not an explicitly supported revision")

        identity = (game_code, revision)
        if identity in seen_identity:
            die(f"duplicate runtime cartridge identity: {game_code} rev {revision}")
        seen_identity.add(identity)

        runtime = profile.get("runtime")
        if not isinstance(runtime, dict):
            die(f"{key}.runtime is required")
        parsed_runtime: dict[str, int] = {}
        for profile_field in REQUIRED_RUNTIME_FIELDS:
            value = parse_hex(runtime.get(profile_field), f"{key}.runtime.{profile_field}")
            if not 0x02000000 <= value <= 0x023FFFFF:
                die(f"{key}.runtime.{profile_field} is outside DS main RAM")
            parsed_runtime[profile_field] = value

        if melon is not None:
            if key not in melon:
                die(f"{key} is not present in melonPrimeDS RomGroup")
            for profile_field, melon_field in REQUIRED_RUNTIME_FIELDS.items():
                actual = parsed_runtime[profile_field]
                expected = melon[key][melon_field]
                if actual != expected:
                    die(
                        f"{key}.{profile_field}=0x{actual:08X}, but "
                        f"melonPrimeDS {melon_field}=0x{expected:08X}"
                    )

        validated[key] = profile

    return validated


def validate_registry(repo: Path, table: Path | None) -> None:
    registry_path = repo / "config" / "mph_rom_profiles.json"
    registry_obj = load_json(registry_path)
    if not isinstance(registry_obj, dict):
        die("ROM profile registry must be a JSON object")
    registry: dict[str, object] = registry_obj

    if registry.get("schema") != 3:
        die("ROM profile registry schema must be 3")

    expected_address_source = (
        "https://github.com/ag-advania/melonPrimeDS/blob/develop_hud/"
        "src/frontend/qt_sdl/MelonPrimeGameRomAddrTable.h"
    )
    expected_detection_source = (
        "https://github.com/ag-advania/melonPrimeDS/blob/develop_hud/"
        "src/frontend/qt_sdl/MelonPrimeGameRomDetect.cpp"
    )
    if registry.get("runtime_address_source") != expected_address_source:
        die("runtime_address_source is not the approved develop_hud address table")
    if registry.get("runtime_detection_source") != expected_detection_source:
        die("runtime_detection_source is not the approved develop_hud detector")

    melon = parse_melonprime_table(table) if table else None
    runtime_profiles = validate_runtime_profiles(registry, melon)

    profiles = registry.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        die("ROM profile registry has no clean build/capture profiles")

    seen_sha1: set[str] = set()
    seen_fmv_banks: set[str] = set()

    for key, profile in profiles.items():
        if not isinstance(profile, dict):
            die(f"profile {key} must be an object")
        if key not in runtime_profiles:
            die(f"{key}: clean build profile has no runtime base profile")

        sha1 = profile.get("sha1")
        game_code = profile.get("game_code")
        revision = profile.get("revision")
        if not isinstance(sha1, str) or not SHA1_RE.fullmatch(sha1):
            die(f"{key}.sha1 must be 40 lowercase hex digits")
        if sha1 in seen_sha1:
            die(f"duplicate SHA-1 in profile registry: {sha1}")
        seen_sha1.add(sha1)

        runtime_profile = runtime_profiles[key]
        if (
            game_code != runtime_profile.get("game_code")
            or revision != runtime_profile.get("revision")
        ):
            die(f"{key}: clean build identity disagrees with runtime base profile")

        launcher_default_rom = profile.get("launcher_default_rom")
        if (
            not isinstance(launcher_default_rom, str)
            or not launcher_default_rom
            or not launcher_default_rom.lower().endswith(".nds")
        ):
            die(f"{key}.launcher_default_rom must be a non-empty .nds filename")
        if Path(launcher_default_rom).name != launcher_default_rom:
            die(f"{key}.launcher_default_rom must be a filename, not a path")
        adaptive_widescreen = profile.get("adaptive_widescreen")
        if not isinstance(adaptive_widescreen, bool):
            die(f"{key}.adaptive_widescreen must be boolean")

        fmv_runtime = profile.get("fmv_runtime")
        if not isinstance(fmv_runtime, bool):
            die(f"{key}.fmv_runtime must be boolean")
        fmv_runtime_bank = profile.get("fmv_runtime_bank")
        if (
            not isinstance(fmv_runtime_bank, str)
            or not BANK_RE.fullmatch(fmv_runtime_bank)
            or "_arm9_" not in fmv_runtime_bank
        ):
            die(f"{key}.fmv_runtime_bank must be a C identifier-style ARM9 bank name")
        if fmv_runtime_bank in seen_fmv_banks:
            die(f"duplicate FMV runtime bank identity: {fmv_runtime_bank}")
        seen_fmv_banks.add(fmv_runtime_bank)

        if fmv_runtime:
            runtime_config_path = repo / "config" / f"{fmv_runtime_bank}.toml"
            if not runtime_config_path.is_file():
                die(
                    f"{key} enables FMV runtime but config is missing: "
                    f"{runtime_config_path}"
                )
            with runtime_config_path.open("rb") as f:
                runtime_config = tomllib.load(f)
            runtime_program = runtime_config.get("program")
            if not isinstance(runtime_program, dict):
                die(f"{runtime_config_path} has no [program] table")
            if runtime_program.get("id") != fmv_runtime_bank:
                die(
                    f"{runtime_config_path} program.id={runtime_program.get('id')!r}; "
                    f"expected {fmv_runtime_bank!r}"
                )

        coverage_path = repo / str(profile.get("coverage", ""))
        if not coverage_path.is_file():
            die(f"{key}.coverage does not exist: {coverage_path}")
        coverage = load_json(coverage_path)
        if not isinstance(coverage, dict) or coverage.get("game_sha1") != sha1:
            die(f"{key}.coverage game_sha1 does not match profile SHA-1")

        game_config_path = repo / str(profile.get("game_config", ""))
        if not game_config_path.is_file():
            die(f"{key}.game_config does not exist: {game_config_path}")
        with game_config_path.open("rb") as f:
            game_config = tomllib.load(f)
        game = game_config.get("game")
        if not isinstance(game, dict):
            die(f"{key}.game_config has no [game] table")
        expected_config = {
            "id": game_code,
            "revision": revision,
            "rom_size": profile.get("rom_size"),
            "sha1": sha1,
        }
        for field, expected in expected_config.items():
            if game.get(field) != expected:
                die(
                    f"{key}.game_config game.{field}={game.get(field)!r}; "
                    f"expected {expected!r}"
                )

        display = game_config.get("display", {})
        if not isinstance(display, dict):
            die(f"{key}.game_config [display] must be a table")
        config_adaptive = display.get("adaptive_widescreen")
        if adaptive_widescreen:
            if config_adaptive != "top":
                die(
                    f"{key} enables adaptive_widescreen in the profile but "
                    "game config does not enable top-screen adaptive widescreen"
                )
        elif config_adaptive not in (None, "none"):
            die(
                f"{key} disables adaptive_widescreen in the profile but "
                f"game config enables {config_adaptive!r}"
            )

    us = profiles.get("US1_0")
    if not isinstance(us, dict):
        die("US1_0 clean build profile is required")
    if us.get("fmv_runtime_bank") != "mph_arm9_fmv_runtime":
        die("US1_0 historical FMV runtime bank identity changed unexpectedly")

    eu = profiles.get("EU1_1")
    if not isinstance(eu, dict):
        die("EU1_1 clean build profile is required")
    if eu.get("game_code") != "AMHP" or eu.get("revision") != 1:
        die("EU1_1 must remain AMHP revision 1")
    if eu.get("sha1") != "bdcd1dea293e24c98d4c481430e90d21198985a5":
        die("EU1_1 SHA-1 changed unexpectedly")
    eu_runtime = runtime_profiles["EU1_1"].get("runtime", {})
    expected_eu_runtime = {
        "morph_state": "0x020DB138",
        "aim_x": "0x020DEE46",
        "aim_y": "0x020DEE4E",
    }
    if eu_runtime != expected_eu_runtime:
        die(f"EU1_1 runtime profile changed unexpectedly: {eu_runtime!r}")
    if eu.get("fmv_runtime") is not False:
        die("EU1_1 must not reuse the US1.0 FMV runtime capture")
    if eu.get("fmv_runtime_bank") != "mph_amhp1_arm9_fmv_runtime":
        die("EU1_1 FMV runtime bank identity changed unexpectedly")
    if eu.get("adaptive_widescreen") is not False:
        die("EU1_1 adaptive widescreen must remain disabled until validated")
    if eu.get("launcher_default_rom") != "Metroid Prime Hunters (Europe Rev 1).nds":
        die("EU1_1 launcher default ROM filename changed unexpectedly")

    print(
        f"OK: validated {len(runtime_profiles)} runtime base profiles and "
        f"{len(profiles)} clean build/capture profiles"
    )
    if melon is not None:
        print(f"OK: all seven Aim/Morph profiles match melonPrimeDS table: {table}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--melonprime-table",
        type=Path,
        help="Downloaded MelonPrimeGameRomAddrTable.h to cross-check",
    )
    args = parser.parse_args()
    validate_registry(args.repo.resolve(), args.melonprime_table)


if __name__ == "__main__":
    main()
