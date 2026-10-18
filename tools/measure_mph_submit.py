"""Bounded MPH HLE canary: fresh same-build preparation and equal-frame timing.

One process per arm; private room/inventory data assists match the existing
campaign harness. No cross-build snapshot loads or retired-instruction anchors.
The prepare action leaves its own stopped debug process alive for measurement.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from harvest_campaign_coverage import Harvest, ROOM, PLAYER_INDEX, PLAYER_STRIDE
from mph_overlay_route import DebugClient, KEY_BITS, RELEASED

GAME = Path(__file__).resolve().parents[1]
FRAMEWORK = GAME.parent / "ndsrecomp"


def dump(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def process_cpu(pid: int) -> float:
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not api.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        return sum((t.dwHighDateTime << 32) | t.dwLowDateTime for t in times[2:]) / 1e7
    finally:
        api.CloseHandle(handle)


def prepare(args: argparse.Namespace) -> None:
    args.out.mkdir(parents=True, exist_ok=False)
    exe = args.exe.resolve()
    env = dict(os.environ)
    env.update(PATH=r"C:\msys64\mingw64\bin;" + env.get("PATH", ""),
               SDL_AUDIODRIVER="dummy", SDL_AUDIO_DRIVER="dummy",
               NDS_3D_RENDERER="compute", NDS_HOSTPROF="1", NDS_DEEP_TRACE="0")
    # Leave the ordinary cheap counters identical in both arms. Expensive
    # instruction recording and optional scheduler/GPU clocks are disabled.
    for key in ("NDS_PROFILE_SCHED", "NDS_PROFILE_GPU", "NDS_FORCE_TIER3"):
        env.pop(key, None)
    command = [str(exe), str(FRAMEWORK / "bios"), "--serve", "--port", str(args.port),
               "--rom", str(GAME / "Metroid Prime Hunters.nds"),
               "--config", str(GAME / "game.toml"), "--boot", "direct", "--no-save",
               "--performance-governor", "off"]
    with (args.out / "stdout.log").open("wb") as stdout, (args.out / "stderr.log").open("wb") as stderr:
        process = subprocess.Popen(command, cwd=exe.parent, env=env, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    dump(args.out / "process.json", {"pid": process.pid, "port": args.port,
         "command": command, "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
         "renderer": "compute", "governor": "off", "audio_output": "dummy"})
    client = None
    harvest = None
    try:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError(f"runner exited {process.returncode}")
            try:
                client = DebugClient(args.port)
                break
            except OSError:
                time.sleep(0.5)
        if client is None:
            raise RuntimeError("debug server did not start")
        client.cmd("deep_trace", on=0)
        harvest = Harvest(client, args.out)
        print(f"preparing PID {process.pid}", flush=True)
        if args.checkpoint is not None:
            # Exact same binary/build only: the core's normal identity check
            # remains authoritative. This avoids another boot/route for a
            # justified reverse pair or a focused reproduction.
            client.cmd("state_load", path=args.checkpoint.resolve().as_posix())
            client.cmd("deep_trace", on=0)
            shutil.copyfile(args.checkpoint, args.out / "active.state")
            dump(args.out / "ready.json", {"state": harvest.status(), "service": client.cmd("mph_submit"),
                 "coverage": client.cmd("static_coverage"), "checkpoint": str(args.checkpoint.resolve())})
            print("ready from same-build checkpoint", json.dumps(harvest.status()), flush=True)
            return
        harvest.prepare_ship(args.out / "ship.state")
        print("fresh same-build ship prepared", flush=True)
        harvest.room = 92
        harvest.write(ROOM, 92)
        client.press("a", 3)
        for tick in range(120):
            harvest.write(ROOM, 92)
            client.advance(10)
            if tick >= 30 and 1 <= harvest.read(ROOM + 2) <= 4 and harvest.read(0x020E4A04, 4) == 14:
                break
        client.advance(90)
        for _ in range(30):
            slot = harvest.read(PLAYER_INDEX)
            if slot <= 3 and harvest.read(0x020DA7EE + slot * PLAYER_STRIDE, 2):
                break
            client.press("a", 3)
            client.advance(60)
        state = harvest.status()
        if state["room"] != 92 or state["frontend_state"] != 14 or not state["health"]:
            raise RuntimeError(f"Gorea did not become active: {state}")
        harvest.dismiss()
        harvest.supply()
        client.cmd("keys", mask=RELEASED)
        client.cmd("touch", down=False, x=0, y=0)
        client.cmd("run_vblanks", count=120)
        harvest.save(args.out / "active.state")
        dump(args.out / "ready.json", {"state": harvest.status(), "service": client.cmd("mph_submit"),
             "coverage": client.cmd("static_coverage")})
        print("ready", json.dumps(harvest.status()), flush=True)
    except BaseException:
        process.terminate()
        process.wait(timeout=30)
        raise
    finally:
        if harvest:
            harvest.log.close()
        if client:
            client.sock.close()


def measure(args: argparse.Namespace) -> None:
    metadata = json.loads((args.out / "process.json").read_text())
    client = DebugClient(metadata["port"])
    harvest = Harvest(client, args.out)
    try:
        client.cmd("state_load", path=(args.out / "active.state").resolve().as_posix())
        client.cmd("deep_trace", on=0)
        client.cmd("keys", mask=RELEASED & ~(1 << KEY_BITS["l"]))
        before = {"state": harvest.status(), **{name: client.cmd(name) for name in
                  ("event_counts", "static_coverage", "mph_submit", "emu_attrib", "dispatch_stats")}}
        cpu_start = process_cpu(metadata["pid"])
        start = time.perf_counter()
        result = client.cmd("run_vblanks", count=600)
        seconds = time.perf_counter() - start
        cpu_seconds = process_cpu(metadata["pid"]) - cpu_start
        after = {"state": harvest.status(), **{name: client.cmd(name) for name in
                 ("event_counts", "static_coverage", "mph_submit", "emu_attrib", "dispatch_stats")}}
        if result["terminal"] or result["vblanks"] != 600:
            raise RuntimeError(f"incomplete timing interval: {result}")
        record = {"diagnostic": args.diagnostic, "wall_seconds": seconds,
                  "process_cpu_seconds": cpu_seconds, "ms_per_vblank": seconds * 1000 / 600,
                  "cpu_ms_per_vblank": cpu_seconds * 1000 / 600,
                  "vblanks_per_second": 600 / seconds, "result": result,
                  "before": before, "after": after, "identity": metadata}
        name = "diagnostic" if args.diagnostic else "measurement" + ("-" + args.label if args.label else "")
        dump(args.out / f"{name}.json", record)
        if args.diagnostic:
            client.cmd("hostprof_dump", path=(args.out / "hostprof.json").resolve().as_posix(),
                       window_ms=round(seconds * 1000))
        elif not args.label and after["mph_submit"]["implementation"] == "HLE":
            client.screenshot(args.out / "active.png")
        print(name, json.dumps({k: record[k] for k in ("wall_seconds", "process_cpu_seconds",
              "ms_per_vblank", "vblanks_per_second")}), flush=True)
    finally:
        harvest.log.close()
        client.sock.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "measure"))
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=19948)
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--label", choices=("reverse",), default="")
    parser.add_argument("--checkpoint", type=Path, help="reuse an exact same-build checkpoint")
    args = parser.parse_args()
    args.out = args.out.resolve()
    if args.action == "prepare":
        if args.exe is None:
            parser.error("prepare requires --exe")
        prepare(args)
    else:
        measure(args)


if __name__ == "__main__":
    main()
