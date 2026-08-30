#!/usr/bin/env python3
"""Replay one benchmark route with live-overlay autocompile pointed at a cache.

This is the route engine behind the Windows and Linux release-cache builders.
The packaged release ships PRE-COMPILED native shards so a player's first session
already runs the game's hot RAM-generated pages natively instead of
interpreted, and the only way to produce those shards is to actually play the
game while the runner's autocompile tier is armed.

The route landmarks come from tools/measure_mph_scenario.py, so the workload
walked here is exactly the workload the perf harness measures -- a cache warmed
against a route nobody benchmarks would be a cache of unknown value.

Never terminates anything but the PID it spawned: this machine runs concurrent
sessions of the same executable.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time


def load_harness(mph_root: pathlib.Path):
    sys.path.insert(0, str(mph_root / "tools"))
    import measure_mph_scenario as mph  # noqa: E402

    return mph


def shard_paths(cache: pathlib.Path, backend: str) -> set[str]:
    return {
        p.name for pattern in ("*.dll", "*.so")
        for p in (cache / backend).glob(pattern)
    }


def status_line(tag: str, status: dict, shards: int) -> None:
    print(
        f"[{tag}] shards={shards} scan_done={status['initial_cache_scan_done']} "
        f"loaded={status['banks_loaded']} rejected={status['banks_rejected']} "
        f"registered={sum(1 for b in status['loaded'] if b['registered'])} "
        f"tier3_9={status['tier3_arm9']} tier3_7={status['tier3_arm7']} "
        f"runs={status['runs_started']}/{status['runs_finished']}"
        f"/{status['runs_failed']} "
        f"native_hits={sum(b['native_hits'] for b in status['loaded'])} "
        f"err={status['last_error'][:100]!r}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mph-root", type=pathlib.Path, required=True)
    parser.add_argument("--runner", type=pathlib.Path, required=True)
    parser.add_argument("--bios", type=pathlib.Path, required=True)
    parser.add_argument("--rom", type=pathlib.Path, required=True)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--cache", type=pathlib.Path, required=True)
    parser.add_argument("--backend", default="gcc")
    parser.add_argument("--route", required=True)
    parser.add_argument("--port", type=int, default=19910)
    parser.add_argument("--live-command", required=True,
                        help="full autocompile command line the runner spawns")
    parser.add_argument("--log-dir", type=pathlib.Path, required=True)
    parser.add_argument("--boot-timeout", type=float, default=900.0)
    parser.add_argument("--hold-frames", type=int, default=3)
    parser.add_argument("--settle-frames", type=int, default=45)
    # After the route's own phases the compiler is usually still working
    # through its backlog (max-pages per run, plus a cooldown between runs), so
    # the guest is kept running until the shard count stops growing.
    parser.add_argument("--drain-vblank-step", type=int, default=300)
    parser.add_argument("--drain-idle-rounds", type=int, default=4)
    parser.add_argument("--drain-max-rounds", type=int, default=40)
    args = parser.parse_args()

    mph = load_harness(args.mph_root)
    bench = mph.bench
    if args.route not in mph.ROUTES:
        raise SystemExit(
            f"unknown route {args.route!r}; known: {sorted(mph.ROUTES)}")
    route = mph.ROUTES[args.route]

    args.log_dir.mkdir(parents=True, exist_ok=True)
    (args.cache / args.backend).mkdir(parents=True, exist_ok=True)

    extra = [
        "--boot", "direct",
        "--live-overlay-enable", "--live-overlay-auto",
        "--live-overlay-cache", str(args.cache),
        "--live-overlay-command", args.live_command,
        # A release cache is built by a machine whose whole job is to build it:
        # there is no reason to make it wait out the player-facing warm-up
        # delays before the first capture is taken.
        "--live-overlay-activation-delay-ms", "0",
        "--live-overlay-auto-delay-ms", "0",
        "--live-overlay-auto-cooldown-ms", "1000",
    ]
    env = {"NDS_LIVE_OVERLAY_BACKEND": args.backend}

    process, out_log, err_log = bench.launch_runtime(
        args.runner, args.bios, args.rom, args.port,
        args.log_dir / f"{args.route}.stdout.log",
        args.log_dir / f"{args.route}.stderr.log",
        config=args.config, save_path=None, startup_mode="automatic",
        threaded=True, renderer="auto", extra_args=extra, env_overrides=env,
    )
    print(f"route={args.route} pid={process.pid} port={args.port} "
          f"cache={args.cache}", flush=True)
    client = None
    summary: dict = {"route": args.route, "backend": args.backend}
    try:
        client = bench.wait_for_client(process, args.port)
        before = len(shard_paths(args.cache, args.backend))
        status_line("boot", client.cmd("live_overlay_status"), before)

        mph.navigate_route(client, process, route, args.hold_frames,
                           args.settle_frames, args.boot_timeout)
        status_line("route", client.cmd("live_overlay_status"),
                    len(shard_paths(args.cache, args.backend)))

        for label, target in route["vblank_windows"]:
            bench.wait_until_vblank9(client, target, args.boot_timeout, process)
            status_line(f"vblank:{label}",
                        client.cmd("live_overlay_status"),
                        len(shard_paths(args.cache, args.backend)))

        if route["insn_phases"]:
            hold = route["hold_key"]
            if hold:
                client.cmd("keys",
                           mask=bench.KEYS_RELEASED & ~(1 << bench.KEY_BITS[hold]))
            anchor = int(client.event_counts()["insn9"])
            try:
                for label, cumulative in route["insn_phases"]:
                    bench.wait_until_insn9(client, anchor + cumulative,
                                           args.boot_timeout, process)
                    status_line(f"insn:{label}",
                                client.cmd("live_overlay_status"),
                                len(shard_paths(args.cache, args.backend)))
            finally:
                if hold:
                    client.cmd("keys", mask=bench.KEYS_RELEASED)

        # ---- drain the compiler backlog ------------------------------------
        idle = 0
        rounds = 0
        seen = len(shard_paths(args.cache, args.backend))
        while idle < args.drain_idle_rounds and rounds < args.drain_max_rounds:
            rounds += 1
            base = int(client.event_counts()["vblank9"])
            bench.wait_until_vblank9(client, base + args.drain_vblank_step,
                                     args.boot_timeout, process)
            now = len(shard_paths(args.cache, args.backend))
            status = client.cmd("live_overlay_status")
            status_line(f"drain:{rounds}", status, now)
            idle = 0 if now > seen else idle + 1
            seen = now
            if status["runs_started"] == status["runs_finished"] and now == seen:
                time.sleep(0.2)

        final = client.cmd("live_overlay_status")
        summary["status"] = final
        summary["shards_before"] = before
        summary["shards_after"] = len(shard_paths(args.cache, args.backend))
        summary["shards_added"] = summary["shards_after"] - before
        status_line("FINAL", final, summary["shards_after"])
        (args.log_dir / f"{args.route}.summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8")
        if final["runs_failed"]:
            print(f"WARNING: {final['runs_failed']} autocompile run(s) failed; "
                  f"last error: {final['last_error']}", flush=True)
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass
        bench.terminate_runtime(process)
        out_log.close()
        err_log.close()
    print(f"route {args.route}: +{summary.get('shards_added', 0)} shard(s), "
          f"{summary.get('shards_after', 0)} total in {args.cache / args.backend}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
