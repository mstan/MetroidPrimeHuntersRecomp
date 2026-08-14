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
        print(f"{Path(path).name}: {identify(image)}\n    {readings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
