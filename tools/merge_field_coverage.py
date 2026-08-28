#!/usr/bin/env python3
"""Merge a Tier-3 coverage ingest into the committed MPH seed corpus.

beads-lqa.39. `ndsrecomp/tools/ingest_coverage_manifests.py` and
`tools/seed_overlay_from_coverage.py` both emit a corpus derived from ONLY the
manifests handed to that one run. The committed corpus, by contrast, is the
monotonic union of every ingest to date, and the manifests behind the earlier
rounds no longer all exist on disk. So copying a fresh run's output over the
committed files is a REGRESSION, not an update:

  measured 2026-08-28, re-seeding the 12 declared overlays from the 67
  schema-3+ manifests still on disk produced 3,225 seeds against the 5,350
  committed -- overwriting would have silently dropped 2,126 proven entry
  points, including every one of overlay 11's 193.

This tool therefore only ever ADDS. It unions, reports precisely what changed,
and never deletes a seed or a bank. Run it after an ingest instead of copying
by hand.

  1. config/coverage_arm*.toml + generated/capture/*.bin
     Add-only. A bank stem carries its image SHA-1, so a stem that already
     exists is by construction the same bytes; the tool verifies that rather
     than assuming it, and refuses to overwrite a differing image.
  2. coverage/adventure-main-entry-points.json
     Union of (addr, mode); hits are summed, kinds unioned.
  3. coverage/arm7-alias-entry-points.json
     Same, per alias key.
  4. config/mph_arm9_ov*.toml
     Union of (addr, mode) per overlay, preserving the seeder's file shape.

Nothing here needs dumped bytes it did not already have: every input was
produced by a tool that SHA-1 verified the captured page against its own
manifest first.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

# The three producers emit slightly different [[entry_point]] bodies:
# ingest_coverage_manifests.py's merged/split seed lists carry an extra
# `cpu = "armN"` line between mode and kind, its bank configs do not, and
# seed_overlay_from_coverage.py's overlay configs do not either. Accept all
# three rather than silently reading zero entries out of one of them.
ENTRY_BLOCK = re.compile(
    r"\[\[entry_point\]\]\s*\n"
    r"addr\s*=\s*0x([0-9A-Fa-f]+)\s*\n"
    r"mode\s*=\s*\"(\w+)\"\s*\n"
    r"(?:cpu\s*=\s*\"\w+\"\s*\n)?"
    r"kind\s*=\s*\"(\w+)\"\s*\n"
    r"(?:#\s*hits\s*=\s*(\d+)(?:,\s*seen as ([\w/]+))?\s*\n)?", re.M)

OVERLAY_IDS = (0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 15)


def read_entry_toml(path: Path) -> dict[tuple[int, str], dict]:
    """(addr, mode) -> {hits, kinds} from any of the seed TOML shapes."""
    if not path.exists():
        return {}
    out: dict[tuple[int, str], dict] = {}
    for addr, mode, _kind, hits, kinds in ENTRY_BLOCK.findall(
            path.read_text(encoding="utf-8")):
        key = (int(addr, 16), mode)
        slot = out.setdefault(key, {"hits": 0, "kinds": set()})
        slot["hits"] += int(hits or 0)
        if kinds:
            slot["kinds"] |= set(kinds.split("/"))
    return out


def merge_json_seeds(path: Path, produced: dict[str, dict], note: str,
                     report: dict) -> None:
    """Union produced seeds into one of the committed coverage JSONs."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for key, incoming in produced.items():
        existing = payload["entry_points"].setdefault(key, [])
        index = {(int(e["addr"], 16), e["mode"]): e for e in existing}
        added = 0
        for (addr, mode), slot in sorted(incoming.items()):
            found = index.get((addr, mode))
            if found is None:
                existing.append({
                    "addr": f"0x{addr:08x}",
                    "mode": mode,
                    "hits": slot["hits"],
                    "kinds": sorted(slot["kinds"]) or ["call"],
                })
                added += 1
            else:
                # Monotonic: a later session can only have seen it more often.
                found["hits"] = max(int(found.get("hits", 0)), slot["hits"])
                found["kinds"] = sorted(
                    set(found.get("kinds", [])) | slot["kinds"])
        existing.sort(key=lambda e: (int(e["addr"], 16), e["mode"]))
        report[f"{path.name}:{key}"] = {
            "committed": len(index), "produced": len(incoming),
            "added": added, "total": len(existing)}
        changed = changed or added > 0
    if note:
        payload["scenario"] = note
    path.write_text(json.dumps(payload, indent=2) + "\n",
                    encoding="utf-8", newline="\n")
    report[f"{path.name}:rewritten"] = True


