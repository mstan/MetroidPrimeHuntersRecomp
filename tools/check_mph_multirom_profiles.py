#!/usr/bin/env python3
"""Validate the current multi-ROM schema, then run the legacy deep checks.

The legacy checker predates the all-version Adaptive Widescreen address table
and intentionally asserted EU1_1=false plus three runtime fields. Preserve its
broad coverage on a compatibility view while validating the new scale fields
against melonPrimeDS on the real registry.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import tempfile
from pathlib import Path

EXPECTED_SCALE = {
    "JP1_0": (0x0211313C, 0x0211E7E8, 0x02112960),
    "JP1_1": (0x021130FC, 0x0211E7A8, 0x02112920),
    "US1_0": (0x02110FFC, 0x0211C638, 0x02110820),
    "US1_1": (0x02111ABC, 0x0211D168, 0x021112E0),
    "EU1_0": (0x02111ADC, 0x0211D114, 0x02111300),
    "EU1_1": (0x02111B5C, 0x0211D208, 0x02111380),
    "KR1_0": (0x02109B64, 0x02114838, 0x021091A4),
}
SCALE_FIELDS = ("scale_patch_addr1", "scale_patch_addr2", "scale_value_addr")


def die(message: str) -> None:
    raise SystemExit(message)


def load_legacy(path: Path):
    spec = importlib.util.spec_from_file_location("mph_multirom_legacy", path)
    if spec is None or spec.loader is None:
        die(f"unable to import legacy checker: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_scale_registry(repo: Path, table: Path | None) -> None:
    registry_path = repo / "config" / "mph_rom_profiles.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    runtime = registry.get("runtime_profiles")
    if not isinstance(runtime, dict) or set(runtime) != set(EXPECTED_SCALE):
        die("runtime profile set no longer matches the seven MPH revisions")

    for key, expected in EXPECTED_SCALE.items():
        item = runtime[key]
        fields = item.get("runtime") if isinstance(item, dict) else None
        if not isinstance(fields, dict):
            die(f"{key}: runtime table missing")
        got = []
        for name in SCALE_FIELDS:
            value = fields.get(name)
            if not isinstance(value, str):
                die(f"{key}.{name}: expected hex string")
            got.append(int(value, 0))
        if tuple(got) != expected:
            die(f"{key}: widescreen address triple changed: {tuple(hex(x) for x in got)}")

    profiles = registry.get("profiles")
    if not isinstance(profiles, dict):
        die("content profiles missing")
    for key, profile in profiles.items():
        if not isinstance(profile, dict):
            die(f"{key}: invalid content profile")
        if profile.get("adaptive_widescreen") is not True:
            die(f"{key}: Adaptive Widescreen must remain exposed for known content profiles")
        config_path = repo / str(profile.get("game_config", ""))
        text = config_path.read_text(encoding="utf-8")
        if 'adaptive_widescreen = "top"' not in text or 'adaptive_capability = "top"' not in text:
            die(f"{key}: game config does not expose top-screen Adaptive Widescreen")

    if table:
        text = table.read_text(encoding="utf-8")
        row_names = {
            "scale_patch_addr1": "ScalePatchAddr1",
            "scale_patch_addr2": "ScalePatchAddr2",
            "scale_value_addr": "ScaleValueAddr",
        }
        order = ("JP1_0", "JP1_1", "US1_0", "US1_1", "EU1_0", "EU1_1", "KR1_0")
        for field, list_name in row_names.items():
            match = re.search(
                rf"X\(ADDR,\s*{field},\s*{list_name},\s*([^\n]+)\)", text
            )
            if not match:
                die(f"melonPrimeDS table missing {list_name}")
            values = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)u?", match.group(1))]
            expected = [EXPECTED_SCALE[key][SCALE_FIELDS.index(field)] for key in order]
            if values[:7] != expected:
                die(f"melonPrimeDS {list_name} drifted from registry")


def legacy_compat_view(repo: Path, destination: Path) -> Path:
    target = destination / "repo"
    shutil.copytree(
        repo, target,
        ignore=shutil.ignore_patterns(".git", "generated", "build", "build-*", "scratch"),
    )
    registry_path = target / "config" / "mph_rom_profiles.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for item in registry["runtime_profiles"].values():
        runtime = item["runtime"]
        for field in SCALE_FIELDS:
            runtime.pop(field, None)
    registry["profiles"]["EU1_1"]["adaptive_widescreen"] = False
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    eu_config = target / "config" / "game-eu11.toml"
    lines = eu_config.read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if not line.startswith("adaptive_widescreen =")]
    eu_config.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--melonprime-table", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    table = args.melonprime_table.resolve() if args.melonprime_table else None

    validate_scale_registry(repo, table)
    legacy = load_legacy(repo / "tools" / "check_mph_multirom_profiles_legacy.py")
    with tempfile.TemporaryDirectory(prefix="mph-multirom-check-") as temp:
        compat = legacy_compat_view(repo, Path(temp))
        legacy.validate_registry(compat, table)
    print("OK: Adaptive Widescreen address/capability checks passed for all seven MPH revisions")


if __name__ == "__main__":
    main()
