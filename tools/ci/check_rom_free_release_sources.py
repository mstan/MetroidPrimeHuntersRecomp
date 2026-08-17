#!/usr/bin/env python3
"""Pin the public Nightly's no-ROM-secret source policy."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = [
    ROOT / ".github" / "workflows" / "build-windows.yml",
    ROOT / ".github" / "workflows" / "build-linux.yml",
    ROOT / ".github" / "workflows" / "build.yml",
    ROOT / ".github" / "workflows" / "nightly-release.yml",
]


def main() -> int:
    failures: list[str] = []
    for path in WORKFLOWS:
        if not path.is_file():
            failures.append(f"missing release workflow: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        if "MPH_US10_ROM_URL" in text:
            failures.append(f"{path.relative_to(ROOT)} still references MPH_US10_ROM_URL")
        if "secrets." in text:
            failures.append(
                f"{path.relative_to(ROOT)} references repository/environment secrets"
            )

    nightly = (ROOT / ".github" / "workflows" / "nightly-release.yml").read_text(
        encoding="utf-8"
    )
    for required in (
        "uses: ./.github/workflows/build-windows.yml",
        "uses: ./.github/workflows/build-linux.yml",
        "NIGHTLY_TAG: nightly-release",
        "verify-nightly-assets.py",
    ):
        if required not in nightly:
            failures.append(f"nightly workflow missing required contract: {required}")

    for workflow in ("build-windows.yml", "build-linux.yml"):
        text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        for required in (
            "patch_ndsrecomp_rom_free_release.py",
            "prepare_freebios_banks.py",
            "-DNDS_RETAIL_BIOS_BANKS=OFF",
        ):
            if required not in text:
                failures.append(f"{workflow} missing ROM-free build contract: {required}")

    if failures:
        print("ROM-free release policy check FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("OK: public build/Nightly workflow uses no ROM secret path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
