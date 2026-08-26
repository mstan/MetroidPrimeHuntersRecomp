"""Sample native instruction pointers during one MPH route phase.

The MPH sibling of supermario64dsrecomp/tools/profile_sm64ds_worst_phase.py.
It navigates with the same route replayer measure_mph_scenario.py uses, so
"the slow phase" means exactly the phase that harness reports as slow, then
attaches tools/windows_rip_sampler.cpp to that one PID for that one window.

The sampler is a window-scoped tool, not an observability substitute: it is
started at the phase boundary and stopped at the next one, and it samples
only the process this script spawned. Everything else the report contains
(tier-3, dispatch, frontend counters) is read from the runner's always-on
accumulators.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
import time
from typing import Any

import measure_mph_scenario as scenario

sys.path.insert(0, str(scenario.FRAMEWORK_ROOT / "tools"))
import scenario_bench as bench  # noqa: E402


TOOLS_DIR = pathlib.Path(__file__).resolve().parent
SAMPLER_SOURCE = TOOLS_DIR / "windows_rip_sampler.cpp"
SAMPLER_EXE = TOOLS_DIR / "windows_rip_sampler.exe"


def all_phase_labels() -> list[str]:
    labels: list[str] = []
    for route in scenario.ROUTES.values():
        labels += [label for label, _ in route["vblank_windows"]]
        labels += [label for label, _ in route["insn_phases"]]
    return sorted(set(labels))


def route_for_phase(name: str, requested_route: str | None) -> str:
    if requested_route:
        return requested_route
    for route_name, route in scenario.ROUTES.items():
        labels = [label for label, _ in route["vblank_windows"]]
        labels += [label for label, _ in route["insn_phases"]]
        if name in labels:
            return route_name
    raise SystemExit(f"phase {name!r} belongs to no route")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        required=True,
        choices=all_phase_labels(),
        help="route phase to sample (every earlier phase is replayed first)",
    )
    parser.add_argument(
        "--route",
        choices=sorted(scenario.ROUTES),
        help="disambiguate a phase label shared by several routes",
    )
    parser.add_argument(
        "--exe",
        type=pathlib.Path,
        default=scenario.default_exe(),
    )
    parser.add_argument(
        "--bios",
        type=pathlib.Path,
        default=scenario.WORKSPACE_ROOT / "ndsrecomp" / "bios",
    )
    parser.add_argument("--rom", type=pathlib.Path, default=scenario.default_rom())
    parser.add_argument(
        "--config", type=pathlib.Path, default=scenario.TARGET_ROOT / "game.toml"
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--port", type=int, default=19871)
    parser.add_argument(
        "--boot",
        choices=("direct", "lle"),
        default=scenario.DEFAULT_BOOT,
        help="guest boot path; matches measure_mph_scenario.py's default",
    )
    parser.add_argument("--interval-us", type=int, default=1000)
    parser.add_argument("--hold-frames", type=int, default=3)
    parser.add_argument("--settle-frames", type=int, default=45)
    parser.add_argument("--boot-timeout", type=float, default=600.0)
    parser.add_argument("--phase-timeout", type=float, default=600.0)
    parser.add_argument("--save-source", type=pathlib.Path)
    parser.add_argument(
        "--screen-layout", choices=("stacked", "separate"), default=None
    )
    parser.add_argument(
        "--adaptive-widescreen",
        choices=("none", "top", "bottom", "both"),
        default=None,
    )
    parser.add_argument(
        "--renderer", choices=("auto", "soft", "compute"), default="auto"
    )
    parser.add_argument("--threaded", type=int, choices=(0, 1), default=1)
    parser.add_argument(
        "--no-hold",
        action="store_true",
        help="do not hold forward during instruction-anchored phases",
    )
    parser.add_argument(
        "--no-symbolize",
        action="store_true",
        help="keep the raw RIP samples but skip the slower symbol pass",
    )
    parser.add_argument(
        "--discover-static-misses",
        action="store_true",
        help="record Tier-3 entry coverage (diagnostic run; distorts timing)",
    )
    parser.add_argument("--runner-arg", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    route_name = route_for_phase(args.phase, args.route)
    route = scenario.ROUTES[route_name]
    executable = args.exe.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    bench.build_sampler(SAMPLER_SOURCE, SAMPLER_EXE)

    save_path = None
    if args.save_source is not None:
        save_path = output_dir / "cartridge.sav"
        shutil.copy2(args.save_source.resolve(), save_path)

    extra_args: list[str] = ["--boot", args.boot]
    if args.screen_layout:
        extra_args += ["--screen-layout", args.screen_layout]
    if args.adaptive_widescreen:
        extra_args += ["--adaptive-widescreen", args.adaptive_widescreen]
    if args.discover_static_misses:
        extra_args += ["--discover-static-misses"]
    extra_args += args.runner_arg

    process, stdout_file, stderr_file = bench.launch_runtime(
        executable,
        args.bios.resolve(),
        args.rom.resolve(),
        args.port,
        output_dir / "runner.stdout.log",
        output_dir / "runner.stderr.log",
        config=args.config.resolve() if args.config else None,
        save_path=save_path,
        startup_mode="automatic",
        profiled=False,
        threaded=bool(args.threaded),
        renderer=args.renderer,
        extra_args=extra_args,
    )
    client = None
    sampler = None
    samples_path = output_dir / "rip-samples.csv"
    try:
        client = bench.wait_for_client(process, args.port)
        scenario.navigate_route(
            client,
            process,
            route,
            args.hold_frames,
            args.settle_frames,
            args.boot_timeout,
        )

        phase: dict[str, Any] | None = None
        before_tier3: dict[str, Any] | None = None

        for label, boundary in route["vblank_windows"]:
            if label == args.phase:
                before_tier3 = client.cmd("static_coverage")
                sampler = bench.start_sampler(
                    SAMPLER_EXE, process.pid, samples_path, args.interval_us
                )
            measured = scenario.measure_to_vblank9(
                client,
                process,
                label,
                boundary,
                args.phase_timeout,
                None,
                False,
            )
            if label == args.phase:
                phase = measured
                break

        if phase is None and route["insn_phases"]:
            held = route["hold_key"]
            if held and not args.no_hold:
                client.cmd(
                    "keys",
                    mask=bench.KEYS_RELEASED & ~(1 << bench.KEY_BITS[held]),
                )
            try:
                anchor = client.event_counts()["insn9"]
                previous = 0
                for label, cumulative in route["insn_phases"]:
                    if label == args.phase:
                        before_tier3 = client.cmd("static_coverage")
                        sampler = bench.start_sampler(
                            SAMPLER_EXE, process.pid, samples_path, args.interval_us
                        )
                    measured = scenario.measure_to_insn9(
                        client,
                        process,
                        label,
                        anchor + cumulative,
                        cumulative - previous,
                        args.phase_timeout,
                        None,
                        False,
                    )
                    previous = cumulative
                    if label == args.phase:
                        phase = measured
                        break
            finally:
                client.cmd("keys", mask=bench.KEYS_RELEASED)

        if sampler is None or phase is None or before_tier3 is None:
            raise RuntimeError(f"phase {args.phase!r} was never reached")

        after_tier3 = client.cmd("static_coverage")
        tier3_coverage = (
            client.cmd("tier3_coverage", max=262_144)["entries"]
            if args.discover_static_misses
            else []
        )
        tier3_hot_bytes = []
        if args.discover_static_misses:
            for entry in sorted(
                tier3_coverage, key=lambda item: item["hits"], reverse=True
            )[:32]:
                memory = client.cmd(
                    "read_mem", cpu=entry["cpu"], addr=entry["pc"], len=64
                )
                tier3_hot_bytes.append({**entry, "bytes": memory["hex"]})

        bench.stop_sampler(sampler)
        sampler = None

        runtime_base, by_thread = bench.parse_samples(samples_path)
        preferred_base = bench.preferred_image_base(executable)
        report: dict[str, Any] = {
            "created_local": time.strftime("%Y%m%d-%H%M%S"),
            "title": "Metroid Prime Hunters",
            "route": route_name,
            "executable": str(executable),
            "executable_sha256": bench.sha256_file(executable),
            "phase": phase,
            "tier3_delta": bench.subtract(after_tier3, before_tier3),
            "tier3_coverage": tier3_coverage,
            "tier3_hot_bytes": tier3_hot_bytes,
            "sampler": {
                "interval_us": args.interval_us,
                "runtime_image_base": f"0x{runtime_base:x}",
                "preferred_image_base": f"0x{preferred_base:x}",
            },
        }
        bench.write_json(output_dir / "report.partial.json", report)
        if not args.no_symbolize:
            report.update(
                bench.symbolize(executable, runtime_base, preferred_base, by_thread)
            )
        report_path = output_dir / "report.json"
        bench.write_json(report_path, report)
        (output_dir / "report.partial.json").unlink(missing_ok=True)
        print(report_path)
        return 0
    finally:
        if sampler is not None and sampler.poll() is None:
            try:
                bench.stop_sampler(sampler, timeout=10.0)
            except Exception:  # noqa: BLE001 - cleanup must not mask the cause
                sampler.kill()
        if client is not None:
            client.close()
        bench.terminate_runtime(process)
        stdout_file.close()
        stderr_file.close()


if __name__ == "__main__":
    raise SystemExit(main())
