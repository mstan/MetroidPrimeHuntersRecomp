#!/usr/bin/env python3
"""Shared Metroid Prime Hunters ROM-profile helpers for build/capture tools."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_FILE = REPO_ROOT / "config" / "mph_rom_profiles.json"
DEFAULT_VERSION = "US1_0"


def load_profile(path: Path, version: str) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"unable to read ROM profile registry {path}: {exc}") from exc

    profiles = document.get("profiles")
    if not isinstance(profiles, dict):
        raise SystemExit(f"ROM profile registry has no object-valued 'profiles': {path}")
    profile = profiles.get(version)
    if not isinstance(profile, dict):
        choices = ", ".join(sorted(str(key) for key in profiles))
        raise SystemExit(
            f"unknown MPH version {version!r}; configured versions: {choices}"
        )

    required = {
        "display_name": str,
        "game_code": str,
        "revision": int,
        "rom_size": int,
        "sha1": str,
        "program_id": str,
        "coverage": str,
        "game_config": str,
        "fmv_runtime": bool,
        "fmv_runtime_bank": str,
        "launcher_default_rom": str,
        "adaptive_widescreen": bool,
    }
    for key, expected_type in required.items():
        value = profile.get(key)
        if not isinstance(value, expected_type):
            raise SystemExit(
                f"ROM profile {version!r} field {key!r} must be "
                f"{expected_type.__name__}"
            )

    game_code = str(profile["game_code"])
    if len(game_code) != 4 or not game_code.isascii():
        raise SystemExit(
            f"ROM profile {version!r} game_code must be exactly four ASCII bytes"
        )
    digest = str(profile["sha1"])
    if len(digest) != 40 or any(c not in "0123456789abcdef" for c in digest):
        raise SystemExit(
            f"ROM profile {version!r} sha1 must be 40 lowercase hex digits"
        )
    revision = int(profile["revision"])
    if revision < 0 or revision > 255:
        raise SystemExit(f"ROM profile {version!r} revision must fit one byte")
    if int(profile["rom_size"]) <= 0:
        raise SystemExit(f"ROM profile {version!r} rom_size must be positive")

    bank = str(profile["fmv_runtime_bank"])
    if not bank or "_arm9_" not in bank or not bank.replace("_", "a").isalnum():
        raise SystemExit(
            f"ROM profile {version!r} fmv_runtime_bank must be an ARM9 bank identifier"
        )

    return profile


def default_generated_inputs_dir(version: str) -> Path:
    if version == "US1_0":
        return REPO_ROOT / "generated" / "inputs"
    return REPO_ROOT / "generated" / version / "inputs"


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def verify_game_config_identity(
    config_path: Path,
    profile: dict[str, object],
    version: str,
) -> None:
    try:
        with config_path.open("rb") as f:
            document = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"unable to read game config {config_path}: {exc}") from exc

    game = document.get("game")
    if not isinstance(game, dict):
        raise SystemExit(f"game config has no [game] table: {config_path}")
    expected = {
        "id": profile["game_code"],
        "revision": profile["revision"],
        "rom_size": profile["rom_size"],
        "sha1": profile["sha1"],
    }
    for key, value in expected.items():
        if game.get(key) != value:
            raise SystemExit(
                f"game config {config_path} game.{key}={game.get(key)!r}; "
                f"expected {value!r} for {version}"
            )


def verify_rom_identity(
    rom_path: Path,
    profile: dict[str, object],
    version: str,
) -> str:
    expected_size = int(profile["rom_size"])
    try:
        size = rom_path.stat().st_size
    except OSError as exc:
        raise SystemExit(f"unable to stat ROM {rom_path}: {exc}") from exc
    if size != expected_size:
        raise SystemExit(
            f"ROM size mismatch for {version}: got {size}, expected {expected_size}"
        )

    digest = hashlib.sha1()
    try:
        with rom_path.open("rb") as f:
            header = f.read(0x200)
            digest.update(header)
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise SystemExit(f"unable to read ROM {rom_path}: {exc}") from exc

    actual_sha1 = digest.hexdigest()
    expected_sha1 = str(profile["sha1"])
    if actual_sha1 != expected_sha1:
        raise SystemExit(
            f"ROM SHA-1 mismatch for {version}: got {actual_sha1}, "
            f"expected {expected_sha1}"
        )

    expected_code = str(profile["game_code"]).encode("ascii")
    if len(header) <= 0x1E:
        raise SystemExit(f"ROM header is truncated: {rom_path}")
    if header[0x0C:0x10] != expected_code:
        raise SystemExit(
            f"game code mismatch for {version}: got {header[0x0C:0x10]!r}, "
            f"expected {expected_code!r}"
        )
    revision = int(profile["revision"])
    if header[0x1E] != revision:
        raise SystemExit(
            f"ROM revision mismatch for {version}: got {header[0x1E]}, "
            f"expected {revision}"
        )
    return actual_sha1
