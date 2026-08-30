#!/usr/bin/env python3
"""Install the AppImage's exact prebuilt shard projection into writable state."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--cache", type=pathlib.Path, required=True)
    args = parser.parse_args()

    source = args.source.resolve()
    cache = args.cache.absolute()
    if cache.name != "live-shard-cache" or cache.is_symlink():
        raise RuntimeError(f"refusing unsafe cache destination: {cache}")
    release_id = (source / "release-id.txt").read_text(
        encoding="ascii").strip()
    current_id = ""
    marker = cache / ".mph-prebuilt-release-id"
    if marker.is_file():
        current_id = marker.read_text(encoding="ascii").strip()
    if current_id == release_id:
        return 0

    # Compatibility with an older provider is deliberately unsupported. An
    # identity transition starts from the package's audited cache instead of
    # merging stale native code and stale absolute index paths.
    cache.parent.mkdir(parents=True, exist_ok=True)
    staging = pathlib.Path(tempfile.mkdtemp(
        prefix=f".{cache.name}.seed-", dir=cache.parent))
    try:
        source_index = json.loads((source / "live-index.json").read_text(
            encoding="utf-8"))
        captures = {}
        for key, entry in source_index.get("captures", {}).items():
            relative = pathlib.Path(entry["dll"])
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"unsafe packaged shard path: {relative}")
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)
            staged = dict(entry)
            staged["dll"] = str((cache / relative).resolve())
            captures[key] = staged
        (staging / "live-index.json").write_text(
            json.dumps({"schema": 2,
                        "rom_sha1": source_index.get("rom_sha1"),
                        "captures": captures}, indent=2) + "\n",
            encoding="utf-8")
        shutil.copy2(source / "shard-manifest.txt",
                     staging / "shard-manifest.txt")
        (staging / marker.name).write_text(release_id + "\n", encoding="ascii")
        if cache.exists():
            shutil.rmtree(cache)
        os.replace(staging, cache)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
