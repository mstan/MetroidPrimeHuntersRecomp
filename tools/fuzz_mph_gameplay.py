#!/usr/bin/env python3
"""Deterministically fuzz Prime Hunters input and preserve replayable traces."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
from pathlib import Path

from PIL import Image

import capture_mph_checkpoints as capture_lib


KEY_BITS = {
    "a": 0,
    "b": 1,
    "select": 2,
    "start": 3,
    "right": 4,
    "left": 5,
    "up": 6,
    "down": 7,
    "r": 8,
    "l": 9,
    "x": 10,
    "y": 11,
}
RELEASED_KEYS = 0x0FFF


def advance_to_vblank(
    client: capture_lib.DebugClient,
    target: int,
) -> dict[str, object]:
    previous = -1
    while True:
        response = client.command(
            "run_to_event",
            event="vblank9",
            count=target,
            stall=300_000,
            max_rounds=100_000_000,
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"invalid run_to_event response: {response!r}")
        if response.get("reached"):
            return response
        counts = response.get("counts")
        current = (
            int(counts.get("vblank9", -1))
            if isinstance(counts, dict)
            else -1
        )
        if response.get("terminal") or response.get("stalled"):
            raise RuntimeError(
                f"failed to reach VBlank {target}: {json.dumps(response)}"
            )
        if not response.get("exhausted") or current <= previous:
            raise RuntimeError(
                f"no progress toward VBlank {target}: {json.dumps(response)}"
            )
        previous = current


def event_counts(client: capture_lib.DebugClient) -> dict[str, int]:
    response = client.command("event_counts")
    if not isinstance(response, dict):
        raise RuntimeError(f"invalid event_counts response: {response!r}")
    return {key: int(value) for key, value in response.items()}


def advance_frames(
    client: capture_lib.DebugClient,
    count: int,
) -> dict[str, object]:
    current = event_counts(client)["vblank9"]
    return advance_to_vblank(client, current + count)


def combined_framebuffer(client: capture_lib.DebugClient) -> Image.Image:
    screens = [
        capture_lib.framebuffer(client, engine)
        for engine in ("A", "B")
    ]
    image = Image.new(
        "RGB",
        (
            max(screen.width for screen in screens),
            sum(screen.height for screen in screens),
        ),
    )
    y = 0
    for screen in screens:
        image.paste(screen, (0, y))
        y += screen.height
    return image


def frame_signature(image: Image.Image) -> str:
    reduced = image.convert("L").resize((32, 48), Image.Resampling.BILINEAR)
    return hashlib.sha256(reduced.tobytes()).hexdigest()


def save_checkpoint(
    client: capture_lib.DebugClient,
    output: Path,
    index: int,
    label: str,
) -> dict[str, object]:
    counts = event_counts(client)
    image = combined_framebuffer(client)
    safe_label = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in label
    ).strip("-")
    name = f"{index:04d}-{counts['vblank9']:05d}-{safe_label}.png"
    image.save(output / name)
    return {
        "index": index,
        "label": label,
        "vblank9": counts["vblank9"],
        "image": name,
        "signature": frame_signature(image),
        "rgb_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
        "counts": counts,
    }


def tap(
    client: capture_lib.DebugClient,
    x: int,
    y: int,
    hold_frames: int,
) -> None:
    client.command("touch", x=x, y=y, down=True)
    advance_frames(client, hold_frames)
    client.command("touch", x=x, y=y, down=False)


def press_key(
    client: capture_lib.DebugClient,
    key: str,
    hold_frames: int,
) -> None:
    client.command("keys", mask=RELEASED_KEYS & ~(1 << KEY_BITS[key]))
    advance_frames(client, hold_frames)
    client.command("keys", mask=RELEASED_KEYS)


def random_action(rng: random.Random) -> dict[str, object]:
    if rng.random() < 0.72:
        return {
            "kind": "touch",
            "x": rng.choice((24, 56, 88, 120, 152, 184, 216, 240)),
            "y": rng.choice((20, 44, 68, 92, 116, 140, 164, 184)),
        }
    return {
        "kind": "key",
        "key": rng.choice(
            ("a", "b", "start", "select", "up", "down", "left", "right", "x", "y")
        ),
    }


def load_actions(path: Path | None) -> list[dict[str, object]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("actions")
    if not isinstance(payload, list):
        raise ValueError("action trace must be a list or contain an actions list")
    return [dict(action) for action in payload]


def apply_action(
    client: capture_lib.DebugClient,
    action: dict[str, object],
    hold_frames: int,
) -> str:
    kind = str(action.get("kind"))
    if kind == "touch":
        x = int(action["x"])
        y = int(action["y"])
        tap(client, x, y, hold_frames)
        return f"touch-{x}-{y}"
    if kind == "key":
        key = str(action["key"]).lower()
        if key not in KEY_BITS:
            raise ValueError(f"unknown key: {key}")
        press_key(client, key, hold_frames)
        return f"key-{key}"
    if kind == "wait":
        frames = int(action["frames"])
        advance_frames(client, frames)
        return f"wait-{frames}"
    raise ValueError(f"unknown action kind: {kind}")


def launch(args: argparse.Namespace, output: Path) -> subprocess.Popen[bytes]:
    if args.runner is not None:
        executable = args.runner.resolve()
        command = [
            str(executable),
            str(args.bios.resolve()),
            "--serve",
            "--port",
            str(args.port),
            "--rom",
            str(args.rom.resolve()),
            "--config",
            str(args.config.resolve()),
            "--no-save",
            "--startup-mode",
            "automatic",
        ]
        if args.capture_static_coverage:
            command.append("--discover-static-misses")
    else:
        executable = args.oracle.resolve()
        firmware = output / "firmware-automatic.bin"
        capture_lib.automatic_firmware(
            args.bios.resolve() / "firmware.bin", firmware
        )
        command = [
            str(executable),
            "--bios9",
            str(args.bios.resolve() / "biosnds9.rom"),
            "--bios7",
            str(args.bios.resolve() / "biosnds7.rom"),
            "--firmware",
            str(firmware),
            "--rom",
            str(args.rom.resolve()),
            "--boot",
            "firmware",
            "--port",
            str(args.port),
        ]
    stdout = (output / "runner.stdout.log").open("wb")
    stderr = (output / "runner.stderr.log").open("wb")
    process = subprocess.Popen(
        command,
        cwd=executable.parent,
        stdout=stdout,
        stderr=stderr,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    process._mph_logs = (stdout, stderr)  # type: ignore[attr-defined]
    return process


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    backend = parser.add_mutually_exclusive_group(required=True)
    backend.add_argument("--runner", type=Path)
    backend.add_argument("--oracle", type=Path)
    parser.add_argument("--bios", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=19860)
    parser.add_argument("--seed", type=int, default=0x4D5048)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--actions", type=Path)
    parser.add_argument("--start-vblank", type=int, default=7800)
    parser.add_argument("--hold-frames", type=int, default=3)
    parser.add_argument("--settle-frames", type=int, default=45)
    parser.add_argument("--post-start-frames", type=int, default=180)
    parser.add_argument("--skip-start-tap", action="store_true")
    parser.add_argument("--capture-static-coverage", action="store_true")
    args = parser.parse_args()
    if args.runner is not None and args.config is None:
        parser.error("--config is required with --runner")

    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    replay_actions = load_actions(args.actions)
    actions = replay_actions + [
        random_action(rng) for _ in range(args.steps)
    ]

    process = launch(args, output)
    trace: dict[str, object] = {
        "seed": args.seed,
        "backend": "native" if args.runner is not None else "oracle",
        "start_vblank": args.start_vblank,
        "actions": [],
        "checkpoints": [],
    }
    try:
        capture_lib.wait_for_server(args.port, process)
        client = capture_lib.DebugClient(args.port, timeout=1800.0)
        try:
            client.command("reset")
            advance_to_vblank(client, args.start_vblank)
            checkpoints = trace["checkpoints"]
            assert isinstance(checkpoints, list)
            checkpoints.append(
                save_checkpoint(client, output, 0, "title-before-input")
            )
            if not args.skip_start_tap:
                tap(client, 128, 96, args.hold_frames)
                advance_frames(client, args.post_start_frames)
                checkpoints.append(
                    save_checkpoint(client, output, 1, "after-title-tap")
                )

            action_log = trace["actions"]
            assert isinstance(action_log, list)
            for index, action in enumerate(actions, 1):
                label = apply_action(client, action, args.hold_frames)
                advance_frames(client, args.settle_frames)
                checkpoint = save_checkpoint(
                    client, output, index + 1, label
                )
                record = dict(action)
                record.update(
                    {
                        "index": index,
                        "label": label,
                        "checkpoint": checkpoint,
                    }
                )
                action_log.append(record)
                (output / "trace.json").write_text(
                    json.dumps(trace, indent=2) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                print(
                    f"[{index}/{len(actions)}] {label} "
                    f"vblank={checkpoint['vblank9']} "
                    f"signature={str(checkpoint['signature'])[:12]}",
                    flush=True,
                )
            if args.runner is not None and args.capture_static_coverage:
                trace["static_coverage"] = client.command("static_coverage")
                trace["tier3_coverage"] = client.command(
                    "tier3_coverage", max=262_144
                )
            (output / "trace.json").write_text(
                json.dumps(trace, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        finally:
            client.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        logs = getattr(process, "_mph_logs", ())
        for log in logs:
            log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
