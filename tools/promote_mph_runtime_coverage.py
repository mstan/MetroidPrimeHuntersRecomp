#!/usr/bin/env python3
"""Create a profile-specific content-validated MPH ARM9 runtime-bank config."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from mph_profile import DEFAULT_PROFILE_FILE, DEFAULT_VERSION, load_profile


ITCM_BASE = 0x01FF8000
MAIN_RAM_END = 0x02400000
IMAGE_SIZE = MAIN_RAM_END - ITCM_BASE


def runtime_address(address: int) -> bool:
    return ITCM_BASE <= address < MAIN_RAM_END


def coverage_key(item: dict[str, object]) -> tuple[int, ...]:
    return tuple(
        int(item[field])
        for field in ("cpu", "pc", "thumb", "kind", "caller")
    )


def verify_report_identity(
    report: dict[str, object],
    *,
    version: str,
    expected_sha1: str,
    label: str,
    require_identity: bool,
) -> None:
    observed_profile = report.get("mph_profile")
    observed_sha1 = report.get("rom_sha1")
    if require_identity and (observed_profile is None or observed_sha1 is None):
        raise SystemExit(
            f"{label} for {version} is missing profile/ROM identity; "
            "recapture with the profile-aware FMV benchmark tool"
        )
    if observed_profile is not None and str(observed_profile) != version:
        raise SystemExit(
            f"{label} profile {observed_profile!r} does not match {version!r}"
        )
    if observed_sha1 is not None and str(observed_sha1) != expected_sha1:
        raise SystemExit(
            f"{label} ROM SHA-1 {observed_sha1!r} does not match "
            f"{version} ({expected_sha1})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument(
        "--before-benchmark",
        type=Path,
        help="subtract cumulative coverage captured before the target phase",
    )
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bank")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--profiles",
        type=Path,
        default=DEFAULT_PROFILE_FILE,
        help=f"ROM profile registry (default: {DEFAULT_PROFILE_FILE})",
    )
    parser.add_argument(
        "--include-slice-resumes",
        action="store_true",
        help="also seed kind-1 scheduler resume PCs (usually fragments code)",
    )
    args = parser.parse_args()

    profile = load_profile(args.profiles.resolve(), args.version)
    expected_sha1 = str(profile["sha1"])
    bank = args.bank or str(profile["fmv_runtime_bank"])
    require_identity = args.version != DEFAULT_VERSION

    image = args.image.read_bytes()
    if len(image) != IMAGE_SIZE:
        raise SystemExit(
            f"runtime image is 0x{len(image):X} bytes; expected 0x{IMAGE_SIZE:X}"
        )
    identity = hashlib.sha1(image).hexdigest()

    report = json.loads(args.benchmark.read_text(encoding="utf-8"))
    verify_report_identity(
        report,
        version=args.version,
        expected_sha1=expected_sha1,
        label="benchmark",
        require_identity=require_identity,
    )
    if require_identity:
        runtime_capture = report.get("runtime_capture")
        if not isinstance(runtime_capture, dict):
            raise SystemExit(
                f"benchmark for {args.version} has no runtime_capture metadata"
            )
        capture_sha1 = runtime_capture.get("sha1")
        capture_bytes_raw = runtime_capture.get("bytes")
        if capture_sha1 != identity:
            raise SystemExit(
                f"runtime image SHA-1 {identity} does not match benchmark "
                f"capture SHA-1 {capture_sha1!r}"
            )
        try:
            capture_bytes = int(capture_bytes_raw)
        except (TypeError, ValueError) as exc:
            raise SystemExit(
                f"benchmark runtime capture has invalid byte count "
                f"{capture_bytes_raw!r}"
            ) from exc
        if capture_bytes != IMAGE_SIZE:
            raise SystemExit(
                f"benchmark runtime capture size {capture_bytes} does not "
                f"match 0x{IMAGE_SIZE:X}"
            )

    coverage = report.get("tier3_coverage", {}).get("entries", [])

    if args.before_benchmark is not None:
        before_report = json.loads(
            args.before_benchmark.read_text(encoding="utf-8")
        )
        verify_report_identity(
            before_report,
            version=args.version,
            expected_sha1=expected_sha1,
            label="before-benchmark",
            require_identity=require_identity,
        )
        before_entries = before_report.get(
            "tier3_coverage", {}
        ).get("entries", [])
        before_hits = {
            coverage_key(item): int(item["hits"])
            for item in before_entries
        }
        coverage = [
            item
            for item in coverage
            if int(item["hits"]) - before_hits.get(coverage_key(item), 0) > 0
        ]

    entries = sorted({
        (int(item["pc"]), "thumb" if int(item["thumb"]) else "arm")
        for item in coverage
        if int(item["cpu"]) == 9
        and runtime_address(int(item["pc"]))
        and (args.include_slice_resumes or int(item["kind"]) in (2, 3))
    })
    if not entries:
        raise SystemExit("benchmark contains no ARM9 runtime Tier-3 coverage")

    display_name = str(profile["display_name"])
    lines = [
        "# AUTO-GENERATED by tools/promote_mph_runtime_coverage.py; committed.",
        f"# Profile: {args.version}; retail ROM SHA-1: {expected_sha1}.",
        f"# Source image: {args.image.name} (git-ignored capture artifact).",
        "# Every function is validated against live guest bytes before dispatch.",
        "",
        "[program]",
        f'name         = "{display_name} ARM9 FMV runtime"',
        f'id           = "{bank}"',
        'cpu          = "arm9"',
        'isa          = "armv5te"',
        f"load_address = 0x{ITCM_BASE:08X}",
        f"size         = 0x{IMAGE_SIZE:08X}",
        f"entry_pc     = 0x{entries[0][0]:08X}",
        "",
        "[identity]",
        f'sha1 = "{identity}"',
        "",
    ]
    for address, mode in entries:
        lines += [
            "[[entry_point]]",
            f"addr = 0x{address:08X}",
            f'mode = "{mode}"',
            'kind = "runtime_observed"',
            "",
        ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps({
        "profile": args.version,
        "game_sha1": expected_sha1,
        "config": str(args.out),
        "bank": bank,
        "image_sha1": identity,
        "entry_points": len(entries),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
