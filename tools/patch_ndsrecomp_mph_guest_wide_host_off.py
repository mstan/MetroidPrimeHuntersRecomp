#!/usr/bin/env python3
"""Build-only experiment: keep MPH guest 21:9 patches but disable host adaptive output.

This patch is intentionally for comparison builds only. It latches the MPH
projection/culling patch from the user's Adaptive Widescreen request, then
removes TOP from frontend_options.adaptive_screens and disables host HUD
anchoring before renderer presentation state is configured.

Result:
  guest projection/culling patch: ON for executable-compatible MPH
  host 448px adaptive framebuffer: OFF
  host adaptive HUD anchoring: OFF
"""

from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "MPH_TEST_GUEST_WIDE_HOST_ADAPTIVE_OFF"
OLD = '''    nds_title_patches_set_mph_adaptive(\n        nds_title_patches_mph_host_writes_compatible() &&\n        (frontend_options.adaptive_screens & NDS_ADAPTIVE_TOP) != 0u);\n    nds_title_patches_set_mph_mouse_aim(mph_mouse_aim_policy);\n'''
NEW = '''    // MPH_TEST_GUEST_WIDE_HOST_ADAPTIVE_OFF: comparison build only.\n    // Preserve the user's Adaptive Widescreen request long enough to enable\n    // the validated guest projection/culling patch, then force host adaptive\n    // presentation back to native 256x192 and disable HUD band anchoring.\n    const bool mph_guest_widescreen_policy =\n        nds_title_patches_mph_host_writes_compatible() &&\n        (frontend_options.adaptive_screens & NDS_ADAPTIVE_TOP) != 0u;\n    nds_title_patches_set_mph_adaptive(mph_guest_widescreen_policy);\n    if (mph_guest_widescreen_policy) {\n        frontend_options.adaptive_screens &= ~NDS_ADAPTIVE_TOP;\n        frontend_options.adaptive_hud_anchor = false;\n        std::fprintf(stderr,\n                     "[mph-test] guest 21:9 projection/culling ON; "\n                     "host 448px adaptive framebuffer/HUD anchoring OFF\\n");\n    }\n    nds_title_patches_set_mph_mouse_aim(mph_mouse_aim_policy);\n'''

def patch(framework_root: Path) -> None:
    main_cpp = framework_root / "runner" / "src" / "main.cpp"
    if not main_cpp.is_file():
        raise SystemExit(f"runner source missing: {main_cpp}")
    text = main_cpp.read_text(encoding="utf-8")
    if MARKER in text:
        print("MPH guest-wide/host-off comparison patch already applied")
        return
    if OLD not in text:
        raise SystemExit(
            "Refusing comparison patch: expected MPH adaptive call site was not found; "
            "apply patch_ndsrecomp_mph_widescreen.py first"
        )
    main_cpp.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("Patched comparison build: guest widescreen ON, host adaptive output OFF")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", type=Path, required=True)
    # Accepted so this experiment can be appended to the normal runtime patch
    # stack, which forwards the shared --profiles argument to every layer.
    parser.add_argument("--profiles", type=Path, required=False)
    args = parser.parse_args()
    patch(args.framework_root.resolve())

if __name__ == "__main__":
    main()
