#!/usr/bin/env python3
"""Apply the MPH runtime-profile patch stack to the pinned ndsrecomp runner.

The core detector is kept separately so upstream-facing additions can be layered
without weakening its whole-ROM/content identity rules. The later stages add
the melonPrimeDS/mphCodex profile-aware 21:9 projection/culling patch and make
that patch re-eligible after an in-process guest reset.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    here = Path(__file__).resolve().parent
    args = sys.argv[1:]
    for script in (
        here / "patch_ndsrecomp_mph_runtime_core.py",
        here / "patch_ndsrecomp_mph_widescreen.py",
        here / "patch_ndsrecomp_mph_widescreen_reset.py",
    ):
        subprocess.run([sys.executable, str(script), *args], check=True)


if __name__ == "__main__":
    main()
