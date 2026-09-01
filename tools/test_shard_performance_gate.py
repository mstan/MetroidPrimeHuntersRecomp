#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import shard_performance_gate as gate


PHASES = ("mp_bots_settle", "mp_bots_fight", "mp_bots_steady")


def phase(label: str, mode: str) -> dict:
    hits = 1000 if mode in ("prebuilt_gcc", "runtime_tcc") else 0
    poll = 0.05 if mode != "disabled" else 0.0
    emu = 9.5 if mode in ("prebuilt_gcc", "runtime_tcc") else 10.0
    return {
        "label": label,
        "frames": 120,
        "fps": 59.8,
        "phase_ms_per_frame": {"emu": emu},
        "emu_attrib_ms_per_frame": {
            "overlay_poll": poll, "exec_arm9": 5.0, "exec_arm7": 1.0,
        },
        "tier3_delta": {"tier3_insns9": 20, "tier3_insns7": 0},
        "dispatch_delta": {
            "arm9": {"dispatch_total": 2_400_000, "crs_hit": 120_000,
                     "crs_miss": 1200},
            "arm7": {"dispatch_total": 600_000, "crs_hit": 30_000,
                     "crs_miss": 300},
        },
        "live_overlay_before": {"native_hits": 0},
        "live_overlay_after": {
            "native_hits": hits, "banks_loaded": 2, "registered_banks": 2,
        },
        "live_overlay_delta": {"native_hits": hits},
    }


def status(mode: str) -> dict:
    common = {
        "enabled": mode != "disabled", "auto_trigger": mode == "runtime_tcc",
        "banks_loaded": 0, "banks_rejected": 0, "registered_banks": 0,
        "native_hits": 0, "runs_started": 0, "runs_finished": 0,
        "runs_failed": 0, "busy": False, "pending_candidates": 0,
    }
    if mode == "prebuilt_gcc":
        common.update(banks_loaded=2, registered_banks=2, native_hits=3000)
    if mode == "runtime_tcc":
        common.update(banks_loaded=2, registered_banks=2, native_hits=3000,
                      runs_started=1, runs_finished=1)
    return common


def report(mode: str) -> dict:
    return {
        "build": {
            "executable_sha256": "exe", "config_sha256": "config",
            "rom_sha256": "rom", "save_source_sha256": None,
            "framework_revision": "framework", "target_revision": "target",
            "profiled": False, "boot": "direct", "renderer": "auto",
            "gpu3d_threaded": True, "compute_readback_overlap": True,
            "screen_layout": "from game.toml",
            "adaptive_widescreen": "from game.toml",
            "runner_args": [],
        },
        "route": {
            "name": "mp_bots_blank", "scenario": "mp_bots_start.json",
            "insn9_phases": list(PHASES),
        },
        "host": {"platform": "test", "processor": "test", "python": "test"},
        "runs": [{
            "valid": True,
            "phases": [phase(label, mode) for label in PHASES],
            "final_live_overlay": status(mode),
        }],
    }


