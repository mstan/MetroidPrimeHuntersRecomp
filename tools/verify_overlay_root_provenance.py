#!/usr/bin/env python3
"""Verify promoted overlay roots against one unambiguous ROM-derived page."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Union

PAGE_SIZE = 4096


def parse_int(value: Union[str, int]) -> int:
    return int(value, 0) if isinstance(value, str) else int(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--overlays-json", type=Path, required=True)
    parser.add_argument("--overlays-dir", type=Path, required=True)
    parser.add_argument("--overlay-id", type=int, required=True)
    parser.add_argument("--page", type=lambda s: int(s, 0), required=True)
    parser.add_argument("--page-sha1", required=True)
    parser.add_argument("--root", type=lambda s: int(s, 0), action="append",
                        required=True)
    args = parser.parse_args()

    if args.page & (PAGE_SIZE - 1):
        raise SystemExit("--page must be 4 KiB aligned")
    expected_sha1 = args.page_sha1.lower()
    metadata = json.loads(args.overlays_json.read_text(encoding="utf-8"))
    overlays = {int(item["id"]): item for item in metadata}
    if args.overlay_id not in overlays:
        raise SystemExit(f"overlay {args.overlay_id} is absent from metadata")

    matches: list[int] = []
    containing: list[tuple[int, str]] = []
    for overlay_id, item in sorted(overlays.items()):
        base = parse_int(item["load_address"])
        size = parse_int(item["size"])
        if not (base <= args.page and args.page + PAGE_SIZE <= base + size):
            continue
        image = (args.overlays_dir / item["file"]).read_bytes()
        if len(image) != size:
            raise SystemExit(
                f"overlay {overlay_id} size mismatch: {len(image)} != {size}")
        offset = args.page - base
        digest = hashlib.sha1(image[offset:offset + PAGE_SIZE]).hexdigest()
        containing.append((overlay_id, digest))
        if digest == expected_sha1:
            matches.append(overlay_id)

    if matches != [args.overlay_id]:
        detail = ", ".join(f"ov{i}={digest}" for i, digest in containing)
        raise SystemExit(
            f"page 0x{args.page:08X} sha1 {expected_sha1} must identify only "
            f"overlay {args.overlay_id}; matches={matches}; candidates: {detail}")

    config_text = args.config.read_text(encoding="utf-8")
    header = config_text.split("[[entry_point]]", 1)[0]
    base_match = re.search(
        r"^load_address\s*=\s*(0x[0-9A-Fa-f]+)\s*$", header, re.MULTILINE)
    if not base_match:
        raise SystemExit(f"config has no program load_address: {args.config}")
    config_base = int(base_match.group(1), 16)
    target_base = parse_int(overlays[args.overlay_id]["load_address"])
    if config_base != target_base:
        raise SystemExit(
            f"config base 0x{config_base:08X} does not match overlay "
            f"{args.overlay_id} base 0x{target_base:08X}")
    roots = {
        (int(addr, 16), mode)
        for addr, mode in re.findall(
            r"\[\[entry_point\]\]\s*\n"
            r"addr\s*=\s*0x([0-9A-Fa-f]+)\s*\n"
            r"mode\s*=\s*\"(arm|thumb)\"",
            config_text)
    }
    missing = [root for root in args.root if (root, "arm") not in roots]
    if missing:
        formatted = ", ".join(f"0x{root:08X}" for root in missing)
        raise SystemExit(f"proven overlay roots missing from config: {formatted}")

    print(
        f"overlay {args.overlay_id} uniquely owns page 0x{args.page:08X} "
        f"({expected_sha1}); verified {len(args.root)} ARM roots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
