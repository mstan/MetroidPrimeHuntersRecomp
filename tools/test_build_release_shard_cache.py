#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import sys
import tempfile
import types
import unittest


TOOLS = pathlib.Path(__file__.replace("\\", "/")).resolve().parent


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_release_shard_cache", TOOLS / "build_release_shard_cache.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_status(runs_failed: int) -> dict:
    return {
        "initial_cache_scan_done": True,
        "banks_loaded": 0,
        "banks_rejected": 0,
        "loaded": [],
        "tier3_arm9": 1,
        "tier3_arm7": 0,
        "pending_candidates": 0,
        "trigger_requests": 1,
        "runs_started": 1,
        "runs_finished": 1,
        "runs_failed": runs_failed,
        "native_hits": 0,
        "last_error": "synthetic compiler failure",
    }


class FakeProcess:
    pid = 1234


class FakeLog:
    def close(self) -> None:
        pass


class FakeClient:
    def __init__(self, runs_failed: int):
        self._runs_failed = runs_failed
        self._vblank9 = 0

    def cmd(self, name: str, **_kwargs):
        assert name in ("live_overlay_status", "live_overlay_trigger", "keys")
        if name == "keys":
            return {}
        if name == "live_overlay_trigger":
            return {"ok": True, "status": live_status(self._runs_failed)}
        return live_status(self._runs_failed)

    def event_counts(self) -> dict:
        self._vblank9 += 300
        return {"vblank9": self._vblank9, "insn9": 0}

    def close(self) -> None:
        pass


class FakeBench:
    KEYS_RELEASED = 0xFFF
    KEY_BITS = {}

    def __init__(self, runs_failed: int):
        self._runs_failed = runs_failed

    def launch_runtime(self, *_args, **_kwargs):
        return FakeProcess(), FakeLog(), FakeLog()

    def wait_for_client(self, *_args, **_kwargs):
        return FakeClient(self._runs_failed)

    def wait_until_vblank9(self, *_args, **_kwargs):
        pass

    def terminate_runtime(self, *_args, **_kwargs):
        pass


class ReleaseShardCacheBuilderTest(unittest.TestCase):
    def run_builder(self, root: pathlib.Path, runs_failed: int) -> tuple[int, str]:
        builder = load_builder()
        fake_mph = types.SimpleNamespace(
            ROUTES={"mp_bots_blank": {
                "vblank_windows": [],
                "insn_phases": [],
                "hold_key": None,
            }},
            bench=FakeBench(runs_failed),
            navigate_route=lambda *_args, **_kwargs: None,
        )
        builder.load_harness = lambda _mph_root: fake_mph
        argv = [
            "build_release_shard_cache.py",
            "--mph-root", str(root),
            "--runner", str(root / "nds_runner.exe"),
            "--bios", str(root / "bios"),
            "--rom", str(root / "game.nds"),
            "--config", str(root / "game.toml"),
            "--cache", str(root / "cache"),
            "--route", "mp_bots_blank",
            "--live-command", "fake compiler command",
            "--log-dir", str(root / "logs"),
        ]
        previous = sys.argv
        stderr = io.StringIO()
        try:
            sys.argv = argv
            with contextlib.redirect_stderr(stderr):
                code = builder.main()
        finally:
            sys.argv = previous
        return code, stderr.getvalue()

    def test_compile_failures_are_fatal_after_summary_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            code, stderr = self.run_builder(root, runs_failed=1)
            self.assertEqual(code, 1)
            self.assertIn("FATAL: 1 autocompile run(s) failed", stderr)
            self.assertIn("synthetic compiler failure", stderr)
            self.assertTrue((root / "logs" /
                             "mp_bots_blank.summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
