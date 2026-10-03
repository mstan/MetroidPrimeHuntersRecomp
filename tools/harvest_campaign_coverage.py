#!/usr/bin/env python3
"""Harvest AMHE0 campaign rooms from an isolated, headless debug runner.

Run the runner with --serve --no-save and real BIOS files. This tool requires
write_mem and state_save/state_load support. It edits game DATA, never code,
and writes private snapshots/manifests/screenshots below --out. Do not publish
that directory. A room-byte edit alone is not proof of a visit: review the
screenshots alongside the recorded gameplay state before promoting coverage.

The landing modifier is from libretro/libretro-database, Nintendo DS,
Metroid Prime - Hunters (USA).cht (Select + 220E78FD). It is held during the
native ship landing, not used as an incomplete door-transition shortcut.
All prior coverage seeds must be preserved when ingesting the resulting data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from mph_overlay_route import DebugClient, KEY_BITS, RELEASED

ROM_SHA1 = "90164d1ac127ee5f9815ea4ae7de798c7b5fc629"
ROOM = 0x020E78FD
PLAYER_INDEX = 0x020D9CB8
PLAYER_STRIDE = 0xF30


def room_ids(value: str) -> list[int]:
    result = []
    for item in value.split(","):
        ends = [int(v) for v in item.split("-")]
        result.extend(range(ends[0], ends[-1] + 1))
    if not result or any(r < 27 or r > 92 for r in result):
        raise argparse.ArgumentTypeError("campaign rooms must be within 27..92")
    return list(dict.fromkeys(result))


class Harvest:
    def __init__(self, client: DebugClient, out: Path):
        self.c = client
        self.out = out
        self.log = (out / "writes.jsonl").open("a", encoding="utf-8")
        self.room = None

    def read(self, addr: int, size: int = 1) -> int:
        return int.from_bytes(bytes.fromhex(self.c.cmd("read_mem", addr=addr,
                                                       len=size)["hex"]), "little")

    def write(self, addr: int, value: int, size: int = 1) -> None:
        # Exact data fields only; room progression and live player fields.
        live = any(addr in {a + p * PLAYER_STRIDE for a in
                   (0x020DA7EE, 0x020DA7F0, 0x020DA860, 0x020DA862,
                    0x020DA864, 0x020DA866, 0x020DABE6, 0x020DABE8,
                    0x020DABE3, 0x020DABDB, 0x020DABD9)} for p in range(4))
        if addr != ROOM and not live:
            raise ValueError(f"unapproved data address {addr:#x}")
        before = self.read(addr, size)
        self.c.cmd("write_mem", addr=addr, hex=value.to_bytes(size, "little").hex())
        self.log.write(json.dumps(dict(room=self.room, addr=f"0x{addr:08X}",
                                      size=size, before=before, after=value)) + "\n")
        self.log.flush()

    def save(self, path: Path) -> None:
        # The existing GPU validator can reject some in-flight command states.
        # Advance a few scheduler rounds to a serializable boundary; never
        # weaken the save validator or accept a partially written snapshot.
        for attempt in range(200):
            try:
                self.c.cmd("state_save", path=path.resolve().as_posix())
                return
            except RuntimeError as exc:
                if "GPU3D command state" not in str(exc):
                    raise
                self.c.cmd("run_rounds", count=107 + attempt * 11)
        raise RuntimeError("no serializable GPU boundary found")

    def prepare_ship(self, path: Path) -> None:
        self.c.cmd("reset")
        self.c.advance(7800)
        self.c.tap(128, 96, 3)
        self.c.advance(180)
        actions = json.loads((Path(__file__).resolve().parents[1] /
                              "scenarios/adventure_start.json").read_text())["actions"]
        for action in actions[:8]:
            if action["kind"] == "touch":
                self.c.tap(action["x"], action["y"], 3)
            elif action["kind"] == "key":
                self.c.press(action["key"], 3)
            else:
                self.c.advance(action["frames"])
            self.c.advance(45)
        self.c.tap(236, 184, 3)  # briefing skip
        self.c.advance(1800)
        self.c.screenshot(self.out / "ship.png")
        self.save(path)

    def status(self) -> dict:
        slot = self.read(PLAYER_INDEX)
        offset = min(slot, 3) * PLAYER_STRIDE
        return dict(vblank=self.c.vblank(), mode=self.read(ROOM - 1),
                    room=self.read(ROOM), area=self.read(ROOM + 1),
                    players=self.read(ROOM + 2), player_slot=slot,
                    frontend_state=self.read(0x020E4A04, 4),
                    paused=self.read(0x020FB458),
                    health=self.read(0x020DA7EE + offset, 2),
                    morph=self.read(0x020DA818 + offset),
                    weapon=self.read(0x020DABE2 + offset),
                    special=self.read(0x020DA86E + offset),
                    position=self.c.cmd("read_mem", addr=0x020DA730 + offset,
                                        len=12)["hex"])

    def supply(self) -> int:
        slot = self.read(PLAYER_INDEX)
        if slot > 3:
            raise RuntimeError(f"invalid player index {slot}")
        offset = slot * PLAYER_STRIDE
        for addr, value in ((0x020DA7EE, 799), (0x020DA7F0, 799),
                            (0x020DA860, 4000), (0x020DA864, 4000),
                            (0x020DA862, 950), (0x020DA866, 950)):
            self.write(addr + offset, value, 2)
        self.write(0x020DABE6 + offset, 255)
        self.write(0x020DABE8 + offset, 255)
        return offset

    def select(self, weapon: int) -> None:
        offset = self.supply()
        # Preserve the game's special-slot lock if Omega has been picked up.
        if weapon not in (0, 2) and self.read(0x020DA86E + offset) == 8:
            weapon = 8
        jump = self.read(0x020DABD9 + offset)
        change = self.read(0x020DABDB + offset)
        self.write(0x020DABD9 + offset, (jump & 0xF0) | 1)
        self.write(0x020DABDB + offset, (change & 0xF0) | 11)
        self.write(0x020DABE3 + offset, weapon)
        self.c.advance(4)
        self.write(0x020DABD9 + offset, jump)
        self.c.advance(26)

    def dismiss(self) -> None:
        # Native transmission/dialog continuation. A tap also advances a
        # partially printed message; record the frame for later review.
        for _ in range(3):
            self.c.tap(185, 141, 3)  # next page in the native bottom-screen HUD
            self.c.advance(12)
        self.c.tap(128, 142, 3)  # final-page confirmation
        self.c.advance(18)

    def visit(self, room: int, checkpoint: Path, action_frames: int) -> dict:
        self.room = room
        start = time.monotonic()
        folder = self.out / f"room-{room:02d}"
        folder.mkdir(exist_ok=True)
        record = dict(room=room, verification="pending screenshot review", actions=[])
        self.c.cmd("state_load", path=checkpoint.resolve().as_posix())
        self.c.cmd("deep_trace", on=0)
        self.c.cmd("keys", mask=RELEASED)
        self.c.cmd("touch", x=0, y=0, down=False)
        before = self.c.cmd("static_coverage")
        try:
            self.write(ROOM, room)
            self.c.press("a", 3)
            # The native landing sets its own destination initially. Hold the
            # modifier through that handoff, then stop once a player exists.
            for tick in range(120):
                self.write(ROOM, room)
                self.c.advance(10)
                if tick >= 30 and 1 <= self.read(ROOM + 2) <= 4 and self.read(0x020E4A04, 4) == 14:
                    break
            self.c.advance(90)
            # First landings and boss introductions can publish the room and
            # player count before constructing the local player. Wait for the
            # guest's own health initialization before applying inventory edits.
            for _ in range(30):
                slot = self.read(PLAYER_INDEX)
                if slot <= 3 and self.read(0x020DA7EE + slot * PLAYER_STRIDE, 2):
                    break
                self.c.press("a", 3)
                self.c.advance(60)
            record["arrival"] = self.status()
            self.c.screenshot(folder / "arrival.png")
            # Rival hunters also occupy player slots in adventure mode.
            if not 1 <= record["arrival"]["players"] <= 4 or record["arrival"]["frontend_state"] != 14:
                raise RuntimeError("landing did not reach native gameplay state")
            if not record["arrival"]["health"]:
                raise RuntimeError("local player did not become active")
            self.dismiss()
            for weapon in range(8):
                if weapon in (2, 5):
                    self.dismiss()
                self.select(weapon)
                self.c.press("l", 8)
                self.c.advance(20)
                self.c.press("l", action_frames)
                self.c.advance(25)
                record["actions"].append(dict(requested_weapon=weapon, state=self.status()))
            self.c.screenshot(folder / "weapons.png")
            self.dismiss()
            self.c.tap(231, 167, 3)  # native morph icon
            self.c.advance(45)
            self.c.press("l", 8)
            self.c.press("up", 45)
            self.c.screenshot(folder / "morph.png")
            self.c.tap(231, 167, 3)
            self.c.advance(45)
            self.c.tap(128, 173, 30)  # native scan visor
            self.c.advance(30)
            self.c.press("l", 80)
            self.c.screenshot(folder / "scan.png")
            self.c.tap(128, 173, 30)
            self.c.advance(30)
            # Short movement/jump and touch aim expose collision and camera
            # paths without prolonged blind movement into pits or door loads.
            for key in ("right", "left", "up", "down", "b"):
                self.supply()
                self.c.press(key, 16)
                self.c.advance(8)
            self.c.screenshot(folder / "final.png")
            record["final"] = self.status()
        except Exception as exc:
            record["error"] = str(exc)
        finally:
            self.c.cmd("keys", mask=RELEASED)
            self.c.cmd("touch", x=0, y=0, down=False)
            record["coverage"] = self.c.cmd("coverage_manifest", path=(folder / "coverage.json").resolve().as_posix())
            after = self.c.cmd("static_coverage")
            record["fallback_delta"] = {key: after[key] - before[key] for key in before}
            record["seconds"] = round(time.monotonic() - start, 3)
            (folder / "visit.json").write_text(json.dumps(record, indent=2) + "\n")
        return record


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=19944)
    p.add_argument("--rom", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--make-checkpoint", action="store_true")
    p.add_argument("--rooms", type=room_ids, default=room_ids("27-92"))
    p.add_argument("--charge-frames", type=int, default=65)
    args = p.parse_args()
    if hashlib.sha1(args.rom.read_bytes()).hexdigest() != ROM_SHA1:
        p.error("memory map requires the verified USA AMHE revision-0 ROM")
    args.out.mkdir(parents=True, exist_ok=True)
    c = DebugClient(args.port)
    identity = args.out / "session-start.json"
    c.cmd("coverage_manifest", path=identity.resolve().as_posix())
    if json.loads(identity.read_text())["rom_sha1"] != ROM_SHA1:
        p.error("connected runner has a different ROM")
    harvest = Harvest(c, args.out)
    try:
        if args.make_checkpoint:
            harvest.prepare_ship(args.checkpoint)
        if not args.checkpoint.is_file():
            p.error("checkpoint missing; use --make-checkpoint")
        for room in args.rooms:
            if (args.out / "STOP").exists():
                print("STOP requested; all completed visits retained", flush=True)
                break
            if (args.out / f"room-{room:02d}" / "visit.json").exists():
                print(f"room {room}: existing visit retained", flush=True)
                continue
            record = harvest.visit(room, args.checkpoint, args.charge_frames)
            print(json.dumps({k: record[k] for k in ("room", "fallback_delta", "seconds")} |
                             {"error": record.get("error"), "arrival": record.get("arrival")}), flush=True)
    finally:
        harvest.log.close()
        c.sock.close()


if __name__ == "__main__":
    main()
