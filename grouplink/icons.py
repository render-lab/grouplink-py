"""The card icon library. A leaf module: both the Notion reader and the page
renderer name icons, and neither should have to import the other.

An icon name is the filename without its extension under grouplink/assets/link-icons.
The file is a .svg for the names in SVG_ICONS and a .png for all others. The names in
ORDINALS have no file. The page draws them as digits.
Adding an icon takes a file, a name here, and an option in the Notion dropdown. A new
SVG icon also needs its name in SVG_ICONS.
"""

from __future__ import annotations

from typing import Literal, TypeGuard, get_args

IconName = Literal[
    "arrow",
    "credits",
    "download",
    "email",
    "form",
    "info",
    "render",
    "sandbox",
    "upload",
    "workflows",
    "one",
    "two",
    "three",
    "play",
]

#: The same names at runtime, in declaration order. That order decides the order of
#: the mask rules page.py generates, which changes the CSP style hash.
ICON_NAMES: tuple[IconName, ...] = get_args(IconName)

#: Icons drawn as a digit. They have no file and no mask rule.
ORDINALS: dict[IconName, int] = {"one": 1, "two": 2, "three": 3}

#: Icons whose file is an .svg. All other icon files are .png.
SVG_ICONS: frozenset[IconName] = frozenset(
    {"email", "form", "render", "play", "sandbox", "workflows"}
)

#: What a row with an empty or unrecognized Icon cell renders.
DEFAULT_ICON: IconName = "arrow"


def is_icon_name(value: str) -> TypeGuard[IconName]:
    """True when the value names one of the icon files."""
    return value in ICON_NAMES
