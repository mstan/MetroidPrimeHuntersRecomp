"""Interleaved A/B comparison of two runner builds over an MPH route.

Two builds measured back-to-back on a shared machine are not comparable: host
variance drifts over minutes, so measuring all of build A and then all of
build B attributes that drift to the build. This runs the two sides
alternately - A, B, A, B, ... - so every A leg has a B leg adjacent to it, and
reports the minimum across legs per side.

Minimum, not median, because emulation time per frame has a hard floor and an
open-ended tail: everything above the floor is host interference. The minimum
of several legs is the closest estimate of what the build actually costs. The
median of the same legs is reported alongside it so a noisy set is visible
rather than hidden.

Each leg is a separate `measure_mph_scenario.py --repetitions 1` process, so
every leg starts from the same cartridge-save state.

Usage:
  py -3 tools/pgo_ab_compare.py --route adventure \
      --exe-a <baseline>/nds_runner.exe --label-a baseline \
      --exe-b <pgo>/nds_runner.exe --label-b pgo \
      --legs 3 --out perf-results/pgo-ab-adventure
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent


def run_leg(args: argparse.Namespace, exe: str, label: str, leg: int,
            out_dir: Path) -> dict:
    """Run one measurement leg and return its parsed report."""
    tag_dir = out_dir / f"leg{leg:02d}-{label}"
    # "-3" selects Python 3 from the `py` launcher; a python.exe rejects it.
    launcher = [args.python]
    if Path(args.python).stem.lower() == "py":
        launcher.append("-3")
    cmd = [
        *launcher, str(TOOLS / "measure_mph_scenario.py"),
        "--route", args.route,
        "--exe", exe,
        "--port", str(args.port),
        "--repetitions", "1",
        "--output", str(tag_dir),
    ]
    if args.rom:
        cmd += ["--rom", args.rom]
    if args.bios:
        cmd += ["--bios", args.bios]
    print(f"\n=== leg {leg} / side {label} ===", flush=True)
    completed = subprocess.run(cmd, cwd=str(ROOT))
    if completed.returncode != 0:
        raise SystemExit(
            f"leg {leg} ({label}) failed with exit code {completed.returncode}")
    report_path = tag_dir / "report.json"
    if not report_path.is_file():
        raise SystemExit(f"leg {leg} ({label}) wrote no report at {report_path}")
    return json.loads(report_path.read_text(encoding="utf-8"))


def phase_emu_ms(report: dict) -> dict[str, float]:
    """Emulation ms per frame for each phase of a single-repetition report."""
    runs = [r for r in report.get("runs", []) if r.get("valid")]
    if not runs:
        raise SystemExit("report contains no valid repetition")
    out: dict[str, float] = {}
    for phase in runs[0].get("phases", []):
        label = phase.get("label")
        value = (phase.get("phase_ms_per_frame") or {}).get("emu")
        if label and value is not None:
            out[label] = float(value)
    return out


def state_fingerprint(report: dict) -> dict:
    """Guest-state identity of a leg: event counters plus framebuffer hash."""
    runs = [r for r in report.get("runs", []) if r.get("valid")]
    if not runs:
        return {}
    return {
        "final_event_counts": runs[0].get("final_event_counts"),
        "final_framebuffer_sha256": runs[0].get("final_framebuffer_sha256"),
    }


def summarize(side_reports: list[dict]) -> dict[str, dict[str, float]]:
    per_phase: dict[str, list[float]] = {}
    for report in side_reports:
        for label, value in phase_emu_ms(report).items():
            per_phase.setdefault(label, []).append(value)
    return {
        label: {
            "min": min(values),
            "median": statistics.median(values),
            "max": max(values),
            "legs": len(values),
        }
        for label, values in per_phase.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", default="adventure")
    parser.add_argument("--exe-a", required=True)
    parser.add_argument("--exe-b", required=True)
    parser.add_argument("--label-a", default="a")
    parser.add_argument("--label-b", default="b")
    parser.add_argument("--legs", type=int, default=3,
                        help="legs per side (default 3)")
    parser.add_argument("--rom", default="")
    parser.add_argument("--bios", default="")
    parser.add_argument("--python", default="py")
    parser.add_argument("--port", type=int, default=19882,
                        help="keep clear of 19842/19843, 19870 and 27610")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    reports: dict[str, list[dict]] = {args.label_a: [], args.label_b: []}
    sides = [(args.label_a, args.exe_a), (args.label_b, args.exe_b)]
    leg = 0
    for round_index in range(args.legs):
        # Alternate which side leads each round so neither side systematically
        # occupies the same position relative to host warm-up.
        ordered = sides if round_index % 2 == 0 else list(reversed(sides))
        for label, exe in ordered:
            leg += 1
            reports[label].append(run_leg(args, exe, label, leg, out_dir))

    summary = {label: summarize(rs) for label, rs in reports.items()}

    a, b = args.label_a, args.label_b
    lines = []
    lines.append(f"route: {args.route}   legs per side: {args.legs}")
    lines.append("")
    header = (f"{'phase':<24}{a + ' min':>14}{b + ' min':>14}"
              f"{'delta':>10}{'  (median-of-legs)':>22}")
    lines.append(header)
    lines.append("-" * len(header))
    deltas = []
    for phase in summary[a]:
        if phase not in summary[b]:
            continue
        a_min = summary[a][phase]["min"]
        b_min = summary[b][phase]["min"]
        pct = (b_min - a_min) / a_min * 100.0 if a_min else 0.0
        deltas.append(pct)
        med = (f"{summary[a][phase]['median']:.3f} / "
               f"{summary[b][phase]['median']:.3f}")
        lines.append(f"{phase:<24}{a_min:>14.3f}{b_min:>14.3f}"
                     f"{pct:>9.2f}%{med:>22}")
    lines.append("")
    lines.append("emulation ms per frame; negative delta means "
                 f"{b} is faster than {a}")
    if deltas:
        lines.append(f"mean delta across phases: {statistics.mean(deltas):.2f}%")

    # End-of-run state, reported for information only - NOT a correctness gate.
    # These routes hold a key for a wall-clock duration, so the run ends at
    # whatever guest instruction the host happened to reach: two legs of the
    # *same* build finish at different counters and different final frames.
    # Comparing it across builds therefore proves nothing either way.
    #
    # The byte-exact gate is capture_mph_checkpoints.py, which anchors on
    # run_to_event(vblank9) in serve mode and so stops at exactly the same
    # guest event on every build; compare_mph_checkpoints.py then diffs both
    # register files, the mode registers and every event counter.
    fp_a = [state_fingerprint(r) for r in reports[a]]
    fp_b = [state_fingerprint(r) for r in reports[b]]
    within_a = all(f == fp_a[0] for f in fp_a)
    within_b = all(f == fp_b[0] for f in fp_b)
    across = fp_a[0] == fp_b[0]
    lines.append("")
    lines.append("end-of-run state (informational; this route is wall-clock "
                 "paced, so it varies run to run even within one build):")
    lines.append(f"  identical within {a}: {within_a}")
    lines.append(f"  identical within {b}: {within_b}")
    lines.append(f"  identical across builds: {across}")
    lines.append("  byte-exact correctness is gated by "
                 "capture_mph_checkpoints.py, not by this line")

    text = "\n".join(lines)
    print("\n" + text)
    (out_dir / "ab-summary.txt").write_text(text + "\n", encoding="utf-8")
    (out_dir / "ab-summary.json").write_text(
        json.dumps(
            {
                "route": args.route,
                "legs": args.legs,
                "sides": {a: args.exe_a, b: args.exe_b},
                "summary": summary,
                "end_state_informational": {
                    f"identical_within_{a}": within_a,
                    f"identical_within_{b}": within_b,
                    "identical_across_builds": across,
                    "note": "wall-clock paced route; not a correctness gate",
                },
                "state": {a: fp_a, b: fp_b},
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {out_dir / 'ab-summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
