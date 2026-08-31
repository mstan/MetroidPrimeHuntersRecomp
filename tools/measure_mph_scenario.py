"""Measure repeatable Metroid Prime Hunters routes through the live frontend.

This is the MPH sibling of supermario64dsrecomp/tools/measure_sm64ds_scenario.py.
Everything generic (process control, counter diffing, report shape) lives in
the framework worktree's tools/scenario_bench.py; this file owns only what is
MPH-specific: the routes, their landmarks, and the CLI.

Three routes ship:

  attract     boot -> title -> the intro/FMV windows, measured as absolute
              guest-VBlank boundaries (the same boundaries
              tools/benchmark_mph_fmv.py has been reporting).
  adventure   scenarios/adventure_start.json -> Celestial Archives gameplay,
              then ARM9-instruction-anchored gameplay phases.
  mp_bots     scenarios/multiplayer_battle_bots.json -> a local Battle against
              three bots, then instruction-anchored match phases.
  mp_bots_blank
              scenarios/mp_bots_start.json, the same match reached from a
              blank save (it walks the nickname dialog itself).

Why two different clocks:

* Menus and FMV are driven by the guest's own frame pacing, so their windows
  are absolute guest VBlank boundaries. A faster host reaches the same VBlank
  having done the same guest work.
* Gameplay phases are anchored to cumulative ARM9 instruction counts
  (event_counts.insn9). Host seconds and presented-frame counts both shrink
  when a build gets faster, which would silently measure a smaller workload;
  an instruction landmark does not move.

Each repetition launches its own process so the route always starts from the
same cartridge-save state, and only that PID is ever terminated - this machine
runs concurrent sessions of the same executable.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys
import time
from typing import Any

TARGET_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = TARGET_ROOT.parent


def _framework_root() -> pathlib.Path:
    """Prefer this target worktree's paired framework worktree.

    metroidprimehuntersrecomp-<topic> pairs with ndsrecomp-<topic>; a plain
    checkout pairs with ndsrecomp. Measuring against the wrong framework
    checkout would benchmark code that is not the code under test.
    """
    name = TARGET_ROOT.name
    candidates = []
    if "-" in name:
        candidates.append(WORKSPACE_ROOT / ("ndsrecomp-" + name.split("-", 1)[1]))
    candidates.append(WORKSPACE_ROOT / "ndsrecomp")
    for candidate in candidates:
        if (candidate / "tools" / "scenario_bench.py").exists():
            return candidate
    raise RuntimeError(
        "no framework checkout with tools/scenario_bench.py next to " + str(TARGET_ROOT)
    )


FRAMEWORK_ROOT = _framework_root()
sys.path.insert(0, str(FRAMEWORK_ROOT / "tools"))

import scenario_bench as bench  # noqa: E402


SCENARIO_DIR = TARGET_ROOT / "scenarios"

# ---------------------------------------------------------------------------
# ROUTE LANDMARKS
#
# Every constant below is a route landmark, not a tuning knob. They describe
# WHERE in the guest's own timeline a phase boundary sits, so the same guest
# work is measured on every build.
#
#   boot_vblank      absolute guest VBlank at which the title screen is live
#                    and accepts the TOUCH-TO-START tap. 7800 is the value
#                    tools/mph_overlay_route.py has used for every MPH route.
#   vblank_windows   (label, absolute guest VBlank) boundaries for menu/FMV
#                    routes. The attract boundaries are the ones
#                    tools/benchmark_mph_fmv.py already reports.
#   insn_phases      (label, cumulative ARM9 instructions since the route's
#                    anchor). PROVISIONAL until calibrated: run this harness
#                    once with --calibrate on the build under test, which
#                    replays the route and prints the measured insn9 for a
#                    fixed number of gameplay VBlanks, then paste the emitted
#                    block here. The calibration output is written to
#                    calibration.json in the run directory.
# ---------------------------------------------------------------------------

# Guest VBlank at which the TOUCH TO START title screen is up and taps land.
# Verified on 2026-08-25 against build-mph-release-050 with --boot direct:
# vblank9 6800 is still the intro FMV, 7800 shows the title with TOUCH TO
# START. It is the same landmark tools/mph_overlay_route.py uses.
TITLE_VBLANK = 7800
TITLE_TAP = (128, 96)
TITLE_SETTLE_VBLANKS = 180

# MPH-SPECIFIC BOOT QUIRK.
#
# --boot direct is the default here because the LLE firmware boot hangs on the
# MPH runner builds present in this workspace: with --boot lle the ARM9 spins
# in its BIOS around 0xFFFF03E4 while the ARM7 stays halted at 0x2F2C, DISPSTAT
# bit 3 is never set, and event_counts.vblank9 stays at 0 for hundreds of
# millions of ARM9 instructions. tools/benchmark_mph_fmv.py reproduces the same
# stall on the same build, so it is not a harness defect - but it does mean any
# measurement taken here is of the direct-boot path until that is fixed.
DEFAULT_BOOT = "direct"

# Absolute guest-VBlank boundaries through boot, the Nintendo/logo screens and
# the attract-mode FMV loop.
ATTRACT_VBLANK_WINDOWS = (
    ("attract_boot", 600),
    ("attract_0600_1200", 1200),
    ("attract_1200_1800", 1800),
    ("attract_1800_2400", 2400),
    ("attract_2400_3000", 3000),
    ("attract_3000_3600", 3600),
    ("attract_3600_4200", 4200),
)

# Gameplay phases, cumulative ARM9 instructions past the end of the scenario
# replay, covering roughly the first 60 / 360 / 960 guest VBlanks of gameplay.
#
# Measured with --calibrate on 2026-08-25 against build-mph-release-050
# (--boot direct, one instrumented pass, perf-results/smoke-adventure-calibrate):
# 99k insn9 per VBlank over the first 63 VBlanks, 115k over the next 302, 139k
# over the next 604 as the room finishes coming up. Rounded to 5 M.
ADVENTURE_INSN_PHASES = (
    ("adventure_settle", 5_000_000),
    ("adventure_walk", 40_000_000),
    ("adventure_steady", 125_000_000),
)

# NOT yet calibrated: the multiplayer route has not been through a --calibrate
# pass, so these mirror the adventure landmarks. Run
#   measure_mph_scenario.py --route mp_bots_blank --calibrate
# and paste the emitted block here before quoting any mp_bots number.
MP_BOTS_INSN_PHASES = (
    ("mp_bots_settle", 5_000_000),
    ("mp_bots_fight", 40_000_000),
    ("mp_bots_steady", 125_000_000),
)

# Guest VBlanks sampled by --calibrate after the route completes, per phase
# slot. Long enough that startup transients do not dominate the rate.
CALIBRATION_VBLANKS = (60, 300, 600)


ROUTES: dict[str, dict[str, Any]] = {
    "attract": {
        "description": "boot, title and the attract-mode FMV windows",
        "scenario": None,
        "tap_title": False,
        "vblank_windows": ATTRACT_VBLANK_WINDOWS,
        "insn_phases": (),
        "hold_key": None,
        "requires_profile_save": False,
    },
    "adventure": {
        "description": "Adventure file A into Celestial Archives gameplay",
        "scenario": "adventure_start.json",
        "tap_title": True,
        "vblank_windows": (),
        "insn_phases": ADVENTURE_INSN_PHASES,
        # Hold forward through the measured gameplay phases so the workload is
        # moving-camera rendering, not a stationary idle frame.
        "hold_key": "up",
        "requires_profile_save": False,
    },
    "mp_bots": {
        "description": "local Multi-Card Battle against three bots",
        "scenario": "multiplayer_battle_bots.json",
        "tap_title": True,
        "vblank_windows": (),
        "insn_phases": MP_BOTS_INSN_PHASES,
        "hold_key": "up",
        # This route starts from the configured-profile main menu: it does not
        # walk the nickname dialog. Pass --save-source, or use mp_bots_blank.
        "requires_profile_save": True,
    },
    "mp_bots_blank": {
        "description": "the same bot Battle reached from a blank save",
        "scenario": "mp_bots_start.json",
        "tap_title": True,
        "vblank_windows": (),
        "insn_phases": MP_BOTS_INSN_PHASES,
        "hold_key": "up",
        "requires_profile_save": False,
    },
}


def live_overlay_snapshot(client: Any) -> dict[str, Any] | None:
    """Return the small, cumulative overlay surface needed by perf gates."""
    try:
        status = client.cmd("live_overlay_status")
    except RuntimeError as error:
        if str(error).endswith("unknown cmd"):
            return None
        raise
    loaded = status.get("loaded", [])
    return {
        "enabled": bool(status.get("enabled", False)),
        "active": bool(status.get("active", False)),
        "auto_trigger": bool(status.get("auto_trigger", False)),
        "initial_cache_scan_done": bool(
            status.get("initial_cache_scan_done", False)
        ),
        "banks_loaded": int(status.get("banks_loaded", len(loaded))),
        "banks_rejected": int(status.get("banks_rejected", 0)),
        "registered_banks": sum(
            1
            for bank in loaded
            if bank.get("registered") and not bank.get("superseded")
        ),
        "native_hits": sum(int(bank.get("native_hits", 0)) for bank in loaded),
        "tier3_arm9": int(status.get("tier3_arm9", 0)),
        "tier3_arm7": int(status.get("tier3_arm7", 0)),
        "runs_started": int(status.get("runs_started", 0)),
        "runs_finished": int(status.get("runs_finished", 0)),
        "runs_failed": int(status.get("runs_failed", 0)),
        "pending_candidates": int(status.get("pending_candidates", 0)),
        "busy": bool(status.get("busy", False)),
        "last_error": str(status.get("last_error", "")),
    }


def attach_live_overlay_delta(
    result: dict[str, Any],
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    result["live_overlay_before"] = before
    result["live_overlay_after"] = after
    if before is None or after is None:
        result["live_overlay_delta"] = None
        return
    result["live_overlay_delta"] = {
        key: after[key] - before[key]
        for key in (
            "banks_loaded",
            "banks_rejected",
            "registered_banks",
            "native_hits",
            "tier3_arm9",
            "tier3_arm7",
            "runs_started",
            "runs_finished",
            "runs_failed",
        )
    }


def sha256_optional(path: pathlib.Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def measure_to_vblank9(
    client: Any,
    process: subprocess.Popen[bytes],
    label: str,
    target_vblank9: int,
    timeout_seconds: float,
    screenshot_path: pathlib.Path | None,
    adaptive_screenshot: bool,
) -> dict[str, Any]:
    before_live = live_overlay_snapshot(client)
    before_front = bench.live_stats(client)
    before_profile = bench.profile_snapshot(client)
    before_counts = client.event_counts()
    end_counts = bench.wait_until_vblank9(
        client, target_vblank9, timeout_seconds, process
    )
    after_front = bench.live_stats(client)
    after_profile = bench.profile_snapshot(client)
    result = bench.summarize_window(
        label, before_front, after_front, before_profile, after_profile
    )
    result["target_vblank9"] = target_vblank9
    result["vblank9"] = end_counts["vblank9"] - before_counts["vblank9"]
    result["insn9"] = end_counts["insn9"] - before_counts["insn9"]
    bench.finish_phase(client, result, screenshot_path, adaptive_screenshot)
    attach_live_overlay_delta(result, before_live, live_overlay_snapshot(client))
    print(
        f"{label}: {result['frames']} frames / {result['vblank9']} guest VBlanks "
        f"in {result['seconds']:.3f}s, {result['fps']:.3f} FPS",
        flush=True,
    )
    return result


def measure_to_insn9(
    client: Any,
    process: subprocess.Popen[bytes],
    label: str,
    target_insn9: int,
    requested_insn9: int,
    timeout_seconds: float,
    screenshot_path: pathlib.Path | None,
    adaptive_screenshot: bool,
) -> dict[str, Any]:
    before_live = live_overlay_snapshot(client)
    before_front = bench.live_stats(client)
    before_profile = bench.profile_snapshot(client)
    before_counts = client.event_counts()
    end_counts = bench.wait_until_insn9(
        client, target_insn9, timeout_seconds, process
    )
    after_front = bench.live_stats(client)
    after_profile = bench.profile_snapshot(client)
    result = bench.summarize_window(
        label, before_front, after_front, before_profile, after_profile
    )
    result["requested_insn9"] = requested_insn9
    result["insn9"] = end_counts["insn9"] - before_counts["insn9"]
    result["vblank9"] = end_counts["vblank9"] - before_counts["vblank9"]
    bench.finish_phase(client, result, screenshot_path, adaptive_screenshot)
    attach_live_overlay_delta(result, before_live, live_overlay_snapshot(client))
    print(
        f"{label}: {result['insn9']} ARM9 instructions and {result['frames']} "
        f"frames in {result['seconds']:.3f}s, {result['fps']:.3f} FPS",
        flush=True,
    )
    return result


def navigate_route(
    client: Any,
    process: subprocess.Popen[bytes],
    route: dict[str, Any],
    hold_frames: int,
    settle_frames: int,
    boot_timeout: float,
) -> None:
    """Reach the point where a route's measured phases begin.

    The attract route measures boot itself, so it must NOT be advanced past
    its own first boundary here; only routes that navigate into the game wait
    for the title screen first.
    """
    if route["tap_title"] or route["scenario"]:
        bench.wait_until_vblank9(client, TITLE_VBLANK, boot_timeout, process)
    if route["tap_title"]:
        bench.touch(client, *TITLE_TAP, hold_frames, process)
        bench.advance_vblanks(client, TITLE_SETTLE_VBLANKS, process)
    scenario_name = route["scenario"]
    if scenario_name:
        actions = bench.load_actions(SCENARIO_DIR / scenario_name)
        bench.replay_actions(
            client,
            actions,
            hold_frames=hold_frames,
            settle_frames=settle_frames,
            process=process,
            on_step=lambda index, label: print(
                f"  route step {index}/{len(actions)}: {label}", flush=True
            ),
        )


def calibrate(
    client: Any, process: subprocess.Popen[bytes], route_name: str
) -> dict[str, Any]:
    """Measure this route's insn9-per-VBlank rate and emit landmark counts.

    Landmarks must describe guest work, and only the guest can say how much
    work a second of its own gameplay is. This samples the live route instead
    of guessing, and prints a block ready to paste into the landmark section.
    """
    anchor = client.event_counts()
    samples = []
    previous_vblank = int(anchor["vblank9"])
    previous_insn = int(anchor["insn9"])
    cumulative = 0
    landmarks = []
    prefix = "adventure" if route_name.startswith("adventure") else "mp_bots"
    names = ("settle", "walk" if prefix == "adventure" else "fight", "steady")
    for index, vblanks in enumerate(CALIBRATION_VBLANKS):
        bench.wait_until_vblank9(
            client, previous_vblank + vblanks, 600.0, process
        )
        counts = client.event_counts()
        delta_insn = int(counts["insn9"]) - previous_insn
        delta_vblank = int(counts["vblank9"]) - previous_vblank
        cumulative += delta_insn
        samples.append(
            {
                "requested_vblanks": vblanks,
                "vblanks": delta_vblank,
                "insn9": delta_insn,
                "insn9_per_vblank": delta_insn / max(delta_vblank, 1),
                "cumulative_insn9": cumulative,
            }
        )
        # Round to 5 M so the pasted landmark reads as a deliberate landmark
        # rather than a single session's exact sample.
        landmarks.append(
            (f"{prefix}_{names[index]}", round(cumulative / 5_000_000) * 5_000_000)
        )
        previous_vblank = int(counts["vblank9"])
        previous_insn = int(counts["insn9"])
    block = "\n".join(
        f'    ("{label}", {value:_}),' for label, value in landmarks
    )
    print(
        "\ncalibrated landmarks - paste into measure_mph_scenario.py:\n"
        f"{prefix.upper()}_INSN_PHASES = (\n{block}\n)\n",
        flush=True,
    )
    return {"anchor": anchor, "samples": samples, "landmarks": landmarks}


def run_repetition(args: argparse.Namespace, repetition: int) -> dict[str, Any]:
    route = ROUTES[args.route]
    mode = "profiled" if args.profile else "plain"
    stem = f"{args.route}-{mode}-{repetition:02d}"
    save_path = None
    if args.save_source is not None:
        save_path = args.output / f"{stem}.sav"
        shutil.copy2(args.save_source, save_path)

    extra_args: list[str] = ["--boot", args.boot]
    if args.screen_layout:
        extra_args += ["--screen-layout", args.screen_layout]
    if args.adaptive_widescreen:
        extra_args += ["--adaptive-widescreen", args.adaptive_widescreen]
    if args.discover_static_misses:
        extra_args += ["--discover-static-misses"]
    extra_args += args.runner_arg

    process, stdout_file, stderr_file = bench.launch_runtime(
        args.exe,
        args.bios,
        args.rom,
        args.port,
        args.output / f"{stem}.stdout.log",
        args.output / f"{stem}.stderr.log",
        config=args.config,
        save_path=save_path,
        startup_mode="automatic",
        profiled=args.profile,
        threaded=bool(args.threaded),
        renderer=args.renderer,
        compute_readback_overlap=bool(args.compute_readback_overlap),
        extra_args=extra_args,
    )
    run: dict[str, Any] = {
        "mode": mode,
        "route": args.route,
        "repetition": repetition,
        "pid": process.pid,
        "valid": False,
        "phases": [],
    }
    client = None
    screenshot_dir = args.output / f"{stem}-screenshots"
    if args.screenshots:
        screenshot_dir.mkdir(exist_ok=True)
    try:
        client = bench.wait_for_client(process, args.port)
        navigate_route(
            client,
            process,
            route,
            args.hold_frames,
            args.settle_frames,
            args.boot_timeout,
        )

        def shot(label: str) -> pathlib.Path | None:
            if not args.screenshots:
                return None
            return screenshot_dir / f"{len(run['phases']) + 1:02d}-{label}.png"

        for label, boundary in route["vblank_windows"]:
            run["phases"].append(
                measure_to_vblank9(
                    client,
                    process,
                    label,
                    boundary,
                    args.phase_timeout,
                    shot(label),
                    args.adaptive_screenshots,
                )
            )
            if label == args.stop_after_phase:
                break

        if route["insn_phases"] or args.calibrate:
            held = route["hold_key"]
            if held and not args.no_hold:
                # Press-and-hold is a mask write plus time; there is no
                # hold-for-N command on the debug surface.
                client.cmd(
                    "keys",
                    mask=bench.KEYS_RELEASED & ~(1 << bench.KEY_BITS[held]),
                )
            try:
                if args.calibrate:
                    run["calibration"] = calibrate(client, process, args.route)
                    bench.write_json(
                        args.output / "calibration.json", run["calibration"]
                    )
                else:
                    anchor = client.event_counts()["insn9"]
                    previous = 0
                    for label, cumulative in route["insn_phases"]:
                        run["phases"].append(
                            measure_to_insn9(
                                client,
                                process,
                                label,
                                anchor + cumulative,
                                cumulative - previous,
                                args.phase_timeout,
                                shot(label),
                                args.adaptive_screenshots,
                            )
                        )
                        previous = cumulative
                        if label == args.stop_after_phase:
                            break
            finally:
                client.cmd("keys", mask=bench.KEYS_RELEASED)

        run["final_event_counts"] = client.event_counts()
        run["final_framebuffer_sha256"] = bench.framebuffer_digest(client)
        run["final_live_overlay"] = live_overlay_snapshot(client)
        if args.discover_static_misses:
            run["tier3_coverage"] = client.cmd("tier3_coverage", max=262_144)
        run["valid"] = True
        try:
            if client.cmd("frontend_exit").get("requested"):
                process.wait(timeout=30.0)
        except (ConnectionError, RuntimeError, subprocess.TimeoutExpired):
            pass
        return run
    except bench.RunnerDied as error:
        # A dead runner invalidates the repetition; it never contributes a
        # number. Flag it loudly rather than averaging a truncated route in.
        run["error"] = f"runner died: {error}"
        print(f"[discarded] repetition {repetition}: {run['error']}", flush=True)
        return run
    except (TimeoutError, RuntimeError, ConnectionError, OSError) as error:
        run["error"] = f"{type(error).__name__}: {error}"
        print(f"[discarded] repetition {repetition}: {run['error']}", flush=True)
        return run
    finally:
        if client is not None:
            client.close()
        bench.terminate_runtime(process)
        run["returncode"] = process.returncode
        stdout_file.close()
        stderr_file.close()


DEFAULT_BUILD = "runner/build-mph-release-050/nds_runner.exe"


def default_exe() -> pathlib.Path:
    """Prefer a build in the paired framework worktree, else the main one.

    A topic worktree usually has no build directory of its own yet; falling
    back keeps the harness runnable, and the report records the exact path
    and SHA-256 of whatever was actually measured.
    """
    for root in (FRAMEWORK_ROOT, WORKSPACE_ROOT / "ndsrecomp"):
        candidate = root / DEFAULT_BUILD
        if candidate.exists():
            return candidate
    return FRAMEWORK_ROOT / DEFAULT_BUILD


def default_rom() -> pathlib.Path:
    local = TARGET_ROOT / "Metroid Prime Hunters.nds"
    if local.exists():
        return local
    return WORKSPACE_ROOT / "metroidprimehuntersrecomp" / "Metroid Prime Hunters.nds"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--route", choices=sorted(ROUTES), default="adventure")
    parser.add_argument(
        "--exe",
        type=pathlib.Path,
        default=default_exe(),
    )
    parser.add_argument(
        "--bios", type=pathlib.Path, default=WORKSPACE_ROOT / "ndsrecomp" / "bios"
    )
    parser.add_argument("--rom", type=pathlib.Path, default=default_rom())
    parser.add_argument("--config", type=pathlib.Path, default=TARGET_ROOT / "game.toml")
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="run directory (default: perf-results/<timestamp>-<route>-<mode>)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=19870,
        help="debug TCP port; keep clear of 19842/19843 (oracle) and 27610",
    )
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--boot",
        choices=("direct", "lle"),
        default=DEFAULT_BOOT,
        help="guest boot path; see the DEFAULT_BOOT note - lle currently "
        "stalls before the first VBlank on the available MPH builds",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="arm NDS_PROFILE_GPU/NDS_PROFILE_SCHED so gpu2d/gpu3d/scheduler "
        "shares are populated (adds measurement overhead; off by default)",
    )
    parser.add_argument("--screenshots", action="store_true")
    parser.add_argument("--adaptive-screenshots", action="store_true")
    parser.add_argument("--threaded", type=int, choices=(0, 1), default=1)
    parser.add_argument(
        "--renderer", choices=("auto", "soft", "compute"), default="auto"
    )
    parser.add_argument(
        "--compute-readback-overlap", type=int, choices=(0, 1), default=1
    )
    parser.add_argument(
        "--screen-layout",
        choices=("stacked", "separate"),
        help="override game.toml's host layout",
    )
    parser.add_argument(
        "--adaptive-widescreen",
        choices=("none", "top", "bottom", "both"),
        help="override game.toml's adaptive surface",
    )
    parser.add_argument(
        "--save-source",
        type=pathlib.Path,
        help="cartridge save copied fresh into every repetition (required by "
        "routes that start from a configured profile)",
    )
    parser.add_argument("--hold-frames", type=int, default=3)
    parser.add_argument("--settle-frames", type=int, default=45)
    parser.add_argument(
        "--boot-timeout",
        type=float,
        default=600.0,
        help="seconds allowed to reach the title screen",
    )
    parser.add_argument(
        "--phase-timeout",
        type=float,
        default=600.0,
        help="seconds allowed for one measured phase",
    )
    parser.add_argument("--stop-after-phase")
    parser.add_argument(
        "--no-hold",
        action="store_true",
        help="do not hold forward during instruction-anchored phases",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="replay the route, sample its insn9 rate, and print landmark "
        "constants instead of measuring the shipped phases",
    )
    parser.add_argument(
        "--discover-static-misses",
        action="store_true",
        help="record Tier-3 entry coverage (diagnostic; distorts timing)",
    )
    parser.add_argument(
        "--runner-arg",
        action="append",
        default=[],
        help="extra argument passed through to nds_runner.exe",
    )
    parser.add_argument("--tag", help="output directory suffix")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.exe = args.exe.resolve()
    args.bios = args.bios.resolve()
    args.rom = args.rom.resolve()
    args.config = args.config.resolve() if args.config else None
    if args.save_source is not None:
        args.save_source = args.save_source.resolve()
    for required in (args.exe, args.bios, args.rom, args.config, args.save_source):
        if required is not None and not required.exists():
            raise FileNotFoundError(required)
    if args.repetitions < 1:
        raise ValueError("--repetitions must be positive")

    route = ROUTES[args.route]
    if route["requires_profile_save"] and args.save_source is None:
        print(
            f"warning: route {args.route!r} starts from the configured-profile "
            "main menu and no --save-source was given; the nickname dialog will "
            "swallow the first taps. Use --route mp_bots_blank for a blank save.",
            file=sys.stderr,
        )

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    mode = "profiled" if args.profile else "plain"
    tag = args.tag or f"{timestamp}-{args.route}-{mode}"
    args.output = (
        args.output.resolve()
        if args.output
        else TARGET_ROOT / "perf-results" / tag
    )
    args.output.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "schema": 1,
        "created_local": timestamp,
        "title": "Metroid Prime Hunters",
        "route": {
            "name": args.route,
            "description": route["description"],
            "scenario": route["scenario"],
            "scenario_actions": (
                bench.load_actions(SCENARIO_DIR / route["scenario"])
                if route["scenario"]
                else []
            ),
            "title_vblank": TITLE_VBLANK,
            "title_tap": list(TITLE_TAP),
            "vblank_windows": [
                {"label": label, "absolute_vblank9": value}
                for label, value in route["vblank_windows"]
            ],
            "insn9_phases": [
                {"label": label, "cumulative_insn9": value}
                for label, value in route["insn_phases"]
            ],
            "hold_key": None if args.no_hold else route["hold_key"],
            "hold_frames": args.hold_frames,
            "settle_frames": args.settle_frames,
            "phase_timeout_seconds": args.phase_timeout,
        },
        "build": {
            "executable": str(args.exe),
            "executable_sha256": bench.sha256_file(args.exe),
            "config": str(args.config) if args.config else None,
            "config_sha256": sha256_optional(args.config),
            "rom": str(args.rom),
            "rom_sha256": sha256_optional(args.rom),
            "framework_root": str(FRAMEWORK_ROOT),
            "framework_revision": bench.git_revision(FRAMEWORK_ROOT),
            "target_revision": bench.git_revision(TARGET_ROOT),
            "profiled": args.profile,
            "boot": args.boot,
            "renderer": args.renderer,
            "gpu3d_threaded": bool(args.threaded),
            "compute_readback_overlap": bool(args.compute_readback_overlap),
            "screen_layout": args.screen_layout or "from game.toml",
            "adaptive_widescreen": args.adaptive_widescreen or "from game.toml",
            "save_source": str(args.save_source) if args.save_source else None,
            "save_source_sha256": sha256_optional(args.save_source),
            "discover_static_misses": args.discover_static_misses,
            "runner_args": list(args.runner_arg),
        },
        "host": bench.host_description(),
        "runs": [],
    }

    partial = args.output / "report.partial.json"
    try:
        for repetition in range(1, args.repetitions + 1):
            report["runs"].append(run_repetition(args, repetition))
            report["summary"] = bench.aggregate_runs(report["runs"])
            bench.write_json(partial, report)
    finally:
        report["summary"] = bench.aggregate_runs(report["runs"])
        report_path = args.output / "report.json"
        bench.write_json(report_path, report)
    if partial.exists():
        partial.unlink()

    discarded = report["summary"].get("discarded_runs", 0)
    if discarded and not args.calibrate:
        print(f"warning: {discarded} repetition(s) discarded", file=sys.stderr)
    print(report_path)
    if args.calibrate:
        # A calibration pass produces landmarks, not phases; an empty phase
        # list is the expected outcome, not a failed measurement.
        return 0 if any(run.get("calibration") for run in report["runs"]) else 1
    return 0 if report["summary"].get("run_count") else 1


if __name__ == "__main__":
    raise SystemExit(main())