class GateTest(unittest.TestCase):
    def fixture(self, root: pathlib.Path) -> pathlib.Path:
        legs = []
        inventory = {
            "native_file_count": 2, "native_bytes": 20,
            "native_inventory_sha256": "cache-digest",
            "provider_identities": ["provider"],
        }
        for repetition in (1, 2, 3):
            for mode in gate.MODES:
                path = root / f"{mode}-{repetition}.json"
                gate.write_json(path, report(mode))
                legs.append({
                    "mode": mode, "repetition": repetition,
                    "report": path.name,
                    "exit_code": 0,
                    "cache_before": (copy.deepcopy(inventory)
                                     if mode == "prebuilt_gcc" else {
                                         "native_file_count": 0,
                                         "native_inventory_sha256": "empty",
                                     }),
                    "cache_after": (copy.deepcopy(inventory)
                                    if mode in ("prebuilt_gcc", "runtime_tcc")
                                    else {"native_file_count": 0,
                                          "native_inventory_sha256": "empty"}),
                })
        manifest = root / "manifest.json"
        gate.write_json(manifest, {
            "schema": 1, "kind": "mph-shard-performance-matrix",
            "route": "mp_bots_blank", "repetitions": 3, "legs": legs,
        })
        return manifest

    def test_accepts_controlled_matrix_with_native_hits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = gate.evaluate_manifest(self.fixture(pathlib.Path(directory)))
        self.assertTrue(result["pass"], [c for c in result["checks"]
                                         if not c["pass"]])
        self.assertEqual(result["prebuilt_cache"]["native_inventory_sha256"],
                         "cache-digest")
        self.assertTrue(any(row["matched_all_modes"]
                            for row in result["dispatch_bands"]))

    def test_rejects_incomparable_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            manifest_path = self.fixture(root)
            manifest = gate.read_json(manifest_path)
            victim = root / manifest["legs"][0]["report"]
            payload = gate.read_json(victim)
            payload["build"]["executable_sha256"] = "different"
            gate.write_json(victim, payload)
            result = gate.evaluate_manifest(manifest_path)
        self.assertFalse(result["pass"])
        self.assertFalse(next(c for c in result["checks"]
                              if c["name"] == "same_build_route_host")["pass"])

    def test_rejects_nonexecuting_prebuilt_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            manifest_path = self.fixture(root)
            manifest = gate.read_json(manifest_path)
            victim = next(leg for leg in manifest["legs"]
                          if leg["mode"] == "prebuilt_gcc")
            payload = gate.read_json(root / victim["report"])
            payload["runs"][0]["final_live_overlay"]["native_hits"] = 0
            gate.write_json(root / victim["report"], payload)
            result = gate.evaluate_manifest(manifest_path)
        self.assertFalse(result["pass"])
        self.assertTrue(any(not c["pass"] and c["name"].endswith("native_hits")
                            for c in result["checks"]))

    def test_rejects_missing_counter_surface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            manifest_path = self.fixture(root)
            manifest = gate.read_json(manifest_path)
            victim = root / manifest["legs"][0]["report"]
            payload = gate.read_json(victim)
            del payload["runs"][0]["phases"][0]["dispatch_delta"]["arm9"][
                "crs_miss"]
            gate.write_json(victim, payload)
            result = gate.evaluate_manifest(manifest_path)
        self.assertFalse(result["pass"])
        self.assertTrue(any(not c["pass"] and c["name"].endswith(
            "metric_surface") for c in result["checks"]))

    def test_rejects_truncated_route_landmarks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            manifest_path = self.fixture(root)
            manifest = gate.read_json(manifest_path)
            for leg in manifest["legs"]:
                payload = gate.read_json(root / leg["report"])
                payload["runs"][0]["phases"] = payload["runs"][0]["phases"][:1]
                gate.write_json(root / leg["report"], payload)
            result = gate.evaluate_manifest(manifest_path)
        self.assertFalse(result["pass"])
        self.assertTrue(any(not c["pass"] and c["name"].endswith(
            "phase_landmarks") for c in result["checks"]))

    def test_rejects_nonzero_measurement_exit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            manifest_path = self.fixture(root)
            manifest = gate.read_json(manifest_path)
            manifest["legs"][0]["exit_code"] = 1
            gate.write_json(manifest_path, manifest)
            result = gate.evaluate_manifest(manifest_path)
        self.assertFalse(result["pass"])
        self.assertFalse(next(c for c in result["checks"]
                              if c["name"].endswith(".exit_code"))["pass"])

    def test_rejects_native_hits_only_before_steady_phase(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            manifest_path = self.fixture(root)
            manifest = gate.read_json(manifest_path)
            for leg in manifest["legs"]:
                if leg["mode"] != "prebuilt_gcc":
                    continue
                payload = gate.read_json(root / leg["report"])
                payload["runs"][0]["phases"][-1]["live_overlay_delta"][
                    "native_hits"] = 0
                gate.write_json(root / leg["report"], payload)
            result = gate.evaluate_manifest(manifest_path)
        self.assertFalse(result["pass"])
        self.assertFalse(next(c for c in result["checks"]
                              if c["name"].endswith("steady_native_hits"))["pass"])

    def test_rejects_native_mode_without_steady_emu_gain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            manifest_path = self.fixture(root)
            manifest = gate.read_json(manifest_path)
            for leg in manifest["legs"]:
                if leg["mode"] != "prebuilt_gcc":
                    continue
                payload = gate.read_json(root / leg["report"])
                for item in payload["runs"][0]["phases"]:
                    item["phase_ms_per_frame"]["emu"] = 10.0
                gate.write_json(root / leg["report"], payload)
            result = gate.evaluate_manifest(manifest_path)
        self.assertFalse(result["pass"])
        self.assertFalse(next(c for c in result["checks"]
                              if c["name"].endswith("steady_emu_improvement"))[
                                  "pass"])

    def test_rejects_unmatched_steady_dispatch_band(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            manifest_path = self.fixture(root)
            manifest = gate.read_json(manifest_path)
            for leg in manifest["legs"]:
                if leg["mode"] != "runtime_tcc":
                    continue
                payload = gate.read_json(root / leg["report"])
                payload["runs"][0]["phases"][-1]["dispatch_delta"]["arm9"][
                    "dispatch_total"] = 6_000_000
                gate.write_json(root / leg["report"], payload)
            result = gate.evaluate_manifest(manifest_path)
        self.assertFalse(result["pass"])
        self.assertFalse(next(c for c in result["checks"]
                              if c["name"].endswith("matched_dispatch_band"))[
                                  "pass"])

    def test_package_verifier_binds_measured_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            cache = root / "cache"
            (cache / "gcc").mkdir(parents=True)
            (cache / "gcc" / "one.dll").write_bytes(b"native")
            (cache / "live-index.json").write_text(json.dumps({
                "captures": {"one": {"provider_id": "provider"}}
            }), encoding="utf-8")
            inventory = gate.cache_inventory(cache)
            result = {
                "kind": "mph-shard-performance-gate", "pass": True,
                "route": "mp_bots_blank", "repetitions": 3,
                "checks": [{"name": "fixture", "pass": True, "detail": ""}],
                "prebuilt_cache": inventory,
                "measurement_identity": {"executable_sha256": "runner"},
            }
            result_path = root / "gate.json"
            gate.write_json(result_path, result)
            self.assertEqual(gate.verify_package(
                result_path, cache, "provider", "runner"), 0)
            (cache / "gcc" / "two.dll").write_bytes(b"unmeasured")
            with self.assertRaisesRegex(RuntimeError, "differs"):
                gate.verify_package(result_path, cache, "provider", "runner")

    def test_package_verifier_accepts_basic_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            cache = root / "cache"
            (cache / "gcc").mkdir(parents=True)
            (cache / "gcc" / "one.dll").write_bytes(b"native")
            (cache / "live-index.json").write_text(json.dumps({
                "captures": {"one": {"provider_id": "provider"}}
            }), encoding="utf-8")
            inventory = gate.cache_inventory(cache)
            result = {
                "kind": "mph-shard-basic-validation", "pass": True,
                "route": "mp_bots_blank",
                "checks": [{"name": "basic", "pass": True, "detail": ""}],
                "prebuilt_cache": inventory,
                "measurement_identity": {"executable_sha256": "runner"},
            }
            result_path = root / "basic.json"
            gate.write_json(result_path, result)
            self.assertEqual(gate.verify_package(
                result_path, cache, "provider", "runner"), 0)

    def test_package_verifier_rejects_minimal_fabricated_gate_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            cache = root / "cache"
            (cache / "gcc").mkdir(parents=True)
            (cache / "gcc" / "one.dll").write_bytes(b"native")
            result_path = root / "gate.json"
            gate.write_json(result_path, {
                "kind": "mph-shard-performance-gate", "pass": True,
                "route": "mp_bots_blank",
                "prebuilt_cache": gate.cache_inventory(cache),
            })
            with self.assertRaisesRegex(RuntimeError, "passing check record"):
                gate.verify_package(result_path, cache, None, "runner")


if __name__ == "__main__":
    unittest.main()
