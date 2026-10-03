"""Regression tests for generation-bound overlay span promotion."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from seed_overlay_from_coverage import span_starts


class OverlaySeedsTest(unittest.TestCase):
    def test_spans_keep_modes_and_gaps(self):
        points = [dict(addr=hex(addr), mode=mode, kind="root") for addr, mode in
                  [(0x1000, "arm"), (0x1004, "arm"), (0x1010, "arm"),
                   (0x1000, "thumb"), (0x1002, "thumb"), (0x1006, "thumb")]]
        self.assertEqual(set(span_starts(points)),
                         {(0x1000, "arm"), (0x1010, "arm"),
                          (0x1000, "thumb"), (0x1006, "thumb")})

    def test_same_address_foreign_overlay_is_excluded_and_hashes_checked(self):
        with tempfile.TemporaryDirectory(prefix="mph-overlay-seeds-") as temp:
            root = Path(temp)
            image = bytes(range(256)) * 16
            sha = hashlib.sha1(image).hexdigest()
            (root / "overlay.bin").write_bytes(image)
            (root / "overlays.json").write_text(json.dumps([dict(
                id=12, file="overlay.bin", load_address="0x02133000",
                size=len(image), sha1=sha)]))
            pages = []
            for data, offsets in ((image, [0, 4, 8, 32]), (b"Z" * 4096, [64, 68])):
                bits = bytearray(128)
                for offset in offsets:
                    index = offset // 4
                    bits[index // 8] |= 1 << (index % 8)
                pages.append(dict(addr="0x02133000", cpu=9,
                                  sha1=hashlib.sha1(data).hexdigest(),
                                  data=base64.b64encode(data).decode(),
                                  entry_points=[], root_arm=base64.b64encode(bits).decode()))
            manifest = dict(schema=4, kind="ndsrecomp-tier3-coverage",
                            pages=dict(entries=pages))
            path = root / "coverage.json"
            path.write_text(json.dumps(manifest))
            out = root / "seeds.toml"
            args = [sys.executable, str(Path(__file__).with_name("seed_overlay_from_coverage.py")),
                    "--overlay-id", "12", "--overlays-dir", str(root),
                    "--overlays-json", str(root / "overlays.json"),
                    "--manifest", str(path), "--out", str(out),
                    "--kinds", "call,indirect", "--span-starts"]
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = out.read_text()
            self.assertIn("addr = 0x02133000", text)
            self.assertIn("addr = 0x02133020", text)
            self.assertNotIn("addr = 0x02133004", text)
            self.assertNotIn("addr = 0x02133040", text)
            pages[0]["sha1"] = "0" * 40
            path.write_text(json.dumps(manifest))
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("captured page SHA-1 mismatch", result.stderr)
            (root / "overlay.bin").write_bytes(b"A" * 4096)
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("overlay image SHA-1", result.stderr)


if __name__ == "__main__":
    unittest.main()
