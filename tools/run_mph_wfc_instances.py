#!/usr/bin/env python3
"""Drive multiple Metroid Prime Hunters instances into Wiimmfi matchmaking.

This is an exploratory M7/M8 tool. Its output can contain real console/network
identifiers in ring metadata and screenshots; keep it under scratch/.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent / "tools"))

import capture_mph_checkpoints as capture_lib  # noqa: E402
import fuzz_mph_gameplay as input_lib  # noqa: E402


FILTERS = (
    "dhcp",
    "dns_query",
    "dns_response",
    "tcp_open",
    "tcp_packet",
    "tls_record",
    "udp_packet",
    "backend_error",
    "backend_drop",
)


@dataclass
class Instance:
    index: int
    port: int
    output: Path
    save_path: Path
    firmware_path: Path | None
    inject_firmware_path: Path | None
    process: subprocess.Popen[bytes]
    client: capture_lib.DebugClient | None = None
    report: list[dict[str, Any]] | None = None


def launch_instance(
    args: argparse.Namespace,
    index: int,
    save_path: Path,
    firmware_path: Path | None,
    inject_firmware_path: Path | None,
) -> Instance:
    output = args.out / f"instance{index}"
    output.mkdir(parents=True, exist_ok=True)
    command = [
        str(args.runner),
        str(args.bios),
        "--serve",
        "--port",
        str(args.base_port + index),
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
        str(0 if args.inject_profiles else index),
        "--save-path",
        str(save_path),
    ]
    if firmware_path:
        command.extend(["--firmware-path", str(firmware_path)])

    stdout = (output / "runner.stdout.log").open("wb")
    stderr = (output / "runner.stderr.log").open("wb")
    try:
        process = subprocess.Popen(
            command,
            cwd=args.runner.parent,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        stdout.close()
        stderr.close()
    return Instance(
        index=index,
        port=args.base_port + index,
        output=output,
        save_path=save_path,
        firmware_path=firmware_path,
        inject_firmware_path=inject_firmware_path,
        process=process,
        report=[],
    )


def ring_count(item: dict[str, Any], kind: str) -> int:
    ring = item.get("ring", {}).get(kind, {})
    events = ring.get("events", []) if isinstance(ring, dict) else []
    return len(events)


def save_checkpoint(instance: Instance, label: str) -> dict[str, Any]:
    if instance.client is None or instance.report is None:
        raise RuntimeError("instance is not connected")
    item = input_lib.save_checkpoint(
        instance.client, instance.output, len(instance.report), label
    )
    item["port"] = instance.port
    item["save_path"] = str(instance.save_path)
    item["firmware_path"] = str(instance.firmware_path) if instance.firmware_path else None
    item["inject_firmware_path"] = (
        str(instance.inject_firmware_path) if instance.inject_firmware_path else None
    )
    item["net_state"] = instance.client.command("net_state")
    item["ring"] = {
        name: instance.client.command("net_ring_dump", max=256, filter=name)
        for name in FILTERS
    }
    instance.report.append(item)
    return item


def summarize_instance(instance: Instance) -> dict[str, Any]:
    report = instance.report or []
    steps = [
        {
            "label": item["label"],
            "vblank9": item["vblank9"],
            "image": item["image"],
            "counts": {name: ring_count(item, name) for name in FILTERS},
        }
        for item in report
    ]
    max_counts = {
        name: max((step["counts"][name] for step in steps), default=0)
        for name in FILTERS
    }
    network_reached = (
        max_counts["dhcp"] > 0
        and max_counts["dns_query"] > 0
        and max_counts["tcp_open"] > 0
    )
    backend_clean = max_counts["backend_error"] == 0 and max_counts["backend_drop"] == 0
    return {
        "instance": instance.index,
        "port": instance.port,
        "save_path": str(instance.save_path),
        "firmware_path": str(instance.firmware_path) if instance.firmware_path else None,
        "inject_firmware_path": (
            str(instance.inject_firmware_path) if instance.inject_firmware_path else None
        ),
        "network_reached": network_reached,
        "tls_reached": max_counts["tls_record"] > 0,
        "backend_clean": backend_clean,
        "max_counts": max_counts,
        "final_label": steps[-1]["label"] if steps else None,
        "final_vblank9": steps[-1]["vblank9"] if steps else None,
        "steps": steps,
    }


def for_each(
    instances: list[Instance],
    action: Callable[[Instance], Any],
    workers: int,
) -> list[Any]:
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(action, instance) for instance in instances]
        return [future.result() for future in futures]


def tap_and_wait(instance: Instance, label: str, x: int, y: int, wait: int) -> None:
    assert instance.client is not None
    input_lib.tap(instance.client, x, y, 12)
    input_lib.advance_frames(instance.client, wait)
    save_checkpoint(instance, label)


def advance_to(instance: Instance, target: int) -> None:
    assert instance.client is not None
    input_lib.advance_to_vblank(instance.client, target)
    save_checkpoint(instance, f"wait-{target}")


def drive(args: argparse.Namespace, instances: list[Instance]) -> dict[str, Any]:
    for_each(
        instances,
        lambda instance: capture_lib.wait_for_server(instance.port, instance.process),
        args.instances,
    )
    for instance in instances:
        instance.client = capture_lib.DebugClient(instance.port, timeout=1800)

    if args.inject_profiles:
        def inject(instance: Instance) -> None:
            assert instance.client is not None
            if instance.inject_firmware_path is None:
                raise RuntimeError("missing firmware image for injection")
            input_lib.advance_to_vblank(instance.client, 120)
            response = instance.client.command(
                "firmware_replace",
                hex=instance.inject_firmware_path.read_bytes().hex(),
            )
            if not isinstance(response, dict) or not response.get("ok"):
                raise RuntimeError(f"firmware_replace failed: {response!r}")

        for_each(instances, inject, args.instances)

    def title(instance: Instance) -> None:
        assert instance.client is not None
        input_lib.advance_to_vblank(instance.client, 7800)
        save_checkpoint(instance, "title")

    for_each(instances, title, args.instances)
    for label, x, y, wait in (
        ("main-menu", 84, 92, 180),
        ("nickname-dialog", 168, 92, 180),
        ("multiplayer-menu", 128, 126, 240),
        ("wfc-menu", 198, 92, 360),
        ("find-game", 58, 96, 1200),
        ("find-game-confirm", 189, 125, 900),
        ("find-game-yes", 108, 124, 1200),
    ):
        for_each(
            instances,
            lambda instance, label=label, x=x, y=y, wait=wait: tap_and_wait(
                instance, label, x, y, wait
            ),
            args.instances,
        )

    for target in (13000, 16000, 22000):
        for_each(instances, lambda instance, target=target: advance_to(instance, target), args.instances)

    if args.fresh_profiles:
        for_each(
            instances,
            lambda instance: tap_and_wait(instance, "ack-wfc-id", 178, 171, 900),
            args.instances,
        )
        for_each(
            instances,
            lambda instance: tap_and_wait(instance, "post-id-connect", 108, 124, 4200),
            args.instances,
        )

    for_each(
        instances,
        lambda instance: tap_and_wait(instance, "search-for-game", 178, 171, 1200),
        args.instances,
    )

    for target in args.targets:
        for_each(instances, lambda instance, target=target: advance_to(instance, target), args.instances)

    summaries = [summarize_instance(instance) for instance in instances]
    return {
        "instances": args.instances,
        "network_backend": args.network_backend,
        "wfc_provider": args.wfc_provider,
        "summaries": summaries,
        "backend_clean": all(summary["backend_clean"] for summary in summaries),
    }


def prepare_saves(args: argparse.Namespace) -> list[Path]:
    if args.profile_dir is not None:
        return [
            (args.profile_dir / f"mph_instance{index}.sav").resolve()
            for index in range(args.instances)
        ]
    profile_dir = args.out / "profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    save_paths = []
    for index in range(args.instances):
        destination = profile_dir / f"mph_instance{index}.sav"
        if args.reuse_saves and destination.exists():
            pass
        else:
            shutil.copyfile(args.save_source, destination)
        save_paths.append(destination.resolve())
    return save_paths


def prepare_firmware(args: argparse.Namespace) -> list[Path | None]:
    if args.profile_dir is not None:
        return [
            (args.profile_dir / f"mph_instance{index}.firmware.bin").resolve()
            for index in range(args.instances)
        ]
    if args.firmware_path is None:
        return [None for _ in range(args.instances)]
    profile_dir = args.out / "profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    firmware_paths: list[Path | None] = []
    for index in range(args.instances):
        destination = profile_dir / f"mph_instance{index}.firmware.bin"
        if args.reuse_saves and destination.exists():
            pass
        else:
            shutil.copyfile(args.firmware_path, destination)
        firmware_paths.append(destination.resolve())
    return firmware_paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runner",
        type=Path,
        default=Path(r"F:\Projects\ndsrecomp\ndsrecomp\runner\build-mph-release\nds_runner.exe"),
    )
    parser.add_argument(
        "--bios",
        type=Path,
        default=Path(r"F:\Projects\ndsrecomp\ndsrecomp\bios"),
    )
    parser.add_argument("--rom", type=Path, default=Path("Metroid Prime Hunters.nds"))
    parser.add_argument("--config", type=Path, default=Path("game.toml"))
    parser.add_argument("--save-source", type=Path, required=True)
    parser.add_argument("--firmware-path", type=Path)
    parser.add_argument("--profile-dir", type=Path)
    parser.add_argument("--inject-profiles", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-port", type=int, default=20020)
    parser.add_argument("--instances", type=int, default=4)
    parser.add_argument("--reuse-saves", action="store_true")
    parser.add_argument("--fresh-profiles", action="store_true")
    parser.add_argument(
        "--startup-mode",
        choices=("preserve", "manual", "automatic"),
        default="automatic",
    )
    parser.add_argument(
        "--network-backend",
        choices=("slirp", "pcap"),
        default="slirp",
    )
    parser.add_argument("--wfc-provider", default="wiimmfi")
    parser.add_argument(
        "--targets",
        type=int,
        nargs="+",
        default=[25000, 30000, 45000, 60000],
    )
    args = parser.parse_args()

    if args.instances < 1 or args.instances > 8:
        parser.error("--instances must be in 1..8")
    if args.base_port < 1 or args.base_port + args.instances - 1 > 65535:
        parser.error("--base-port range must fit in 1..65535")

    args.runner = args.runner.resolve()
    args.bios = args.bios.resolve()
    args.rom = args.rom.resolve()
    args.config = args.config.resolve()
    args.save_source = args.save_source.resolve()
    args.firmware_path = args.firmware_path.resolve() if args.firmware_path else None
    args.profile_dir = args.profile_dir.resolve() if args.profile_dir else None
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)

    save_paths = prepare_saves(args)
    firmware_paths = prepare_firmware(args)
    if args.inject_profiles and args.firmware_path is None:
        parser.error("--inject-profiles requires --firmware-path as boot firmware")
    instances = [
        launch_instance(
            args,
            index,
            save_paths[index],
            args.firmware_path if args.inject_profiles else firmware_paths[index],
            firmware_paths[index] if args.inject_profiles else None,
        )
        for index in range(args.instances)
    ]
    try:
        summary = drive(args, instances)
        for instance in instances:
            if instance.report is not None:
                (instance.output / "report.json").write_text(
                    json.dumps(instance.report, indent=2) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
        (args.out / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps(summary, indent=2), flush=True)
        return 0 if summary["backend_clean"] else 1
    finally:
        for instance in instances:
            if instance.client is not None:
                instance.client.close()
            instance.process.terminate()
        for instance in instances:
            try:
                instance.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                instance.process.kill()
                instance.process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
