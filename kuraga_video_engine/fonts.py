"""Font resolution with Cyrillic-capable fallbacks.

Lookup order: ``--font`` / def ``font`` > ``$KURAGA_VIDEO_FONT`` > common
DejaVu/Liberation system paths. All shipped fallbacks cover Cyrillic.
"""

from __future__ import annotations

import os
from pathlib import Path

_BOLD_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)
_REGULAR_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)


class FontNotFoundError(RuntimeError):
    """Raised when no usable TTF is found anywhere on the box."""


def _pick(candidates: tuple[str, ...], explicit: str | None) -> str:
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return str(path)
        raise FontNotFoundError(f"font file not found: {explicit}")
    env = os.getenv("KURAGA_VIDEO_FONT", "").strip()
    if env and Path(env).is_file():
        return env
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise FontNotFoundError(
        "no Cyrillic-capable TTF found; pass --font / def `font:` "
        "or set KURAGA_VIDEO_FONT to a .ttf path"
    )


def bold_font(explicit: str | None = None) -> str:
    """Path to a bold TTF (subtitles, card titles, bait overlays)."""
    return _pick(_BOLD_CANDIDATES, explicit)


def regular_font(explicit: str | None = None) -> str:
    """Path to a regular TTF (bubble body text)."""
    return _pick(_REGULAR_CANDIDATES, explicit)
