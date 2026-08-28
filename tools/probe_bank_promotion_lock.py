#!/usr/bin/env python3
"""Instruction-anchored guest-state lock between TWO runner binaries.

beads-lqa.37. Promoting Tier-3 coverage into static banks changes WHO executes
a guest instruction, never WHAT it does. The gate for such a change is
therefore an equality gate, and it has to span two different binaries -- the
before build and the after build -- which
tools/probe_machinery_bytelock.py (framework) cannot do: that probe toggles
one env selector inside ONE executable.

Same discipline, two exes. Both sides are driven through the debug server with
`run_to_event insn9 N`, so each stops at the Nth retired ARM9 instruction
exactly and the two runs do identical guest work. Anything that then differs
is the candidate, not host timing. The route harness cannot be used for this:
it navigates the live frontend at wall-clock speed and the same binary in the
same state produces different final framebuffers run to run.

EQUALITY SET (a difference here fails the gate):
  * both framebuffers, SHA-256
  * both CPUs' full register file, CPSR, SPSR and mode
  * the whole event_counts block -- insn9/insn7/vblank/IRQ/IPC ordinals, the
    cross-CPU sync evidence the dual-CPU rule cares about

RECORDED BUT NOT COMPARED (these are SUPPOSED to move -- they are the point):
  * static_coverage: tier3_entries/insns per CPU. Fewer interpreted
    instructions on the after side is the whole objective.
  * dispatch_stats composition per CPU.
A gate that also demanded these match would fail on success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import time

EQUALITY_KEYS = ("fb_A", "fb_B", "regs9", "regs7", "events")


class Client:
    def __init__(self, port: int, timeout: float = 1800.0) -> None:
        deadline = time.time() + 120.0
        last = None
        while time.time() < deadline:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), 5.0)
                break
            except OSError as exc:
                last = exc
                time.sleep(0.25)
        else:
            raise SystemExit(f"could not connect to port {port}: {last}")
        self.sock.settimeout(timeout)
        self.buf = b""

    def cmd(self, name: str, **kwargs) -> dict:
        payload = {"cmd": name}
        payload.update(kwargs)
        self.sock.sendall((json.dumps(payload) + "\n").encode())
        while b"\n" not in self.buf:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise SystemExit(f"debug server closed during {name}")
            self.buf += chunk
        line, _, self.buf = self.buf.partition(b"\n")
        return json.loads(line.decode())

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def digest(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def capture(client: Client) -> dict:
    out: dict = {}
    for engine in ("A", "B"):
        fb = client.cmd("framebuffer", engine=engine)
        pixels = fb.get("rgb") or fb.get("pixels") or fb.get("data")
        out[f"fb_{engine}"] = (hashlib.sha256(pixels.encode()).hexdigest()
                               if isinstance(pixels, str) else digest(fb))
    out["regs9"] = client.cmd("regs", cpu=9)
    out["regs7"] = client.cmd("regs", cpu=7)
    out["events"] = client.cmd("event_counts")
    out["static_coverage"] = client.cmd("static_coverage")
    stats = client.cmd("dispatch_stats")
    out["dispatch_composition"] = {
        cpu: {key: stats.get(cpu, {}).get(key)
              for key in ("literal_branch", "literal_call",
                          "literal_fallthrough", "resume_dispatch",
                          "dispatch_total", "cache_hit", "cache_hit_absent",
                          "cache_slow_lookup")}
        for cpu in ("arm9", "arm7") if isinstance(stats.get(cpu), dict)
    }
    return out


def run_leg(args, label: str, exe: pathlib.Path, port: int) -> list[dict]:
    cmd = [str(exe), str(args.bios), "--serve", "--port", str(port),
           "--boot", args.boot, "--no-save", "--rom", str(args.rom)]
    if args.config:
        cmd += ["--config", str(args.config)]
    cmd += list(args.runner_arg)
    args.output.mkdir(parents=True, exist_ok=True)
    log = args.output / f"leg-{label}.log"
    stops: list[dict] = []
    with open(log, "wb") as handle:
        proc = subprocess.Popen(cmd, stdout=handle, stderr=subprocess.STDOUT,
                                env=dict(os.environ))
        try:
            client = Client(port, args.timeout)
            for i in range(args.count):
                target = args.start + i * args.step
                reply = client.cmd("run_to_event", event="insn9",
                                   count=target, max_rounds=100000000)
                if not reply.get("reached", False):
                    print(f"  {label} stop {target}: NOT REACHED {reply}")
                    break
                snap = capture(client)
                snap["stop"] = target
                stops.append(snap)
                sc = snap["static_coverage"]
                print(f"  {label} stop {target:>12,}: "
                      f"fbA={snap['fb_A'][:12]} fbB={snap['fb_B'][:12]} "
                      f"tier3_insns9={sc.get('tier3_insns9'):>12,} "
                      f"tier3_insns7={sc.get('tier3_insns7'):>10,} "
                      f"tier3_entries9={sc.get('tier3_entries9'):>10,}")
            client.close()
        finally:
            proc.terminate()
            try:
                proc.wait(30)
            except subprocess.TimeoutExpired:
                proc.kill()
    return stops


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--exe-before", type=pathlib.Path, required=True)
    p.add_argument("--exe-after", type=pathlib.Path, required=True)
    p.add_argument("--bios", type=pathlib.Path, required=True)
    p.add_argument("--rom", type=pathlib.Path, required=True)
    p.add_argument("--config", type=pathlib.Path, default=None)
    p.add_argument("--boot", default="direct", choices=("direct", "lle"))
    p.add_argument("--port", type=int, default=19970)
    p.add_argument("--start", type=int, default=100_000_000)
    p.add_argument("--step", type=int, default=100_000_000)
    p.add_argument("--count", type=int, default=7)
    p.add_argument("--timeout", type=float, default=3600.0)
    p.add_argument("--runner-arg", action="append", default=[])
    p.add_argument("--output", type=pathlib.Path,
                   default=pathlib.Path("perf-results/bank-promotion-lock"))
    args = p.parse_args()

    print(f"BEFORE {args.exe_before}")
    before = run_leg(args, "before", args.exe_before, args.port)
    print(f"AFTER  {args.exe_after}")
    after = run_leg(args, "after", args.exe_after, args.port + 1)

    if len(before) != len(after):
        print(f"FAIL: {len(before)} before stops vs {len(after)} after stops")
        return 1

    differences: list[str] = []
    compared = 0
    for b, a in zip(before, after):
        for key in EQUALITY_KEYS:
            if key in ("regs9", "regs7", "events"):
                for field in sorted(set(b[key]) | set(a[key])):
                    compared += 1
                    if b[key].get(field) != a[key].get(field):
                        differences.append(
                            f"stop {b['stop']}: {key}.{field} "
                            f"{b[key].get(field)} != {a[key].get(field)}")
            else:
                compared += 1
                if b[key] != a[key]:
                    differences.append(f"stop {b['stop']}: {key} differs")

    print()
    print("TIER-3, before -> after (LOWER IS THE POINT; not part of the gate)")
    for b, a in zip(before, after):
        bs, as_ = b["static_coverage"], a["static_coverage"]
        for field in ("tier3_insns9", "tier3_entries9",
                      "tier3_insns7", "tier3_entries7"):
            bv, av = int(bs.get(field, 0)), int(as_.get(field, 0))
            pct = (100.0 * (av - bv) / bv) if bv else 0.0
            print(f"  stop {b['stop']:>12,} {field:<15} "
                  f"{bv:>14,} -> {av:>14,}  {pct:+7.2f}%")

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(
        {"before": before, "after": after, "fields_compared": compared,
         "differences": differences}, indent=2), encoding="utf-8")

    print()
    print(f"fields compared: {compared}, differing: {len(differences)}")
    for line in differences[:40]:
        print(f"  ! {line}")
    if differences:
        print("GUEST-STATE LOCK FAIL: coverage promotion changed guest "
              "behaviour, not just who executes it")
        return 1
    print("GUEST-STATE LOCK PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
