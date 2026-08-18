#!/usr/bin/env python3
"""Drive Metroid Prime Hunters through Nintendo WFC paths.

This is a title-specific M8 probe. It can stop at the standard Nintendo WFC
setup connection test, enter Find Game, or tap through to the one-instance
matchmaking search screen. It can also enter the Friends and Rivals branch for
manual/path exploration.
The output directory can contain real console/network identifiers in ring
events and screenshots; keep it under scratch/ and do not publish it raw.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent / "tools"))

import capture_mph_checkpoints as capture_lib  # noqa: E402
import fuzz_mph_gameplay as input_lib  # noqa: E402


DEFAULT_FILTERS = (
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


def save_checkpoint(
    client: capture_lib.DebugClient,
    output: Path,
    report: list[dict[str, Any]],
    label: str,
    filters: tuple[str, ...],
) -> None:
    item = input_lib.save_checkpoint(client, output, len(report), label)
    item["net_state"] = client.command("net_state")
    try:
        item["net_progress"] = client.command("net_progress")
    except RuntimeError:
        item["net_progress"] = {"counts": {}}
    item["ring"] = {
        name: client.command("net_ring_dump", max=256, filter=name)
        for name in filters
    }
    report.append(item)


def ring_count(item: dict[str, Any], kind: str) -> int:
    ring = item.get("ring", {}).get(kind, {})
    events = ring.get("events", []) if isinstance(ring, dict) else []
    return len(events)


def event_counts_for_item(item: dict[str, Any]) -> dict[str, int]:
    progress = item.get("net_progress", {})
    if isinstance(progress, dict):
        raw = progress.get("counts", {})
        if isinstance(raw, dict):
            return {str(name): int(value) for name, value in raw.items()}
    return {name: ring_count(item, name) for name in DEFAULT_FILTERS}


def wait_for_connection(
    client: capture_lib.DebugClient,
    *,
    require_tls: bool,
    timeout_s: float,
    stall_s: float,
) -> dict[str, int]:
    end = time.monotonic() + timeout_s
    last_progress = time.monotonic()
    last_total = 0
    while time.monotonic() < end:
        progress = client.command("net_progress")
        counts_raw = progress.get("counts", {})
        if not isinstance(counts_raw, dict):
            raise RuntimeError("net_progress returned malformed payload")
        counts = {str(kind): int(value) for kind, value in counts_raw.items()}

        if counts.get("backend_error", 0) > 0:
            raise RuntimeError(f"backend_error during test-connection: {counts}")
        if counts.get("backend_drop", 0) > 0:
            raise RuntimeError(f"backend_drop during test-connection: {counts}")

        if (
            counts.get("dhcp", 0) > 0
            and counts.get("dns_query", 0) > 0
            and counts.get("tcp_open", 0) > 0
            and (counts.get("tls_record", 0) > 0 if require_tls else True)
        ):
            return counts

        total = sum(counts.values())
        if total != last_total:
            last_total = total
            last_progress = time.monotonic()
        elif time.monotonic() - last_progress >= stall_s:
            raise TimeoutError(f"connection progress stalled: {counts}")
        time.sleep(0.25)
    raise TimeoutError(f"connection test timed out: {counts}")


def summarize(
    report: list[dict[str, Any]],
    filters: tuple[str, ...],
    flow: str,
) -> dict[str, Any]:
    steps = []
    for item in report:
        steps.append({
            "label": item["label"],
            "vblank9": item["vblank9"],
            "image": item["image"],
            "counts": event_counts_for_item(item),
            "ring_counts": {name: ring_count(item, name) for name in filters},
        })

    final = report[-1] if report else {}
    final_counts = {name: ring_count(final, name) for name in filters}
    max_counts = {
        name: max((step["counts"][name] for step in steps), default=0)
        for name in filters
    }
    network_reached = (
        max_counts.get("dhcp", 0) > 0
        and max_counts.get("dns_query", 0) > 0
        and max_counts.get("tcp_open", 0) > 0
    )
    tls_reached = max_counts.get("tls_record", 0) > 0
    backend_clean = (
        max_counts.get("backend_error", 0) == 0
        and max_counts.get("backend_drop", 0) == 0
    )
    status_prefix = flow.replace("-", "_")
    if network_reached and tls_reached and backend_clean:
        status = f"{status_prefix}_reached_nas_tls"
    elif network_reached and backend_clean:
        status = f"{status_prefix}_reached_network"
    elif backend_clean:
        status = f"{status_prefix}_no_network"
    else:
        status = "backend_error"

    return {
        "status": status,
        "final_label": final.get("label"),
        "final_vblank9": final.get("vblank9"),
        "network_reached": network_reached,
        "tls_reached": tls_reached,
        "backend_clean": backend_clean,
        "final_counts": final_counts,
        "max_counts": max_counts,
        "steps": steps,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)

    runner = args.runner.resolve()
    command = [
        str(runner),
        str(args.bios.resolve()),
        "--serve",
        "--port",
        str(args.port),
        "--rom",
        str(args.rom.resolve()),
        "--config",
        str(args.config.resolve()),
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
        str(args.instance_index),
    ]
    if args.save_path:
        command.extend(["--save-path", str(args.save_path.resolve())])
    else:
        command.append("--no-save")
    if args.firmware_path:
        command.extend(["--firmware-path", str(args.firmware_path.resolve())])
    if args.firmware_state_path:
        command.extend([
            "--firmware-state-path", str(args.firmware_state_path.resolve())
        ])
    if args.no_dumps:
        command.extend(["--freebios", "--generated-firmware", "--boot", "direct"])
    if args.discover_static_misses:
        command.append("--discover-static-misses")

    filters = tuple(args.filter)
    with (output / "runner.stdout.log").open("wb") as stdout, (
        output / "runner.stderr.log"
    ).open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=runner.parent,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            capture_lib.wait_for_server(args.port, process)
            client = capture_lib.DebugClient(args.port, timeout=1800)
            try:
                report: list[dict[str, Any]] = []
                save = lambda label: save_checkpoint(
                    client, output, report, label, filters
                )

                input_lib.advance_to_vblank(client, 7800)
                save("title")

                # MPH shell to the online menu.
                for label, x, y, wait in (
                    ("main-menu", 84, 92, 180),
                    ("nickname-dialog", 168, 92, 180),
                    ("multiplayer-menu", 128, 126, 240),
                    ("wfc-menu", 198, 92, 360),
                ):
                    input_lib.tap(client, x, y, 12)
                    input_lib.advance_frames(client, wait)
                    save(label)

                if args.flow == "setup":
                    input_lib.tap(client, 128, 36, 12)
                    input_lib.advance_frames(client, 600)
                    save("wfc-setup-root")

                    # Standard WFC setup flow, shared with MKDS.
                    flow_steps = (
                        ("settings-tile", 85, 100, 220),
                        ("slot1", 43, 35, 220),
                        ("search-for-ap", 128, 37, 1600),
                        # Generated firmware already advertises the runner's
                        # ndsrecomp AP. Discovery selects it and returns to
                        # Connection 1 Settings; the old probe tapped (50,65)
                        # here, which is the SSID row and opened the keyboard.
                        ("test-connection", 192, 36, 2400),
                        ("save-settings", 190, 177, 600),
                    )
                else:
                    if args.flow == "friends-rivals":
                        flow_steps = (
                            ("friends-rivals", 194, 96, 1200),
                        )
                    else:
                        flow_steps = (
                            ("find-game", 58, 96, 1200),
                            ("find-game-confirm", 189, 125, 900),
                            ("find-game-yes", 108, 124, 1200),
                        )

                for label, x, y, wait in flow_steps:
                    input_lib.tap(client, x, y, 12)
                    if args.flow == "setup" and label == "test-connection":
                        wait_for_connection(
                            client,
                            require_tls=args.require_tls,
                            timeout_s=args.connection_timeout,
                            stall_s=args.connection_stall_s,
                        )
                    else:
                        input_lib.advance_frames(client, wait)
                    save(label)

                if args.flow == "setup":
                    input_lib.press_key(client, "b", 12)
                    input_lib.advance_frames(client, 600)
                    save("setup-root-after-back")
                    input_lib.press_key(client, "b", 12)
                    input_lib.advance_frames(client, 600)
                    save("exit-prompt")

                if args.flow == "search-game":
                    for target in args.targets:
                        if target > 22000:
                            break
                        input_lib.advance_to_vblank(client, target)
                        save(f"wait-{target}")

                    if args.fresh_profile:
                        input_lib.tap(client, 178, 171, 12)
                        input_lib.advance_frames(client, 900)
                        save("ack-wfc-id")
                        input_lib.tap(client, 108, 124, 12)
                        input_lib.advance_frames(client, 4200)
                        save("post-id-connect")
                    else:
                        # Returning profiles are already on the search filter
                        # screen. This tap is harmless there and keeps older
                        # evidence paths stable.
                        input_lib.tap(client, 189, 125, 12)
                        input_lib.advance_frames(client, 900)
                        save("ack-or-filter")
                    input_lib.tap(client, 178, 171, 12)
                    input_lib.advance_frames(client, 1200)
                    save("search-for-game")

                current_vblank = report[-1]["vblank9"] if report else 0
                for target in args.targets:
                    if target <= current_vblank:
                        continue
                    input_lib.advance_to_vblank(client, target)
                    save(f"wait-{target}")

                (output / "report.json").write_text(
                    json.dumps(report, indent=2) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                summary = summarize(report, filters, args.flow)
                summary["output"] = str(output)
                summary["network_backend"] = args.network_backend
                summary["wfc_provider"] = args.wfc_provider
                summary["instance_index"] = args.instance_index
                summary["flow"] = args.flow
                summary["firmware_path"] = (
                    str(args.firmware_path.resolve())
                    if args.firmware_path
                    else None
                )
                summary["save_path"] = str(args.save_path.resolve()) if args.save_path else None
                if args.firmware_out:
                    firmware = client.command("firmware_dump")
                    if not isinstance(firmware, dict):
                        raise RuntimeError("firmware_dump returned a non-object response")
                    if int(firmware.get("size", 0)) not in (131072, 262144):
                        raise RuntimeError(
                            f"firmware_dump returned {firmware.get('size')} bytes"
                        )
                    firmware_bytes = bytes.fromhex(str(firmware["hex"]))
                    args.firmware_out.parent.mkdir(parents=True, exist_ok=True)
                    args.firmware_out.write_bytes(firmware_bytes)
                    summary["firmware_out"] = str(args.firmware_out.resolve())
                (output / "summary.json").write_text(
                    json.dumps(summary, indent=2) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                return summary
            finally:
                client.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


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
    parser.add_argument("--save-path", type=Path)
    parser.add_argument("--firmware-path", type=Path)
    parser.add_argument("--firmware-state-path", type=Path)
    parser.add_argument("--no-dumps", action="store_true")
    parser.add_argument("--firmware-out", type=Path)
    parser.add_argument("--discover-static-misses", action="store_true")
    parser.add_argument(
        "--fresh-profile",
        action="store_true",
        help="drive first-time MPH WFC ID acknowledgement before searching",
    )
    parser.add_argument(
        "--startup-mode",
        choices=("preserve", "manual", "automatic"),
        default="automatic",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=19983)
    parser.add_argument("--instance-index", type=int, default=0)
    parser.add_argument(
        "--flow",
        choices=("setup", "find-game", "search-game", "friends-rivals"),
        default="setup",
    )
    parser.add_argument(
        "--network-backend",
        choices=("slirp", "pcap"),
        default="slirp",
    )
    parser.add_argument("--wfc-provider", default="wiimmfi")
    parser.add_argument("--filter", action="append", default=list(DEFAULT_FILTERS))
    parser.add_argument(
        "--connection-timeout",
        type=float,
        default=60.0,
        help="wall-time limit in seconds for WFC test-connection",
    )
    parser.add_argument(
        "--connection-stall-s",
        type=float,
        default=12.0,
        help="fail if network event counts make no progress for this many seconds",
    )
    parser.add_argument(
        "--require-tls",
        action="store_true",
        help="require at least one tls_record event before test-connection succeeds",
    )
    parser.add_argument(
        "--targets",
        type=int,
        nargs="+",
        default=[13000, 14500, 16000, 18000, 20000, 23000, 26000, 30000, 34000],
    )
    parser.add_argument(
        "--require-network",
        action="store_true",
        help="fail unless DHCP, DNS, TCP, TLS and no backend errors are observed",
    )
    args = parser.parse_args()

    if args.port < 1 or args.port > 65535:
        parser.error("--port must be in 1..65535")
    if args.instance_index < 0 or args.instance_index > 255:
        parser.error("--instance-index must be in 0..255")
    if args.no_dumps and args.firmware_path:
        parser.error("--no-dumps and --firmware-path are mutually exclusive")

    summary = run(args)
    print(json.dumps(summary, indent=2), flush=True)
    if args.require_network and not (
        summary["network_reached"]
        and summary["tls_reached"]
        and summary["backend_clean"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
