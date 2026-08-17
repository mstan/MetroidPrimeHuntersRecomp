#!/usr/bin/env python3
"""Build-only experiment: guest MPH 21:9 patch + native-frame stretch.

This is a diagnostic comparison build, not a develop candidate.

When Adaptive Widescreen is requested for an executable-compatible MPH ROM:

* keep the validated guest-side projection/culling patch enabled;
* disable ndsrecomp's host adaptive 448px renderer/compositor path;
* disable adaptive HUD anchoring/splitting;
* keep the emulated top-screen render surface at native 256x192; and
* stretch that completed native top-screen image to 448x192 only at SDL
  presentation time.

That separation is important: a guest 21:9 projection patch rendered into the
DS-native 256x192 surface is expected to look horizontally compressed if it is
then displayed as 4:3. The final 256->448 stretch restores the intended 21:9
shape without re-enabling the host-side 448px renderer we are trying to remove
from this A/B test.
"""

from __future__ import annotations

import argparse
from pathlib import Path

MAIN_MARKER = "MPH_TEST_GUEST_WIDE_HOST_ADAPTIVE_OFF"
GETTER_MARKER = "MPH_TEST_GUEST_WIDE_STATE_GETTER"
FRONTEND_MARKER = "MPH_TEST_NATIVE_WIDE_STRETCH_PRESENTATION"

MAIN_OLD = '''    nds_title_patches_set_mph_adaptive(\n        nds_title_patches_mph_host_writes_compatible() &&\n        (frontend_options.adaptive_screens & NDS_ADAPTIVE_TOP) != 0u);\n    nds_title_patches_set_mph_mouse_aim(mph_mouse_aim_policy);\n'''
MAIN_NEW = '''    // MPH_TEST_GUEST_WIDE_HOST_ADAPTIVE_OFF: comparison build only.\n    // Latch the user's Adaptive Widescreen request into the guest-side MPH\n    // projection/culling patch, then remove TOP from the host adaptive path.\n    // frontend.cpp still presents the completed native 256x192 image at\n    // 448x192, so the guest 21:9 projection is not left horizontally squashed.\n    const bool mph_guest_widescreen_policy =\n        nds_title_patches_mph_host_writes_compatible() &&\n        (frontend_options.adaptive_screens & NDS_ADAPTIVE_TOP) != 0u;\n    nds_title_patches_set_mph_adaptive(mph_guest_widescreen_policy);\n    if (mph_guest_widescreen_policy) {\n        frontend_options.adaptive_screens &= ~NDS_ADAPTIVE_TOP;\n        frontend_options.adaptive_hud_anchor = false;\n        std::fprintf(stderr,\n                     "[mph-test] guest 21:9 projection/culling ON; "\n                     "host adaptive renderer/HUD OFF; "\n                     "native 256x192 -> 448x192 present stretch ON\\n");\n    }\n    nds_title_patches_set_mph_mouse_aim(mph_mouse_aim_policy);\n'''


