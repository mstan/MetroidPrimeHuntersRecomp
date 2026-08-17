#!/usr/bin/env python3
"""Apply the MPH runtime-profile patch stack to the pinned ndsrecomp runner.

The core detector is kept separately so upstream-facing additions can be layered
without weakening its whole-ROM/content identity rules. The later stages add
the melonPrimeDS/mphCodex profile-aware 21:9 projection/culling patch, grant
adaptive TOP capability only after authoritative MPH executable detection, make
that patch re-eligible after an in-process guest reset, add end-user startup
diagnostics plus the ROM-free multi-ROM content-gate policy, expose the
game-side aspect-ratio patch independently from ndsrecomp's host Adaptive
Widescreen renderer, and finally force native framebuffer presentation to use
nearest-neighbor sampling so supersampling/AA cannot blur DS pixels.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _framework_root(args: list[str]) -> Path | None:
    for index, arg in enumerate(args[:-1]):
        if arg == "--framework-root":
            return Path(args[index + 1]).resolve()
    return None


def main() -> None:
    here = Path(__file__).resolve().parent
    args = sys.argv[1:]
    framework_root = _framework_root(args)
    for script in (
        here / "patch_ndsrecomp_mph_runtime_core.py",
        here / "patch_ndsrecomp_mph_widescreen.py",
        here / "patch_ndsrecomp_mph_adaptive_capability.py",
        here / "patch_ndsrecomp_mph_widescreen_reset.py",
        here / "patch_ndsrecomp_mph_diagnostics.py",
        here / "patch_ndsrecomp_mph_aspect_ratio_mod.py",
        here / "patch_ndsrecomp_nearest_presentation.py",
    ):
        # The aspect layer consists of several coordinated edits across main,
        # title_patches and frontend. Its primary marker in main is enough to
        # establish that the complete layer was applied by a prior successful
        # stack invocation. Skip the whole layer on rerun rather than trying to
        # match already-transformed frontend width expressions piecemeal.
        if (script.name == "patch_ndsrecomp_mph_aspect_ratio_mod.py" and
                framework_root is not None):
            main_cpp = framework_root / "runner" / "src" / "main.cpp"
            if main_cpp.is_file() and "MPH_ASPECT_RATIO_MOD_CLI_VAR" in \
                    main_cpp.read_text(encoding="utf-8"):
                print("MPH independent aspect-ratio mod already applied")
                continue
        subprocess.run([sys.executable, str(script), *args], check=True)


if __name__ == "__main__":
    main()
