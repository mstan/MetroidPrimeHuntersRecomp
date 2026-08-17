#!/usr/bin/env python3
"""Add an independent MPH game-side aspect-ratio feature to the launcher TU.

The repository launcher source intentionally tracks upstream closely. The MPH
profile CMake already generates a launcher_main_profile.cpp and layers project-
specific multi-ROM transforms onto it. This script adds one more project layer:

* Adaptive Widescreen remains the original ndsrecomp host-side 448px renderer
  and HUD anchoring feature.
* Game Aspect Ratio Patch controls the melonPrimeDS/mphCodex guest-side 21:9
  projection/culling writes via --mph-aspect-ratio-patch.

The guest patch defaults OFF so existing users receive only the original host
Adaptive Widescreen path unless they explicitly opt into the comparison mod.
"""

from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "MPH_GAME_ASPECT_RATIO_MOD"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(
            f"Refusing launcher aspect-mod patch: expected preimage for {label} "
            "was not found"
        )
    return text.replace(old, new, 1)


def patch(source: Path) -> None:
    text = source.read_text(encoding="utf-8")
    if MARKER in text:
        print("MPH launcher game aspect-ratio mod already applied")
        return

    text = replace_once(
        text,
        "struct ModState {\n    bool adaptive_widescreen = true;\n",
        "struct ModState {\n"
        "    bool adaptive_widescreen = true;\n"
        "    // MPH_GAME_ASPECT_RATIO_MOD: independent game-side 21:9 patch.\n"
        "    // OFF by default so the original ndsrecomp host Adaptive\n"
        "    // Widescreen path remains the baseline and is not double-applied.\n"
        "    bool aspect_ratio_patch = false;\n",
        "ModState aspect flag",
    )

    text = replace_once(
        text,
        "        } else if (key == \"adaptive_widescreen\") {\n"
        "            state.adaptive_widescreen = value != \"false\";\n"
        "        } else if (key == \"hd_rendering\") {\n",
        "        } else if (key == \"adaptive_widescreen\") {\n"
        "            state.adaptive_widescreen = value != \"false\";\n"
        "        } else if (key == \"aspect_ratio_patch\") {\n"
        "            state.aspect_ratio_patch = value == \"true\";\n"
        "        } else if (key == \"hd_rendering\") {\n",
        "settings load",
    )

    text = replace_once(
        text,
        "        file << \"settings_version=3\\n\"\n"
        "             << \"adaptive_widescreen=\"\n"
        "             << (state.adaptive_widescreen ? \"true\" : \"false\") << '\\n'\n"
        "             << \"hd_rendering=\"\n",
        "        file << \"settings_version=4\\n\"\n"
        "             << \"adaptive_widescreen=\"\n"
        "             << (state.adaptive_widescreen ? \"true\" : \"false\") << '\\n'\n"
        "             << \"aspect_ratio_patch=\"\n"
        "             << (state.aspect_ratio_patch ? \"true\" : \"false\") << '\\n'\n"
        "             << \"hd_rendering=\"\n",
        "settings save",
    )

    text = replace_once(
        text,
        "// The online identity is NOT a mod: it lives on the dashboard's ONLINE\n"
        "// card (GameInfo.has_player_name + the NDS profile's \"identity\" panel),\n"
        "// directly under the controller card. Only the two real gameplay mods\n"
        "// remain here.\n"
        "int mod_feature_count(void*) {\n"
        "    return 3;\n"
        "}\n",
        "// The online identity is NOT a mod: it lives on the dashboard's ONLINE\n"
        "// card. Display features deliberately expose host Adaptive Widescreen\n"
        "// and the game-side aspect-ratio patch independently for A/B testing.\n"
        "int mod_feature_count(void*) {\n"
        "    return 4;\n"
        "}\n",
        "feature count",
    )

    text = replace_once(
        text,
        "    if (!context || !output || index < 0 || index > 2) return 0;\n",
        "    if (!context || !output || index < 0 || index > 3) return 0;\n",
        "feature index range",
    )

    aspect_feature = '''    } else if (index == 3) {
        copy_text(output->id, "game-aspect-ratio-patch");
        copy_text(output->package_id, "mph-game-aspect-ratio-patch");
        copy_text(output->package_version, "0.1.0");
        copy_text(output->package_name, "MPH Game Aspect Ratio Patch");
        copy_text(output->name, "Game Aspect Ratio Patch");
        copy_text(output->author, "melonPrimeDS / mphCodex integration");
        copy_text(
            output->description,
            "Applies the MPH game-side 21:9 projection and culling patch. "
            "This is independent from Recomp's host Adaptive Widescreen, "
            "so either path can be tested alone or both can be enabled.");
        copy_text(output->source_name, "ag-advania/melonPrimeDS");
        copy_text(output->source_url,
                  "https://github.com/ag-advania/melonPrimeDS");
        copy_text(output->group, "Display enhancements");
        copy_text(output->status,
                  state->aspect_ratio_patch ? "Enabled" : "Disabled");
        output->enabled = state->aspect_ratio_patch ? 1 : 0;
'''
    text = replace_once(
        text,
        "        output->option_count = 2;\n    } else {\n"
        "        copy_text(output->id, \"prime-controls\");\n",
        "        output->option_count = 2;\n" + aspect_feature +
        "    } else {\n"
        "        copy_text(output->id, \"prime-controls\");\n",
        "aspect feature metadata",
    )

    text = replace_once(
        text,
        "    if (std::strcmp(package_id, \"mph-adaptive-widescreen\") == 0 &&\n"
        "        std::strcmp(feature_id, \"adaptive-widescreen\") == 0) {\n"
        "        state->adaptive_widescreen = enabled != 0;\n"
        "        return 1;\n"
        "    }\n"
        "    if (std::strcmp(package_id, \"mph-prime-controls\") == 0 &&\n",
        "    if (std::strcmp(package_id, \"mph-adaptive-widescreen\") == 0 &&\n"
        "        std::strcmp(feature_id, \"adaptive-widescreen\") == 0) {\n"
        "        state->adaptive_widescreen = enabled != 0;\n"
        "        return 1;\n"
        "    }\n"
        "    if (std::strcmp(package_id, \"mph-game-aspect-ratio-patch\") == 0 &&\n"
        "        std::strcmp(feature_id, \"game-aspect-ratio-patch\") == 0) {\n"
        "        state->aspect_ratio_patch = enabled != 0;\n"
        "        return 1;\n"
        "    }\n"
        "    if (std::strcmp(package_id, \"mph-prime-controls\") == 0 &&\n",
        "aspect feature enable",
    )

    text = replace_once(
        text,
        "        (adaptive || mods.prime_controls || display_layout == 1\n"
        "            ? L\"separate\"\n"
        "            : L\"stacked\") +\n"
        "        L\" --adaptive-widescreen \" +\n"
        "        (adaptive ? L\"top\" : L\"none\") +\n",
        "        (adaptive || mods.aspect_ratio_patch || mods.prime_controls ||\n"
        "         display_layout == 1\n"
        "            ? L\"separate\"\n"
        "            : L\"stacked\") +\n"
        "        L\" --adaptive-widescreen \" +\n"
        "        (adaptive ? L\"top\" : L\"none\") +\n"
        "        L\" --mph-aspect-ratio-patch \" +\n"
        "        (mods.aspect_ratio_patch ? L\"on\" : L\"off\") +\n",
        "runner launch arguments",
    )

    source.write_text(text, encoding="utf-8")
    print(
        "Patched launcher Mods: Adaptive Widescreen (host) and Game Aspect "
        "Ratio Patch (guest) are independent; guest default=off"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    patch(args.source.resolve())


if __name__ == "__main__":
    main()
