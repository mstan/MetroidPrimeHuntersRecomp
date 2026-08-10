#!/usr/bin/env python3
"""Promote deterministic Tier-3 call targets into reproducible main-bank seeds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


GAME_SHA1 = "90164d1ac127ee5f9815ea4ae7de798c7b5fc629"
MAIN_RANGES = {
    9: (0x02004000, 0x020E19D8),
    7: (0x02380000, 0x023A8464),
}
PROMOTABLE_KINDS = {2: "call", 3: "indirect"}
EXISTING_SEEDS = {(9, 0x02004800, 0), (7, 0x02380000, 0)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--scenario", default="scenarios/adventure_start.json"
    )
    parser.add_argument("--runner-commit", required=True)
    args = parser.parse_args()

    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    coverage = trace.get("tier3_coverage", {}).get("entries", [])
    if not coverage:
        raise SystemExit(
            "trace has no Tier-3 addresses; run with --discover-static-misses"
        )

    grouped: dict[tuple[int, int, int], dict[str, object]] = {}
    for observed in coverage:
        cpu = int(observed["cpu"])
        pc = int(observed["pc"])
        thumb = int(observed["thumb"])
        kind = int(observed["kind"])
        if cpu not in MAIN_RANGES or kind not in PROMOTABLE_KINDS:
            continue
        start, end = MAIN_RANGES[cpu]
        if not start <= pc < end:
            continue
        key = (cpu, pc, thumb)
        if key in EXISTING_SEEDS:
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
    for (cpu, pc, thumb), entry in sorted(grouped.items()):
        del pc, thumb
        entry["kinds"] = sorted(entry["kinds"])
        by_cpu["arm7" if cpu == 7 else "arm9"].append(entry)

    payload = {
        "schema": 1,
        "game_sha1": GAME_SHA1,
        "scenario": args.scenario,
        "runner_commit": args.runner_commit,
        "selection": (
            "Tier-3 call and indirect targets inside immutable ARM9/ARM7 "
            "main-image ranges; slice-resume roots and runtime overlays omitted"
        ),
        "static_coverage": trace.get("static_coverage", {}),
        "entry_points": by_cpu,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"wrote {len(by_cpu['arm9'])} ARM9 and "
        f"{len(by_cpu['arm7'])} ARM7 static coverage seeds to {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
