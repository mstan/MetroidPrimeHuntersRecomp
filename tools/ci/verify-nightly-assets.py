#!/usr/bin/env python3
"""Validate MPH Nightly release assets before publishing them."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys
import zipfile


FORBIDDEN_PARTS = {
    "biosnds9.rom",
    "biosnds7.rom",
    "firmware.bin",
}
FORBIDDEN_SUFFIXES = {
    ".nds",
    ".sav",
    ".dsv",
}
FORBIDDEN_DIRS = {
    "generated",
    "capture",
    "captures",
    "saves",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if normalized.startswith("/") or any(part == ".." for part in parts):
        return False
    lowered = [part.lower() for part in parts]
    if any(part in FORBIDDEN_PARTS for part in lowered):
        return False
    if any(part in FORBIDDEN_DIRS for part in lowered):
        return False
    if parts and Path(parts[-1]).suffix.lower() in FORBIDDEN_SUFFIXES:
        return False
    return True


def verify_windows(path: Path) -> None:
    required = {
        "MetroidPrimeHuntersRecomp.exe",
        "nds_runner.exe",
        "game.toml",
        "README.md",
        "LICENSE",
        "bios/README.txt",
    }
    with zipfile.ZipFile(path) as archive:
        names = {
            name.replace("\\", "/").rstrip("/")
            for name in archive.namelist()
            if name and not name.endswith("/")
        }
        unsafe = sorted(name for name in names if not safe_member(name))
        if unsafe:
            raise SystemExit(f"{path.name}: forbidden/unsafe ZIP entries: {unsafe}")
        missing = sorted(required - names)
        if missing:
            raise SystemExit(f"{path.name}: required release entries missing: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--write-sums", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        raise SystemExit(f"invalid version: {args.version!r}")

    expected = {
        f"MetroidPrimeHuntersRecomp-windows-x64-v{args.version}.zip",
        f"MetroidPrimeHuntersRecomp-linux-v{args.version}-x86_64.AppImage",
    }
    actual = {p.name for p in args.dist.iterdir() if p.is_file()}
    extra = actual - expected
    missing = expected - actual
    if extra or missing:
        raise SystemExit(
            f"nightly payload mismatch; missing={sorted(missing)} extra={sorted(extra)}"
        )

    windows = args.dist / f"MetroidPrimeHuntersRecomp-windows-x64-v{args.version}.zip"
    linux = args.dist / f"MetroidPrimeHuntersRecomp-linux-v{args.version}-x86_64.AppImage"
    if windows.stat().st_size <= 0 or linux.stat().st_size <= 0:
        raise SystemExit("nightly payload contains an empty asset")

    verify_windows(windows)

    sums = "\n".join(
        f"{sha256(args.dist / name)}  {name}" for name in sorted(expected)
    ) + "\n"
    if args.write_sums:
        (args.dist / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    else:
        sys.stdout.write(sums)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
