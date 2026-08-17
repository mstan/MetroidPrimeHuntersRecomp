#!/usr/bin/env python3
"""Seed one overlay's recompiler config with provably-that-overlay entry points.

beads-yjp.31. tools/prepare_mph.py deliberately emits overlay configs with NO
entry points -- its own docstring says real entry points must come from Tier-3
coverage recorded while that exact overlay body was resident. This produces
them.

THE ATTRIBUTION PROBLEM. MPH reuses virtual addresses across overlays: all 18
overlap at least one other by span, and overlay 0 alone shares its range with
eight. A Tier-3 coverage record is {pc, caller, cpu, thumb, kind, hits} and
carries no overlay identity, so on its own it cannot say whether a PC executed
while overlay 0 or overlay 9 was resident. docs/BRINGUP.md calls combining
entry points across overlay generations unsound, and it is right.

THE SOLUTION, and why no runtime change is needed. The coverage manifest also
carries the 4 KiB code pages the guest actually executed, captured verbatim at
execution time. Comparing a captured page against each overlay's decompressed
ROM image at the corresponding offset identifies which overlay was resident
when that page ran. Measured on a real capture: of 65 captured ARM9 pages, 33
fell inside some overlay and every one attributed to exactly ONE overlay --
28 to overlay 0, 2 to overlay 1, 3 to overlay 4, with zero ambiguity. The
bytes are distinct enough that overlapping spans do not produce collisions.

Only entry points sitting inside a page that byte-matched THIS overlay are
emitted. Everything else is excluded and counted, never guessed at.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

PAGE = 4096
# Roots are scheduler slice-resume points and usually land mid-function, which
# makes them poor discovery seeds. Calls and indirect targets are real entries.
GOOD_KINDS = {"call", "indirect"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--overlay-id", type=int, required=True)
    parser.add_argument("--overlays-dir", type=Path,
                        default=Path("generated/inputs/overlays"))
    parser.add_argument("--overlays-json", type=Path,
                        default=Path("generated/inputs/overlays.json"))
    parser.add_argument("--manifest", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--include-roots", action="store_true",
                        help="also seed kind=root PCs (usually fragments code)")
    args = parser.parse_args()

    meta = {int(o["id"]): o
            for o in json.loads(args.overlays_json.read_text(encoding="utf-8"))}
    if args.overlay_id not in meta:
        raise SystemExit(f"no overlay {args.overlay_id} in {args.overlays_json}")
    entry = meta[args.overlay_id]
    base = int(entry["load_address"], 16)
    image = (args.overlays_dir / entry["file"]).read_bytes()
    if len(image) != int(entry["size"]):
        raise SystemExit(f"{entry['file']} is {len(image)} bytes, "
                         f"overlays.json says {entry['size']}")
    lo, hi = base, base + len(image)
    print(f"overlay {args.overlay_id}: 0x{lo:08X}-0x{hi:08X} "
          f"({len(image)} bytes) sha1 {entry['sha1']}")

    # Which captured pages prove this overlay was resident?
    resident: set[int] = set()
    foreign = 0
    points: list[dict] = []
    for path in args.manifest:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("kind") != "ndsrecomp-tier3-coverage":
            raise SystemExit(f"{path} is not a coverage manifest")
        for page in data.get("pages", {}).get("entries", []):
            if int(page["cpu"]) != 9:
                continue
            addr = int(page["addr"], 16)
            if not (lo <= addr < hi):
                continue
            raw = base64.b64decode(page["data"])
            off = addr - lo
            if image[off:off + len(raw)] == raw:
                resident.add(addr)
            else:
                foreign += 1
        points += data.get("entry_points_arm9", [])

    print(f"captured pages inside this overlay that MATCH its image: "
          f"{len(resident)}")
    print(f"captured pages inside its span from a DIFFERENT generation: "
          f"{foreign}  (excluded)")
    if not resident:
        raise SystemExit("no page proved this overlay resident; nothing to seed")

    kinds_ok = GOOD_KINDS | ({"root"} if args.include_roots else set())
    seeds: dict[tuple[int, str], int] = {}
    dropped_kind = dropped_unproven = 0
    for point in points:
        addr = int(point["addr"], 16)
        if not (lo <= addr < hi):
            continue
        if (addr & ~(PAGE - 1)) not in resident:
            dropped_unproven += 1
            continue
        if point.get("kind") not in kinds_ok:
            dropped_kind += 1
            continue
        key = (addr, "thumb" if point.get("mode") == "thumb" else "arm")
        seeds[key] = seeds.get(key, 0) + int(point.get("hits", 0))

    print(f"entry points in span, dropped as unproven generation: "
          f"{dropped_unproven}")
    print(f"entry points dropped by kind filter                 : {dropped_kind}")
    print(f"SEEDS EMITTED                                       : {len(seeds)}")
    if not seeds:
        raise SystemExit("no seeds survived; capture a route that runs this overlay")

    ordered = sorted(seeds.items())
    lines = [
        "# AUTO-GENERATED by tools/seed_overlay_from_coverage.py; do not commit.",
        "# Entry points are Tier-3 observations whose containing 4 KiB page was",
        "# byte-identical to this overlay's decompressed ROM image at the time it",
        "# executed, so every seed below is provably from THIS overlay generation",
        "# and not from one of the overlays sharing its address range.",
        "",
        "[program]",
        f'name = "Metroid Prime Hunters (USA rev 0) ARM9 overlay {args.overlay_id}"',
        f'id = "mph_amhe0_arm9_ov{args.overlay_id:03d}"',
        f"load_address = 0x{lo:08X}",
        f"size = 0x{len(image):08X}",
        f"entry_pc = 0x{ordered[0][0][0]:08X}",
        "authoritative_entry_points = false",
        "",
        "[identity]",
        f'sha1 = "{entry["sha1"]}"',
        "",
    ]
    for (addr, mode), hits in ordered:
        lines += [
            "[[entry_point]]",
            f"addr = 0x{addr:08X}",
            f'mode = "{mode}"',
            'kind = "runtime_observed"',
            f"# hits = {hits}",
            "",
        ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
