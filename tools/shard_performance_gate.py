#!/usr/bin/env python3
"""Run and evaluate the MPH fresh-install live-shard performance matrix.

The four legs are intentionally same-binary, same-route fresh processes:
overlay disabled, overlay enabled with an empty cache and no compiler, a
fresh copy of the release GCC cache, and runtime TCC starting empty.  The
evaluator refuses reports whose immutable inputs or route landmarks differ.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import shutil
import statistics
import subprocess
import sys
from typing import Any


MODES = ("disabled", "empty", "prebuilt_gcc", "runtime_tcc")
DISPATCH_BANDS = ((0, 15_000), (15_000, 25_000), (25_000, 40_000),
                  (40_000, math.inf))
DEFAULT_THRESHOLDS = {
    "min_steady_fps": 58.0,
    "empty_max_emu_ratio": 1.05,
    "empty_max_emu_slack_ms": 0.15,
    "empty_max_poll_ms_per_frame": 0.25,
    "native_max_emu_ratio": 1.05,
    "native_max_emu_slack_ms": 0.25,
    "native_min_steady_emu_improvement_ms": 0.25,
}


def read_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cache_inventory(root: pathlib.Path) -> dict[str, Any]:
    """Hash only runtime cache inputs, excluding logs and gate reports."""
    files = []
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (".dll", ".so"):
                continue
            files.append({
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":"))
    providers: set[str] = set()
    index = root / "live-index.json"
    if index.is_file():
        for entry in read_json(index).get("captures", {}).values():
            if isinstance(entry, dict) and entry.get("provider_id"):
                providers.add(str(entry["provider_id"]))
    return {
        "root": str(root.resolve()),
        "native_file_count": len(files),
        "native_bytes": sum(item["bytes"] for item in files),
        "native_inventory_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "provider_identities": sorted(providers),
        "files": files,
    }


def report_identity(report: dict[str, Any]) -> dict[str, Any]:
    build = report["build"]
    return {
        "executable_sha256": build.get("executable_sha256"),
        "config_sha256": build.get("config_sha256"),
        "rom_sha256": build.get("rom_sha256"),
        "save_source_sha256": build.get("save_source_sha256"),
        "framework_revision": build.get("framework_revision"),
        "target_revision": build.get("target_revision"),
        "profiled": build.get("profiled"),
        "boot": build.get("boot"),
        "renderer": build.get("renderer"),
        "gpu3d_threaded": build.get("gpu3d_threaded"),
        "compute_readback_overlap": build.get("compute_readback_overlap"),
        "screen_layout": build.get("screen_layout"),
        "adaptive_widescreen": build.get("adaptive_widescreen"),
        "route": report.get("route"),
        "host": report.get("host"),
    }


def nested_number(value: Any, *path: str) -> float:
    for key in path:
        if not isinstance(value, dict):
            return 0.0
        value = value.get(key, 0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def tier3_instructions(phase: dict[str, Any], cpu: int) -> float:
    data = phase.get("tier3_delta", {})
    for key in (f"tier3_insns{cpu}", f"instructions{cpu}"):
        if isinstance(data.get(key), (int, float)):
            return float(data[key])
    block = data.get(f"arm{cpu}", {}) if isinstance(data, dict) else {}
    return nested_number(block, "instructions")


def phase_metric(mode: str, repetition: int,
                 phase: dict[str, Any]) -> dict[str, Any]:
    frames = max(int(phase.get("frames", 0)), 1)
    dispatch = phase.get("dispatch_delta", {})
    attrib = phase.get("emu_attrib_ms_per_frame", {})
    live = phase.get("live_overlay_after") or {}
    delta = phase.get("live_overlay_delta") or {}
    arm9_dispatch = nested_number(dispatch, "arm9", "dispatch_total") / frames
    result = {
        "mode": mode,
        "repetition": repetition,
        "phase": phase.get("label"),
        "frames": int(phase.get("frames", 0)),
        "fps": float(phase.get("fps", 0)),
        "emu_ms_per_frame": nested_number(phase, "phase_ms_per_frame", "emu"),
        "overlay_poll_ms_per_frame": float(attrib.get("overlay_poll", 0)),
        "exec_arm9_ms_per_frame": float(attrib.get("exec_arm9", 0)),
        "exec_arm7_ms_per_frame": float(attrib.get("exec_arm7", 0)),
        "tier3_arm9_instructions": tier3_instructions(phase, 9),
        "tier3_arm7_instructions": tier3_instructions(phase, 7),
        "native_hits": int(delta.get("native_hits", 0)),
        "banks_loaded": int(live.get("banks_loaded", 0)),
        "registered_banks": int(live.get("registered_banks", 0)),
        "dispatch_arm9_per_frame": arm9_dispatch,
        "dispatch_arm7_per_frame": (
            nested_number(dispatch, "arm7", "dispatch_total") / frames
        ),
        "crs_hit_arm9_per_frame": (
            nested_number(dispatch, "arm9", "crs_hit") / frames
        ),
        "crs_miss_arm9_per_frame": (
            nested_number(dispatch, "arm9", "crs_miss") / frames
        ),
        "crs_hit_arm7_per_frame": (
            nested_number(dispatch, "arm7", "crs_hit") / frames
        ),
        "crs_miss_arm7_per_frame": (
            nested_number(dispatch, "arm7", "crs_miss") / frames
        ),
    }
    result["dispatch_band"] = next(
        f"{low}-{('inf' if math.isinf(high) else int(high))}"
        for low, high in DISPATCH_BANDS if low <= arm9_dispatch < high
    )
    return result


def has_required_metrics(phase: dict[str, Any]) -> bool:
    attrib = phase.get("emu_attrib_ms_per_frame")
    dispatch = phase.get("dispatch_delta")
    tier3 = phase.get("tier3_delta")
    live = phase.get("live_overlay_delta")
    if not isinstance(attrib, dict) or not all(
            key in attrib for key in ("overlay_poll", "exec_arm9", "exec_arm7")):
        return False
    if not isinstance(dispatch, dict):
        return False
    for cpu in ("arm9", "arm7"):
        block = dispatch.get(cpu)
        if not isinstance(block, dict) or not all(
                key in block for key in ("dispatch_total", "crs_hit", "crs_miss")):
            return False
    if not isinstance(tier3, dict) or not all(
            key in tier3 for key in ("tier3_insns9", "tier3_insns7")):
        return False
    return isinstance(live, dict) and "native_hits" in live


def median_by_phase(metrics: list[dict[str, Any]], mode: str,
                    field: str) -> dict[str, float]:
    labels = sorted({m["phase"] for m in metrics if m["mode"] == mode})
    return {
        label: statistics.median(
            m[field] for m in metrics
            if m["mode"] == mode and m["phase"] == label
        )
        for label in labels
    }


def final_status(report: dict[str, Any]) -> dict[str, Any]:
    runs = [run for run in report.get("runs", []) if run.get("valid")]
    return runs[0].get("final_live_overlay") or {} if len(runs) == 1 else {}


def phase_labels_from_route(report: dict[str, Any]) -> list[str]:
    route = report.get("route", {})
    if not isinstance(route, dict):
        return []
    values = []
    for item in route.get("vblank_windows", []):
        if isinstance(item, dict) and isinstance(item.get("label"), str):
            values.append(item["label"])
    for item in route.get("insn9_phases", []):
        if isinstance(item, dict) and isinstance(item.get("label"), str):
            values.append(item["label"])
        elif isinstance(item, str):
            values.append(item)
    return values


def add_check(checks: list[dict[str, Any]], name: str, passed: bool,
              detail: str) -> None:
    checks.append({"name": name, "pass": bool(passed), "detail": detail})


def evaluate_manifest(path: pathlib.Path) -> dict[str, Any]:
    manifest = read_json(path)
    base = path.parent
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update(manifest.get("thresholds", {}))
    legs = manifest.get("legs", [])
    checks: list[dict[str, Any]] = []
    reports: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen: set[tuple[str, int]] = set()
    identities = []
    expected_phase_labels: list[str] = []

    for leg in legs:
        mode = str(leg.get("mode"))
        repetition = int(leg.get("repetition", 0))
        seen.add((mode, repetition))
        report_path = pathlib.Path(leg["report"])
        if not report_path.is_absolute():
            report_path = base / report_path
        if not report_path.is_file():
            add_check(checks, f"{mode}.r{repetition}.report_exists", False,
                      f"missing report: {report_path}")
            continue
        report = read_json(report_path)
        labels = phase_labels_from_route(report)
        if not expected_phase_labels and labels:
            expected_phase_labels = labels
        reports.append((leg, report))
        identities.append(report_identity(report))

    repetitions = int(manifest.get("repetitions", 0))
    expected = {(mode, rep) for mode in MODES
                for rep in range(1, repetitions + 1)}
    add_check(checks, "manifest_kind",
              manifest.get("kind") == "mph-shard-performance-matrix",
              f"kind={manifest.get('kind')!r}")
    add_check(checks, "minimum_repetitions", repetitions >= 3,
              f"repetitions={repetitions}")
    add_check(checks, "complete_matrix",
              seen == expected and len(legs) == len(expected),
              f"legs={len(legs)} unique={len(seen)} expected={len(expected)}")
    add_check(checks, "same_build_route_host",
              bool(identities) and all(value == identities[0]
                                       for value in identities[1:]),
              "all immutable build, ROM, save, route, settings and host fields match")
    add_check(checks, "configured_bot_route",
              manifest.get("route") in ("mp_bots", "mp_bots_blank")
              and all(report.get("route", {}).get("name") == manifest.get("route")
                      for _, report in reports),
              f"route={manifest.get('route')!r}")

    metrics = []
    for leg, report in reports:
        mode = leg["mode"]
        rep = int(leg["repetition"])
        add_check(checks, f"{mode}.r{rep}.exit_code",
                  "exit_code" in leg and int(leg["exit_code"]) == 0,
                  f"exit_code={leg.get('exit_code', 'missing')}")
        runs = report.get("runs", [])
        valid = [run for run in runs if run.get("valid") and run.get("phases")]
        add_check(checks, f"{mode}.r{rep}.fresh_process",
                  len(runs) == 1 and len(valid) == 1,
                  f"runs={len(runs)} valid={len(valid)}")
        if not valid:
            continue
        labels = [phase.get("label") for phase in valid[0]["phases"]]
        add_check(checks, f"{mode}.r{rep}.phase_landmarks",
                  bool(expected_phase_labels) and labels == expected_phase_labels,
                  f"labels={labels!r} expected={expected_phase_labels!r}")
        add_check(checks, f"{mode}.r{rep}.metric_surface",
                  all(has_required_metrics(phase)
                      for phase in valid[0]["phases"]),
                  "requires emu attribution, Tier-3, native-hit, dispatch and CRS counters")
        metrics.extend(phase_metric(mode, rep, phase)
                       for phase in valid[0]["phases"])
        status = final_status(report)
        before = leg.get("cache_before", {})
        if mode in ("empty", "runtime_tcc"):
            add_check(checks, f"{mode}.r{rep}.cold_cache",
                      before.get("native_file_count") == 0,
                      f"native_files={before.get('native_file_count')}")
        if mode == "disabled":
            add_check(checks, f"{mode}.r{rep}.contract",
                      status.get("enabled") is False,
                      f"enabled={status.get('enabled')}")
        elif mode == "empty":
            ok = (status.get("enabled") is True
                  and status.get("auto_trigger") is False
                  and int(status.get("banks_loaded", 0)) == 0
                  and int(status.get("native_hits", 0)) == 0)
            add_check(checks, f"{mode}.r{rep}.contract", ok,
                      f"loaded={status.get('banks_loaded')} hits={status.get('native_hits')}")
        elif mode == "prebuilt_gcc":
            after = leg.get("cache_after", {})
            ok = (before.get("native_file_count", 0) > 0
                  and before.get("native_inventory_sha256") == after.get(
                      "native_inventory_sha256")
                  and int(status.get("registered_banks", 0)) > 0
                  and int(status.get("native_hits", 0)) > 0
                  and int(status.get("banks_rejected", 0)) == 0)
            add_check(checks, f"{mode}.r{rep}.native_hits", ok,
                      f"files={before.get('native_file_count')} registered="
                      f"{status.get('registered_banks')} hits={status.get('native_hits')}")
        elif mode == "runtime_tcc":
            after = leg.get("cache_after", {})
            ok = (status.get("auto_trigger") is True
                  and int(status.get("runs_started", 0)) > 0
                  and int(status.get("runs_finished", 0)) > 0
                  and int(status.get("runs_failed", 0)) == 0
                  and int(status.get("registered_banks", 0)) > 0
                  and int(status.get("native_hits", 0)) > 0
                  and int(after.get("native_file_count", 0)) > 0
                  and not status.get("busy")
                  and int(status.get("pending_candidates", 0)) == 0)
            add_check(checks, f"{mode}.r{rep}.converged", ok,
                      f"runs={status.get('runs_started')}/{status.get('runs_finished')}/"
                      f"{status.get('runs_failed')} registered={status.get('registered_banks')} "
                      f"hits={status.get('native_hits')} busy={status.get('busy')}")

    phases = expected_phase_labels or sorted({m["phase"] for m in metrics})
    per_mode_phase = {
        mode: {
            field: median_by_phase(metrics, mode, field)
            for field in ("fps", "emu_ms_per_frame", "overlay_poll_ms_per_frame",
                          "exec_arm9_ms_per_frame", "exec_arm7_ms_per_frame",
                          "tier3_arm9_instructions", "tier3_arm7_instructions",
                          "native_hits", "dispatch_arm9_per_frame",
                          "dispatch_arm7_per_frame", "crs_hit_arm9_per_frame",
                          "crs_miss_arm9_per_frame")
        } for mode in MODES
    }

    for phase in phases:
        disabled = per_mode_phase["disabled"]["emu_ms_per_frame"].get(phase)
        empty = per_mode_phase["empty"]["emu_ms_per_frame"].get(phase)
        poll = per_mode_phase["empty"]["overlay_poll_ms_per_frame"].get(phase)
        if disabled is not None and empty is not None:
            limit = (disabled * thresholds["empty_max_emu_ratio"]
                     + thresholds["empty_max_emu_slack_ms"])
            add_check(checks, f"empty.{phase}.emu_overhead", empty <= limit,
                      f"empty={empty:.3f} disabled={disabled:.3f} limit={limit:.3f} ms/f")
        if poll is not None:
            add_check(checks, f"empty.{phase}.idle_poll", poll <= thresholds[
                "empty_max_poll_ms_per_frame"],
                f"poll={poll:.3f} limit={thresholds['empty_max_poll_ms_per_frame']:.3f} ms/f")
        if empty is None:
            continue
        for mode in ("prebuilt_gcc", "runtime_tcc"):
            candidate = per_mode_phase[mode]["emu_ms_per_frame"].get(phase)
            if candidate is None:
                continue
            # Runtime compilation may hitch earlier phases; steady-state is the
            # final instruction-anchored phase after convergence.
            if mode == "runtime_tcc" and phase != phases[-1]:
                continue
            limit = (empty * thresholds["native_max_emu_ratio"]
                     + thresholds["native_max_emu_slack_ms"])
            add_check(checks, f"{mode}.{phase}.emu_regression",
                      candidate <= limit,
                      f"candidate={candidate:.3f} empty={empty:.3f} limit={limit:.3f} ms/f")

    if phases:
        steady = phases[-1]
        steady_bands = {
            mode: {
                m["dispatch_band"] for m in metrics
                if m["mode"] == mode and m["phase"] == steady
            } for mode in MODES
        }
        common_bands = set.intersection(*steady_bands.values()) if all(
            steady_bands.values()) else set()
        add_check(checks, f"{steady}.matched_dispatch_band",
                  bool(common_bands),
                  "steady dispatch bands by mode: " + ", ".join(
                      f"{mode}={sorted(values)}"
                      for mode, values in steady_bands.items()))
        empty_emu = per_mode_phase["empty"]["emu_ms_per_frame"].get(steady)
        for mode in ("prebuilt_gcc", "runtime_tcc"):
            fps = per_mode_phase[mode]["fps"].get(steady, 0)
            add_check(checks, f"{mode}.{steady}.steady_fps",
                      fps >= thresholds["min_steady_fps"],
                      f"fps={fps:.3f} minimum={thresholds['min_steady_fps']:.3f}")
            hits = [
                m["native_hits"] for m in metrics
                if m["mode"] == mode and m["phase"] == steady
            ]
            add_check(checks, f"{mode}.{steady}.steady_native_hits",
                      bool(hits) and all(hit > 0 for hit in hits),
                      f"native_hit_deltas={hits}")
            candidate_emu = per_mode_phase[mode]["emu_ms_per_frame"].get(steady)
            if empty_emu is not None and candidate_emu is not None:
                improvement = empty_emu - candidate_emu
                minimum = thresholds["native_min_steady_emu_improvement_ms"]
                add_check(checks, f"{mode}.{steady}.steady_emu_improvement",
                          improvement >= minimum,
                          f"improvement={improvement:.3f} minimum={minimum:.3f} ms/f")

    bands = []
    for low, high in DISPATCH_BANDS:
        label = f"{low}-{('inf' if math.isinf(high) else int(high))}"
        row: dict[str, Any] = {"band": label, "modes": {}}
        for mode in MODES:
            samples = [m for m in metrics if m["mode"] == mode
                       and m["dispatch_band"] == label]
            if samples:
                row["modes"][mode] = {
                    "samples": len(samples),
                    "median_emu_ms_per_frame": statistics.median(
                        m["emu_ms_per_frame"] for m in samples),
                    "median_overlay_poll_ms_per_frame": statistics.median(
                        m["overlay_poll_ms_per_frame"] for m in samples),
                    "median_native_hits": statistics.median(
                        m["native_hits"] for m in samples),
                }
        if row["modes"]:
            row["matched_all_modes"] = all(mode in row["modes"] for mode in MODES)
            bands.append(row)

    prebuilt_legs = [leg for leg in legs if leg.get("mode") == "prebuilt_gcc"]
    inventories = [leg.get("cache_before", {}) for leg in prebuilt_legs]
    same_inventory = (bool(inventories) and all(
        inv.get("native_inventory_sha256") == inventories[0].get(
            "native_inventory_sha256") for inv in inventories[1:]))
    add_check(checks, "stable_prebuilt_inventory", same_inventory,
              inventories[0].get("native_inventory_sha256", "missing")
              if inventories else "missing")

    result = {
        "schema": 1,
        "kind": "mph-shard-performance-gate",
        "pass": all(check["pass"] for check in checks),
        "manifest": str(path.resolve()),
        "route": manifest.get("route"),
        "repetitions": repetitions,
        "thresholds": thresholds,
        "checks": checks,
        "metrics": metrics,
        "phase_medians": per_mode_phase,
        "dispatch_bands": bands,
        "prebuilt_cache": inventories[0] if same_inventory else None,
        "measurement_identity": identities[0] if identities else None,
    }
    return result


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        f"# MPH shard performance gate: {'PASS' if result['pass'] else 'FAIL'}",
        "",
        f"Route: `{result.get('route')}`; repetitions: {result.get('repetitions')}",
        "",
        "| Mode | Phase | FPS | emu ms/f | poll ms/f | native hits | A9 dispatch/f |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    medians = result.get("phase_medians", {})
    phases = sorted(medians.get("disabled", {}).get("fps", {}))
    for mode in MODES:
        data = medians.get(mode, {})
        for phase in phases:
            lines.append(
                f"| {mode} | {phase} | {data['fps'].get(phase, 0):.3f} | "
                f"{data['emu_ms_per_frame'].get(phase, 0):.3f} | "
                f"{data['overlay_poll_ms_per_frame'].get(phase, 0):.3f} | "
                f"{data['native_hits'].get(phase, 0):.0f} | "
                f"{data['dispatch_arm9_per_frame'].get(phase, 0):.0f} |"
            )
    failed = [check for check in result["checks"] if not check["pass"]]
    lines += ["", "## Failed checks"]
    lines += ([f"- `{item['name']}`: {item['detail']}" for item in failed]
              or ["- None"])
    lines += ["", "Dispatch-band summaries are in `performance-gate.json`; "
              "only bands marked `matched_all_modes` are direct band controls."]
    return "\n".join(lines) + "\n"


def runner_args(mode: str, cache: pathlib.Path | None,
                runtime_command: str | None) -> list[str]:
    if mode == "disabled":
        return []
    assert cache is not None
    values = ["--live-overlay-enable", "--live-overlay-cache", str(cache),
              "--live-overlay-activation-delay-ms", "0"]
    if mode == "runtime_tcc":
        assert runtime_command
        values += ["--live-overlay-auto"]
        if runtime_command != "@bundled":
            values += ["--live-overlay-command", runtime_command]
        values += ["--live-overlay-auto-delay-ms", "0",
                   "--live-overlay-auto-cooldown-ms", "1000"]
    return values


def run_matrix(args: argparse.Namespace) -> pathlib.Path:
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"output must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    source_cache = args.prebuilt_cache.resolve()
    source_inventory = cache_inventory(source_cache)
    if source_inventory["native_file_count"] == 0:
        raise RuntimeError(f"prebuilt cache has no native shards: {source_cache}")
    measure = pathlib.Path(__file__).with_name("measure_mph_scenario.py")
    manifest: dict[str, Any] = {
        "schema": 1,
        "kind": "mph-shard-performance-matrix",
        "route": args.route,
        "repetitions": args.repetitions,
        "thresholds": DEFAULT_THRESHOLDS,
        "prebuilt_source": source_inventory,
        "legs": [],
    }
    # Rotate a fixed order. This exposes thermal drift without pretending the
    # much longer compiler leg can be statistically randomized away.
    base_order = list(MODES)
    for repetition in range(1, args.repetitions + 1):
        order = base_order[(repetition - 1) % len(base_order):] + base_order[:
            (repetition - 1) % len(base_order)]
        for mode in order:
            leg_dir = output / f"r{repetition:02d}-{mode}"
            cache = None if mode == "disabled" else leg_dir / "cache"
            leg_dir.mkdir(parents=True)
            if mode == "prebuilt_gcc":
                shutil.copytree(source_cache, cache)
            elif cache is not None:
                cache.mkdir()
            before = cache_inventory(cache) if cache else None
            command = [sys.executable, str(measure), "--route", args.route,
                       "--exe", str(args.runner), "--bios", str(args.bios),
                       "--rom", str(args.rom), "--config", str(args.config),
                       "--output", str(leg_dir / "measurement"),
                       "--repetitions", "1", "--port", str(args.base_port),
                       "--threaded", str(args.threaded), "--renderer", args.renderer]
            if args.save_source:
                command += ["--save-source", str(args.save_source)]
            for value in runner_args(mode, cache, args.runtime_tcc_command):
                command.append(f"--runner-arg={value}")
            completed = subprocess.run(command, check=False)
            report_path = leg_dir / "measurement" / "report.json"
            manifest["legs"].append({
                "mode": mode,
                "repetition": repetition,
                "report": report_path.relative_to(output).as_posix(),
                "cache_before": before,
                "cache_after": cache_inventory(cache) if cache else None,
                "command": command,
                "exit_code": completed.returncode,
            })
            write_json(output / "manifest.partial.json", manifest)
            args.base_port += 1
    manifest_path = output / "manifest.json"
    write_json(manifest_path, manifest)
    (output / "manifest.partial.json").unlink(missing_ok=True)
    result = evaluate_manifest(manifest_path)
    write_json(output / "performance-gate.json", result)
    (output / "performance-gate.md").write_text(markdown_report(result),
                                                 encoding="utf-8", newline="\n")
    return output / "performance-gate.json"


def verify_package(gate_path: pathlib.Path, cache: pathlib.Path,
                   provider_identity: str | None,
                   runner_sha256: str | None = None) -> int:
    result = read_json(gate_path)
    if result.get("kind") != "mph-shard-performance-gate" or not result.get("pass"):
        raise RuntimeError(f"performance gate did not pass: {gate_path}")
    checks = result.get("checks")
    if not isinstance(checks, list) or not checks or not all(
            isinstance(check, dict) and check.get("pass") is True
            for check in checks):
        raise RuntimeError(f"performance gate has no passing check record: {gate_path}")
    if result.get("route") not in ("mp_bots", "mp_bots_blank"):
        raise RuntimeError(f"performance gate route is not a bot route: {gate_path}")
    if int(result.get("repetitions", 0)) < 3:
        raise RuntimeError(f"performance gate has fewer than three repetitions: {gate_path}")
    expected = result.get("prebuilt_cache") or {}
    actual = cache_inventory(cache)
    if actual["native_inventory_sha256"] != expected.get(
            "native_inventory_sha256"):
        raise RuntimeError("cache native inventory differs from measured prebuilt cache")
    if provider_identity and provider_identity not in actual["provider_identities"]:
        raise RuntimeError(
            f"measured cache does not contain provider identity {provider_identity}")
    measured_runner = (result.get("measurement_identity") or {}).get(
        "executable_sha256")
    if not measured_runner:
        raise RuntimeError(f"performance gate does not record a measured runner: {gate_path}")
    if runner_sha256 and measured_runner != runner_sha256:
        raise RuntimeError(
            f"gate measured runner {measured_runner}, package has {runner_sha256}")
    print(json.dumps({"pass": True, "route": result.get("route"),
                      "native_files": actual["native_file_count"],
                      "native_inventory_sha256": actual["native_inventory_sha256"]}))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    for name in ("runner", "bios", "rom", "config", "prebuilt-cache", "output"):
        run.add_argument(f"--{name}", type=pathlib.Path, required=True)
    run.add_argument("--runtime-tcc-command", default="@bundled",
                     help="full command, or @bundled to exercise the toolchain "
                          "beside the packaged runner (default)")
    run.add_argument("--route", choices=("mp_bots", "mp_bots_blank"),
                     default="mp_bots_blank")
    run.add_argument("--save-source", type=pathlib.Path)
    run.add_argument("--repetitions", type=int, default=3)
    run.add_argument("--base-port", type=int, default=20100)
    run.add_argument("--threaded", type=int, choices=(0, 1), default=1)
    run.add_argument("--renderer", choices=("auto", "soft", "compute"),
                     default="auto")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--manifest", type=pathlib.Path, required=True)
    evaluate.add_argument("--output", type=pathlib.Path)
    verify = sub.add_parser("verify-package")
    verify.add_argument("--gate", type=pathlib.Path, required=True)
    verify.add_argument("--cache", type=pathlib.Path, required=True)
    verify.add_argument("--provider-identity")
    verify.add_argument("--runner-sha256")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "run":
        if args.repetitions < 1:
            raise ValueError("--repetitions must be positive")
        if not args.runtime_tcc_command.strip():
            raise ValueError("--runtime-tcc-command must not be empty")
        gate = run_matrix(args)
        result = read_json(gate)
        print(gate)
        return 0 if result["pass"] else 1
    if args.command == "evaluate":
        result = evaluate_manifest(args.manifest.resolve())
        output = args.output or args.manifest.with_name("performance-gate.json")
        write_json(output, result)
        output.with_suffix(".md").write_text(markdown_report(result),
                                                  encoding="utf-8", newline="\n")
        print(output)
        return 0 if result["pass"] else 1
    if args.command == "verify-package":
        return verify_package(args.gate.resolve(), args.cache.resolve(),
                              args.provider_identity, args.runner_sha256)
    raise AssertionError(args.command)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
