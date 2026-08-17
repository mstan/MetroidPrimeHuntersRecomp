#!/usr/bin/env python3
"""Benchmark MPH intro/FMV windows in the real interactive frontend."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import tomllib
from pathlib import Path

import capture_mph_checkpoints as capture_lib
from mph_profile import (
    DEFAULT_PROFILE_FILE,
    DEFAULT_VERSION,
    load_profile,
    resolve_repo_path,
    verify_rom_identity,
)


DEFAULT_TARGETS = [600, 1200, 1800, 2400, 3000, 3600, 4200]


def frontend_stats(client: capture_lib.DebugClient) -> dict[str, int]:
    response = client.command("frontend_stats")
    if not isinstance(response, dict):
        raise RuntimeError(f"invalid frontend_stats response: {response!r}")
    return {key: int(value) for key, value in response.items()}


def event_counts(client: capture_lib.DebugClient) -> dict[str, int]:
    response = client.command("event_counts")
    if not isinstance(response, dict):
        raise RuntimeError(f"invalid event_counts response: {response!r}")
    return {key: int(value) for key, value in response.items()}


def sample(
    client: capture_lib.DebugClient, *, instrument: bool
) -> dict[str, object]:
    result: dict[str, object] = {
        "counts": event_counts(client),
        "frontend": frontend_stats(client),
    }
    if instrument:
        result.update({
            "static_coverage": client.command("static_coverage"),
            "dispatch": client.command("dispatch_stats"),
            "profile": client.command("profile"),
        })
    return result


def phase(previous: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    before = previous["frontend"]
    after = current["frontend"]
    assert isinstance(before, dict) and isinstance(after, dict)
    frequency = int(after["freq"])
    frames = int(after["frames"]) - int(before["frames"])
    wall_ticks = int(after["now_ticks"]) - int(before["now_ticks"])
    seconds = wall_ticks / frequency if frequency else 0.0

    def milliseconds_per_frame(field: str) -> float:
        ticks = int(after[field]) - int(before[field])
        return (ticks * 1000.0 / frequency / frames) if frequency and frames else 0.0

    return {
        "from_vblank": int(previous["counts"]["vblank9"]),
        "to_vblank": int(current["counts"]["vblank9"]),
        "frames": frames,
        "seconds": seconds,
        "fps": frames / seconds if seconds else 0.0,
        "ms_per_frame": {
            "emu": milliseconds_per_frame("emu_ticks"),
            "present": milliseconds_per_frame("present_ticks"),
            "adaptive": milliseconds_per_frame("adaptive_ticks"),
            "upload": milliseconds_per_frame("upload_ticks"),
            "draw": milliseconds_per_frame("draw_ticks"),
            "swap": milliseconds_per_frame("swap_ticks"),
            "drain": milliseconds_per_frame("drain_ticks"),
        },
        "underruns": int(after["underruns"]) - int(before["underruns"]),
    }


def verify_config(path: Path, profile: dict[str, object], version: str) -> None:
    try:
        with path.open("rb") as f:
            document = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"unable to read game config {path}: {exc}") from exc
    game = document.get("game")
    if not isinstance(game, dict):
        raise SystemExit(f"game config has no [game] table: {path}")
    expected = {
        "id": profile["game_code"],
        "revision": profile["revision"],
        "rom_size": profile["rom_size"],
        "sha1": profile["sha1"],
    }
    for key, value in expected.items():
        if game.get(key) != value:
            raise SystemExit(
                f"game config {path} game.{key}={game.get(key)!r}; "
                f"expected {value!r} for {version}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--bios", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--profiles",
        type=Path,
        default=DEFAULT_PROFILE_FILE,
        help=f"ROM profile registry (default: {DEFAULT_PROFILE_FILE})",
    )
    parser.add_argument("--port", type=int, default=19873)
    parser.add_argument("--targets", type=int, nargs="+", default=DEFAULT_TARGETS)
    parser.add_argument(
        "--instrument", action="store_true",
        help="collect scheduler/GPU/dispatch attribution at each boundary",
    )
    parser.add_argument("--discover-static-misses", action="store_true")
    parser.add_argument(
        "--capture-runtime", type=Path,
        help="save final ITCM+main-RAM image for a content-validated bank",
    )
    parser.add_argument(
        "--rip-sampler", type=Path,
        help="optional windows_rip_sampler.exe for one target interval",
    )
    parser.add_argument("--rip-from", type=int)
    parser.add_argument("--rip-to", type=int)
    parser.add_argument("--rip-interval-us", type=int, default=1000)
    parser.add_argument(
        "--adaptive",
        choices=("auto", "none", "top"),
        default="auto",
        help="auto follows the selected ROM profile's validated policy",
    )
    parser.add_argument("--supersampling", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument("--antialiasing", type=int, choices=(0, 2, 4, 8), default=0)
    parser.add_argument(
        "--direct-present", choices=("auto", "on", "off"), default="auto",
        help="override the compute renderer's visible top-screen presenter",
    )
    args = parser.parse_args()

    profile = load_profile(args.profiles.resolve(), args.version)
    rom_path = args.rom.resolve()
    rom_sha1 = verify_rom_identity(rom_path, profile, args.version)
    config_path = (
        args.config.resolve()
        if args.config is not None
        else resolve_repo_path(str(profile["game_config"])).resolve()
    )
    verify_config(config_path, profile, args.version)

    profile_adaptive = bool(profile["adaptive_widescreen"])
    if args.adaptive == "top" and not profile_adaptive:
        raise SystemExit(
            f"{args.version} does not have validated Adaptive Widescreen; "
            "refusing an FMV/coverage capture with --adaptive top"
        )
    adaptive = args.adaptive
    if adaptive == "auto":
        adaptive = "top" if profile_adaptive else "none"

    targets = sorted(set(args.targets))
    if not targets or targets[0] <= 0:
        parser.error("targets must contain positive VBlank counts")
    if args.rip_sampler is not None:
        if args.rip_from not in targets or args.rip_to not in targets:
            parser.error("--rip-from and --rip-to must both be target boundaries")
        if args.rip_from >= args.rip_to:
            parser.error("--rip-from must precede --rip-to")

    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    executable = args.runner.resolve()
    command = [
        str(executable),
        str(args.bios.resolve()),
        "--interactive",
        "--port",
        str(args.port),
        "--rom",
        str(rom_path),
        "--config",
        str(config_path),
        "--no-save",
        "--startup-mode",
        "automatic",
        "--screen-layout",
        "separate",
        "--adaptive-widescreen",
        adaptive,
        "--supersampling",
        str(args.supersampling),
        "--antialiasing",
        str(args.antialiasing),
    ]
    if args.discover_static_misses:
        command.append("--discover-static-misses")

    environment = os.environ.copy()
    environment["PATH"] = r"C:\msys64\mingw64\bin;" + environment.get("PATH", "")
    environment["NDS_FRONTEND_STATS"] = "1"
    if args.direct_present != "auto":
        environment["NDS_COMPUTE_DIRECT_PRESENT"] = (
            "1" if args.direct_present == "on" else "0"
        )
    if args.instrument:
        environment["NDS_PROFILE_GPU"] = "1"
        environment["NDS_PROFILE_SCHED"] = "1"

    stdout = (output / "runner.stdout.log").open("wb")
    stderr = (output / "runner.stderr.log").open("wb")
    process = subprocess.Popen(
        command,
        cwd=executable.parent,
        env=environment,
        stdout=stdout,
        stderr=stderr,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    report: dict[str, object] = {
        "mph_profile": args.version,
        "rom_sha1": rom_sha1,
        "display_name": profile["display_name"],
        "config": str(config_path),
        "adaptive": adaptive,
        "command": command,
        "targets": targets,
        "samples": [],
        "phases": [],
    }
    client: capture_lib.DebugClient | None = None
    sampler: subprocess.Popen[str] | None = None
    try:
        capture_lib.wait_for_server(args.port, process)
        client = capture_lib.DebugClient(args.port, timeout=30.0)
        first = sample(client, instrument=args.instrument)
        samples = report["samples"]
        phases = report["phases"]
        assert isinstance(samples, list) and isinstance(phases, list)
        samples.append(first)
        previous = first
        for target in targets:
            while True:
                counts = event_counts(client)
                if counts["vblank9"] >= target:
                    break
                if process.poll() is not None:
                    raise RuntimeError(
                        f"runner exited early with {process.returncode}"
                    )
                time.sleep(0.025)
            current = sample(client, instrument=args.instrument)
            samples.append(current)
            measured = phase(previous, current)
            measured["target_vblank"] = target
            phases.append(measured)
            print(
                f"vblank {measured['from_vblank']}..{measured['to_vblank']}: "
                f"{measured['fps']:.2f} fps, "
                f"emu={measured['ms_per_frame']['emu']:.2f} ms/frame, "
                f"present={measured['ms_per_frame']['present']:.2f} ms/frame, "
                f"underruns={measured['underruns']}",
                flush=True,
            )
            if args.rip_sampler is not None and target == args.rip_from:
                samples_path = output / "rip-samples.csv"
                sampler = subprocess.Popen(
                    [
                        str(args.rip_sampler.resolve()),
                        str(process.pid),
                        str(samples_path),
                        str(args.rip_interval_us),
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            if sampler is not None and target == args.rip_to:
                assert sampler.stdin is not None
                sampler.stdin.write("\n")
                sampler.stdin.flush()
                sampler_stdout, sampler_stderr = sampler.communicate(timeout=30)
                if sampler.returncode:
                    raise RuntimeError(
                        f"RIP sampler failed: {sampler_stdout}\n{sampler_stderr}"
                    )
                sampler = None
            previous = current
            output.joinpath("benchmark.json").write_text(
                json.dumps(report, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )

        if args.discover_static_misses:
            report["tier3_coverage"] = client.command(
                "tier3_coverage", max=262_144
            )
        if args.capture_runtime is not None:
            destination = args.capture_runtime.resolve()
            itcm_response = client.command("read_region", region="itcm")
            ram_response = client.command("read_region", region="mainram")
            assert isinstance(itcm_response, dict)
            assert isinstance(ram_response, dict)
            image = bytes.fromhex(str(itcm_response["hex"]))
            image += bytes.fromhex(str(ram_response["hex"]))
            if len(image) != 0x00408000:
                raise RuntimeError(
                    f"unexpected runtime image size 0x{len(image):X}"
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(image)
            report["runtime_capture"] = {
                "path": str(destination),
                "sha1": hashlib.sha1(image).hexdigest(),
                "bytes": len(image),
            }
        client.command("frontend_exit")
    finally:
        if sampler is not None and sampler.poll() is None:
            if sampler.stdin is not None:
                sampler.stdin.write("\n")
                sampler.stdin.flush()
            sampler.wait(timeout=10)
        if client is not None:
            client.close()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        stdout.close()
        stderr.close()

    report["returncode"] = process.returncode
    output.joinpath("benchmark.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return process.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
