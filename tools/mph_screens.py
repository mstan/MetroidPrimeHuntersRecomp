#!/usr/bin/env python3
"""Recognise which Metroid Prime Hunters menu screen is on the framebuffer.

Navigating these menus by fixed frame budgets is not reliable. MPH menus sit on
an animated 3D background, so "did the frame change" is always true and proves
nothing, and with networking enabled the runs are not even frame-identical to
each other: host packet arrival feeds back into guest timing, so two runs with
byte-identical input sequences reach visibly different animation phases at the
same vblank. A tap delivered mid-transition is silently swallowed and the driver
sails on believing it advanced.

So classify the screen instead. The discriminators below are mean colours of
small UI boxes that do not animate, measured across known-good captures of each
screen rather than estimated.
"""

from __future__ import annotations

from typing import Callable

from PIL import Image

# Boxes are in combined-frame space: 256x384, top screen y 0..191, touch screen
# y 192..383.
BOXES = {
    # Nintendo WFC menu: the orange CONFIGURE WI-FI bar.
    "configure_bar": (95, 222, 165, 236),
    # Friends/Rivals roster: the blue FRIENDS and red RIVALS tabs.
    "friends_tab": (10, 232, 70, 244),
    "rivals_tab": (140, 232, 200, 244),
    # Top screen: bright on logo screens, near-black behind the Hunter License.
    "top_banner": (60, 30, 200, 45),
    # "CONNECT TO NINTENDO WI-FI CONNECTION?" dialog: green check on the left,
    # red cross on the right, both ringed in orange.
    "dialog_yes": (98, 302, 120, 324),
    "dialog_no": (138, 302, 160, 324),
    # Single green check used by pairing/update notices and acknowledgements.
    "dialog_ok": (116, 300, 140, 326),
    # Friends/Rivals lobby, top screen: the ARENA thumbnail. Flat dark green
    # while no game row is selected, a lit photo of the arena once a row is
    # selected and the host's settings have been pulled down (measured: 0
    # bright pixels unselected, 1300-1800 selected).
    "arena_thumb": (140, 45, 245, 120),
    # Lobby overlays cover the orange CREATE GAME bar, which is otherwise the
    # brightest fixed thing on the lobby (measured mean red 158-163 with no
    # dialog, 13-18 under one).
    "create_bar": (30, 318, 120, 332),
    # The orange ">" continue arrow, bottom right of the error dialog only.
    "dialog_arrow": (178, 300, 202, 324),
    # The rotating "no entry" badge of CONNECTING TO FRIEND'S GAME.
    "dialog_spinner": (118, 292, 142, 316),
}


