#!/usr/bin/env python3
"""Compare matching native/oracle checkpoint PNGs without embedding them."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(native_path: Path, oracle_path: Path) -> dict[str, object]:
    native = Image.open(native_path).convert("RGB")
    oracle = Image.open(oracle_path).convert("RGB")
    if native.size != oracle.size:
        return {
            "native_size": list(native.size),
            "oracle_size": list(oracle.size),
            "same_size": False,
        }
    difference = ImageChops.difference(native, oracle)
    differing_pixels = sum(
        1
        for pixel in difference.get_flattened_data()
        if pixel != (0, 0, 0)
    )
    extrema = difference.getextrema()
    return {
        "same_size": True,
        "exact": difference.getbbox() is None,
        "native_sha256": digest(native_path),
        "oracle_sha256": digest(oracle_path),
        "differing_pixels": differing_pixels,
        "total_pixels": native.width * native.height,
        "max_channel_delta": max(high for _, high in extrema),
        "rms_channel_delta": [
            round(value, 6) for value in ImageStat.Stat(difference).rms
        ],
    }


def _load_state(directory: Path) -> dict[str, object] | None:
    """Per-checkpoint guest state from a capture's report.json, if present."""
    report_path = directory / "report.json"
    if not report_path.is_file():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    # capture_mph_checkpoints.py writes a bare list of checkpoint records.
    # Accept a wrapped form too so this keeps working if that report grows a
    # header.
    if isinstance(report, list):
        checkpoints = report
    elif isinstance(report, dict):
        checkpoints = report.get("checkpoints")
    else:
        return None
    if not isinstance(checkpoints, list):
        return None
    out: dict[str, object] = {}
    for entry in checkpoints:
        if isinstance(entry, dict) and "state" in entry:
            out[str(entry.get("vblank9"))] = entry["state"]
    return out or None


def compare_state(native_dir: Path, oracle_dir: Path) -> dict[str, object] | None:
    native = _load_state(native_dir)
    oracle = _load_state(oracle_dir)
    if native is None or oracle is None:
        return {
            "available": False,
            "reason": "one or both captures carry no per-checkpoint state; "
                      "recapture with a capture_mph_checkpoints.py that "
                      "records it",
        }
    shared = sorted(native.keys() & oracle.keys(), key=lambda key: int(key))
    if not shared:
        return {"available": False, "reason": "no shared checkpoints"}
    differing = [key for key in shared if native[key] != oracle[key]]
    result: dict[str, object] = {
        "available": True,
        "checkpoints_compared": len(shared),
        "identical": not differing,
        "differing_checkpoints": differing,
    }
    if differing:
        # Only the earliest divergence has a root cause; later ones are
        # downstream of it.
        first = differing[0]
        result["first_divergence"] = {
            "vblank9": first,
            "native": native[first],
            "oracle": oracle[first],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--pattern",
        default="vblank-*.png",
        help="checkpoint filename glob (default: vblank-*.png)",
    )
    args = parser.parse_args()

    native_files = {
        path.name: path for path in args.native.glob(args.pattern)
    }
    oracle_files = {
        path.name: path for path in args.oracle.glob(args.pattern)
    }
    names = sorted(native_files.keys() & oracle_files.keys())
    if not names:
        raise SystemExit(f"no matching {args.pattern} checkpoints")

    report: dict[str, object] = {
        name: compare(native_files[name], oracle_files[name])
        for name in names
    }

    # Screens agreeing is necessary but not sufficient: two builds can paint
    # the same frame from divergent machine state. When both captures carry
    # the full state block written by capture_mph_checkpoints.py, compare it
    # exactly - both register files, the mode registers and every event
    # counter - and report the first checkpoint that differs.
    state = compare_state(args.native, args.oracle)
    if state is not None:
        report["guest_state"] = state

    encoded = json.dumps(report, indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
