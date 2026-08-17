#!/usr/bin/env python3
"""Run a route and report which overlays it exercised.

beads-yjp.31. The measurement loop: cold boot -> replay a scenario -> dump the
Tier-3 coverage manifest over TCP -> map it onto the overlay table.

The manifest dump is a debug command rather than an exit-path write because
--serve never exits its accept loop, so a harness-killed session would
otherwise lose everything it recorded. Dumping on demand also means a route
can be sampled part-way through instead of only at the end.

Screenshots are captured at every step so a route can be checked visually and
so new screen predicates can be measured from real frames.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

KEY_BITS = {
    "a": 0, "b": 1, "select": 2, "start": 3, "right": 4, "left": 5,
    "up": 6, "down": 7, "r": 8, "l": 9, "x": 10, "y": 11,
}
# Active-low, and the server's own default of 0x3FF would leave X and Y held.
RELEASED = 0x0FFF


class DebugClient:
    def __init__(self, port: int, timeout: float = 1800.0) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.buf = b""

    def cmd(self, name: str, **args: object) -> dict:
        args["cmd"] = name
        self.sock.sendall((json.dumps(args) + "\n").encode())
        while b"\n" not in self.buf:
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                raise RuntimeError("debug server closed the connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        reply = json.loads(line)
        if isinstance(reply, dict) and "error" in reply:
            raise RuntimeError(f"{name}: {reply['error']}")
        return reply

    def vblank(self) -> int:
        return int(self.cmd("event_counts")["vblank9"])

    def advance_to(self, target: int) -> None:
        """Advance to an absolute vblank, resuming when the round budget runs out.

        run_to_event caps at max_rounds and returns exhausted=True having gone
        only part way -- reaching the title screen alone needs more than the
        50M default. Not resuming silently under-ran every route: the boot
        stopped at vblank 6461 instead of 7800 and every subsequent tap landed
        at the wrong moment, which looked exactly like a regression in the
        build under test. It was not; all builds stop at the same vblank.
        """
        for _ in range(200):
            reply = self.cmd("run_to_event", event="vblank9", count=target,
                             max_rounds=50_000_000)
            if reply.get("terminal"):
                raise RuntimeError(f"runner halted: {reply.get('reason9')} / "
                                   f"{reply.get('reason7')}")
            if reply.get("stalled"):
                raise RuntimeError(f"stalled before vblank9 {target}")
            if self.vblank() >= target:
                return
        raise RuntimeError(f"could not reach vblank9 {target}")

    def advance(self, frames: int) -> None:
        self.advance_to(self.vblank() + frames)

    def tap(self, x: int, y: int, hold: int) -> None:
        self.cmd("touch", x=x, y=y, down=True)
        self.advance(hold)
        self.cmd("touch", x=0, y=0, down=False)

    def press(self, key: str, hold: int) -> None:
        bit = KEY_BITS[key]
        self.cmd("keys", mask=RELEASED & ~(1 << bit))
        self.advance(hold)
        self.cmd("keys", mask=RELEASED)

    def screenshot(self, path: Path) -> None:
        try:
            from PIL import Image
        except ImportError:
            return
        frames = []
        for engine in ("A", "B"):
            fb = self.cmd("framebuffer", engine=engine)
            raw = bytes.fromhex(fb["rgb"])
            frames.append(Image.frombytes("RGB", (fb["w"], fb["h"]), raw))
        combined = Image.new("RGB", (frames[0].width,
                                     frames[0].height + frames[1].height))
        combined.paste(frames[0], (0, 0))
        combined.paste(frames[1], (0, frames[0].height))
        combined.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--bios", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--actions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--overlays", type=Path,
                        default=Path("generated/inputs/overlays.json"))
    parser.add_argument("--port", type=int, default=19890)
    parser.add_argument("--start-vblank", type=int, default=7800)
    parser.add_argument("--hold-frames", type=int, default=3)
    parser.add_argument("--settle-frames", type=int, default=45)
    parser.add_argument("--play-frames", type=int, default=0,
                        help="hold forward this many frames after the route")
    parser.add_argument("--no-shots", action="store_true")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    actions = json.loads(args.actions.read_text(encoding="utf-8"))
    if isinstance(actions, dict):
        actions = actions.get("actions", [])

    proc = subprocess.Popen(
        [str(args.runner), str(args.bios), "--serve", "--port", str(args.port),
         "--rom", str(args.rom.resolve()), "--config", str(args.config.resolve()),
         "--no-save", "--startup-mode", "automatic"],
        cwd=str(args.runner.parent),
        stdout=(args.out / "runner.stdout.log").open("wb"),
        stderr=(args.out / "runner.stderr.log").open("wb"))
    print(f"runner pid={proc.pid} port={args.port}")

    try:
        client = None
        for _ in range(240):
            if proc.poll() is not None:
                raise SystemExit(f"runner exited early rc={proc.returncode}")
            try:
                client = DebugClient(args.port)
                break
            except OSError:
                time.sleep(0.5)
        if client is None:
            raise SystemExit("debug server never came up")

        client.cmd("reset")
        target = args.start_vblank
        client.advance_to(target)
        if not args.no_shots:
            client.screenshot(args.out / f"0000-{target:05d}-title.png")
        client.tap(128, 96, args.hold_frames)
        client.advance(180)

        for index, action in enumerate(actions, 1):
            kind = action["kind"]
            if kind == "touch":
                client.tap(int(action["x"]), int(action["y"]), args.hold_frames)
                label = f"touch-{action['x']}-{action['y']}"
            elif kind == "key":
                client.press(str(action["key"]), args.hold_frames)
                label = f"key-{action['key']}"
            elif kind == "wait":
                client.advance(int(action["frames"]))
                label = f"wait-{action['frames']}"
            else:
                raise SystemExit(f"unknown action kind {kind!r}")
            client.advance(args.settle_frames)
            if not args.no_shots:
                client.screenshot(
                    args.out / f"{index:04d}-{client.vblank():05d}-{label}.png")
            print(f"[{index}/{len(actions)}] {label}")

        if args.play_frames:
            # Hold forward. Press-and-hold is state plus time advance; there is
            # no hold-for-N command.
            client.cmd("keys", mask=RELEASED & ~(1 << KEY_BITS["up"]))
            client.advance(args.play_frames)
            client.cmd("keys", mask=RELEASED)
            if not args.no_shots:
                client.screenshot(args.out / "9998-after-walk.png")
            print(f"held forward {args.play_frames} frames")

        print("static_coverage:", json.dumps(client.cmd("static_coverage")))
        manifest = (args.out / "coverage.json").resolve()
        res = client.cmd("coverage_manifest", path=manifest.as_posix())
        print("coverage_manifest:", json.dumps(res))
        print(f"\nmanifest: {manifest}")
        print("now run:")
        print(f"  py -3 tools/overlay_coverage_report.py {manifest} "
              f"--overlays {args.overlays}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        print(f"stopped pid={proc.pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