def mean_box(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    region = image.crop(box).resize((1, 1), Image.Resampling.BOX)
    return region.getpixel((0, 0))


def samples(image: Image.Image) -> dict[str, tuple[int, int, int]]:
    return {name: mean_box(image, box) for name, box in BOXES.items()}


def is_wfc_menu(image: Image.Image) -> bool:
    """Nintendo WFC menu: Find Game / Friends and Rivals / Edit Friends."""
    r, g, b = mean_box(image, BOXES["configure_bar"])
    return r > 150 and 40 < g < 130 and b < 45


def is_roster(image: Image.Image) -> bool:
    """Friends and Rivals roster behind the Hunter License."""
    fr, fg, fb = mean_box(image, BOXES["friends_tab"])
    rr, rg, rb = mean_box(image, BOXES["rivals_tab"])
    return fb > 55 and fb > 2 * fr and rr > 70 and rr > 3 * rb


def is_connect_dialog(image: Image.Image) -> bool:
    """The "CONNECT TO NINTENDO WI-FI CONNECTION?" yes/no prompt.

    Both buttons sit on the dialog's flat black fill, so the giveaway is that
    neither box carries any blue at all while the right one is strongly red.
    """
    yr, yg, yb = mean_box(image, BOXES["dialog_yes"])
    nr, ng, nb = mean_box(image, BOXES["dialog_no"])
    return (
        yb <= 8
        and nb <= 8
        and nr > 2 * max(ng, 1)
        and yr > 15
        and yg > 12
    )


def has_available_game(image: Image.Image) -> bool:
    """True when the Friends/Rivals lobby lists at least one hosted game.

    The first AVAILABLE GAMES row is flat dark when the list is empty and
    carries bright HOST / name / PLAYERS text once a friend publishes a game,
    so a bright-pixel count over that row separates the two cleanly (measured:
    0 when empty, ~260 when listed).
    """
    crop = image.crop((12, 234, 110, 276))
    bright = sum(1 for r, g, b in crop.getdata() if r + g + b > 250)
    return bright > 100


def bright_count(image: Image.Image, box: tuple[int, int, int, int]) -> int:
    crop = image.crop(box)
    return sum(1 for r, g, b in crop.getdata() if r + g + b > 250)


def has_selected_game(image: Image.Image) -> bool:
    """True once a lobby row is selected and the host's settings are shown.

    Selecting the advertised row pulls the host's game configuration down onto
    the guest's top screen; the ARENA thumbnail going from flat dark green to a
    lit photo is the cleanest witness of it.
    """
    return bright_count(image, BOXES["arena_thumb"]) > 600


def lobby_dialog_open(image: Image.Image) -> bool:
    """True when a modal covers the lobby's CREATE GAME bar."""
    r, _g, _b = mean_box(image, BOXES["create_bar"])
    return r < 70


def is_join_error(image: Image.Image) -> bool:
    """The "ERROR CODE 80430 ... GAME IS NO LONGER AVAILABLE" modal.

    Its only bright feature is the orange ">" continue arrow in the bottom
    right corner, which the CONNECTING modal does not have.
    """
    if not lobby_dialog_open(image):
        return False
    r, _g, _b = mean_box(image, BOXES["dialog_arrow"])
    return r > 20 and bright_count(image, BOXES["dialog_arrow"]) > 40


def is_connecting(image: Image.Image) -> bool:
    """The "CONNECTING TO FRIEND'S GAME..." modal with its spinning badge."""
    if not lobby_dialog_open(image) or is_join_error(image):
        return False
    return bright_count(image, BOXES["dialog_spinner"]) > 40


def lobby_state(image: Image.Image) -> str:
    """Classify what the guest is looking at during the join attempts."""
    if is_join_error(image):
        return "join-error"
    if is_connecting(image):
        return "connecting"
    if lobby_dialog_open(image):
        return "lobby-dialog"
    if has_available_game(image):
        return "selected-lobby" if has_selected_game(image) else "lobby"
    return "off-lobby"


# Only the navigation screens belong here: identify() is what the driver uses
# to steer between menus, and the lobby-modal predicates above are not safe
# outside the Friends/Rivals lobby. lobby_dialog_open() keys off the CREATE
# GAME bar, which simply does not exist on the roster or the Hunter License, so
# those screens read as "a modal is up" and, because the roster carries orange
# UI where the 80430 dialog's continue arrow sits, as "join-error". Adding them
# here made register_friend() give up on the way back to the WFC menu.
SCREENS: dict[str, Callable[[Image.Image], bool]] = {
    "connect-dialog": is_connect_dialog,
    "wfc-menu": is_wfc_menu,
    "roster": is_roster,
}


def identify(image: Image.Image) -> str:
    for name, predicate in SCREENS.items():
        if predicate(image):
            return name
    return "unknown"


def main() -> int:
    import sys
    from pathlib import Path

    for path in sys.argv[1:]:
        image = Image.open(path).convert("RGB")
        readings = "  ".join(
            f"{name}={value}" for name, value in samples(image).items()
        )
        print(
            f"{Path(path).name}: {identify(image)} lobby={lobby_state(image)}"
            f"\n    {readings}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
