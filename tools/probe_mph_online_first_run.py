#!/usr/bin/env python3
"""Validate MPH Wiimmfi setup and persistence across real process restarts.

The runner stays in interactive mode. Navigation, screenshots, and lifecycle
control all use its TCP debug surface; input/checkpoint primitives come from
fuzz_mph_gameplay. The source ROM, save, and identity are copied/read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import capture_mph_checkpoints as capture_lib  # noqa: E402
import fuzz_mph_gameplay as input_lib  # noqa: E402
import mph_screens  # noqa: E402
from add_mph_friend import MENU_PATH  # noqa: E402
from run_mph_friend_match import DIALOG_YES, FRIENDS_AND_RIVALS  # noqa: E402
from run_mph_wfc_instances import FILTERS  # noqa: E402

INPUT_FUZZ = random.Random()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_frames(
    client: capture_lib.DebugClient,
    process: subprocess.Popen[bytes],
    count: int,
    timeout: float = 300.0,
) -> None:
    start = input_lib.event_counts(client)["vblank9"]
    target = start + count
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"runner exited with code {process.returncode}")
        if input_lib.event_counts(client)["vblank9"] >= target:
            return
        time.sleep(0.025)
    raise TimeoutError(f"runner did not advance {count} frames")


def tap(
    client: capture_lib.DebugClient,
    process: subprocess.Popen[bytes],
    x: int,
    y: int,
    wait: int,
) -> None:
    fuzzed_x = max(0, min(255, x + INPUT_FUZZ.randint(-2, 2)))
    fuzzed_y = max(0, min(191, y + INPUT_FUZZ.randint(-2, 2)))
    client.command("touch", x=fuzzed_x, y=fuzzed_y, down=True)
    wait_frames(client, process, INPUT_FUZZ.randint(8, 14))
    client.command("touch", x=fuzzed_x, y=fuzzed_y, down=False)
    wait_frames(client, process, wait)


def press(
    client: capture_lib.DebugClient,
    process: subprocess.Popen[bytes],
    key: str,
    wait: int,
) -> None:
    bit = input_lib.KEY_BITS[key]
    client.command("keys", mask=input_lib.RELEASED_KEYS & ~(1 << bit))
    wait_frames(client, process, INPUT_FUZZ.randint(8, 14))
    client.command("keys", mask=input_lib.RELEASED_KEYS)
    wait_frames(client, process, wait)


class InteractiveSession:
    def __init__(
        self,
        args: argparse.Namespace,
        name: str,
        port: int,
        profile: Path,
    ) -> None:
        self.output = args.out / name
        self.output.mkdir(parents=True, exist_ok=True)
        self.report: list[dict[str, Any]] = []
        self.stdout = (self.output / "runner.stdout.log").open("wb")
        self.stderr = (self.output / "runner.stderr.log").open("wb")
        command = [
            str(args.runner), str(profile / "bios"), "--interactive",
            "--port", str(port), "--rom", str(args.rom),
            "--config", str(args.config), "--save-path",
            str(profile / "Metroid Prime Hunters.sav"),
            "--firmware-state-path", str(profile / "firmware-generated.bin"),
            "--startup-mode", "automatic", "--network", "on",
            "--network-backend", "slirp", "--wfc", "on",
            "--wfc-provider", args.wfc_provider, "--freebios",
            "--generated-firmware", "--boot", "direct",
        ]
        self.process = subprocess.Popen(
            command, cwd=args.runner.parent, stdout=self.stdout,
            stderr=self.stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        capture_lib.wait_for_server(port, self.process)
        self.client = capture_lib.DebugClient(port, timeout=600.0)

    def save(self, label: str) -> dict[str, Any]:
        item = input_lib.save_checkpoint(
            self.client, self.output, len(self.report), label
        )
        self.report.append(item)
        return item

    def close_handles(self) -> None:
        try:
            self.client.close()
        except OSError:
            pass
        self.stdout.close()
        self.stderr.close()
        (self.output / "report.json").write_text(
            json.dumps(self.report, indent=2) + "\n", encoding="utf-8"
        )

    def force_cleanup(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.close_handles()


def reach_wfc_menu(session: InteractiveSession) -> None:
    wait_frames(session.client, session.process, 7800)
    session.save("title")
    for label, x, y, wait in MENU_PATH[:4]:
        tap(session.client, session.process, x, y, wait)
        session.save(label)


def setup_and_power_off(session: InteractiveSession) -> dict[str, Any]:
    reach_wfc_menu(session)
    route = (
        ("wfc-setup-root", 128, 36, 600),
        ("settings-tile", 85, 100, 220),
        ("slot1", 43, 35, 220),
        ("search-for-ap", 128, 37, 1600),
        ("test-connection", 192, 36, 2400),
        ("save-settings", 190, 177, 600),
    )
    for label, x, y, wait in route:
        tap(session.client, session.process, x, y, wait)
        session.save(label)
    press(session.client, session.process, "b", 600)
    session.save("setup-root-after-back")
    press(session.client, session.process, "b", 600)
    prompt = session.save("system-will-shut-down")

    rings = {
        name: session.client.command("net_ring_dump", max=256, filter=name)
        for name in FILTERS
    }
    counts = {
        name: len(value.get("events", [])) if isinstance(value, dict) else 0
        for name, value in rings.items()
    }
    if counts.get("dhcp", 0) == 0 or counts.get("backend_error", 0) != 0:
        raise RuntimeError(f"connection test did not succeed cleanly: {counts}")

    # The green check confirms the firmware's terminal shutdown prompt.
    session.client.command("touch", x=128, y=128, down=True)
    try:
        session.process.wait(timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("guest power-off left the application open") from exc
    if session.process.returncode != 0:
        raise RuntimeError(
            f"guest power-off returned {session.process.returncode}"
        )
    session.close_handles()
    stderr_text = (session.output / "runner.stderr.log").read_text(
        encoding="utf-8", errors="replace"
    )
    if "[sdl] guest requested power-off; closing" not in stderr_text:
        raise RuntimeError("runner did not report the guest power-off exit")
    return {"prompt": prompt, "net_counts": counts, "returncode": 0}


def direct_online(
    session: InteractiveSession,
    require_no_notice_pages: bool,
) -> dict[str, Any]:
    reach_wfc_menu(session)
    tap(session.client, session.process, *FRIENDS_AND_RIVALS, 240)
    session.save("friends-rivals")

    arrow_pages = 0
    yes_pages = 0
    ok_pages = 0
    for index in range(8):
        item = session.save(f"dialog-{index}")
        image = Image.open(session.output / str(item["image"])).convert("RGB")
        ok_bright = mph_screens.bright_count(
            image, mph_screens.BOXES["dialog_ok"]
        )
        if mph_screens.bright_count(
                image, mph_screens.BOXES["dialog_arrow"]) > 40:
            arrow_pages += 1
            tap(session.client, session.process, 190, 120, 240)
        elif mph_screens.is_connect_dialog(image):
            yes_pages += 1
            tap(session.client, session.process, *DIALOG_YES, 240)
        elif 40 < ok_bright < 200:
            ok_pages += 1
            tap(session.client, session.process, 128, 128, 240)
        elif ok_bright >= 200:
            # The animated connection badge shares the acknowledgement's
            # screen region. Leave it alone and wait for authentication.
            break
        else:
            break
    wait_frames(session.client, session.process, 2400)
    final = session.save("post-connect")
    rings = {
        name: session.client.command("net_ring_dump", max=256, filter=name)
        for name in FILTERS
    }
    counts = {
        name: len(value.get("events", [])) if isinstance(value, dict) else 0
        for name, value in rings.items()
    }
    if counts.get("tls_record", 0) == 0 or counts.get("backend_error", 0) != 0:
        raise RuntimeError(f"Wiimmfi authentication failed: {counts}")
    if require_no_notice_pages and (arrow_pages != 0 or ok_pages != 0):
        raise RuntimeError(
            "returning profile repeated pairing/update pages: "
            f"arrow={arrow_pages}, ok={ok_pages}"
        )

    response = session.client.command("frontend_exit")
    if not isinstance(response, dict) or not response.get("requested"):
        raise RuntimeError(f"frontend_exit was not accepted: {response!r}")
    session.process.wait(timeout=30)
    if session.process.returncode != 0:
        raise RuntimeError(
            f"normal window close returned {session.process.returncode}"
        )
    session.close_handles()
    return {
        "final": final,
        "arrow_pages": arrow_pages,
        "yes_pages": yes_pages,
        "ok_pages": ok_pages,
        "net_counts": counts,
        "returncode": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source-save", type=Path, required=True)
    parser.add_argument("--source-identity", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=21020)
    parser.add_argument("--wfc-provider", default="wiimmfi")
    parser.add_argument("--input-fuzz-seed", type=int, default=0x4D5048)
    parser.add_argument(
        "--resume-after-setup", action="store_true",
        help="reuse an existing profile after a successful setup/power-off run",
    )
    args = parser.parse_args()
    INPUT_FUZZ.seed(args.input_fuzz_seed)
    for key in ("runner", "rom", "config", "source_save", "source_identity"):
        setattr(args, key, getattr(args, key).resolve())
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    profile = args.out / "profile"
    (profile / "bios").mkdir(parents=True, exist_ok=True)

    source_hashes = {
        "save": sha256(args.source_save),
        "identity": sha256(args.source_identity),
    }
    if not args.resume_after_setup:
        shutil.copy2(args.source_save, profile / "Metroid Prime Hunters.sav")
        shutil.copy2(
            args.source_identity, profile / "bios" / "generated-identity.bin"
        )
    elif not (profile / "firmware-generated.bin").is_file():
        parser.error("--resume-after-setup requires an existing profile state")

    summary: dict[str, Any] = {
        "input_fuzz_seed": args.input_fuzz_seed,
        "source_hashes": source_hashes,
    }
    sessions: list[InteractiveSession] = []
    try:
        state = profile / "firmware-generated.bin"
        cartridge = profile / "Metroid Prime Hunters.sav"
        if not args.resume_after_setup:
            first = InteractiveSession(
                args, "01-setup-poweroff", args.port, profile
            )
            sessions.append(first)
            summary["setup"] = setup_and_power_off(first)
            summary["state_after_setup"] = {
                "size": state.stat().st_size, "sha256": sha256(state)
            }
            summary["save_after_setup"] = sha256(cartridge)
        else:
            summary["setup"] = "resumed"

        online_port = args.port + (0 if args.resume_after_setup else 1)
        second = InteractiveSession(args, "02-first-online", online_port, profile)
        sessions.append(second)
        summary["first_online"] = direct_online(second, False)
        summary["state_after_first_online"] = sha256(state)
        summary["save_after_first_online"] = sha256(cartridge)

        third = InteractiveSession(args, "03-returning-online", online_port + 1, profile)
        sessions.append(third)
        summary["returning_online"] = direct_online(third, True)
        summary["state_after_returning_online"] = sha256(state)
        summary["save_after_returning_online"] = sha256(cartridge)
    finally:
        for session in sessions:
            if session.process.poll() is None:
                session.force_cleanup()

    if sha256(args.source_save) != source_hashes["save"] or \
       sha256(args.source_identity) != source_hashes["identity"]:
        raise RuntimeError("source save/identity changed during QA")
    summary["sources_unchanged"] = True
    summary["success"] = True
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
