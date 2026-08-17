#!/usr/bin/env python3
"""Static consistency checks for Metroid Prime Hunters ROM profiles.

This intentionally does not need a copyrighted ROM. It verifies that each
profile's identity, coverage seed, game config, and host-side runtime addresses
agree. When --melonprime-table is provided, Aim/Morph addresses are also
cross-checked against melonPrimeDS's MelonPrimeGameRomAddrTable.h, which is the
source of truth for those fields.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path


SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
HEX_RE = re.compile(r"0x[0-9A-Fa-f]+u?")
REQUIRED_RUNTIME_FIELDS = {
    "morph_state": "baseIsAltForm",
    "aim_x": "baseAimX",
    "aim_y": "baseAimY",
}


def die(message: str) -> "NoReturn":
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


def validate_registry(repo: Path, table: Path | None) -> None:
    registry_path = repo / "config" / "mph_rom_profiles.json"
    registry = load_json(registry_path)
    if not isinstance(registry, dict):
        die("ROM profile registry must be a JSON object")
    if registry.get("schema") != 2:
        die("ROM profile registry schema must be 2")

    expected_source = (
        "https://github.com/ag-advania/melonPrimeDS/blob/main/"
        "src/frontend/qt_sdl/MelonPrimeGameRomAddrTable.h"
    )
    if registry.get("runtime_address_source") != expected_source:
        die("runtime_address_source is not the approved melonPrimeDS address table")

    profiles = registry.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        die("ROM profile registry has no profiles")

    melon = parse_melonprime_table(table) if table else None
    seen_sha1: set[str] = set()
    seen_identity: set[tuple[str, int]] = set()

    for key, profile in profiles.items():
        if not isinstance(profile, dict):
            die(f"profile {key} must be an object")
        sha1 = profile.get("sha1")
        game_code = profile.get("game_code")
        revision = profile.get("revision")
        if not isinstance(sha1, str) or not SHA1_RE.fullmatch(sha1):
            die(f"{key}.sha1 must be 40 lowercase hex digits")
        if sha1 in seen_sha1:
            die(f"duplicate SHA-1 in profile registry: {sha1}")
        seen_sha1.add(sha1)
        if not isinstance(game_code, str) or len(game_code) != 4:
            die(f"{key}.game_code must be four characters")
        if not isinstance(revision, int) or not 0 <= revision <= 255:
            die(f"{key}.revision must be an unsigned byte")
        identity = (game_code, revision)
        if identity in seen_identity:
            die(f"duplicate cartridge identity: {game_code} rev {revision}")
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

    # Explicit regression guard for the first non-US revision. These are the
    # values currently published by melonPrimeDS's source-of-truth table.
    eu = profiles.get("EU1_1")
    if not isinstance(eu, dict):
        die("EU1_1 profile is required")
    if eu.get("game_code") != "AMHP" or eu.get("revision") != 1:
        die("EU1_1 must remain AMHP revision 1")
    if eu.get("sha1") != "bdcd1dea293e24c98d4c481430e90d21198985a5":
        die("EU1_1 SHA-1 changed unexpectedly")
    eu_runtime = eu.get("runtime", {})
    expected_eu_runtime = {
        "morph_state": "0x020DB138",
        "aim_x": "0x020DEE46",
        "aim_y": "0x020DEE4E",
    }
    if eu_runtime != expected_eu_runtime:
        die(f"EU1_1 runtime profile changed unexpectedly: {eu_runtime!r}")
    if eu.get("fmv_runtime") is not False:
        die("EU1_1 must not reuse the US1.0 FMV runtime capture")

    print(f"OK: validated {len(profiles)} MPH ROM profiles")
    if melon is not None:
        print(f"OK: Aim/Morph addresses match melonPrimeDS table: {table}")


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
