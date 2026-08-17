#!/usr/bin/env python3
"""Verify the MPH executable-checksum registry against melonPrimeDS develop_hud.

This deliberately parses only the authoritative CHECKSUM_TABLE from
MelonPrimeGameRomDetect.cpp. Runtime addresses are cross-checked separately
against MelonPrimeGameRomAddrTable.h.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ENTRY_RE = re.compile(
    r'\{\s*(0x[0-9A-Fa-f]{8})u\s*,\s*RomGroup::([A-Za-z0-9_]+)\s*,\s*"([^"]+)"\s*\}'
)


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--detector", type=Path, required=True)
    args = parser.parse_args()

    registry = json.loads(args.profiles.read_text(encoding="utf-8"))
    configured = registry.get("runtime_checksums")
    if not isinstance(configured, list):
        fail("profile registry has no runtime_checksums array")

    expected: list[tuple[int, str, str]] = []
    for index, entry in enumerate(configured):
        if not isinstance(entry, dict):
            fail(f"runtime_checksums[{index}] must be an object")
        crc = entry.get("crc32")
        profile = entry.get("profile")
        name = entry.get("name")
        if not isinstance(crc, str) or not isinstance(profile, str) or not isinstance(name, str):
            fail(f"runtime_checksums[{index}] has invalid fields")
        expected.append((int(crc, 16), profile, name))

    source = args.detector.read_text(encoding="utf-8")
    table_match = re.search(
        r"constexpr\s+ChecksumEntry\s+CHECKSUM_TABLE\[\]\s*=\s*\{(.*?)\n\s*\};",
        source,
        re.S,
    )
    if not table_match:
        fail("could not locate CHECKSUM_TABLE in melonPrimeDS detector")

    actual = [
        (int(crc, 16), profile, name)
        for crc, profile, name in ENTRY_RE.findall(table_match.group(1))
    ]
    if not actual:
        fail("melonPrimeDS CHECKSUM_TABLE contained no parseable entries")

    if actual != expected:
        print("Configured runtime checksums:")
        for crc, profile, name in expected:
            print(f"  0x{crc:08X} {profile} {name}")
        print("melonPrimeDS develop_hud checksums:")
        for crc, profile, name in actual:
            print(f"  0x{crc:08X} {profile} {name}")
        fail("runtime checksum registry drifted from MelonPrimeGameRomDetect.cpp")

    # Keep the documented fallback contract visible to CI. If upstream moves
    # either NDS header field, the imported detector source must be re-audited.
    if "gameCode (@0x0C) + revision (@0x1E)" not in source:
        fail("melonPrimeDS detector no longer documents gameCode@0x0C + revision@0x1E")

    print(
        f"OK: {len(actual)} executable checksums and header fallback contract "
        "match melonPrimeDS develop_hud"
    )


if __name__ == "__main__":
    main()
