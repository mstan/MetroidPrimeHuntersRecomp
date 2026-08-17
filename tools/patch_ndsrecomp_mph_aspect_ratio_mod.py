#!/usr/bin/env python3
"""Expose the MPH guest-side 21:9 patch independently from host adaptive output.

The normal ndsrecomp Adaptive Widescreen path and the melonPrimeDS/mphCodex
MPH projection/culling patch solve different parts of widescreen rendering.
This layer deliberately decouples them:

* --adaptive-widescreen controls ndsrecomp host-side wide rendering/HUD logic.
* --mph-aspect-ratio-patch controls the MPH guest projection/culling patch.
* when only the guest patch is enabled, the DS-native 256x192 top image is
  stretched to 448x192 at final presentation so the guest's 21:9 projection is
  displayed at the aspect ratio it targets without enabling host wide render.
* when both are enabled, no extra stretch is added; the host renderer already
  produces a 448-wide source. This intentionally permits A/B testing of the
  suspected double-application path.

The guest patch remains fail-closed: only an authoritative executable checksum
that permits MPH host writes can activate it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

CLI_VAR_MARKER = "MPH_ASPECT_RATIO_MOD_CLI_VAR"
CLI_PARSE_MARKER = "MPH_ASPECT_RATIO_MOD_CLI_PARSE"
CLI_USAGE_MARKER = "MPH_ASPECT_RATIO_MOD_CLI_USAGE"
CLI_VALIDATE_MARKER = "MPH_ASPECT_RATIO_MOD_CLI_VALIDATE"
MAIN_GATE_MARKER = "MPH_ASPECT_RATIO_MOD_GATE"
GETTER_MARKER = "MPH_ASPECT_RATIO_MOD_STATE_GETTER"
FRONTEND_MARKER = "MPH_ASPECT_RATIO_MOD_PRESENTATION"


def patch_once(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    if old not in text:
        raise SystemExit(
            f"Refusing MPH aspect-ratio mod patch for {path}: expected pinned "
            f"preimage for {marker!r} was not found"
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

    # Expose the latched guest-patch state to frontend.cpp. g_mph_adaptive is
    # the existing widescreen patcher's state variable; this layer only
    # changes what policy feeds it, not its guarded code/data writes.
    patch_once(
        title_h,
        "void nds_title_patches_set_mph_adaptive(bool enabled);\n",
        "void nds_title_patches_set_mph_adaptive(bool enabled);\n"
        "// MPH_ASPECT_RATIO_MOD_STATE_GETTER: guest projection/culling state.\n"
        "bool nds_title_patches_mph_aspect_ratio_enabled();\n",
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
        "// MPH_ASPECT_RATIO_MOD_STATE_GETTER: guest projection/culling state.\n"
        "bool nds_title_patches_mph_aspect_ratio_enabled() {\n"
        "    return g_mph_adaptive;\n"
        "}\n\n"
        "bool nds_title_patches_mph_host_writes_compatible() {\n",
        GETTER_MARKER,
    )

    # Independent CLI policy. Default OFF is intentional: existing users keep
    # the original ndsrecomp host Adaptive Widescreen behavior and no longer
    # receive a second game-side aspect transform unless they opt into the mod.
    patch_once(
        main_cpp,
        "    std::string cli_adaptive_screens;\n"
        "    std::string cli_supersampling;\n",
        "    std::string cli_adaptive_screens;\n"
        "    // MPH_ASPECT_RATIO_MOD_CLI_VAR\n"
        "    std::string cli_mph_aspect_ratio_patch;\n"
        "    std::string cli_supersampling;\n",
        CLI_VAR_MARKER,
    )
    patch_once(
        main_cpp,
        "        } else if (a == \"--adaptive-widescreen\" && i + 1 < argc) {\n"
        "            cli_adaptive_screens = argv[++i];\n"
        "        } else if (a == \"--supersampling\" && i + 1 < argc) {\n",
        "        } else if (a == \"--adaptive-widescreen\" && i + 1 < argc) {\n"
        "            cli_adaptive_screens = argv[++i];\n"
        "        // MPH_ASPECT_RATIO_MOD_CLI_PARSE\n"
        "        } else if (a == \"--mph-aspect-ratio-patch\" && i + 1 < argc) {\n"
        "            cli_mph_aspect_ratio_patch = argv[++i];\n"
        "        } else if (a == \"--supersampling\" && i + 1 < argc) {\n",
        CLI_PARSE_MARKER,
    )
    patch_once(
        main_cpp,
        "                \"[--adaptive-widescreen none|top|bottom|both] \"\n"
        "                \"[--supersampling 1|2|3|4] \"\n",
        "                \"[--adaptive-widescreen none|top|bottom|both] \"\n"
        "                // MPH_ASPECT_RATIO_MOD_CLI_USAGE\n"
        "                \"[--mph-aspect-ratio-patch on|off] \"\n"
        "                \"[--supersampling 1|2|3|4] \"\n",
        CLI_USAGE_MARKER,
    )
    patch_once(
        main_cpp,
        "    if (!cli_supersampling.empty() &&\n",
        "    // MPH_ASPECT_RATIO_MOD_CLI_VALIDATE\n"
        "    bool mph_aspect_ratio_patch = false;\n"
        "    if (!cli_mph_aspect_ratio_patch.empty()) {\n"
        "        if (cli_mph_aspect_ratio_patch == \"on\")\n"
        "            mph_aspect_ratio_patch = true;\n"
        "        else if (cli_mph_aspect_ratio_patch != \"off\") {\n"
        "            std::fprintf(stderr,\n"
        "                         \"invalid --mph-aspect-ratio-patch \"\n"
        "                         \"(expected on or off)\\n\");\n"
        "            return 2;\n"
        "        }\n"
        "    }\n"
        "    if (!cli_supersampling.empty() &&\n",
        CLI_VALIDATE_MARKER,
    )

    patch_once(
        main_cpp,
        "    nds_title_patches_set_mph_adaptive(\n"
        "        nds_title_patches_mph_host_writes_compatible() &&\n"
        "        (frontend_options.adaptive_screens & NDS_ADAPTIVE_TOP) != 0u);\n"
        "    nds_title_patches_set_mph_mouse_aim(mph_mouse_aim_policy);\n",
        "    // MPH_ASPECT_RATIO_MOD_GATE: guest aspect patch is independent of\n"
        "    // ndsrecomp host Adaptive Widescreen. Unknown/header-only variants\n"
        "    // still fail closed because host writes are not authorized.\n"
        "    const bool mph_aspect_ratio_patch_policy =\n"
        "        mph_aspect_ratio_patch &&\n"
        "        nds_title_patches_mph_host_writes_compatible();\n"
        "    nds_title_patches_set_mph_adaptive(mph_aspect_ratio_patch_policy);\n"
        "    if (mph_aspect_ratio_patch && !mph_aspect_ratio_patch_policy)\n"
        "        std::fprintf(stderr,\n"
        "                     \"[mph] game aspect-ratio patch disabled: \"\n"
        "                     \"unknown executable checksum\\n\");\n"
        "    if (mph_aspect_ratio_patch_policy)\n"
        "        std::fprintf(stderr,\n"
        "                     \"[mph] game aspect-ratio patch requested; \"\n"
        "                     \"host adaptive=%s\\n\",\n"
        "                     (frontend_options.adaptive_screens & NDS_ADAPTIVE_TOP)\n"
        "                         ? \"on\" : \"off\");\n"
        "    nds_title_patches_set_mph_mouse_aim(mph_mouse_aim_policy);\n",
        MAIN_GATE_MARKER,
    )

    # Separate the emulated source width from its final presentation width.
    # Host Adaptive ON already makes the source 448px. Guest-only mode keeps
    # source render/composition at 256px and stretches only the finished image.
    patch_once(
        frontend_cpp,
        "    int screen_widths[2]{kScreenWidth, kScreenWidth};\n"
        "    int canvas_width = kScreenWidth;\n"
        "    int sample_scale = 1;\n",
        "    // MPH_ASPECT_RATIO_MOD_PRESENTATION\n"
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
        "    if (nds_title_patches_mph_aspect_ratio_enabled() &&\n"
        "        presentation.screen_widths[0] == kScreenWidth) {\n"
        "        // Guest-only mode: preserve native DS rendering but present\n"
        "        // the completed image at the 21:9 width targeted by the patch.\n"
        "        presentation.screen_widths[0] = 448;\n"
        "        std::fprintf(stderr,\n"
        "                     \"[mph] guest-only aspect mode: native 256x192 \"\n"
        "                     \"top -> 448x192 presentation stretch\\n\");\n"
        "    }\n"
        "    presentation.canvas_width = std::max(\n"
        "        presentation.screen_widths[0],\n"
        "        presentation.screen_widths[1]);\n"
        "    const int first_height = presentation.separate\n",
        "MPH_ASPECT_RATIO_MOD_PRESENTATION_DESTINATION",
    )
    patch_once(
        frontend_cpp,
        "            presentation.screen_widths[screen], kScreenHeight);\n"
        "        if (!presentation.textures[screen]) {\n",
        "            presentation.source_widths[screen], kScreenHeight);\n"
        "        if (!presentation.textures[screen]) {\n",
        "MPH_ASPECT_RATIO_MOD_TEXTURE_SOURCE_WIDTH",
    )
    patch_once(
        frontend_cpp,
        "                presentation.screen_widths[screen] *\n"
        "                    presentation.sample_scale,\n"
        "                kScreenHeight * presentation.sample_scale);\n",
        "                presentation.source_widths[screen] *\n"
        "                    presentation.sample_scale,\n"
        "                kScreenHeight * presentation.sample_scale);\n",
        "MPH_ASPECT_RATIO_MOD_SAMPLE_SOURCE_WIDTH",
    )
    patch_once(
        frontend_cpp,
        "    const uint16_t output_width = static_cast<uint16_t>(std::max(\n"
        "        presentation.screen_widths[0],\n"
        "        presentation.screen_widths[1]));\n",
        "    // Guest-only stretch must not silently reactivate a 448px GPU3D\n"
        "    // render surface; only host Adaptive Widescreen may do that.\n"
        "    const uint16_t output_width = static_cast<uint16_t>(std::max(\n"
        "        presentation.source_widths[0],\n"
        "        presentation.source_widths[1]));\n",
        "MPH_ASPECT_RATIO_MOD_GPU_SOURCE_WIDTH",
    )

    print(
        "Patched independent MPH aspect-ratio mod: host Adaptive Widescreen and "
        "guest projection/culling can be toggled separately"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=False)
    args = parser.parse_args()
    patch(args.framework_root.resolve())


if __name__ == "__main__":
    main()
