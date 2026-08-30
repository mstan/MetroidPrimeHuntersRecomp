#!/usr/bin/env python3
"""Discriminating tests for the Linux AppImage shard release path."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import time


TOOLS = pathlib.Path(__file__.replace("\\", "/")).resolve().parent
ROOT = TOOLS.parent
COMMON = TOOLS / "release_shard_common.py"
INSTALLER = TOOLS / "install_prebuilt_shards.py"


def run(*args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True)
    if ok and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    if not ok and not result.returncode:
        raise AssertionError(f"command unexpectedly succeeded: {args}")
    return result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mph-linux-shards-") as raw:
        tmp = pathlib.Path(raw)
        compiler = tmp / "compile_live_shards.py"
        compiler.write_text(
            "def provider_identity(args):\n    return 'wanted-provider'\n",
            encoding="ascii")
        include = tmp / "include"
        include.mkdir()
        recompiler = tmp / "nds_recompile"
        gcc = tmp / "gcc"
        runner_build = tmp / "runner build"
        runner_build.mkdir()
        recompiler.write_text("fixture", encoding="ascii")
        gcc.write_text("fixture", encoding="ascii")

        command = run(
            sys.executable, str(COMMON), "compile-command",
            "--python", "/opt/mph/python/bin/python3",
            "--compile-script", str(compiler),
            "--runtime-include", str(include),
            "--runner-build", str(runner_build),
            "--recompiler", str(recompiler), "--gcc", str(gcc),
        ).stdout.strip()
        assert "--include-roots" in command
        assert "--merge-cache-snapshots" not in command
        assert "--runner-build" in command and "--compiler gcc" in command

        cache = tmp / "cache"
        (cache / "gcc").mkdir(parents=True)
        good = cache / "gcc" / "known.so"
        stale = cache / "gcc" / "stale.so"
        interrupted = cache / "gcc" / "partial.stage.so"
        good.write_bytes(b"known")
        stale.write_bytes(b"stale")
        interrupted.write_bytes(b"partial")
        index = {
            "schema": 2,
            "rom_sha1": "1" * 40,
            "captures": {
                "good": {"provider_id": "wanted-provider",
                         "dll": str(good.resolve()), "cpu": 9},
                "stale": {"provider_id": "old-provider",
                          "dll": str(stale.resolve()), "cpu": 9},
            },
        }
        (cache / "live-index.json").write_text(
            json.dumps(index), encoding="utf-8")
        stage = tmp / "stage"
        output = run(
            sys.executable, str(COMMON), "stage-cache",
            "--compile-script", str(compiler),
            "--runtime-include", str(include),
            "--recompiler", str(recompiler), "--gcc", str(gcc),
            "--cache", str(cache), "--destination", str(stage),
            "--extension", ".so", "--rom-sha1", "1" * 40,
            "--runner-sha256", "2" * 64,
        )
        assert json.loads(output.stdout)["shards"] == 1
        assert (stage / "gcc" / "known.so").read_bytes() == b"known"
        assert not (stage / "gcc" / "stale.so").exists()
        assert not (stage / "gcc" / "partial.stage.so").exists()
        staged_index = json.loads(
            (stage / "live-index.json").read_text(encoding="utf-8"))
        assert staged_index["rom_sha1"] == "1" * 40
        assert staged_index["captures"]["good"]["dll"] == "gcc/known.so"

        wrong_rom = run(
            sys.executable, str(COMMON), "stage-cache",
            "--compile-script", str(compiler),
            "--runtime-include", str(include),
            "--recompiler", str(recompiler), "--gcc", str(gcc),
            "--cache", str(cache), "--destination", str(tmp / "wrong-rom"),
            "--extension", ".so", "--rom-sha1", "3" * 40,
            "--runner-sha256", "2" * 64, ok=False)
        assert "cache ROM identity" in wrong_rom.stderr

        external = tmp / "data" / "live-shard-cache"
        external.mkdir(parents=True)
        (external / ".mph-prebuilt-release-id").write_text(
            "old-release\n", encoding="ascii")
        (external / "stale-provider.so").write_bytes(b"stale")
        run(sys.executable, str(INSTALLER), "--source", str(stage),
            "--cache", str(external))
        assert not (external / "stale-provider.so").exists()
        assert (external / "gcc" / "known.so").is_file()
        installed = json.loads(
            (external / "live-index.json").read_text(encoding="utf-8"))
        assert pathlib.Path(installed["captures"]["good"]["dll"]).is_file()

        ready = tmp / "lock-ready.txt"
        holder_script = tmp / "hold_install_lock.py"
        holder_script.write_text(
            "import importlib.util, pathlib, time\n"
            f"spec = importlib.util.spec_from_file_location('installer', "
            f"{json.dumps(str(INSTALLER))})\n"
            "installer = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(installer)\n"
            f"cache = pathlib.Path({json.dumps(str(external))})\n"
            f"ready = pathlib.Path({json.dumps(str(ready))})\n"
            "with installer.CacheInstallLock(cache):\n"
            "    ready.write_text('ready\\n', encoding='ascii')\n"
            "    time.sleep(1.0)\n",
            encoding="ascii")
        holder = subprocess.Popen(
            [sys.executable, str(holder_script)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 5.0
        while not ready.is_file() and time.monotonic() < deadline:
            if holder.poll() is not None:
                stdout, stderr = holder.communicate()
                raise AssertionError(stderr or stdout)
            time.sleep(0.05)
        assert ready.is_file(), "lock holder did not start"
        waiting = subprocess.Popen(
            [sys.executable, str(INSTALLER), "--source", str(stage),
             "--cache", str(external)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(0.25)
        assert waiting.poll() is None, "installer did not wait on lock"
        stdout, stderr = holder.communicate(timeout=10)
        if holder.returncode:
            raise AssertionError(stderr or stdout)
        stdout, stderr = waiting.communicate(timeout=10)
        if waiting.returncode:
            raise AssertionError(stderr or stdout)

        (external / ".mph-prebuilt-release-id").write_text(
            "old-release\n", encoding="ascii")
        (external / "stale-provider.so").write_bytes(b"stale")
        workers = [
            subprocess.Popen(
                [sys.executable, str(INSTALLER), "--source", str(stage),
                 "--cache", str(external)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(2)
        ]
        for worker in workers:
            stdout, stderr = worker.communicate(timeout=10)
            if worker.returncode:
                raise AssertionError(stderr or stdout)
        assert not (external / "stale-provider.so").exists()
        assert (external / "gcc" / "known.so").is_file()
        assert not any(path.name.startswith(".live-shard-cache.seed-")
                       for path in external.parent.iterdir())

        empty = tmp / "empty"
        empty.mkdir()
        failed = run(
            sys.executable, str(COMMON), "stage-cache",
            "--compile-script", str(compiler),
            "--runtime-include", str(include),
            "--recompiler", str(recompiler), "--gcc", str(gcc),
            "--cache", str(empty), "--destination", str(tmp / "empty-stage"),
            "--extension", ".so", "--rom-sha1", "1" * 40,
            "--runner-sha256", "2" * 64, ok=False)
        assert "none under provider identity" in failed.stderr

    launcher = (ROOT / "launcher/recomp-ui/launcher_main.cpp").read_text(
        encoding="utf-8")
    assert 'game_dir / "overlay_toolchain" / "compile_live_shards.py"' in launcher
    assert '(data_dir / "live-shard-cache").string()' in launcher
    assert "append_live_overlay_args(args, game_dir, data_dir);" in launcher
    package = (TOOLS / "build-linux.sh").read_text(encoding="utf-8")
    for required in (
        "overlay_toolchain/python/bin/python3",
        "overlay_toolchain/install_prebuilt_shards.py",
        "prebuilt-live-shard-cache", "--extension .so",
    ):
        assert required in package, required
    print("Linux release shards: all assertions hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
