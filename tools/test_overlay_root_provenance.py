#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).with_name("verify_overlay_root_provenance.py")
PAGE = 4096


def write_fixture(root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, str]:
    overlays = root / "overlays"
    overlays.mkdir()
    ov0 = bytes([0x11]) * (PAGE * 2)
    ov1 = bytes([0x22]) * PAGE
    (overlays / "ov0.bin").write_bytes(ov0)
    (overlays / "ov1.bin").write_bytes(ov1)
    page = 0x02001000
    digest = hashlib.sha1(ov0[PAGE:PAGE * 2]).hexdigest()
    metadata = [
        {
            "id": 0,
            "file": "ov0.bin",
            "load_address": "0x02000000",
            "size": len(ov0),
            "sha1": hashlib.sha1(ov0).hexdigest(),
        },
        {
            "id": 1,
            "file": "ov1.bin",
            "load_address": "0x02001000",
            "size": len(ov1),
            "sha1": hashlib.sha1(ov1).hexdigest(),
        },
    ]
    overlays_json = root / "overlays.json"
    overlays_json.write_text(json.dumps(metadata), encoding="utf-8")
    config = root / "ov0.toml"
    config.write_text(
        "\n".join([
            "[program]",
            "load_address = 0x02000000",
            "size = 0x00002000",
            "",
            "[identity]",
            f"sha1 = \"{metadata[0]['sha1']}\"",
            "",
            "[[entry_point]]",
            "addr = 0x02001024",
            "mode = \"arm\"",
            "kind = \"runtime_observed\"",
            "",
        ]),
        encoding="utf-8",
        newline="\n",
    )
    return config, overlays_json, overlays, digest


class OverlayRootProvenanceTest(unittest.TestCase):
    def run_verifier(self, root: pathlib.Path, *extra: str,
                     ok: bool = True) -> subprocess.CompletedProcess[str]:
        config, overlays_json, overlays, digest = write_fixture(root)
        command = [
            sys.executable, str(SCRIPT),
            "--config", str(config),
            "--overlays-json", str(overlays_json),
            "--overlays-dir", str(overlays),
            "--overlay-id", "0",
            "--page", "0x02001000",
            "--page-sha1", digest,
        ]
        command.extend(extra or ("--root", "0x02001024"))
        completed = subprocess.run(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ok:
            self.assertEqual(completed.returncode, 0, completed.stderr)
        else:
            self.assertNotEqual(completed.returncode, 0, completed.stdout)
        return completed

    def test_accepts_unique_page_and_in_page_arm_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_verifier(pathlib.Path(directory))
        self.assertIn("uniquely owns page", completed.stdout)

    def test_rejects_root_outside_verified_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_verifier(
                pathlib.Path(directory), "--root", "0x02000024", ok=False)
        self.assertIn("outside verified page", completed.stderr)

    def test_rejects_unaligned_arm_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_verifier(
                pathlib.Path(directory), "--root", "0x02001022", ok=False)
        self.assertIn("not 4-byte aligned", completed.stderr)

    def test_rejects_config_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            config, overlays_json, overlays, digest = write_fixture(root)
            text = config.read_text(encoding="utf-8")
            config.write_text(
                text.replace(
                    f"sha1 = \"{hashlib.sha1(bytes([0x11]) * (PAGE * 2)).hexdigest()}\"",
                    "sha1 = \"0000000000000000000000000000000000000000\""),
                encoding="utf-8")
            completed = subprocess.run([
                sys.executable, str(SCRIPT),
                "--config", str(config),
                "--overlays-json", str(overlays_json),
                "--overlays-dir", str(overlays),
                "--overlay-id", "0",
                "--page", "0x02001000",
                "--page-sha1", digest,
                "--root", "0x02001024",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("config SHA-1", completed.stderr)

    def test_rejects_ambiguous_page_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            config, overlays_json, overlays, digest = write_fixture(root)
            (overlays / "ov1.bin").write_bytes(bytes([0x11]) * PAGE)
            completed = subprocess.run([
                sys.executable, str(SCRIPT),
                "--config", str(config),
                "--overlays-json", str(overlays_json),
                "--overlays-dir", str(overlays),
                "--overlay-id", "0",
                "--page", "0x02001000",
                "--page-sha1", digest,
                "--root", "0x02001024",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("must identify only overlay 0", completed.stderr)


if __name__ == "__main__":
    unittest.main()