def merge_overlay_toml(committed: Path, produced: Path) -> dict:
    """Union produced overlay seeds into a committed overlay bank config."""
    have = read_entry_toml(committed)
    got = read_entry_toml(produced)
    added = sorted(set(got) - set(have))
    if not added:
        return {"committed": len(have), "produced": len(got), "added": 0}
    merged = dict(have)
    for key in got:
        slot = merged.setdefault(key, {"hits": 0, "kinds": set()})
        slot["hits"] = max(slot["hits"], got[key]["hits"])
        slot["kinds"] |= got[key]["kinds"]

    # Rebuild the file with the seeder's own header, keeping [program] and
    # [identity] verbatim so the image identity can never drift here.
    text = committed.read_text(encoding="utf-8")
    head = text.split("[[entry_point]]")[0].rstrip("\n")
    ordered = sorted(merged)
    head = re.sub(r"^entry_pc = 0x[0-9A-Fa-f]+$",
                  f"entry_pc = 0x{ordered[0][0]:08X}", head, flags=re.M)
    lines = [head, ""]
    for addr, mode in ordered:
        lines += [
            "[[entry_point]]",
            f"addr = 0x{addr:08X}",
            f'mode = "{mode}"',
            'kind = "runtime_observed"',
            f"# hits = {merged[(addr, mode)]['hits']}",
            "",
        ]
    committed.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return {"committed": len(have), "produced": len(got),
            "added": len(added),
            "added_addrs": [f"0x{a:08X} {m}" for a, m in added],
            "total": len(merged)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.
                                 RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve()
                    .parent.parent)
    ap.add_argument("--ingest", type=Path, required=True,
                    help="output dir of ndsrecomp/tools/"
                         "ingest_coverage_manifests.py")
    ap.add_argument("--overlay-seeds", type=Path, default=None,
                    help="dir of fresh mph_arm9_ovNNN.toml from "
                         "tools/seed_overlay_from_coverage.py")
    ap.add_argument("--scenario-note", default=None,
                    help="replacement 'scenario' provenance string for the "
                         "coverage JSONs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    report: dict = {"dry_run": args.dry_run}

    # ---- 1. banks -------------------------------------------------------
    config = args.repo / "config"
    capture = args.repo / "generated" / "capture"
    added_banks, same_banks, conflicts = [], [], []
    for toml in sorted(glob.glob(str(args.ingest / "images" /
                                     "coverage_arm*.toml"))):
        stem = Path(toml).stem
        src_bin = Path(toml).with_suffix(".bin")
        dst_toml = config / f"{stem}.toml"
        dst_bin = capture / f"{stem}.bin"
        digest = hashlib.sha1(src_bin.read_bytes()).hexdigest()
        if dst_bin.exists():
            if hashlib.sha1(dst_bin.read_bytes()).hexdigest() != digest:
                conflicts.append(stem)
                continue
            same_banks.append(stem)
            continue
        added_banks.append(stem)
        if not args.dry_run:
            capture.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_bin, dst_bin)
            shutil.copy2(toml, dst_toml)
    report["banks"] = {
        "already_present_identical": len(same_banks),
        "added": len(added_banks),
        "added_stems": added_banks,
        "IMAGE_CONFLICTS": conflicts,
    }
    if conflicts:
        print("REFUSING to overwrite differing bank images: "
              + ", ".join(conflicts))
        return 1

    # ---- 2/3. main + alias seed JSONs -----------------------------------
    seeds = args.ingest / "seeds"
    main_produced = {}
    p = seeds / "arm9_arm9_02004000.toml"
    if p.exists():
        main_produced["arm9"] = read_entry_toml(p)
    p = seeds / "arm7_arm7_02380000.toml"
    if p.exists():
        main_produced["arm7"] = read_entry_toml(p)
    alias_produced = {}
    for key, stem in (("arm7_wram_alias", "arm7_arm7_037f7e50.toml"),
                      ("arm7_mainram_alias", "arm7_arm7_027cfbc4.toml")):
        p = seeds / stem
        if p.exists():
            alias_produced[key] = read_entry_toml(p)

    if not args.dry_run:
        merge_json_seeds(args.repo / "coverage" /
                         "adventure-main-entry-points.json",
                         main_produced, args.scenario_note, report)
        merge_json_seeds(args.repo / "coverage" /
                         "arm7-alias-entry-points.json",
                         alias_produced, args.scenario_note, report)
    else:
        for name, produced in (("adventure-main", main_produced),
                               ("arm7-alias", alias_produced)):
            for key, incoming in produced.items():
                path = (args.repo / "coverage" /
                        (f"{name}-entry-points.json"))
                payload = json.loads(path.read_text(encoding="utf-8"))
                have = {(int(e["addr"], 16), e["mode"])
                        for e in payload["entry_points"].get(key, [])}
                report[f"{name}:{key}"] = {
                    "committed": len(have), "produced": len(incoming),
                    "added": len(set(incoming) - have)}

    # ---- 4. overlays ----------------------------------------------------
    if args.overlay_seeds:
        ov: dict = {}
        for i in OVERLAY_IDS:
            name = f"mph_arm9_ov{i:03d}.toml"
            fresh = args.overlay_seeds / name
            live = config / name
            if not fresh.exists() or not live.exists():
                ov[name] = {"skipped": "no fresh seeds"
                            if not fresh.exists() else "no committed config"}
                continue
            if args.dry_run:
                have, got = read_entry_toml(live), read_entry_toml(fresh)
                ov[name] = {"committed": len(have), "produced": len(got),
                            "added": len(set(got) - set(have))}
            else:
                ov[name] = merge_overlay_toml(live, fresh)
        report["overlays"] = ov

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
