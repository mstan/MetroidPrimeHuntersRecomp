#!/usr/bin/env python3
"""Grant MPH adaptive output capability after executable validation.

The shared ROM-free game.toml intentionally has no exact [game].sha1 because
runtime base selection supports all seven MPH revisions and compatible mods.
ndsrecomp correctly rejects TOML-declared display.adaptive_capability without
an exact SHA, so the generic config must not declare that capability itself.

Instead, this patch runs after the MPH runtime detector/widescreen patch and
marks TOP adaptive output as supported only when the detector has selected MPH
and the executable checksum is authoritative enough to permit host code/data
writes. Header-only fallback therefore remains fail-closed.
"""

from __future__ import annotations

import argparse
from pathlib import Path


MARKER = "MPH_MULTIROM_RUNTIME_ADAPTIVE_CAPABILITY"
INSERT_BEFORE = "    // MPH_MULTIROM_WIDESCREEN_GATE: a header-only base-profile hint is\n"


def patch(framework_root: Path) -> None:
    main_cpp = framework_root / "runner" / "src" / "main.cpp"
    if not main_cpp.is_file():
        raise SystemExit(f"runner source missing: {main_cpp}")

    text = main_cpp.read_text(encoding="utf-8")
    if MARKER in text:
        print("MPH runtime adaptive capability patch already applied")
        return
    if INSERT_BEFORE not in text:
        raise SystemExit(
            "Refusing to patch main.cpp: MPH widescreen gate marker was not found; "
            "apply patch_ndsrecomp_mph_widescreen.py first"
        )

    block = (
        "    // MPH_MULTIROM_RUNTIME_ADAPTIVE_CAPABILITY: the shared game.toml has\n"
        "    // no exact SHA-1, so ndsrecomp cannot safely grant title capability\n"
        "    // during config parsing. Grant TOP only after the executable-compatible\n"
        "    // MPH detector has authorized host code/data access.\n"
        "    if (nds_title_patches_mph_detected() &&\n"
        "        nds_title_patches_mph_host_writes_compatible()) {\n"
        "        frontend_options.adaptive_supported |= NDS_ADAPTIVE_TOP;\n"
        "        frontend_options.adaptive_max_width[0] = 448;\n"
        "    }\n"
    )
    main_cpp.write_text(text.replace(INSERT_BEFORE, block + INSERT_BEFORE, 1),
                        encoding="utf-8")
    print("Patched MPH adaptive capability to follow runtime executable validation")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", type=Path, required=True)
    # Kept for compatibility with the shared patch-stack argument list.
    parser.add_argument("--profiles", type=Path, required=False)
    args = parser.parse_args()
    patch(args.framework_root.resolve())


if __name__ == "__main__":
    main()
