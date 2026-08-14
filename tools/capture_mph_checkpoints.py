#!/usr/bin/env python3
"""Launch an ndsrecomp runner and capture deterministic VBlank checkpoints."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import time
from pathlib import Path

from PIL import Image


def firmware_crc16(data: bytes, start: int = 0xFFFF) -> int:
    polynomial = (
        0xC0C1, 0xC181, 0xC301, 0xC601,
        0xCC01, 0xD801, 0xF001, 0xA001,
    )
    for value in data:
        start ^= value
        for bit in range(8):
            if start & 1:
                start = (start >> 1) ^ (polynomial[bit] << (7 - bit))
            else:
                start >>= 1
    return start & 0xFFFF


def automatic_firmware(source: Path, destination: Path) -> None:
    """Create an ignored private firmware copy with Slot-1 auto-start set."""
    firmware = bytearray(source.read_bytes())
    if len(firmware) < 0x22:
        raise ValueError("firmware image is truncated")
    user = (firmware[0x20] << 3) | (firmware[0x21] << 11)
    if user + 0x200 > len(firmware):
        raise ValueError("firmware user-settings layout is invalid")
    for copy in range(2):
        base = user + copy * 0x100
        flags = int.from_bytes(firmware[base + 0x64:base + 0x66], "little")
        firmware[base + 0x64:base + 0x66] = (
            flags | (1 << 6)
        ).to_bytes(2, "little")
        checksum = firmware_crc16(firmware[base:base + 0x70])
        firmware[base + 0x72:base + 0x74] = checksum.to_bytes(2, "little")
    destination.write_bytes(firmware)


class DebugClient:
    def __init__(self, port: int, timeout: float = 1800.0):
        self.socket = socket.create_connection(("127.0.0.1", port), timeout)
        self.buffer = b""

    def command(self, name: str, **arguments: object) -> object:
        arguments["cmd"] = name
        self.socket.sendall((json.dumps(arguments) + "\n").encode())
        while b"\n" not in self.buffer:
            chunk = self.socket.recv(65536)
            if not chunk:
                raise ConnectionError("debug server closed the connection")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        response = json.loads(line)
        if isinstance(response, dict) and response.get("error"):
            raise RuntimeError(f"{name}: {response['error']}")
        return response

    def close(self) -> None:
        self.socket.close()


def wait_for_server(port: int, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"runner exited early with {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), 0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"runner did not listen on port {port}")


def framebuffer(client: DebugClient, engine: str) -> Image.Image:
    response = client.command("framebuffer", engine=engine)
    assert isinstance(response, dict)
    return Image.frombytes(
        "RGB",
        (int(response["w"]), int(response["h"])),
        bytes.fromhex(str(response["rgb"])),
    )


def capture(
    client: DebugClient,
    output: Path,
    count: int,
    include_native_stats: bool,
) -> dict[str, object]:
    previous_vblank = -1
    while True:
        hit = client.command(
            "run_to_event", event="vblank9", count=count, stall=300_000
        )
        assert isinstance(hit, dict)
        if hit.get("reached"):
            break
        counts = hit.get("counts")
        current_vblank = (
            int(counts.get("vblank9", -1))
            if isinstance(counts, dict)
            else -1
        )
        if hit.get("terminal") or hit.get("stalled"):
            raise RuntimeError(
                f"failed to reach VBlank {count}: {json.dumps(hit)}"
            )
        if not hit.get("exhausted") or current_vblank <= previous_vblank:
            raise RuntimeError(
                f"no progress toward VBlank {count}: {json.dumps(hit)}"
            )
        # A long authentic-firmware run can exceed one server command's
        # safety-round budget. Continue from the live machine rather than
        # saving a misleading image under the requested checkpoint name.
        previous_vblank = current_vblank
    screens = [framebuffer(client, engine) for engine in ("A", "B")]
    image = Image.new(
        "RGB",
        (max(screen.width for screen in screens),
         sum(screen.height for screen in screens)),
    )
    y = 0
    for screen in screens:
        image.paste(screen, (0, y))
        y += screen.height
    image.save(output / f"vblank-{count:04d}.png")

    arm9 = client.command("regs", cpu=9)
    arm7 = client.command("regs", cpu=7)
    powercontrol9 = client.command(
        "read_io", cpu=9, addr=0x04000304, width=16
    )
    dispcnt_a = client.command(
        "read_io", cpu=9, addr=0x04000000, width=32
    )
    dispcnt_b = client.command(
        "read_io", cpu=9, addr=0x04001000, width=32
    )
    assert isinstance(arm9, dict) and isinstance(arm7, dict)
    assert isinstance(powercontrol9, dict)
    assert isinstance(dispcnt_a, dict) and isinstance(dispcnt_b, dict)
    result = {
        "vblank9": count,
        "hit": hit,
        "arm9_pc": f"0x{int(arm9['r'][15]):08x}",
        "arm7_pc": f"0x{int(arm7['r'][15]):08x}",
        "powercontrol9": f"0x{int(powercontrol9['value']):04x}",
        "dispcnt_a": f"0x{int(dispcnt_a['value']):08x}",
        "dispcnt_b": f"0x{int(dispcnt_b['value']):08x}",
    }
    if include_native_stats:
        result["dispatch"] = client.command("dispatch_stats")
        result["cartridge_save"] = client.command("cart_save_info")
    print(json.dumps(result), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    backend = parser.add_mutually_exclusive_group(required=True)
    backend.add_argument("--runner", type=Path)
    backend.add_argument("--oracle", type=Path)
    parser.add_argument("--bios", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=19852)
    parser.add_argument(
        "--targets", type=int, nargs="+", default=[300, 600, 900, 1200]
    )
    parser.add_argument(
        "--boot",
        choices=("firmware", "direct"),
        default="firmware",
        help="boot path: firmware (LLE, default) or direct "
        "(melonDS SetupDirectBoot equivalent on both backends)",
    )
    args = parser.parse_args()
    if args.runner is not None and args.config is None:
        parser.error("--config is required with --runner")

    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "runner.stdout.log").open("wb") as stdout, (
        output / "runner.stderr.log"
    ).open("wb") as stderr:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
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
            if args.boot == "direct":
                command += ["--boot", "direct"]
        else:
            executable = args.oracle.resolve()
            bios = args.bios.resolve()
            firmware = output / "firmware-automatic.bin"
            automatic_firmware(bios / "firmware.bin", firmware)
            command = [
                str(executable),
                "--bios9",
                str(bios / "biosnds9.rom"),
                "--bios7",
                str(bios / "biosnds7.rom"),
                "--firmware",
                str(firmware),
                "--rom",
                str(args.rom.resolve()),
                # The runner's --startup-mode automatic patches its private
                # in-memory firmware; the oracle reads the same patched copy
                # from disk so a direct boot's user-settings mirror carries
                # identical bytes on both sides.
                "--boot",
                args.boot,
                "--port",
                str(args.port),
            ]
        process = subprocess.Popen(
            command,
            cwd=executable.parent,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )
        try:
            wait_for_server(args.port, process)
            client = DebugClient(args.port)
            try:
                client.command("reset")
                report = [
                    capture(
                        client,
                        output,
                        count,
                        include_native_stats=args.runner is not None,
                    )
                    for count in sorted(set(args.targets))
                ]
                (output / "report.json").write_text(
                    json.dumps(report, indent=2) + "\n",
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
