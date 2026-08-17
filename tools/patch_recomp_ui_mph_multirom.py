#!/usr/bin/env python3
"""Patch pinned recomp-ui to render delegated MPH ROM validation honestly.

MPH runtime compatibility is not a whole-ROM SHA-1 gate.  When GameInfo omits
all cartridge fingerprints, the stock recomp-ui model deliberately cannot call
the ROM "verified" and the ImGui dashboard therefore renders "ROM not
recognized" even though launcher_model_can_play() correctly allows the host to
perform its own launch-time validation.

For this project, a fingerprint-free cartridge means exactly that: acceptance
is delegated to nds_runner's MPH executable-compatible detector.  This patch
changes only that dashboard presentation.  Fingerprinted games keep stock
verified/not-recognized semantics, and the runner remains the authoritative
fail-closed validator.
"""

from __future__ import annotations

import argparse
from pathlib import Path


OLD = '''        const bool verified = launcher_model_rom_verified(m);\n        char line[64];\n        if (!m->rom_present)   snprintf(line, sizeof(line), "No %s loaded", noun);\n        else if (verified)     snprintf(line, sizeof(line), "%s verified", noun);\n        else                   snprintf(line, sizeof(line), "%s not recognized", noun);\n        float w = ImGui::GetTextLineHeight() + px(6) + ImGui::CalcTextSize(line).x;\n        ImGui::SetCursorPosX(ImGui::GetCursorPosX() + (availw - w) * 0.5f);\n        state_mark(verified, th);\n        ImGui::SameLine(0, px(6));\n        ImGui::TextColored(verified ? col(th.good) : col(th.warn), "%s", line);'''

NEW = '''        const bool verified = launcher_model_rom_verified(m);\n        // MPH_MULTIROM_DELEGATED_VERIFY: no generic fingerprint means the host\n        // intentionally delegates compatibility to its runtime detector.  Do\n        // not tell the player that such a ROM is "not recognized"; Play is\n        // already allowed by launcher_model_can_play() in this state.\n        const bool delegated = m->rom_present && !m->has_expected_crc &&\n                               m->num_known_sha256 == 0 &&\n                               m->num_known_sha1 == 0;\n        const bool accepted = verified || delegated;\n        char line[96];\n        if (!m->rom_present)   snprintf(line, sizeof(line), "No %s loaded", noun);\n        else if (verified)     snprintf(line, sizeof(line), "%s verified", noun);\n        else if (delegated)    snprintf(line, sizeof(line), "%s selected - runtime validation", noun);\n        else                   snprintf(line, sizeof(line), "%s not recognized", noun);\n        float w = ImGui::GetTextLineHeight() + px(6) + ImGui::CalcTextSize(line).x;\n        ImGui::SetCursorPosX(ImGui::GetCursorPosX() + (availw - w) * 0.5f);\n        state_mark(accepted, th);\n        ImGui::SameLine(0, px(6));\n        ImGui::TextColored(accepted ? col(th.good) : col(th.warn), "%s", line);'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recomp-ui-root", type=Path, required=True)
    args = parser.parse_args()

    root = args.recomp_ui_root.resolve()
    path = root / "src" / "common" / "backends" / "imgui" / "launcher_imgui.cpp"
    if not path.is_file():
        raise SystemExit(f"missing pinned recomp-ui source: {path}")

    text = path.read_text(encoding="utf-8-sig")
    if NEW in text:
        print(f"recomp-ui MPH multi-ROM presentation already patched: {path}")
        return
    count = text.count(OLD)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one launcher ROM-verdict anchor, got {count}; "
            "recomp-ui pin/source shape drifted"
        )
    path.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print(f"Patched delegated MPH ROM validation presentation in {path}")


if __name__ == "__main__":
    main()
