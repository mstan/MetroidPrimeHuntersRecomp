#!/usr/bin/env python3
"""Make the MPH widescreen patch survive guest resets without re-identifying ROM."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    args = parser.parse_args()
    path = args.framework_root.resolve() / "runner" / "src" / "title_patches.cpp"
    text = path.read_text(encoding="utf-8")
    marker = "MPH_MULTIROM_WIDESCREEN_RESET_SAFE"
    if marker in text:
        return
    old = (
        "    if (!g_mph_adaptive || g_mph_aspect_ratio_applied ||\n"
        "        !g_mph_runtime_profile || !g_mph_host_writes_compatible)\n"
        "        return;\n"
    )
    new = (
        "    // MPH_MULTIROM_WIDESCREEN_RESET_SAFE: inspect the guarded words each\n"
        "    // frame. Once patched they no longer match the stock preimage, while a\n"
        "    // guest reset restores the stock words and makes the patch eligible again.\n"
        "    if (!g_mph_adaptive || !g_mph_runtime_profile ||\n"
        "        !g_mph_host_writes_compatible)\n"
        "        return;\n"
    )
    if old not in text:
        raise SystemExit("widescreen reset-safe preimage not found")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


if __name__ == "__main__":
    main()
