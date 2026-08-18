#!/usr/bin/env python3
"""Drive an interactive MPH instance and record live-shard transitions."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import capture_mph_checkpoints as capture_lib
import fuzz_mph_gameplay as input_lib


def wait_frames(
    client: capture_lib.DebugClient, frames: int, timeout: float
) -> dict[str, int]:
    start = input_lib.event_counts(client)["vblank9"]
    target = start + frames
    deadline = time.monotonic() + timeout
    previous = start
    last_progress = time.monotonic()
    while time.monotonic() < deadline:
        counts = input_lib.event_counts(client)
        current = counts["vblank9"]
        if current >= target:
            return counts
        if current != previous:
            previous = current
            last_progress = time.monotonic()
        elif time.monotonic() - last_progress > 15.0:
            raise RuntimeError(
                f"VBlank stopped at {current} while waiting for {target}"
            )
        time.sleep(0.025)
    raise TimeoutError(f"timed out at VBlank {previous}, wanted {target}")


def tap(
    client: capture_lib.DebugClient, x: int, y: int, hold_frames: int
) -> None:
    client.command("touch", x=x, y=y, down=True)
    wait_frames(client, hold_frames, 30.0)
    client.command("touch", x=x, y=y, down=False)


def press_key(
    client: capture_lib.DebugClient, key: str, hold_frames: int
) -> None:
    bit = input_lib.KEY_BITS[key]
    client.command("keys", mask=input_lib.RELEASED_KEYS & ~(1 << bit))
    wait_frames(client, hold_frames, 30.0)
    client.command("keys", mask=input_lib.RELEASED_KEYS)


def checkpoint(
    client: capture_lib.DebugClient,
    output: Path,
    index: int,
    label: str,
    started: float,
    blank_recovery_frames: int,
) -> dict[str, object]:
    counts = input_lib.event_counts(client)
    image = input_lib.combined_framebuffer(client)
    blank_start = counts["vblank9"]
    while True:
        luma = image.convert("L").tobytes()
        luma_mean = sum(luma) / len(luma)
        luma_min = min(luma)
        luma_max = max(luma)
        if not (luma_max - luma_min <= 1 and
                (luma_mean < 1.0 or luma_mean > 254.0)):
            break
        if counts["vblank9"] - blank_start >= blank_recovery_frames:
            break
        wait_frames(client, min(60, blank_recovery_frames), 30.0)
        counts = input_lib.event_counts(client)
        image = input_lib.combined_framebuffer(client)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label)
    filename = f"{index:04d}-{counts['vblank9']:06d}-{safe}.png"
    image.save(output / filename)
    pixels = image.tobytes()
    result = {
        "index": index,
        "label": label,
        "wall_seconds": time.monotonic() - started,
        "counts": counts,
        "live": client.command("live_overlay_status"),
        "static_coverage": client.command("static_coverage"),
        "frontend": client.command("frontend_stats"),
        "image": filename,
        "rgb_sha256": hashlib.sha256(pixels).hexdigest(),
        "luma_mean": luma_mean,
        "luma_min": luma_min,
        "luma_max": luma_max,
    }
    print(
        f"{index:04d} {label}: vblank={counts['vblank9']} "
        f"wall={result['wall_seconds']:.2f}s image={filename}",
        flush=True,
    )
    if luma_max - luma_min <= 1 and (luma_mean < 1.0 or luma_mean > 254.0):
        raise RuntimeError(
            f"blank framebuffer at {label}: luma={luma_mean:.2f}, "
            f"screenshot={filename}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=19842)
    parser.add_argument("--actions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--jitter", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0x4D5048)
    parser.add_argument("--hold-frames", type=int, default=12)
    parser.add_argument("--wait-timeout", type=float, default=180.0)
    parser.add_argument("--blank-recovery-frames", type=int, default=360,
                        help="fail only after a blank transition remains blank "
                             "for this many advancing VBlanks")
    parser.add_argument("--dispatch-misses", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.actions.read_text(encoding="utf-8"))
    actions = payload.get("actions", payload)
    if not isinstance(actions, list):
        parser.error("actions must be a list or an object containing one")

    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    client = capture_lib.DebugClient(args.port, timeout=30.0)
    started = time.monotonic()
    report: dict[str, object] = {
        "port": args.port,
        "actions": str(args.actions.resolve()),
        "jitter": args.jitter,
        "seed": args.seed,
        "checkpoints": [],
    }
    checkpoints = report["checkpoints"]
    assert isinstance(checkpoints, list)
    try:
        checkpoints.append(checkpoint(
            client, output, 0, "initial", started,
            args.blank_recovery_frames))
        for index, action in enumerate(actions, 1):
            kind = str(action.get("kind", ""))
            if kind == "wait":
                frames = int(action["frames"])
                wait_frames(client, frames, args.wait_timeout)
                label = f"wait-{frames}"
            elif kind == "touch":
                source_x = int(action["x"])
                source_y = int(action["y"])
                x = max(0, min(255, source_x + rng.randint(-args.jitter, args.jitter)))
                y = max(0, min(191, source_y + rng.randint(-args.jitter, args.jitter)))
                tap(client, x, y, args.hold_frames)
                label = f"touch-{source_x}-{source_y}-actual-{x}-{y}"
            elif kind == "key":
                key = str(action["key"]).lower()
                if key not in input_lib.KEY_BITS:
                    raise ValueError(f"unsupported key {key!r}")
                press_key(client, key, args.hold_frames)
                label = f"key-{key}"
            else:
                raise ValueError(f"unsupported action {action!r}")
            checkpoints.append(
                checkpoint(client, output, index, label, started,
                           args.blank_recovery_frames)
            )
            output.joinpath("report.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
            if args.dispatch_misses is not None and args.dispatch_misses.exists():
                if args.dispatch_misses.stat().st_size:
                    raise RuntimeError(
                        f"dispatch miss log became nonempty: {args.dispatch_misses}"
                    )
    finally:
        client.command("keys", mask=input_lib.RELEASED_KEYS)
        client.command("touch", x=0, y=0, down=False)
        client.close()

    report["wall_seconds"] = time.monotonic() - started
    output.joinpath("report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
