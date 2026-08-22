#!/usr/bin/env python3
"""Reconnect probe for beads-lqa.8: connect/disconnect/reconnect Nintendo WFC
within one MPH process and attribute where the second connect fails.

Drives the Find Game flow on a returning profile, backs out to trigger the
"disconnect from Nintendo WFC" path, and repeats. Each cycle records the
net_progress counter DELTAS (the rings are cumulative), framebuffer
checkpoints, and at the end full ring dumps. The whole session runs under
--net-capture-out so attempt 1 vs attempt 2 can be diffed on the wire.

Output may contain real console/network identifiers; keep under scratch/.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import capture_mph_checkpoints as capture_lib  # noqa: E402
import fuzz_mph_gameplay as input_lib  # noqa: E402

RING_FILTERS = (
    "dhcp",
    "dns_query",
    "dns_response",
    "tcp_open",
    "tcp_close",
    "tcp_reset",
    "tcp_packet",
    "tls_record",
    "udp_packet",
    "arp",
    "ethernet_tx",
    "ethernet_rx",
    "wifi_tx_frame",
    "wifi_rx_frame",
    "wifi_association",
    "wifi_state_change",
    "backend_error",
    "backend_drop",
)


def net_counts(client: capture_lib.DebugClient) -> dict[str, int]:
    progress = client.command("net_progress")
    counts = progress.get("counts", {})
    if not isinstance(counts, dict):
        raise RuntimeError(f"net_progress malformed: {progress!r}")
    return {str(k): int(v) for k, v in counts.items()}


def delta(now: dict[str, int], base: dict[str, int]) -> dict[str, int]:
    keys = set(now) | set(base)
    return {k: now.get(k, 0) - base.get(k, 0) for k in sorted(keys)}


def read_bytes(client: capture_lib.DebugClient, addr: int, length: int) -> bytes:
    resp = client.command("read_mem", cpu=9, addr=addr, len=length)
    return bytes.fromhex(resp["hex"])


def read_u32(client: capture_lib.DebugClient, addr: int) -> int:
    return int.from_bytes(read_bytes(client, addr, 4), "little")


def dwc_netcheck_state(client: capture_lib.DebugClient) -> dict[str, Any]:
    """Read the DWCnetcheck thread's live state (addresses from the
    ghidra/MPH RAM RE, beads-lqa.8: FUN_0216a6a0 'DWCnetcheck' thread).
    Valid only while the WFC overlay is resident."""
    ctx_ptr = read_u32(client, 0x0219C948)
    out: dict[str, Any] = {
        "ctx_ptr": hex(ctx_ptr),
        "hotspot_flag": read_u32(client, 0x0219C94C),
        "svcloc_cache": read_bytes(client, 0x0219C9A8, 16).hex(),
    }
    if 0x02000000 <= ctx_ptr < 0x02400000:
        out["result_code"] = read_u32(client, ctx_ptr + 0x1000)
        out["progress"] = hex(read_u32(client, ctx_ptr + 0x1004))
        out["conn_state"] = read_u32(client, ctx_ptr + 0x1020)
        out["errno_global"] = read_u32(client, 0x021021EC)
        # ctx+0x1984 = response text pointer (FUN_021692f0's input); grab
        # the first bytes of what the guest HTTP layer actually accumulated.
        resp_ptr = read_u32(client, ctx_ptr + 0x1984)
        out["resp_ptr"] = hex(resp_ptr)
        if 0x02000000 <= resp_ptr < 0x02400000:
            out["resp_head"] = read_bytes(client, resp_ptr, 160).hex()
    return out


def save_checkpoint(
    client: capture_lib.DebugClient,
    output: Path,
    report: list[dict[str, Any]],
    label: str,
) -> dict[str, Any]:
    item = input_lib.save_checkpoint(client, output, len(report), label)
    item["net_progress"] = net_counts(client)
    report.append(item)
    return item


def wait_for_connect_delta(
    client: capture_lib.DebugClient,
    base: dict[str, int],
    *,
    timeout_s: float,
    stall_s: float,
    pc_samples: list[dict[str, Any]] | None = None,
    frames_per_poll: int = 120,
) -> tuple[str, dict[str, int]]:
    """Advance frames until this attempt (relative to `base`) either reaches
    TLS, errors, or stalls. Returns (outcome, delta_counts)."""
    end = time.monotonic() + timeout_s
    last_total = -1
    last_progress = time.monotonic()
    d: dict[str, int] = {}
    while time.monotonic() < end:
        input_lib.advance_frames(client, frames_per_poll)
        if pc_samples is not None:
            try:
                netcheck = dwc_netcheck_state(client)
            except Exception as exc:
                netcheck = {"error": str(exc)}
            # Keep only samples where the netcheck ctx is alive -- that is
            # the ~1-frame window where result_code/progress/conn_state are
            # readable before FUN_0216b660 frees the ctx.
            if netcheck.get("ctx_ptr", "0x0") != "0x0":
                netcheck["vblank9"] = input_lib.event_counts(client)["vblank9"]
                pc_samples.append(netcheck)
        d = delta(net_counts(client), base)
        if d.get("backend_error", 0) > 0:
            return "backend_error", d
        if d.get("backend_drop", 0) > 0:
            return "backend_drop", d
        if d.get("tls_record", 0) > 0 and d.get("tcp_open", 0) > 0:
            return "connected_tls", d
        total = sum(v for v in d.values() if v > 0)
        if total != last_total:
            last_total = total
            last_progress = time.monotonic()
        elif time.monotonic() - last_progress >= stall_s:
            return "stalled", d
    return "timeout", d


def run(args: argparse.Namespace) -> dict[str, Any]:
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    profile = output / "profile"
    profile.mkdir(parents=True, exist_ok=True)

    # Copy the source profile so runs never mutate the good pair.
    save_path = profile / "mph.sav"
    firmware_state = profile / "firmware-generated.bin"
    shutil.copyfile(args.profile_save, save_path)
    shutil.copyfile(args.profile_firmware, firmware_state)

    capture_path = output / "session.pcap"
    command = [
        str(args.runner.resolve()),
        str(args.bios.resolve()),
        "--serve",
        "--port", str(args.port),
        "--rom", str(args.rom.resolve()),
        "--config", str(args.config.resolve()),
        "--startup-mode", "automatic",
        "--network", "on",
        "--network-backend", "slirp",
        "--wfc", "on",
        "--wfc-provider", args.wfc_provider,
        "--instance-index", str(args.instance_index),
        "--save-path", str(save_path),
        "--firmware-state-path", str(firmware_state),
        "--freebios", "--generated-firmware", "--boot", "direct",
        "--net-capture-out", str(capture_path),
    ]

    report: list[dict[str, Any]] = []
    cycles: list[dict[str, Any]] = []
    with (output / "runner.stdout.log").open("wb") as so, (
        output / "runner.stderr.log"
    ).open("wb") as se:
        process = subprocess.Popen(
            command,
            cwd=args.runner.resolve().parent,
            stdout=so,
            stderr=se,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            capture_lib.wait_for_server(args.port, process)
            client = capture_lib.DebugClient(args.port, timeout=1800)
            try:
                save = lambda label: save_checkpoint(client, output, report, label)

                input_lib.advance_to_vblank(client, 7800)
                save("title")
                for label, x, y, wait in (
                    ("main-menu", 84, 92, 180),
                    ("nickname-dialog", 168, 92, 180),
                    ("multiplayer-menu", 128, 126, 240),
                    ("wfc-menu", 198, 92, 360),
                ):
                    input_lib.tap(client, x, y, 12)
                    input_lib.advance_frames(client, wait)
                    save(label)

                for cycle in range(args.cycles):
                    tag = f"c{cycle}"
                    base = net_counts(client)

                    fine = args.frames_per_poll == 1 and cycle > 0
                    pc_samples: list[dict[str, Any]] = []

                    def sampled_advance(frames: int) -> None:
                        if not fine:
                            input_lib.advance_frames(client, frames)
                            return
                        for _ in range(frames):
                            input_lib.advance_frames(client, 1)
                            try:
                                nc = dwc_netcheck_state(client)
                            except Exception:
                                continue
                            if nc.get("ctx_ptr", "0x0") != "0x0":
                                nc["vblank9"] = input_lib.event_counts(
                                    client
                                )["vblank9"]
                                pc_samples.append(nc)

                    # Find Game -> confirm -> yes. On a returning profile the
                    # extra taps are harmless if the screen skips a step.
                    for label, x, y, wait in (
                        ("find-game", 58, 96, 900),
                        ("find-game-confirm", 189, 125, 600),
                        ("find-game-yes", 108, 124, 600),
                    ):
                        input_lib.tap(client, x, y, 12)
                        sampled_advance(wait)
                        save(f"{tag}-{label}")

                    # Catch the DWCnetcheck verdict in the act: run until the
                    # result-setter FUN_0216a658 (ghidra/MPH RE) is entered,
                    # then R0 = result code (0xb = success, 1..10 = the
                    # failing branch) and LR = the exact call site.
                    netcheck_hit: dict[str, Any] | None = None
                    if args.break_error_setter:
                        bp = client.command(
                            "run_to_pc", pc=0x0216A658, max_rounds=100_000_000
                        )
                        if bp.get("reached"):
                            regs9 = client.command("regs", cpu=9)
                            netcheck_hit = {
                                "r0_code": regs9["r"][0],
                                "lr_call_site": hex(regs9["r"][14]),
                                "vblank9": input_lib.event_counts(client)[
                                    "vblank9"
                                ],
                            }
                        else:
                            netcheck_hit = {"reached": False, "resp": bp}

                    outcome, d = wait_for_connect_delta(
                        client,
                        base,
                        timeout_s=args.connect_timeout,
                        stall_s=args.stall_s,
                        pc_samples=pc_samples,
                        # Fine sampling only matters on reconnect attempts;
                        # keep the first (healthy) cycle fast.
                        frames_per_poll=(
                            args.frames_per_poll if cycle > 0 else 120
                        ),
                    )
                    input_lib.advance_frames(client, 600)
                    item = save(f"{tag}-connect-{outcome}")
                    try:
                        netcheck = dwc_netcheck_state(client)
                    except Exception as exc:  # keep the probe robust
                        netcheck = {"error": str(exc)}
                    # DWC error record (FUN_02164e78(1) -> *(0x0219C920));
                    # +0x10 = netcheck progress marker copied at failure.
                    try:
                        rec_ptr = read_u32(client, 0x0219C920)
                        netcheck["dwc_record_ptr"] = hex(rec_ptr)
                        if 0x02000000 <= rec_ptr < 0x02400000:
                            netcheck["dwc_record"] = read_bytes(
                                client, rec_ptr, 0x40
                            ).hex()
                    except Exception as exc:
                        netcheck["dwc_record_error"] = str(exc)
                    # Full main-RAM snapshot for offline diff / 52200 search.
                    if args.dump_ram:
                        try:
                            region = client.command(
                                "read_region", region="mainram"
                            )
                            (output /
                             f"mainram-c{cycle}-{outcome}.bin").write_bytes(
                                bytes.fromhex(region["hex"])
                            )
                        except Exception as exc:
                            netcheck["ram_dump_error"] = str(exc)
                    cycles.append({
                        "cycle": cycle,
                        "outcome": outcome,
                        "delta": d,
                        "vblank9": item["vblank9"],
                        "netcheck": netcheck,
                        "netcheck_hit": netcheck_hit,
                        "pc_samples": pc_samples,
                    })

                    # Back out to trigger the disconnect prompt, confirm it,
                    # and land back on the offline WFC menu.
                    # One B press on the search-filter screen raises the
                    # "OK TO DISCONNECT FROM NINTENDO WI-FI CONNECTION?"
                    # modal; the checkmark sits at (105,121) on the bottom
                    # screen. A second B would CANCEL the modal.
                    for label, action in (
                        ("back1", ("key", "b")),
                        ("disc-confirm", ("tap", 105, 121)),
                        ("settle", None),
                    ):
                        if action is None:
                            input_lib.advance_frames(client, 600)
                        elif action[0] == "key":
                            input_lib.press_key(client, action[1], 12)
                            input_lib.advance_frames(client, 360)
                        else:
                            input_lib.tap(client, action[1], action[2], 12)
                            input_lib.advance_frames(client, 360)
                        save(f"{tag}-{label}")

                rings = {
                    name: client.command("net_ring_dump", max=8192, filter=name)
                    for name in RING_FILTERS
                }
                (output / "rings.json").write_text(
                    json.dumps(rings, indent=2) + "\n", encoding="utf-8"
                )
                net_state = client.command("net_state")
            finally:
                client.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    summary = {
        "cycles": cycles,
        "net_state": net_state,
        "capture": str(capture_path),
        "output": str(output),
        "steps": [
            {"label": i["label"], "image": i["image"], "vblank9": i["vblank9"]}
            for i in report
        ],
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runner",
        type=Path,
        default=Path(r"F:\Projects\ndsrecomp\ndsrecomp\runner\build-mph-release\nds_runner.exe"),
    )
    parser.add_argument(
        "--bios", type=Path, default=Path(r"F:\Projects\ndsrecomp\ndsrecomp\bios")
    )
    parser.add_argument(
        "--rom",
        type=Path,
        default=Path(r"F:\Projects\ndsrecomp\metroidprimehuntersrecomp\Metroid Prime Hunters.nds"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=SCRIPT_DIR.parent / "game.toml",
    )
    parser.add_argument(
        "--profile-save",
        type=Path,
        default=Path(r"F:\Projects\ndsrecomp\scratch\wifi-stability\fable-preconf-profile\mph.sav"),
    )
    parser.add_argument(
        "--profile-firmware",
        type=Path,
        default=Path(r"F:\Projects\ndsrecomp\scratch\wifi-stability\fable-preconf-profile\firmware-generated.bin"),
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=19985)
    parser.add_argument("--instance-index", type=int, default=1)
    parser.add_argument("--wfc-provider", default="wiimmfi")
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument(
        "--dump-ram",
        action="store_true",
        help="write a full mainram snapshot after each cycle outcome",
    )
    parser.add_argument(
        "--require-all-cycles",
        action="store_true",
        help="exit nonzero unless every cycle reaches connected_tls "
        "(regression gate for beads-lqa.8)",
    )
    parser.add_argument(
        "--break-error-setter",
        action="store_true",
        help="run_to_pc on the DWCnetcheck result setter each cycle and "
        "record R0/LR (MPH AMHE rev0 address 0x0216a658)",
    )
    parser.add_argument("--connect-timeout", type=float, default=90.0)
    parser.add_argument(
        "--frames-per-poll",
        type=int,
        default=120,
        help="guest frames advanced per poll iteration; 1 = per-frame "
        "netcheck-ctx sampling (slow but catches the 1-frame result window)",
    )
    parser.add_argument("--stall-s", type=float, default=15.0)
    args = parser.parse_args()

    summary = run(args)
    print(json.dumps(summary, indent=2), flush=True)
    if args.require_all_cycles:
        outcomes = [c["outcome"] for c in summary["cycles"]]
        if len(outcomes) < args.cycles or any(
            o != "connected_tls" for o in outcomes
        ):
            print(f"FAIL: cycle outcomes {outcomes}", flush=True)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
