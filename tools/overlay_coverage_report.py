#!/usr/bin/env python3
"""Report which ARM9 overlays a play route actually exercised.

beads-yjp.31. Answers the question that decides what to recompile ahead of
time: for a given route through the game, which overlays did the guest
actually execute, and how hard?

Takes any number of coverage sources and maps every Tier-3 address onto the
overlay table:

  * a coverage manifest written by the runner (--coverage-manifest, or the
    `coverage_manifest` debug command), which has entry_points_arm9/arm7, or
  * a fuzz/benchmark trace.json carrying a tier3_coverage block.

Collisions are computed by SPAN, not by load address. Judging by load address
alone is wrong and flatters the picture: in MPH three overlays look unshared
by load address, but every one of the eighteen overlaps another by span (e.g.
overlay 4 loads at 0x0214C860 and overlay 10 loads at 0x0214C940, 0xE0 bytes
inside it).

Addresses that fall outside every overlay are reported too, not dropped --
ITCM, ARM7 WRAM and the immutable main image all show up there, and a silent
drop would make a route look better covered than it is.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_overlays(path: Path) -> list[dict]:
    overlays = json.loads(path.read_text(encoding="utf-8"))
    for entry in overlays:
        entry["lo"] = int(entry["load_address"], 16)
        # bss is zero-initialised at load and holds no code, so the executable
        # span is size, not size + bss_size.
        entry["hi"] = entry["lo"] + int(entry["size"])
    return overlays


def load_points(paths: list[Path]) -> tuple[list[tuple[int, int, str]], list[str]]:
    """Return [(addr, hits, kind)] for ARM9, plus a note per source."""
    points: list[tuple[int, int, str]] = []
    notes: list[str] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("kind") == "ndsrecomp-tier3-coverage":
            entries = data.get("entry_points_arm9", [])
            points += [(int(e["addr"], 16), int(e.get("hits", 0)),
                        str(e.get("kind", "?"))) for e in entries]
            notes.append(f"{path.name}: manifest, {len(entries)} ARM9 entries")
            continue
        block = data.get("tier3_coverage") or {}
        entries = [e for e in block.get("entries", []) if int(e["cpu"]) == 9]
        if entries:
            kinds = {1: "root", 2: "call", 3: "indirect"}
            points += [(int(e["pc"]), int(e.get("hits", 0)),
                        kinds.get(int(e.get("kind", 0)), "?")) for e in entries]
            notes.append(f"{path.name}: trace, {len(entries)} ARM9 entries")
        else:
            notes.append(f"{path.name}: NO ARM9 Tier-3 coverage found")
    return points, notes


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", type=Path,
                        help="coverage manifests and/or trace.json files")
    parser.add_argument("--overlays", type=Path,
                        default=Path("generated/inputs/overlays.json"))
    parser.add_argument("--json", type=Path, help="also write the report here")
    args = parser.parse_args()

    overlays = load_overlays(args.overlays)
    points, notes = load_points(args.sources)
    for note in notes:
        print(f"  {note}")
    if not points:
        print("no ARM9 Tier-3 coverage in any source")
        return 1
    print()

    rows = []
    for entry in sorted(overlays, key=lambda o: (o["lo"], o["id"])):
        inside = [p for p in points if entry["lo"] <= p[0] < entry["hi"]]
        shares = [str(o["id"]) for o in overlays
                  if o is not entry and o["lo"] < entry["hi"]
                  and entry["lo"] < o["hi"]]
        rows.append({
            "id": entry["id"],
            "lo": entry["lo"],
            "hi": entry["hi"],
            "kib": int(entry["size"]) // 1024,
            "points": len(inside),
            "hits": sum(p[1] for p in inside),
            "shares_span_with": shares,
        })

    print(f"{'id':>3} {'span':<23} {'KiB':>5} {'points':>7} {'hits':>9}  shares span with")
    for row in rows:
        shared = ",".join(row["shares_span_with"]) or "-"
        print(f"{row['id']:>3} 0x{row['lo']:08X}-0x{row['hi']:08X} "
              f"{row['kib']:>5} {row['points']:>7} {row['hits']:>9}  {shared}")

    covered = {p[0] for row, entry in zip(rows, sorted(overlays, key=lambda o: (o["lo"], o["id"])))
               for p in points if entry["lo"] <= p[0] < entry["hi"]}
    outside = [p for p in points if p[0] not in covered]
    print()
    print(f"addresses inside an overlay : {len(points) - len(outside)}")
    print(f"addresses outside every one : {len(outside)}"
          "   (ITCM / ARM7 WRAM / immutable main image)")
    if outside:
        buckets: dict[int, int] = {}
        for addr, _hits, _kind in outside:
            buckets[addr >> 16 << 16] = buckets.get(addr >> 16 << 16, 0) + 1
        print("  by 64 KiB region:")
        for base in sorted(buckets):
            print(f"    0x{base:08X}  {buckets[base]}")

    exercised = [r for r in rows if r["points"]]
    print()
    print(f"overlays exercised: {len(exercised)} of {len(rows)}")
    if exercised:
        best = max(exercised, key=lambda r: r["hits"])
        print(f"highest-value target: overlay {best['id']} "
              f"({best['points']} points, {best['hits']} hits)")

    if args.json:
        args.json.write_text(json.dumps({
            "sources": [str(p) for p in args.sources],
            "overlays": rows,
            "points_total": len(points),
            "points_outside_overlays": len(outside),
        }, indent=2), encoding="utf-8", newline="\n")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
