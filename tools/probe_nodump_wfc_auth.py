#!/usr/bin/env python3
"""Prove single-instance Nintendo WFC (Wiimmfi) authentication on the full
no-dump path (beads-yjp.15 increment 4): FreeBIOS + generated firmware +
direct boot, only a ROM supplied.

Drives one instance from the title screen into Friends and Rivals, whose
connect dialog starts the real network bring-up (DHCP -> DNS -> TCP -> TLS
-> Wiimmfi login). The auth verdict is evidence-based: TLS records
exchanged with a clean backend (no backend_error/backend_drop), plus the
classified screen and checkpoint screenshots under --out.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_mph_checkpoints as capture_lib  # noqa: E402
import fuzz_mph_gameplay as input_lib  # noqa: E402
import mph_screens  # noqa: E402
from PIL import Image  # noqa: E402
from add_mph_friend import MENU_PATH, Session  # noqa: E402
from run_mph_friend_match import DIALOG_YES, FRIENDS_AND_RIVALS  # noqa: E402
from run_mph_wfc_instances import FILTERS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--bios", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--save-path", type=Path, required=True)
    parser.add_argument(
        "--firmware-state-path", type=Path,
        help="persist the generated firmware (WFC identity) across runs; "
        "without it the guest-assigned WFC ID dies with the process and the "
        "save is left mismatched against every future console identity",
    )
    parser.add_argument("--identity-mac")
    parser.add_argument("--instance-index", type=int, default=0)
    parser.add_argument("--port", type=int, default=20480)
    parser.add_argument("--wfc-provider", default="wiimmfi")
    parser.add_argument("--title-vblank", type=int, default=7800)
    parser.add_argument("--online-wait", type=int, default=2400)
    args = parser.parse_args()

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    command = [
        str(args.runner), str(args.bios), "--serve", "--port", str(args.port),
        "--rom", str(args.rom), "--config", str(args.config),
        "--save-path", str(args.save_path),
        "--network", "on", "--network-backend", "slirp",
        "--wfc", "on", "--wfc-provider", args.wfc_provider,
        "--freebios", "--generated-firmware", "--boot", "direct",
        "--instance-index", str(args.instance_index),
    ]
    if args.firmware_state_path:
        command += ["--firmware-state-path", str(args.firmware_state_path)]
    if args.identity_mac:
        command += ["--identity-mac", args.identity_mac]

    stdout = (out / "runner.stdout.log").open("wb")
    stderr = (out / "runner.stderr.log").open("wb")
    process = subprocess.Popen(
        command, cwd=str(args.runner.parent), stdout=stdout, stderr=stderr,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    result: dict[str, Any] = {"authenticated": False}
    try:
        capture_lib.wait_for_server(args.port, process)
        client = capture_lib.DebugClient(args.port, timeout=3600.0)
        session = Session(client, out)

        input_lib.advance_to_vblank(client, args.title_vblank)
        session.save("title")
        for label, x, y, wait in MENU_PATH[:4]:  # stop at the WFC menu
            session.tap_and_save(label, x, y, wait)

        session.tap_and_save("friends-rivals", *FRIENDS_AND_RIVALS, 240)

        # First-time WFC connection shows a multi-page notice ("your game
        # card and DS are treated as a set...") before the connect prompt.
        # Page any dialog forward via its orange ">" and answer any yes/no
        # or checkmark dialog affirmatively, until no dialog remains.
        for round_index in range(8):
            item = session.save(f"dialog-{round_index}")
            image = Image.open(out / item["image"]).convert("RGB")
            if mph_screens.bright_count(
                    image, mph_screens.BOXES["dialog_arrow"]) > 40:
                session.tap(190, 120, 240)   # next page
            elif mph_screens.bright_count(
                    image, mph_screens.BOXES["dialog_yes"]) > 40:
                session.tap(*DIALOG_YES, 240)  # yes / checkmark
            else:
                break

        input_lib.advance_frames(client, args.online_wait)
        item = session.save("post-connect")

        image = Image.open(out / item["image"]).convert("RGB")
        rings = {
            name: client.command("net_ring_dump", max=256, filter=name)
            for name in FILTERS
        }
        counts = {
            name: len(ring.get("events", []))
            if isinstance(ring, dict) else 0
            for name, ring in rings.items()
        }
        result.update({
            "screen": mph_screens.identify(image),
            "net_counts": counts,
            "tls_reached": counts.get("tls_record", 0) > 0,
            "backend_clean": counts.get("backend_error", 0) == 0
            and counts.get("backend_drop", 0) == 0,
        })
        result["authenticated"] = bool(
            result["tls_reached"] and result["backend_clean"])
        session.report.append(result)
        (out / "report.json").write_text(
            json.dumps(session.report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)
        client.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        stdout.close()
        stderr.close()
    return 0 if result["authenticated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