def patch_once(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    if old not in text:
        raise SystemExit(
            f"Refusing comparison patch for {path}: expected pinned preimage "
            f"for {marker!r} was not found"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch(framework_root: Path) -> None:
    src = framework_root / "runner" / "src"
    main_cpp = src / "main.cpp"
    title_h = src / "title_patches.h"
    title_cpp = src / "title_patches.cpp"
    frontend_cpp = src / "frontend.cpp"
    for path in (main_cpp, title_h, title_cpp, frontend_cpp):
        if not path.is_file():
            raise SystemExit(f"runner source missing: {path}")

    # Expose the already-latched guest widescreen state to frontend.cpp. The
    # normal host adaptive flag is deliberately cleared in main.cpp below, so
    # frontend.cpp cannot infer this comparison mode from adaptive_screens.
    patch_once(
        title_h,
        "void nds_title_patches_set_mph_adaptive(bool enabled);\n",
        "void nds_title_patches_set_mph_adaptive(bool enabled);\n"
        "// MPH_TEST_GUEST_WIDE_STATE_GETTER: comparison build only.\n"
        "bool nds_title_patches_mph_adaptive_enabled();\n",
        GETTER_MARKER,
    )
    patch_once(
        title_cpp,
        "void nds_title_patches_set_mph_adaptive(bool enabled) {\n"
        "    g_mph_adaptive = enabled && g_mph_runtime_profile &&\n"
        "                     g_mph_host_writes_compatible;\n"
        "    if (!g_mph_adaptive) g_mph_aspect_ratio_applied = false;\n"
        "}\n\n"
        "bool nds_title_patches_mph_host_writes_compatible() {\n",
        "void nds_title_patches_set_mph_adaptive(bool enabled) {\n"
        "    g_mph_adaptive = enabled && g_mph_runtime_profile &&\n"
        "                     g_mph_host_writes_compatible;\n"
        "    if (!g_mph_adaptive) g_mph_aspect_ratio_applied = false;\n"
        "}\n\n"
        "// MPH_TEST_GUEST_WIDE_STATE_GETTER: comparison build only.\n"
        "bool nds_title_patches_mph_adaptive_enabled() {\n"
        "    return g_mph_adaptive;\n"
        "}\n\n"
        "bool nds_title_patches_mph_host_writes_compatible() {\n",
        GETTER_MARKER,
    )

    patch_once(main_cpp, MAIN_OLD, MAIN_NEW, MAIN_MARKER)

    # Split source/render width from presentation width. Normal builds use the
    # same value for both. In this experiment only the top destination becomes
    # 448px; its texture, GPU3D output, GPU2D composition and upload pitch all
    # remain native 256px.
    patch_once(
        frontend_cpp,
        "    int screen_widths[2]{kScreenWidth, kScreenWidth};\n"
        "    int canvas_width = kScreenWidth;\n"
        "    int sample_scale = 1;\n",
        "    // MPH_TEST_NATIVE_WIDE_STRETCH_PRESENTATION: comparison build only.\n"
        "    int source_widths[2]{kScreenWidth, kScreenWidth};\n"
        "    int screen_widths[2]{kScreenWidth, kScreenWidth};\n"
        "    int canvas_width = kScreenWidth;\n"
        "    int sample_scale = 1;\n",
        FRONTEND_MARKER,
    )
    patch_once(
        frontend_cpp,
        "    }\n"
        "    presentation.canvas_width = std::max(\n"
        "        presentation.screen_widths[0],\n"
        "        presentation.screen_widths[1]);\n"
        "    const int first_height = presentation.separate\n",
        "    }\n"
        "    presentation.source_widths[0] = presentation.screen_widths[0];\n"
        "    presentation.source_widths[1] = presentation.screen_widths[1];\n"
        "    if (nds_title_patches_mph_adaptive_enabled()) {\n"
        "        // MPH_TEST_NATIVE_WIDE_STRETCH_DESTINATION: render/composite at\n"
        "        // native DS width, stretch only the completed top image.\n"
        "        presentation.source_widths[0] = kScreenWidth;\n"
        "        presentation.screen_widths[0] = 448;\n"
        "    }\n"
        "    presentation.canvas_width = std::max(\n"
        "        presentation.screen_widths[0],\n"
        "        presentation.screen_widths[1]);\n"
        "    const int first_height = presentation.separate\n",
        "MPH_TEST_NATIVE_WIDE_STRETCH_DESTINATION",
    )
    patch_once(
        frontend_cpp,
        "            presentation.screen_widths[screen], kScreenHeight);\n"
        "        if (!presentation.textures[screen]) {\n",
        "            presentation.source_widths[screen], kScreenHeight);\n"
        "        if (!presentation.textures[screen]) {\n",
        "presentation.source_widths[screen], kScreenHeight",
    )
    patch_once(
        frontend_cpp,
        "                presentation.screen_widths[screen] *\n"
        "                    presentation.sample_scale,\n"
        "                kScreenHeight * presentation.sample_scale);\n",
        "                presentation.source_widths[screen] *\n"
        "                    presentation.sample_scale,\n"
        "                kScreenHeight * presentation.sample_scale);\n",
        "presentation.source_widths[screen] *",
    )
    patch_once(
        frontend_cpp,
        "    const uint16_t output_width = static_cast<uint16_t>(std::max(\n"
        "        presentation.screen_widths[0],\n"
        "        presentation.screen_widths[1]));\n",
        "    // MPH_TEST_NATIVE_WIDE_STRETCH_GPU_WIDTH: do not let the 448px\n"
        "    // presentation destination turn the host GPU3D renderer wide again.\n"
        "    const uint16_t output_width = static_cast<uint16_t>(std::max(\n"
        "        presentation.source_widths[0],\n"
        "        presentation.source_widths[1]));\n",
        "MPH_TEST_NATIVE_WIDE_STRETCH_GPU_WIDTH",
    )

    print(
        "Patched comparison build: guest 21:9 ON; host adaptive render/HUD OFF; "
        "native 256x192 top stretched to 448x192 at presentation"
    )


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
