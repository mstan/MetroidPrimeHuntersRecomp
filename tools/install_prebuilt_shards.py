#!/usr/bin/env python3
"""Install the AppImage's exact prebuilt shard projection into writable state."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import tempfile
import time


class CacheInstallLock:
    def __init__(self, cache: pathlib.Path) -> None:
        self.path = cache.parent / f".{cache.name}.install.lock"
        self.file = None

    def __enter__(self) -> "CacheInstallLock":
        self.file = self.path.open("a+b")
        deadline = time.monotonic() + 30.0
        while True:
            if self._try_lock():
                self.file.seek(0)
                self.file.truncate()
                self.file.write(f"{os.getpid()}\n".encode("ascii"))
                self.file.flush()
                return self
            if time.monotonic() >= deadline:
                self.file.close()
                self.file = None
                raise RuntimeError(
                    f"timed out waiting for cache install lock: {self.path}")
            time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.file is None:
            return
        self._unlock()
        self.file.close()
        self.file = None

    def _try_lock(self) -> bool:
        assert self.file is not None
        if os.name == "nt":
            import msvcrt
            try:
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
        import fcntl
        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def _unlock(self) -> None:
        assert self.file is not None
        if os.name == "nt":
            import msvcrt
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl
        fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)


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
    # Compatibility with an older provider is deliberately unsupported. An
    # identity transition starts from the package's audited cache instead of
    # merging stale native code and stale absolute index paths.
    cache.parent.mkdir(parents=True, exist_ok=True)
    marker = cache / ".mph-prebuilt-release-id"
    with CacheInstallLock(cache):
        current_id = ""
        if marker.is_file():
            current_id = marker.read_text(encoding="ascii").strip()
        if current_id == release_id:
            return 0

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
            (staging / marker.name).write_text(
                release_id + "\n", encoding="ascii")
            if cache.exists():
                shutil.rmtree(cache)
            os.replace(staging, cache)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
