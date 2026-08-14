#!/usr/bin/env python3
"""Register a Nintendo WFC friend code in a Metroid Prime Hunters profile.

Public Wiimmfi matchmaking never pairs two locally-driven instances with each
other: every instance reaches Wiimmfi cleanly (DHCP -> DNS -> TCP -> TLS) and
then parks on "SEARCHING FOR PLAYERS" forever. Friend matching is the way to
make two specific instances target each other, and that needs each profile's
Friends/Rivals roster to actually contain the other profile's code.

This drives the whole roster-entry flow on one instance: boot, inject the
prepared profile firmware, walk Multiplayer -> Nintendo WFC -> Edit Friends and
Rivals -> Add Friend, punch in the 12-digit code, then answer the "ENTER A
TEMPORARY NAME FOR THIS FRIEND" prompt on the on-screen keyboard. The friend is
only useful if it survives the run, so the cartridge save is explicitly flushed
through the debug server instead of relying on process teardown.

Output can contain real console/network identifiers in screenshots; keep it
under scratch/.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import capture_mph_checkpoints as capture_lib  # noqa: E402
import fuzz_mph_gameplay as input_lib  # noqa: E402


# Friend-code entry uses the game's own phone-style numeric pad, not the
# alphanumeric keyboard: three columns at x 94/128/162, rows descending 7-8-9 /
# 4-5-6 / 1-2-3 with 0 below.
CODE_PAD = {
    "1": (94, 107), "2": (128, 107), "3": (162, 107),
    "4": (94, 75), "5": (128, 75), "6": (162, 75),
    "7": (94, 44), "8": (128, 44), "9": (162, 44),
    "0": (94, 138),
}
CODE_CONFIRM = (220, 138)

# Temporary-name entry uses a full QWERTY keyboard on the touch screen. These
# centres were measured off a captured keyboard frame by tools/kbdetect-style
# key-box detection (light key blocks on the black panel), not estimated: row
# bands land at touch-y 108 / 124 / 140 / 156 / 171 and the key pitch is 16.
# Guessing here is what produced the earlier "typed z instead of a" runs --
# touch-y 161 is the z row, and touch-y 140 is the a row.
KEYBOARD = {
    "1": (39, 108), "2": (55, 108), "3": (71, 108), "4": (87, 108),
    "5": (103, 108), "6": (119, 108), "7": (135, 108), "8": (151, 108),
    "9": (167, 108), "0": (183, 108), "-": (199, 108), "=": (215, 108),

    "q": (48, 124), "w": (64, 124), "e": (80, 124), "r": (96, 124),
    "t": (112, 124), "y": (128, 124), "u": (144, 124), "i": (160, 124),
    "o": (176, 124), "p": (192, 124),

    "a": (55, 140), "s": (71, 140), "d": (87, 140), "f": (103, 140),
    "g": (119, 140), "h": (135, 140), "j": (151, 140), "k": (167, 140),
    "l": (183, 140),

    "z": (63, 156), "x": (79, 156), "c": (95, 156), "v": (111, 156),
    "b": (127, 156), "n": (143, 156), "m": (159, 156), ",": (175, 156),
    ".": (191, 156), "/": (207, 156),

    ";": (71, 171), "'": (87, 171), " ": (135, 171),
    "[": (183, 171), "]": (199, 171),
}
KEYBOARD_BACKSPACE = (213, 124)
KEYBOARD_ENTER = (208, 140)
# The name field's commit control is the circled check to the right of the text
# box, on the touch screen well above the keyboard.
NAME_CONFIRM = (233, 62)

# Menu path from the title screen to the Add Friend code pad.
MENU_PATH = (
    ("main-menu", 84, 92, 180),
    ("nickname-dialog", 168, 92, 180),
    ("multiplayer-menu", 128, 126, 240),
    ("wfc-menu", 198, 92, 360),
    ("edit-friends-rivals", 183, 176, 900),
    ("add-friend", 220, 171, 600),
)

# The roster screen's back arrow. Registering a friend only dirties the
# cartridge save once the game leaves the Friends/Rivals screens, so the run has
# to walk back out rather than stopping on the roster with the entry in RAM.
ROSTER_BACK = (20, 172)


def launch(args: argparse.Namespace) -> subprocess.Popen[bytes]:
    command = [
        str(args.runner),
        str(args.bios),
        "--serve",
        "--port",
        str(args.port),
        "--rom",
        str(args.rom),
        "--config",
        str(args.config),
        "--startup-mode",
        args.startup_mode,
        "--network",
        "on",
        "--network-backend",
        args.network_backend,
        "--wfc",
        "on",
        "--wfc-provider",
        args.wfc_provider,
        "--instance-index",
        "0",
        "--save-path",
        str(args.save_path),
    ]
    if args.firmware_path is not None:
        command.extend(["--firmware-path", str(args.firmware_path)])

    stdout = (args.out / "runner.stdout.log").open("wb")
    stderr = (args.out / "runner.stderr.log").open("wb")
    try:
        return subprocess.Popen(
            command,
            cwd=args.runner.parent,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        stdout.close()
        stderr.close()


class Session:
    def __init__(self, client: capture_lib.DebugClient, out: Path):
        self.client = client
        self.out = out
        self.report: list[dict[str, Any]] = []

    def save(self, label: str) -> dict[str, Any]:
        item = input_lib.save_checkpoint(
            self.client, self.out, len(self.report), label
        )
        # Track the cartridge-save dirty bit at every checkpoint rather than
        # sampling it once at the end: that is what shows which UI transition
        # actually commits the roster.
        item["cart_save_info"] = self.client.command("cart_save_info")
        self.report.append(item)
        dirty = item["cart_save_info"].get("dirty")
        print(
            f"{label} vblank9={item['vblank9']} dirty={dirty} {item['image']}",
            flush=True,
        )
        return item

    def tap(self, x: int, y: int, wait: int) -> None:
        input_lib.tap(self.client, x, y, 12)
        input_lib.advance_frames(self.client, wait)

    def tap_and_save(self, label: str, x: int, y: int, wait: int) -> None:
        self.tap(x, y, wait)
        self.save(label)


def type_name(session: Session, name: str, settle: int) -> None:
    for character in name:
        key = character.lower()
        if key not in KEYBOARD:
            raise ValueError(
                f"character {character!r} is not on the MPH name keyboard"
            )
        x, y = KEYBOARD[key]
        session.tap(x, y, settle)


def enter_code(session: Session, code: str, settle: int) -> None:
    for digit in code:
        if digit not in CODE_PAD:
            raise ValueError(f"friend code must be digits, got {digit!r}")
        x, y = CODE_PAD[digit]
        session.tap(x, y, settle)


def flush_save(session: Session) -> dict[str, Any]:
    """Force the cartridge save to disk and report whether it settled."""
    before = session.client.command("cart_save_info")
    flushed = session.client.command("cart_save_flush")
    after = session.client.command("cart_save_info")
    result = {
        "before": before,
        "flush": flushed,
        "after": after,
        "ok": bool(isinstance(flushed, dict) and flushed.get("ok")),
    }
    print(f"cart save flush: {json.dumps(result)}", flush=True)
    return result


def drive(args: argparse.Namespace, session: Session) -> dict[str, Any]:
    if args.inject_firmware is not None:
        input_lib.advance_to_vblank(session.client, 120)
        response = session.client.command(
            "firmware_replace", hex=args.inject_firmware.read_bytes().hex()
        )
        if not isinstance(response, dict) or not response.get("ok"):
            raise RuntimeError(f"firmware_replace failed: {response!r}")

    input_lib.advance_to_vblank(session.client, args.title_vblank)
    session.save("title")

    # MENU_PATH[:5] ends on the Friends and Rivals roster; the last step opens
    # Add Friend, which --verify-only deliberately skips so an existing roster
    # can be inspected without writing to it.
    for label, x, y, wait in MENU_PATH[: 5 if args.verify_only else len(MENU_PATH)]:
        session.tap_and_save(label, x, y, wait)

    if args.verify_only:
        for target in args.settle_targets:
            input_lib.advance_to_vblank(session.client, target)
            session.save(f"verify-{target}")
        return {
            "verify_only": True,
            "save_path": str(args.save_path),
            "cart_save": {"after": session.client.command("cart_save_info")},
            "steps": [
                {
                    "label": item["label"],
                    "vblank9": item["vblank9"],
                    "image": item["image"],
                    "signature": item["signature"],
                }
                for item in session.report
            ],
        }

    enter_code(session, args.code, args.key_settle)
    session.save("code-entered")

    session.tap_and_save("code-confirm", *CODE_CONFIRM, 900)

    # The confirmation dialog's centre check opens the name keyboard; a blank
    # name is rejected, so a temporary name is mandatory here.
    session.tap_and_save("name-keyboard", 128, 126, 600)

    type_name(session, args.name, args.key_settle)
    session.save("name-typed")

    session.tap_and_save("name-confirm", *NAME_CONFIRM, 1500)

    for target in args.settle_targets:
        input_lib.advance_to_vblank(session.client, target)
        session.save(f"settle-{target}")

    for step in range(args.exit_taps):
        session.tap_and_save(f"exit-{step}", *ROSTER_BACK, args.exit_wait)

    saved = flush_save(session)
    return {
        "code": args.code,
        "name": args.name,
        "save_path": str(args.save_path),
        "firmware_path": str(args.firmware_path) if args.firmware_path else None,
        "inject_firmware": (
            str(args.inject_firmware) if args.inject_firmware else None
        ),
        "cart_save": saved,
        "steps": [
            {
                "label": item["label"],
                "vblank9": item["vblank9"],
                "image": item["image"],
                "signature": item["signature"],
            }
            for item in session.report
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--bios", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--save-path", type=Path, required=True)
    parser.add_argument("--firmware-path", type=Path)
    parser.add_argument(
        "--inject-firmware",
        type=Path,
        help="Prepared profile firmware pushed in with firmware_replace.",
    )
    parser.add_argument(
        "--code", default="", help="12-digit friend code to register."
    )
    parser.add_argument(
        "--name", default="", help="Temporary friend name (keyboard entry)."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Open the roster and capture it without registering anything.",
    )
    parser.add_argument("--port", type=int, default=20450)
    parser.add_argument("--startup-mode", default="automatic")
    parser.add_argument("--network-backend", default="slirp")
    parser.add_argument("--wfc-provider", default="wiimmfi")
    parser.add_argument("--title-vblank", type=int, default=7800)
    parser.add_argument("--key-settle", type=int, default=18)
    parser.add_argument(
        "--settle-targets", type=int, nargs="*", default=[16000, 18000]
    )
    parser.add_argument(
        "--exit-taps",
        type=int,
        default=3,
        help="Back-arrow taps walked after entry so the game commits the save.",
    )
    parser.add_argument("--exit-wait", type=int, default=900)
    args = parser.parse_args()

    code = args.code.replace(" ", "").replace("-", "")
    if not args.verify_only:
        if len(code) != 12 or not code.isdigit():
            parser.error("--code must be 12 digits")
        if not args.name:
            parser.error("--name must not be empty")
    args.code = code

    for attribute in (
        "runner", "bios", "rom", "config", "save_path",
        "firmware_path", "inject_firmware",
    ):
        value = getattr(args, attribute)
        if value is not None:
            setattr(args, attribute, value.resolve())
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)

    process = launch(args)
    try:
        capture_lib.wait_for_server(args.port, process)
        client = capture_lib.DebugClient(args.port, timeout=1800)
        try:
            session = Session(client, args.out)
            summary = drive(args, session)
        finally:
            client.close()
        (args.out / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
