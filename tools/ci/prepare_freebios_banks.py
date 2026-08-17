#!/usr/bin/env python3
"""Build the redistributable ndsrecomp FreeBIOS native banks for CI/releases."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess


def run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    args = parser.parse_args()

    root = args.framework_root.resolve()
    build = args.build_dir.resolve()
    generated = root / "generated"
    freebios = root / "third_party" / "freebios"
    arm9_bin = freebios / "drastic_bios_arm9.bin"
    arm7_bin = freebios / "drastic_bios_arm7.bin"
    arm9_cfg = root / "bios" / "freebios9.toml"
    arm7_cfg = root / "bios" / "freebios7.toml"

    for path in (arm9_bin, arm7_bin, arm9_cfg, arm7_cfg):
        if not path.is_file():
            raise SystemExit(
                f"missing FreeBIOS source {path}; initialize the pinned "
                "ndsrecomp third_party/freebios submodule"
            )

    run(
        "cmake",
        "-S", str(root / "recompiler"),
        "-B", str(build),
        "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
    )
    run("cmake", "--build", str(build), "--target", "nds_recompile")

    exe = build / ("nds_recompile.exe" if os.name == "nt" else "nds_recompile")
    if not exe.is_file():
        raise SystemExit(f"nds_recompile missing after build: {exe}")

    generated.mkdir(parents=True, exist_ok=True)
    for cpu, config, image in (
        ("arm9", arm9_cfg, arm9_bin),
        ("arm7", arm7_cfg, arm7_bin),
    ):
        run(
            str(exe),
            "--config", str(config),
            "--bin", str(image),
            "--out", str(generated),
            "--bank", f"freebios_{cpu}",
        )

    expected = [
        generated / "freebios_arm9.c",
        generated / "freebios_arm9_dispatch.c",
        generated / "freebios_arm7.c",
        generated / "freebios_arm7_dispatch.c",
    ]
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        raise SystemExit(f"FreeBIOS bank generation incomplete: {missing}")

    print("FreeBIOS banks ready (BSD-2-Clause source path only).")


if __name__ == "__main__":
    main()
