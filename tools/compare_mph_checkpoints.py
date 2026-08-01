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

    report = {
        name: compare(native_files[name], oracle_files[name])
        for name in names
    }
    encoded = json.dumps(report, indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
