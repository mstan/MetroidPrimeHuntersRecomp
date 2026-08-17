#!/usr/bin/env python3
"""Validate the current multi-ROM schema, then run the legacy deep checks.

The legacy checker predates the all-version Adaptive Widescreen address table,
the shared runtime-generic frontend config, and optional bootstrap-only coverage.
Preserve its broad coverage on a temporary compatibility view while validating
the current scale fields and generic config contract against the real registry.
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

    # Runtime frontend policy is shared by every exact-content profile. Exact
    # ROM SHA/header identity belongs in this registry and generated bank/cache
    # provenance, not in one region-specific game TOML.
    shared_config = repo / "game.toml"
    if not shared_config.is_file():
        die("shared runtime frontend config is missing: game.toml")
    shared_text = shared_config.read_text(encoding="utf-8")
    if 'adaptive_widescreen = "top"' not in shared_text:
        die("shared game.toml does not request top-screen Adaptive Widescreen")
    # ndsrecomp deliberately requires an exact [game].sha1 when a TOML grants
    # display.adaptive_capability. The generic seven-version config has no exact
    # SHA, so capability must be granted later by the executable-compatible
    # runtime detector instead of being declared here.
    if 'adaptive_capability = "top"' in shared_text:
        die("shared game.toml must not declare SHA-gated adaptive_capability")
    capability_patch = repo / "tools" / "patch_ndsrecomp_mph_adaptive_capability.py"
    if not capability_patch.is_file():
        die("runtime adaptive capability patch is missing")
    capability_text = capability_patch.read_text(encoding="utf-8")
    for required in (
        "nds_title_patches_mph_host_writes_compatible()",
        "frontend_options.adaptive_supported |= NDS_ADAPTIVE_TOP",
        "MPH_MULTIROM_RUNTIME_ADAPTIVE_CAPABILITY",
    ):
        if required not in capability_text:
            die(f"runtime adaptive capability patch lost required guard: {required}")
    for forbidden in ("\nid =", "\nregion =", "\nrevision =", "\nrom =", "\nrom_size =", "\nsha1 ="):
        if forbidden in shared_text:
            die(f"shared game.toml still contains exact-content identity field: {forbidden.strip()}")

    for key, profile in profiles.items():
        if not isinstance(profile, dict):
            die(f"{key}: invalid content profile")
        if profile.get("adaptive_widescreen") is not True:
            die(f"{key}: Adaptive Widescreen must remain exposed for known content profiles")
        if profile.get("game_config") != "game.toml":
            die(f"{key}: content profiles must share the generic game.toml frontend config")

        coverage = profile.get("coverage")
        if not isinstance(coverage, str):
            die(f"{key}.coverage must be a string; use an empty string for bootstrap-only")
        if coverage:
            coverage_path = repo / coverage
            if not coverage_path.is_file():
                die(f"{key}.coverage does not exist: {coverage_path}")
            coverage_doc = json.loads(coverage_path.read_text(encoding="utf-8"))
            if coverage_doc.get("game_sha1") != profile.get("sha1"):
                die(f"{key}.coverage game_sha1 does not match profile SHA-1")

    # EU1.1 never had promoted coverage: the removed file contained zero ARM9
    # and zero ARM7 entries and existed only to satisfy the old required-file
    # shape. Keep the source tree honest and represent that state as no seed.
    if profiles.get("EU1_1", {}).get("coverage") != "":
        die("EU1_1 should remain bootstrap-only until real coverage is promoted")
    if (repo / "coverage" / "eu11-bootstrap-entry-points.json").exists():
        die("obsolete empty EU1.1 bootstrap coverage placeholder still exists")

    if table:
        text = table.read_text(encoding="utf-8")
        rows = {
            "scale_patch_addr1": ("scalePatchAddr1", "ScalePatchAddr1"),
            "scale_patch_addr2": ("scalePatchAddr2", "ScalePatchAddr2"),
            "scale_value_addr": ("scaleValueAddr", "ScaleValueAddr"),
        }
        order = ("JP1_0", "JP1_1", "US1_0", "US1_1", "EU1_0", "EU1_1", "KR1_0")
        for field, (member_name, list_name) in rows.items():
            match = re.search(
                rf"X\(ADDR,\s*{member_name},\s*{list_name},\s*([^\n]+)\)", text
            )
            if not match:
                die(f"melonPrimeDS table missing {list_name}")
            values = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]+)u?", match.group(1))]
            expected = [EXPECTED_SCALE[key][SCALE_FIELDS.index(field)] for key in order]
            if values[:7] != expected:
                die(f"melonPrimeDS {list_name} drifted from registry")


def legacy_compat_view(repo: Path, destination: Path) -> Path:
    """Synthesize old required-file/profile shapes only for the legacy checker."""
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

    # The old checker requires a concrete coverage file for every profile.
    # Generate an empty identity-only manifest in the temporary compatibility
    # copy when the production profile intentionally has no promoted coverage.
    for key, profile in registry["profiles"].items():
        if not profile.get("coverage"):
            legacy_coverage_rel = f"coverage/.legacy-{key}-bootstrap.json"
            legacy_coverage_path = target / legacy_coverage_rel
            legacy_coverage_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_coverage_path.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "game_sha1": profile["sha1"],
                        "scenario": None,
                        "selection": "legacy checker bootstrap compatibility view",
                        "entry_points": {"arm9": [], "arm7": []},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            profile["coverage"] = legacy_coverage_rel

        legacy_rel = f"config/.legacy-{key}.toml"
        profile["game_config"] = legacy_rel
        adaptive = profile.get("adaptive_widescreen") is True
        if key == "EU1_1":
            adaptive = False
            profile["adaptive_widescreen"] = False
        lines = [
            "[game]",
            f'id = "{profile["game_code"]}"',
            f'revision = {profile["revision"]}',
            f'rom_size = {profile["rom_size"]}',
            f'sha1 = "{profile["sha1"]}"',
            "",
            "[display]",
        ]
        if adaptive:
            lines.append('adaptive_widescreen = "top"')
        (target / legacy_rel).write_text("\n".join(lines) + "\n", encoding="utf-8")

    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
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
    print("OK: seven-version runtime tables and shared generic game.toml are consistent")


if __name__ == "__main__":
    main()
