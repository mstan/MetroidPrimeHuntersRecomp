#!/usr/bin/env python3
"""Promote deterministic Tier-3 call targets into profile-specific main-bank seeds."""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

from mph_profile import (
    DEFAULT_PROFILE_FILE,
    DEFAULT_VERSION,
    default_generated_inputs_dir,
    load_profile,
)


PROMOTABLE_KINDS = {2: "call", 3: "indirect"}


def load_program(path: Path, expected_id: str) -> tuple[int, int, int]:
    try:
        with path.open("rb") as f:
            document = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"unable to read generated program config {path}: {exc}") from exc

    program = document.get("program")
    if not isinstance(program, dict):
        raise SystemExit(f"{path} has no [program] table")
    if str(program.get("id", "")) != expected_id:
        raise SystemExit(
            f"{path} program.id={program.get('id')!r}; expected {expected_id!r}"
        )

    try:
        load_address = int(program["load_address"])
        size = int(program["size"])
        entry_pc = int(program["entry_pc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"{path} has invalid program geometry: {exc}") from exc

    if size <= 0:
        raise SystemExit(f"{path} program.size must be positive")
    if not load_address <= entry_pc < load_address + size:
        raise SystemExit(
            f"{path} entry_pc 0x{entry_pc:08X} is outside "
            f"0x{load_address:08X}..0x{load_address + size:08X}"
        )
    return load_address, load_address + size, entry_pc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenario", default="scenarios/adventure_start.json")
    parser.add_argument("--runner-commit", required=True)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--profiles",
        type=Path,
        default=DEFAULT_PROFILE_FILE,
        help=f"ROM profile registry (default: {DEFAULT_PROFILE_FILE})",
    )
    parser.add_argument(
        "--inputs",
        type=Path,
        help=(
            "prepared input directory containing arm9.toml/arm7.toml; "
            "defaults to the selected profile's generated inputs directory"
        ),
    )
    args = parser.parse_args()

    profile = load_profile(args.profiles.resolve(), args.version)
    inputs = (
        args.inputs.resolve()
        if args.inputs is not None
        else default_generated_inputs_dir(args.version).resolve()
    )
    program_id = str(profile["program_id"])

    main_ranges: dict[int, tuple[int, int]] = {}
    existing_seeds: set[tuple[int, int, int]] = set()
    geometry: dict[str, dict[str, str]] = {}
    for cpu, filename, suffix in (
        (9, "arm9.toml", "arm9"),
        (7, "arm7.toml", "arm7"),
    ):
        start, end, entry_pc = load_program(
            inputs / filename, f"{program_id}_{suffix}"
        )
        main_ranges[cpu] = (start, end)
        existing_seeds.add((cpu, entry_pc, 0))
        geometry[suffix] = {
            "start": f"0x{start:08x}",
            "end": f"0x{end:08x}",
            "entry_pc": f"0x{entry_pc:08x}",
        }

    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    observed_profile = trace.get("mph_profile")
    if observed_profile is not None and str(observed_profile) != args.version:
        raise SystemExit(
            f"trace profile {observed_profile!r} does not match {args.version!r}"
        )
    observed_sha1 = trace.get("rom_sha1")
    expected_sha1 = str(profile["sha1"])
    if observed_sha1 is not None and str(observed_sha1) != expected_sha1:
        raise SystemExit(
            f"trace ROM SHA-1 {observed_sha1!r} does not match "
            f"{args.version} ({expected_sha1})"
        )

    coverage = trace.get("tier3_coverage", {}).get("entries", [])
    if not coverage:
        raise SystemExit(
            "trace has no Tier-3 addresses; capture with --discover-static-misses"
        )

    grouped: dict[tuple[int, int, int], dict[str, object]] = {}
    for observed in coverage:
        cpu = int(observed["cpu"])
        pc = int(observed["pc"])
        thumb = int(observed["thumb"])
        kind = int(observed["kind"])
        if cpu not in main_ranges or kind not in PROMOTABLE_KINDS:
            continue
        start, end = main_ranges[cpu]
        if not start <= pc < end:
            continue
        key = (cpu, pc, thumb)
        if key in existing_seeds:
            continue
        entry = grouped.setdefault(
            key,
            {
                "addr": f"0x{pc:08x}",
                "mode": "thumb" if thumb else "arm",
                "hits": 0,
                "kinds": [],
            },
        )
        entry["hits"] = int(entry["hits"]) + int(observed["hits"])
        kinds = entry["kinds"]
        assert isinstance(kinds, list)
        label = PROMOTABLE_KINDS[kind]
        if label not in kinds:
            kinds.append(label)

    by_cpu: dict[str, list[dict[str, object]]] = {"arm9": [], "arm7": []}
    for (cpu, _pc, _thumb), entry in sorted(grouped.items()):
        entry["kinds"] = sorted(entry["kinds"])
        by_cpu["arm7" if cpu == 7 else "arm9"].append(entry)

    payload = {
        "schema": 1,
        "profile": args.version,
        "game_sha1": expected_sha1,
        "scenario": args.scenario,
        "runner_commit": args.runner_commit,
        "selection": (
            "Tier-3 call and indirect targets inside the selected ROM's "
            "prepared immutable ARM9/ARM7 main-image ranges; slice-resume "
            "roots and runtime overlays omitted"
        ),
        "main_image": geometry,
        "static_coverage": trace.get("static_coverage", {}),
        "entry_points": by_cpu,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"{args.version}: wrote {len(by_cpu['arm9'])} ARM9 and "
        f"{len(by_cpu['arm7'])} ARM7 static coverage seeds to {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
