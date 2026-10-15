"""Shared constants for the Kuraga video pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

# Vertical TikTok/Reels canvas.
WIDTH: Final = 1080
HEIGHT: Final = 1920
SIZE: Final = (WIDTH, HEIGHT)
FPS: Final = 30

PACKAGE_DIR: Final = Path(__file__).resolve().parent


def _project_root() -> Path:
    """``$KURAGA_VIDEO_ROOT`` > source checkout (has pyproject.toml) > cwd."""
    env = os.getenv("KURAGA_VIDEO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    checkout = PACKAGE_DIR.parent
    if (checkout / "pyproject.toml").is_file():
        return checkout
    return Path.cwd()


# Anchor for relative paths in defs (images, music, cards_from, sfx_dir).
REPO_ROOT: Final = _project_root()
EXAMPLES_DIR: Final = REPO_ROOT / "examples"

# Where generated MP4s land when no --out is given.
DEFAULT_OUT_DIR: Final = REPO_ROOT / "out"
# Scratch space for TTS mp3s, synthesized wavs, generated frames.
DEFAULT_WORK_DIR: Final = REPO_ROOT / ".video_work"

# Speaker palette (bubble name tags + karaoke accents).
SPEAKERS: Final = ("student", "professor", "kuraga", "narrator")
SPEAKER_COLORS: Final = {
    "student": "#4da3ff",
    "professor": "#ff5d5d",
    "kuraga": "#ffd23f",
    "narrator": "#9b8cff",
}
SPEAKER_LABELS: Final = {
    "student": "Студент",
    "professor": "Профессор",
    "kuraga": "КУРАГА",
    "narrator": "Рассказ",
}

# Karaoke strip layout.
SUB_FONT_SIZE: Final = 46
SUB_MAX_WIDTH: Final = 980
SUB_BOTTOM_Y: Final = 1690
SUB_COLOR_IDLE: Final = "#e8e8e8cc"
SUB_COLOR_ACTIVE: Final = "#ffd23f"

# Reaction overlay size (mascot insert, bottom-right).
REACTION_SIZE: Final = 360
REACTION_MARGIN: Final = 40
