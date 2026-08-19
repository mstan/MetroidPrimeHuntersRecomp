#!/usr/bin/env python3
"""Drive two Metroid Prime Hunters instances into a Wiimmfi friend match.

Public matchmaking is a dead end for locally-driven instances: every instance
authenticates to Wiimmfi cleanly and then parks on "SEARCHING FOR PLAYERS"
forever, because Find Game only offers REGION and OPPONENT RANK filters -- there
is no way to tell it which console to pair with. Friends and Rivals is the path
that lets two specific profiles target each other.

Each instance registers the *other* profile's friend code (roster entry lives in
RAM -- MPH does not write the roster to the cartridge save on this path, so it is
re-entered every run), backs out to the Nintendo WFC menu, then opens Friends and
Rivals so both consoles are online and visible to each other at the same time.

Output can contain real console/network identifiers in ring metadata and
screenshots; keep it under scratch/.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import capture_mph_checkpoints as capture_lib  # noqa: E402
import fuzz_mph_gameplay as input_lib  # noqa: E402
import mph_screens  # noqa: E402
from add_mph_friend import (  # noqa: E402
    CODE_CONFIRM,
    CODE_PAD,
    KEYBOARD,
    MENU_PATH,
    NAME_CONFIRM,
    ROSTER_BACK,
)
from run_mph_wfc_instances import FILTERS  # noqa: E402


# Nintendo WFC menu: Friends and Rivals is the right-hand circle, Find Game the
# left one. Tapping it opens "ORGANIZE A WI-FI BATTLE WITH YOUR FRIENDS AND
# RIVALS" and prompts to connect.
FRIENDS_AND_RIVALS = (190, 98)
# Yes/no prompts share this layout: green check left, red cross right.
DIALOG_YES = (108, 124)
# Friends/Rivals lobby: AVAILABLE GAMES list with CREATE GAME under it. The
# lobby is asymmetric -- somebody has to host before anybody can join.
CREATE_GAME = (75, 136)
FIRST_GAME_ROW = (85, 52)
# CREATE GAME does not publish the game by itself: it opens "MAKE THIS GAME
# AVAILABLE TO: FRIENDS / RIVALS", whose green check is what actually lists it.
AVAILABILITY_CONFIRM = (128, 136)
# The advertised row's text block. Tapping it SELECTS the row -- the host's
# game settings appear on the guest's top screen, which mph_screens sees as
# "selected-lobby". Selection alone never joins; A is the connect action.
GAME_ROW = (40, 55)
# Right-hand panel under ONLINE n/n: the VIEW button.
VIEW_BUTTON = (215, 110)
# The 80430 modal has TWO pages: the error text with an orange ">" bottom right,
# then a support-phone-number page with a back "<" and a green check. Tapping
# the ">" only turns the page -- the check is what closes it. Getting this wrong
# in an earlier run left the modal open, so the attempts that followed were
# delivered to a dialog instead of the lobby and proved nothing.
ERROR_NEXT_PAGE = (190, 120)
ERROR_CONFIRM = (128, 120)
# Interactions tried, in order, to actually enter the advertised game. Each is
# (name, steps, settle_beats); a step is one beat of the lockstep clock, so the
# host idles for exactly as many frames as the guest spends acting.
JOIN_ATTEMPTS = (
    # PROVEN, twice, to reach "CONNECTING TO FRIEND'S GAME...": select the row,
    # then A. This is the join interaction; everything after it is network. The
    # long settle is to time how long CONNECTING runs before 80430 lands.
    # There is exactly ONE attempt per session: an 80430 does not leave the
    # guest in the lobby to try again, it drops the console off Friends and
    # Rivals and back to the Nintendo WFC menu (measured -- run 3's second and
    # third attempts were delivered to the WFC menu and then to a 52200
    # "unable to connect to Nintendo WFC" modal, proving nothing). Anything
    # else to try has to be a fresh run, not a further tap in this one.
    ("select-then-a", (("tap", *GAME_ROW), ("key", "a")), 8),
)
# Publishing drops the host into game setup, whose first tab is the mode picker
# (BATTLE is the large pre-selected disc). The room is advertised at PLAYERS 1/4
# from this point, but a guest tapping the row is ignored, so the host has to be
# carried through setup rather than left parked here.
MODE_BATTLE = (45, 67)
# Confirming the mode moves setup on to the ARENA tab (arena, point goal, time
# limit, team play); its green check is what finally opens the room.
SETTINGS_CONFIRM = (212, 172)
# ...and that lands on SELECT HUNTER, the third setup tab. Only the first three
# portraits are selectable; the leftmost is Samus.
HUNTER_SAMUS = (27, 132)
HOST_START_DISC = (240, 149)
CONFIG_CAPTURE_FRAMES = (600, 1200, 2400)
POST_JOIN_CAPTURE_FRAMES = (240, 240, 240, 240, 240, 240, 240, 240)


@dataclass
class Instance:
    index: int
    port: int
    output: Path
    save_path: Path
    firmware_path: Path | None
    inject_firmware_path: Path
    code: str
    name: str
    process: subprocess.Popen[bytes]
    client: capture_lib.DebugClient | None = None
    report: list[dict[str, Any]] = field(default_factory=list)


def launch_instance(args: argparse.Namespace, index: int) -> Instance:
    output = args.out / f"instance{index}"
    output.mkdir(parents=True, exist_ok=True)
    port = args.base_port + index
    save_path = (args.profile_dir / f"mph_instance{index}.sav").resolve()
    inject = (args.profile_dir / f"mph_instance{index}.firmware.bin").resolve()
    command = [
        str(args.runner),
        str(args.bios),
        "--serve",
        "--port",
        str(port),
        "--rom",
        str(args.rom),
        "--config",
        str(args.config),
        "--startup-mode",
        args.startup_mode,
        "--network",
        "on",
        "--network-backend",
        args.network_backend,
        "--wfc",
        "on",
        "--wfc-provider",
        args.wfc_provider,
        # Prepared per-profile firmware carries the console identity. The
        # runner instance index is still useful for host-side networking:
        # slirp uses it to place each emulated DS on a distinct virtual LAN,
        # and the local WFC peer bridge binds 127.0.0.1:27610+index. The base
        # offset lets a run coexist with an unrelated live session already
        # holding a lower bridge port.
        "--instance-index",
        str(args.instance_base + index),
        "--save-path",
        str(save_path),
    ]
    if args.firmware_path is not None:
        command.extend(["--firmware-path", str(args.firmware_path)])

    stdout = (output / "runner.stdout.log").open("wb")
    stderr = (output / "runner.stderr.log").open("wb")
    try:
        process = subprocess.Popen(
            command,
            cwd=args.runner.parent,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        stdout.close()
        stderr.close()
    return Instance(
        index=index,
        port=port,
        output=output,
        save_path=save_path,
        firmware_path=args.firmware_path,
        inject_firmware_path=inject,
        code=args.codes[index],
        name=args.names[index],
        process=process,
    )


def ring_count(item: dict[str, Any], kind: str) -> int:
    ring = item.get("ring", {}).get(kind, {})
    events = ring.get("events", []) if isinstance(ring, dict) else []
    return len(events)


def save_checkpoint(instance: Instance, label: str) -> dict[str, Any]:
    assert instance.client is not None
    item = input_lib.save_checkpoint(
        instance.client, instance.output, len(instance.report), label
    )
    item["ring"] = {
        name: instance.client.command("net_ring_dump", max=256, filter=name)
        for name in FILTERS
    }
    instance.report.append(item)
    print(
        f"[{instance.index}] {label} vblank9={item['vblank9']} "
        f"udp={ring_count(item, 'udp_packet')} {item['image']}",
        flush=True,
    )
    return item


def tap_and_save(instance: Instance, label: str, x: int, y: int, wait: int) -> None:
    assert instance.client is not None
    input_lib.tap(instance.client, x, y, 12)
    input_lib.advance_frames(instance.client, wait)
    save_checkpoint(instance, label)


def beat(instance: Instance, action: tuple[Any, ...] | None, frames: int) -> None:
    """One tick of the lockstep clock: optional input, then a fixed idle.

    Both tap() and press_key() hold for 12 frames, and an instance with nothing
    to do idles for the same 12, so every beat costs 12 + frames on every
    instance no matter what it did. That is what lets the guest branch on what
    it sees without drifting away from the host it is trying to talk to.
    """
    assert instance.client is not None
    if action is None:
        input_lib.advance_frames(instance.client, 12)
    elif action[0] == "tap":
        input_lib.tap(instance.client, action[1], action[2], 12)
    elif action[0] == "key":
        input_lib.press_key(instance.client, action[1], 12)
    else:
        raise ValueError(f"unknown beat action: {action!r}")
    input_lib.advance_frames(instance.client, frames)


def current_screen(instance: Instance) -> str:
    assert instance.client is not None
    return mph_screens.identify(
        input_lib.combined_framebuffer(instance.client)
    )


def tap_until_screen(
    instance: Instance,
    label: str,
    x: int,
    y: int,
    wait: int,
    want: str,
    retries: int,
) -> bool:
    """Tap until the expected screen is actually on the framebuffer.

    A tap delivered mid-transition is silently swallowed, and "did the frame
    change" cannot detect that because the menu background animates constantly.
    That is what left an earlier two-instance run parked on the roster for its
    whole online window while every step still reported success. Verify the
    destination instead, and re-tap if it was missed.
    """
    assert instance.client is not None
    for attempt in range(retries + 1):
        input_lib.tap(instance.client, x, y, 12)
        input_lib.advance_frames(instance.client, wait)
        seen = current_screen(instance)
        if seen == want:
            save_checkpoint(instance, label)
            return True
        print(
            f"[{instance.index}] {label} tap {attempt}: expected {want}, "
            f"saw {seen}; retrying",
            flush=True,
        )
    save_checkpoint(instance, f"{label}-missed")
    return False


def for_each(
    instances: list[Instance],
    action: Callable[[Instance], Any],
) -> list[Any]:
    with ThreadPoolExecutor(max_workers=len(instances)) as executor:
        futures = [executor.submit(action, instance) for instance in instances]
        return [future.result() for future in futures]


def register_friend(instance: Instance, args: argparse.Namespace) -> None:
    """Walk Edit Friends and Rivals -> Add Friend and register the peer code."""
    assert instance.client is not None
    settle = args.key_settle
    tap_and_save(instance, "edit-friends-rivals", 183, 176, 900)
    tap_and_save(instance, "add-friend", 220, 171, 600)

    for digit in instance.code:
        x, y = CODE_PAD[digit]
        input_lib.tap(instance.client, x, y, 12)
        input_lib.advance_frames(instance.client, settle)
    save_checkpoint(instance, "code-entered")

    tap_and_save(instance, "code-confirm", *CODE_CONFIRM, 900)
    # A blank temporary name is rejected; the dialog's centre check opens the
    # on-screen keyboard.
    tap_and_save(instance, "name-keyboard", 128, 126, 600)
    for character in instance.name:
        x, y = KEYBOARD[character.lower()]
        input_lib.tap(instance.client, x, y, 12)
        input_lib.advance_frames(instance.client, settle)
    save_checkpoint(instance, "name-typed")
    tap_and_save(instance, "name-confirm", *NAME_CONFIRM, 1500)
    # The Hunter License / roster screen keeps animating after the friend lands;
    # let it settle before trying to leave or the back tap is swallowed.
    input_lib.advance_to_vblank(instance.client, args.roster_settle_vblank)
    save_checkpoint(instance, "roster-settled")
    # One back tap from the settled roster lands on the Nintendo WFC menu.
    if not tap_until_screen(
        instance, "back-to-wfc", *ROSTER_BACK, 900, "wfc-menu", args.tap_retries
    ):
        raise RuntimeError(
            f"instance {instance.index} never reached the WFC menu after entry"
        )


def drive(args: argparse.Namespace, instances: list[Instance]) -> dict[str, Any]:
    for_each(
        instances,
        lambda instance: capture_lib.wait_for_server(
            instance.port, instance.process
        ),
    )
    for instance in instances:
        instance.client = capture_lib.DebugClient(instance.port, timeout=1800)

    def inject(instance: Instance) -> None:
        assert instance.client is not None
        input_lib.advance_to_vblank(instance.client, 120)
        response = instance.client.command(
            "firmware_replace", hex=instance.inject_firmware_path.read_bytes().hex()
        )
        if not isinstance(response, dict) or not response.get("ok"):
            raise RuntimeError(f"firmware_replace failed: {response!r}")

    for_each(instances, inject)

    def title(instance: Instance) -> None:
        assert instance.client is not None
        input_lib.advance_to_vblank(instance.client, args.title_vblank)
        save_checkpoint(instance, "title")

    for_each(instances, title)

    for label, x, y, wait in MENU_PATH[:4]:
        for_each(
            instances,
            lambda instance, label=label, x=x, y=y, wait=wait: tap_and_save(
                instance, label, x, y, wait
            ),
        )

    for_each(instances, lambda instance: register_friend(instance, args))

    for_each(
        instances,
        lambda instance: tap_until_screen(
            instance,
            "connect-prompt",
            *FRIENDS_AND_RIVALS,
            args.prompt_wait,
            "connect-dialog",
            args.tap_retries,
        ),
    )

    # Answering yes takes the console online against its own roster: this is the
    # handshake that public Find Game reached too, only now aimed at a friend.
    for_each(
        instances,
        lambda instance: tap_and_save(
            instance, "wfc-connect", *DIALOG_YES, args.online_wait
        ),
    )

    # The lobby is asymmetric: one console creates the game, the rest pick it out
    # of AVAILABLE GAMES. Driving both sides identically leaves everyone staring
    # at an empty list, which is the same shape of dead end as public search.
    host = instances[args.host_index]
    # Both consoles are live peers on one host network, so neither may free-run
    # while the other is parked: an instance that is not being advanced does not
    # execute, and therefore does not answer its peer. Every lobby phase advances
    # all instances by the same number of guest frames -- only the taps differ.
    tap_frames = args.lobby_wait + 12

    def create_phase(instance: Instance) -> None:
        assert instance.client is not None
        if instance is host:
            tap_and_save(instance, "create-game", *CREATE_GAME, args.lobby_wait)
            tap_and_save(
                instance, "publish-game", *AVAILABILITY_CONFIRM, args.lobby_wait
            )
        else:
            input_lib.advance_frames(instance.client, 2 * tap_frames)
            save_checkpoint(instance, "lobby-wait")

    for_each(instances, create_phase)

    def lockstep_host_action(
        label: str, action: tuple[Any, ...], capture_frames: tuple[int, ...]
    ) -> None:
        """Host drives one setup control; guests idle for the identical frames."""

        def step(instance: Instance) -> None:
            assert instance.client is not None
            beat(instance, action if instance is host else None, 0)
            role = "host" if instance is host else "guest"
            for index, frames in enumerate(capture_frames):
                input_lib.advance_frames(instance.client, frames)
                save_checkpoint(instance, f"{role}-{label}-{index}")

        for_each(instances, step)

    # Setup is a sequence, not a single confirmation: mode, then arena/settings.
    lockstep_host_action("mode", ("tap", *MODE_BATTLE), CONFIG_CAPTURE_FRAMES)
    lockstep_host_action(
        "settings", ("tap", *SETTINGS_CONFIRM), CONFIG_CAPTURE_FRAMES
    )
    lockstep_host_action("hunter", ("tap", *HUNTER_SAMUS), CONFIG_CAPTURE_FRAMES)
    # SELECT HUNTER has no on-screen confirm, and leaving the host parked on it
    # is a candidate explanation for the guest's 80430 ("game is no longer
    # available"): try to carry the host off the setup tabs and into whatever
    # waiting state a real host sits in before a guest arrives.
    lockstep_host_action("hunter-confirm", ("key", "a"), CONFIG_CAPTURE_FRAMES)

    join_log: list[dict[str, Any]] = []

    def guest_state(instance: Instance) -> str:
        assert instance.client is not None
        return mph_screens.lobby_state(
            input_lib.combined_framebuffer(instance.client)
        )

    def join_phase(instance: Instance) -> None:
        assert instance.client is not None
        is_host = instance is host
        role = "host" if is_host else "guest"

        # Wait for the host's game to actually appear before tapping: an earlier
        # run tapped the row on a schedule and there was nothing under the
        # finger yet.
        listed = False
        poll = args.join_poll
        for poll in range(args.join_poll):
            if is_host:
                break
            if mph_screens.has_available_game(
                input_lib.combined_framebuffer(instance.client)
            ):
                listed = True
                break
            input_lib.advance_frames(instance.client, args.join_poll_frames)
        if is_host:
            input_lib.advance_frames(
                instance.client, args.join_poll * args.join_poll_frames
            )
            save_checkpoint(instance, "host-idle")
        else:
            save_checkpoint(instance, f"lobby-listed-{listed}")
            remaining = args.join_poll - (poll if listed else args.join_poll)
            if remaining > 0:
                input_lib.advance_frames(
                    instance.client, remaining * args.join_poll_frames
                )

        # Each attempt is: its input beats, then settle beats to let the join
        # resolve, then dismissal beats that clear an 80430 modal so the next
        # attempt starts from the lobby again. Every beat costs identical frames
        # on host and guest, so the two stay live peers throughout.
        joined = False
        for name, steps, settle_beats in JOIN_ATTEMPTS:
            for step in steps:
                beat(
                    instance,
                    None if is_host or joined else step,
                    args.join_beat_frames,
                )
            for index in range(settle_beats):
                beat(instance, None, args.join_settle_frames)
                state = "" if is_host else guest_state(instance)
                save_checkpoint(
                    instance,
                    f"{role}-{name}-settle{index}"
                    + (f"-{state}" if state else ""),
                )
                if state == "off-lobby":
                    joined = True
            # Clear whatever the attempt left on screen so the next one starts
            # from the lobby: page the 80430 modal forward, close it, and if
            # closing it dropped the console offline, answer the reconnect
            # prompt. Each is one beat whether or not it acts.
            recovery = (
                ("tap", *ERROR_NEXT_PAGE),
                ("tap", *ERROR_CONFIRM),
                ("idle",),
                ("reconnect",),
                ("idle",),
            )
            for action in recovery:
                choice: tuple[Any, ...] | None = None
                if not is_host and not joined:
                    assert instance.client is not None
                    image = input_lib.combined_framebuffer(instance.client)
                    if action[0] == "reconnect":
                        if mph_screens.is_connect_dialog(image):
                            choice = ("tap", *DIALOG_YES)
                    elif action[0] == "tap" and mph_screens.lobby_dialog_open(
                        image
                    ):
                        choice = action
                beat(instance, choice, args.join_beat_frames)
            if not is_host:
                final = guest_state(instance)
                save_checkpoint(instance, f"guest-{name}-after-{final}")
                join_log.append({"attempt": name, "state": final, "joined": joined})
                print(f"[join] {name}: {final} joined={joined}", flush=True)

    for_each(instances, join_phase)

    post_join_log: list[dict[str, Any]] = []

    def post_join_action(
        label: str,
        actor: Instance,
        action: tuple[Any, ...],
        capture_frames: tuple[int, ...] = POST_JOIN_CAPTURE_FRAMES,
    ) -> None:
        def input_step(instance: Instance) -> None:
            assert instance.client is not None
            beat(instance, action if instance is actor else None, 0)

        for_each(instances, input_step)

        for index, frames in enumerate(capture_frames):
            for_each(
                instances,
                lambda instance, frames=frames: input_lib.advance_frames(
                    instance.client, frames
                ),
            )
            for instance in instances:
                role = "host" if instance is host else "guest"
                save_checkpoint(instance, f"{role}-postjoin-{label}-{index}")

    if any(entry["joined"] for entry in join_log):
        guest = next(instance for instance in instances if instance is not host)
        post_join_action("guest-samus", guest, ("tap", *HUNTER_SAMUS))
        post_join_action("guest-confirm", guest, ("key", "a"))
        post_join_action("host-disc", host, ("tap", *HOST_START_DISC))
        for instance in instances:
            state = current_screen(instance)
            post_join_log.append(
                {
                    "instance": instance.index,
                    "screen": state,
                    "final_image": instance.report[-1]["image"],
                    "final_vblank9": instance.report[-1]["vblank9"],
                }
            )
            print(
                f"[post-join] instance {instance.index}: {state} "
                f"{instance.report[-1]['image']}",
                flush=True,
            )

    for target in args.targets:
        for_each(
            instances,
            lambda instance, target=target: (
                input_lib.advance_to_vblank(instance.client, target),
                save_checkpoint(instance, f"wait-{target}"),
            ),
        )

    summaries = []
    for instance in instances:
        # summary.json keeps only per-filter counts, which is enough to say the
        # backend was clean but not enough to say WHO a failing join talked to.
        # The ring entries carry src/dst IPv4 and ports, so keep the raw report
        # per instance: after an 80430 the question is always which peer the
        # guest was trying to reach and whether anything came back.
        (instance.output / "report.json").write_text(
            json.dumps(instance.report, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        steps = [
            {
                "label": item["label"],
                "vblank9": item["vblank9"],
                "image": item["image"],
                "counts": {name: ring_count(item, name) for name in FILTERS},
            }
            for item in instance.report
        ]
        max_counts = {
            name: max((step["counts"][name] for step in steps), default=0)
            for name in FILTERS
        }
        summaries.append(
            {
                "instance": instance.index,
                "port": instance.port,
                "registered_code": instance.code,
                "friend_name": instance.name,
                "save_path": str(instance.save_path),
                "network_reached": (
                    max_counts["dhcp"] > 0
                    and max_counts["dns_query"] > 0
                    and max_counts["tcp_open"] > 0
                ),
                "tls_reached": max_counts["tls_record"] > 0,
                "backend_clean": (
                    max_counts["backend_error"] == 0
                    and max_counts["backend_drop"] == 0
                ),
                "max_counts": max_counts,
                "final_label": steps[-1]["label"] if steps else None,
                "final_vblank9": steps[-1]["vblank9"] if steps else None,
                "steps": steps,
            }
        )
    return {
        "instances": len(instances),
        "network_backend": args.network_backend,
        "wfc_provider": args.wfc_provider,
        "join_attempts": join_log,
        "joined": any(entry["joined"] for entry in join_log),
        "post_join": post_join_log,
        "summaries": summaries,
        "backend_clean": all(s["backend_clean"] for s in summaries),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--bios", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profile-dir", type=Path, required=True)
    parser.add_argument("--firmware-path", type=Path)
    parser.add_argument(
        "--codes",
        nargs="+",
        required=True,
        help="Per instance, the PEER's 12-digit friend code to register.",
    )
    parser.add_argument(
        "--names",
        nargs="+",
        required=True,
        help="Per instance, the temporary name given to that peer.",
    )
    parser.add_argument("--base-port", type=int, default=20460)
    parser.add_argument(
        "--instance-base",
        type=int,
        default=0,
        help="Offset added to each runner --instance-index (slirp subnet and "
        "local WFC peer-bridge slot), so runs can coexist with another live "
        "instance already holding lower bridge ports.",
    )
    parser.add_argument("--startup-mode", default="automatic")
    parser.add_argument("--network-backend", default="slirp")
    parser.add_argument("--wfc-provider", default="wiimmfi")
    parser.add_argument("--title-vblank", type=int, default=7800)
    parser.add_argument("--key-settle", type=int, default=18)
    parser.add_argument("--online-wait", type=int, default=3600)
    parser.add_argument("--prompt-wait", type=int, default=1200)
    parser.add_argument("--lobby-wait", type=int, default=1800)
    parser.add_argument("--join-poll", type=int, default=8)
    parser.add_argument("--join-poll-frames", type=int, default=300)
    parser.add_argument(
        "--join-beat-frames",
        type=int,
        default=400,
        help="Frames per input/dismiss beat during the join attempts.",
    )
    parser.add_argument(
        "--join-settle-frames",
        type=int,
        default=1200,
        help="Frames per settle beat; a join takes several to resolve.",
    )
    parser.add_argument(
        "--host-index",
        type=int,
        default=0,
        help="Instance that taps CREATE GAME; the others join its game.",
    )
    parser.add_argument("--roster-settle-vblank", type=int, default=18000)
    parser.add_argument(
        "--tap-retries",
        type=int,
        default=3,
        help="Extra taps allowed when a transition tap does not change the frame.",
    )
    parser.add_argument(
        "--targets", type=int, nargs="+", default=[30000, 40000, 50000, 60000]
    )
    args = parser.parse_args()

    codes = [code.replace(" ", "").replace("-", "") for code in args.codes]
    for code in codes:
        if len(code) != 12 or not code.isdigit():
            parser.error(f"friend code must be 12 digits: {code!r}")
    args.codes = codes
    if len(args.names) != len(codes):
        parser.error("--names must have one entry per --codes entry")
    for name in args.names:
        for character in name.lower():
            if character not in KEYBOARD:
                parser.error(f"name {name!r} has an unavailable character")

    for attribute in ("runner", "bios", "rom", "config", "profile_dir", "firmware_path"):
        value = getattr(args, attribute)
        if value is not None:
            setattr(args, attribute, value.resolve())
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)

    instances = [launch_instance(args, index) for index in range(len(codes))]
    try:
        summary = drive(args, instances)
        (args.out / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(
            json.dumps(
                {
                    s["instance"]: {
                        "network_reached": s["network_reached"],
                        "tls_reached": s["tls_reached"],
                        "udp_packet": s["max_counts"]["udp_packet"],
                        "final": s["final_label"],
                    }
                    for s in summary["summaries"]
                },
                indent=2,
            ),
            flush=True,
        )
    finally:
        for instance in instances:
            if instance.client is not None:
                try:
                    instance.client.close()
                except OSError:
                    pass
            instance.process.terminate()
            try:
                instance.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                instance.process.kill()
                instance.process.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
