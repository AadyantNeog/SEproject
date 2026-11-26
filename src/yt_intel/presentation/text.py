from string import punctuation
from typing import Literal
from unicodedata import category

from yt_intel.contracts.common import Mode

type TextSurface = Literal["plain", "markdown"]

_MARKDOWN_ESCAPES = str.maketrans(
    {character: f"\\{character}" for character in punctuation}
)
_UNSAFE_CATEGORIES = {"Cc", "Cf", "Cs", "Zl", "Zp"}


def display_text(value: str, surface: TextSurface) -> str:
    """Keep supplied text on one line and make hidden controls visible."""
    parts = []
    for character in value:
        if character == "\\":
            parts.append("\\\\")
        elif category(character) in _UNSAFE_CATEGORIES:
            code = ord(character)
            parts.append(f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}")
        else:
            parts.append(character)
    safe = "".join(parts)
    return safe.translate(_MARKDOWN_ESCAPES) if surface == "markdown" else safe


def format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, remainder = divmod(remainder, 60)
    return f"{seconds} s ({hours}:{minutes:02d}:{remainder:02d})"


def mode_label(mode: Mode) -> str:
    return "Mode: fixture (synthetic data)" if mode == "fixture" else "Mode: live"


def render_lines(lines: list[str], surface: TextSurface) -> str:
    separator = "  \n" if surface == "markdown" else "\n"
    return separator.join(lines)
