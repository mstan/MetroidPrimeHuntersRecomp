#!/usr/bin/env python3
"""Cross-platform release shard policy, identity validation, and staging."""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import shlex
import shutil
import sys


POLICY_PATH = pathlib.Path(__file__).with_name("release_shard_policy.json")


def policy() -> dict:
    value = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    required = {
        "compiler", "generated_opt", "max_function_bytes", "include_roots",
        "merge_cache_snapshots", "max_pages", "min_hits",
    }
    missing = required - value.keys()
    if missing:
        raise RuntimeError(f"release shard policy is missing: {sorted(missing)}")
    if not value["include_roots"]:
        raise RuntimeError("release shard policy must include root-only observations")
    return value


def load_compiler(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("nds_compile_live_shards", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import shard compiler: {path}")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def provider_identity(args: argparse.Namespace) -> str:
    p = policy()
    module = load_compiler(args.compile_script)
    identity_args = argparse.Namespace(
        compiler=p["compiler"],
        gcc=str(args.gcc),
        tcc="tcc",
        recompiler=args.recompiler,
        runtime_include=[args.runtime_include],
        generated_opt=p["generated_opt"],
        max_function_bytes=p["max_function_bytes"],
    )
    return module.provider_identity(identity_args)


def compile_command(args: argparse.Namespace) -> str:
    p = policy()
    values = [
        str(args.python), str(args.compile_script),
        "--runtime-include", str(args.runtime_include),
        "--runner-build", str(args.runner_build),
        "--recompiler", str(args.recompiler),
        "--compiler", p["compiler"],
        "--gcc", str(args.gcc),
        f"--generated-opt={p['generated_opt']}",
        "--max-function-bytes", str(p["max_function_bytes"]),
        "--max-pages", str(p["max_pages"]),
        "--min-hits", str(p["min_hits"]),
    ]
    if p["include_roots"]:
        values.append("--include-roots")
    if p["merge_cache_snapshots"]:
        values.append("--merge-cache-snapshots")
    return shlex.join(values)


def matching_captures(cache: pathlib.Path, identity: str, extension: str,
                      rom_sha1: str) -> list[tuple[str, dict, pathlib.Path]]:
    index_path = cache / "live-index.json"
    if not index_path.is_file():
        return []
    data = json.loads(index_path.read_text(encoding="utf-8-sig"))
    if data.get("rom_sha1") != rom_sha1:
        raise RuntimeError(
            f"shard cache ROM identity is {data.get('rom_sha1')!r}, "
            f"expected {rom_sha1}")
    backend_root = (cache / policy()["compiler"]).resolve()
    result = []
    for key, entry in data.get("captures", {}).items():
        if entry.get("provider_id") != identity or not entry.get("dll"):
            continue
        source = pathlib.Path(entry["dll"])
        if not source.is_absolute():
            source = cache / source
        source = source.resolve()
        if (source.is_file() and source.suffix == extension
                and not source.name.endswith(f".stage{extension}")):
            try:
                relative = source.relative_to(backend_root)
            except ValueError as error:
                raise RuntimeError(
                    f"indexed shard is outside {backend_root}: {source}") from error
            if len(relative.parts) != 1:
                raise RuntimeError(f"indexed shard is not flat: {source}")
            result.append((key, entry, source))
    return sorted(result, key=lambda item: item[2].name)


def stage_cache(args: argparse.Namespace) -> int:
    identity = provider_identity(args)
    captures = matching_captures(
        args.cache, identity, args.extension, args.rom_sha1)
    present = sum(1 for path in args.cache.rglob(f"*{args.extension}")
                  if path.is_file()) if args.cache.is_dir() else 0
    if not captures and not args.allow_empty:
        raise RuntimeError(
            f"shard cache {args.cache} has {present} {args.extension} file(s), "
            f"but none under provider identity {identity}")

    # The package cache is a projection, never a merge. This prevents an old
    # provider or an interrupted .stage.so from leaking into an AppImage.
    if args.destination.exists():
        shutil.rmtree(args.destination)
    args.destination.mkdir(parents=True)
    staged_index = {"schema": 2, "rom_sha1": args.rom_sha1, "captures": {}}
    manifest = []
    for key, entry, source in captures:
        backend = source.parent.name
        if backend != policy()["compiler"]:
            raise RuntimeError(f"unexpected cache backend for {source}: {backend}")
        target = args.destination / backend / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        staged = dict(entry)
        staged["dll"] = f"{backend}/{source.name}"
        staged_index["captures"][key] = staged
        manifest.append(f"{identity} {backend}/{source.name} {target.stat().st_size}")

    (args.destination / "live-index.json").write_text(
        json.dumps(staged_index, indent=2) + "\n", encoding="utf-8")
    release_id = f"{args.rom_sha1}:{args.runner_sha256}:{identity}"
    (args.destination / "release-id.txt").write_text(
        release_id + "\n", encoding="ascii")
    (args.destination / "shard-manifest.txt").write_text(
        "\n".join(manifest) + ("\n" if manifest else ""), encoding="utf-8")
    print(json.dumps({"identity": identity, "shards": len(captures),
                      "release_id": release_id}))
    return 0


def add_identity_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--compile-script", type=pathlib.Path, required=True)
    parser.add_argument("--runtime-include", type=pathlib.Path, required=True)
    parser.add_argument("--recompiler", type=pathlib.Path, required=True)
    parser.add_argument("--gcc", type=pathlib.Path, required=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("compile-command")
    add_identity_args(command)
    command.add_argument("--python", type=pathlib.Path, required=True)
    command.add_argument("--runner-build", type=pathlib.Path, required=True)

    identity = sub.add_parser("identity")
    add_identity_args(identity)

    stage = sub.add_parser("stage-cache")
    add_identity_args(stage)
    stage.add_argument("--cache", type=pathlib.Path, required=True)
    stage.add_argument("--destination", type=pathlib.Path, required=True)
    stage.add_argument("--extension", choices=(".dll", ".so"), required=True)
    stage.add_argument("--rom-sha1", required=True)
    stage.add_argument("--runner-sha256", required=True)
    stage.add_argument("--allow-empty", action="store_true")

    args = parser.parse_args()
    if args.command == "compile-command":
        print(compile_command(args))
        return 0
    if args.command == "identity":
        print(provider_identity(args))
        return 0
    if args.command == "stage-cache":
        return stage_cache(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
