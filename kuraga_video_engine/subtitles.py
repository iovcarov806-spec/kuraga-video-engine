"""Subtitle strips and speech bubbles.

Karaoke is built from word-level timings (edge-tts ``WordBoundary`` or the
offline estimator): every word gets an idle clip for the whole line and an
accent clip for its own interval — words light up as they are spoken.

Speech bubbles are Pillow-drawn rounded cards with a speaker name tag and a
tail that points toward the character's side of the frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .constants import (
    HEIGHT,
    SPEAKER_COLORS,
    SPEAKER_LABELS,
    SUB_COLOR_ACTIVE,
    SUB_COLOR_IDLE,
    SUB_FONT_SIZE,
    WIDTH,
)
from .fonts import bold_font, regular_font
from .tts import LineAudio

if TYPE_CHECKING:
    from PIL import Image


@dataclass(slots=True)
class WordBox:
    text: str
    start: float  # absolute seconds on the video timeline
    end: float
    row: int
    x: int  # left edge inside the subtitle strip


def sub_metrics(size: tuple[int, int]) -> dict:
    """Subtitle geometry scaled to the frame (constants are tuned for 1080x1920)."""
    w, h = size
    scale = w / 1080
    return {
        "font_size": max(18, int(SUB_FONT_SIZE * scale)),
        "max_width": int(w * 0.92),
        "bottom_y": int(h * 0.88),
        "row_gap": max(8, int(14 * scale)),
    }


def _wrap_words(
    words: list[str],
    font_size: int,
    max_width: int,
    font_path: str,
) -> list[tuple[int, int]]:
    """Assign each word a (row, x-offset) within a wrapped, centered layout."""
    from PIL import ImageFont

    font = ImageFont.truetype(font_path, font_size)
    space_w = font.getlength(" ")
    rows: list[list[int]] = [[]]
    widths: list[float] = [0.0]
    for i, word in enumerate(words):
        w = font.getlength(word)
        cur = len(rows) - 1
        need = w if not rows[cur] else widths[cur] + space_w + w
        if rows[cur] and need > max_width:
            rows.append([])
            widths.append(0.0)
            cur += 1
            need = w
        rows[cur].append(i)
        widths[cur] = need
    boxes: list[tuple[int, int]] = [(0, 0)] * len(words)
    for row_idx, row in enumerate(rows):
        x = (max_width - widths[row_idx]) / 2
        for i in row:
            w = font.getlength(words[i])
            boxes[i] = (row_idx, round(x))
            x += w + space_w
    return boxes


def word_boxes(
    line: LineAudio,
    line_start: float,
    font_path: str,
    size: tuple[int, int] = (WIDTH, HEIGHT),
) -> tuple[list[WordBox], int]:
    """Position a line's words on the strip; returns (boxes, row_count)."""
    words = [w.text for w in line.words]
    if not words:
        return [], 0
    metrics = sub_metrics(size)
    laid = _wrap_words(words, metrics["font_size"], metrics["max_width"], font_path)
    rows = max(r for r, _ in laid) + 1
    boxes = [
        WordBox(
            text=w.text,
            start=line_start + w.start,
            end=line_start + w.end,
            row=row,
            x=x,
        )
        for w, (row, x) in zip(line.words, laid, strict=True)
    ]
    return boxes, rows


def karaoke_clips(
    line: LineAudio,
    line_start: float,
    line_end: float,
    font_path: str,
    size: tuple[int, int] = (WIDTH, HEIGHT),
) -> list:
    """MoviePy clips implementing word-by-word karaoke for one line.

    Idle (dim) clips span the line; accent clips cover each word's interval.
    """
    from moviepy import TextClip

    boxes, rows = word_boxes(line, line_start, font_path, size)
    if not boxes:
        return []
    w = size[0]
    metrics = sub_metrics(size)
    font_size = metrics["font_size"]
    row_h = font_size + metrics["row_gap"]
    strip_top = metrics["bottom_y"] - rows * row_h
    strip_left = (w - metrics["max_width"]) // 2
    clips = []
    for box in boxes:
        y = strip_top + box.row * row_h
        x = strip_left + box.x
        idle = (
            TextClip(
                text=box.text,
                font=font_path,
                font_size=font_size,
                color=SUB_COLOR_IDLE,
                stroke_color="#000000",
                stroke_width=max(1, int(font_size / 22)),
                method="label",
            )
            .with_start(box.start if box.start < line_end else line_start)
            .with_duration(max(0.05, line_end - line_start))
            .with_position((x, y))
        )
        clips.append(idle)
        active = (
            TextClip(
                text=box.text,
                font=font_path,
                font_size=font_size,
                color=SUB_COLOR_ACTIVE,
                stroke_color="#000000",
                stroke_width=max(1, int(font_size / 22)),
                method="label",
            )
            .with_start(box.start)
            .with_duration(max(0.05, box.end - box.start))
            .with_position((x, y))
        )
        clips.append(active)
    return clips


def bubble_image(
    speaker: str,
    text: str,
    font_path: str | None = None,
    max_width: int = 940,
) -> Image.Image:
    """PIL RGBA image: name tag + wrapped text in a rounded bubble with tail."""
    from PIL import Image, ImageDraw, ImageFont

    scale = max_width / 940
    name_font_path = font_path or bold_font()
    body_font_path = regular_font()
    name_font = ImageFont.truetype(name_font_path, max(14, int(34 * scale)))
    body_font = ImageFont.truetype(body_font_path, max(16, int(44 * scale)))

    color = SPEAKER_COLORS.get(speaker, "#ffffff")
    label = SPEAKER_LABELS.get(speaker, speaker)

    # Wrap body text.
    words = text.split()
    lines: list[str] = []
    cur = ""
    measure = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    for word in words:
        trial = f"{cur} {word}".strip()
        if measure.textlength(trial, font=body_font) > max_width - 80 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)

    pad_x, pad_y = int(40 * scale), int(26 * scale)
    name_h = int(48 * scale)
    line_h = int(56 * scale)
    text_h = line_h * max(1, len(lines))
    bubble_w = max_width
    bubble_h = pad_y * 2 + name_h + text_h
    tail = int(36 * scale)

    img = Image.new("RGBA", (bubble_w, bubble_h + tail), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (0, 0, bubble_w, bubble_h),
        radius=int(34 * scale),
        fill=(18, 18, 26, 235),
        outline=color,
        width=max(2, int(4 * scale)),
    )
    # Tail: student points left, professor right, kuraga/narrator center.
    anchor = {"student": bubble_w * 0.22, "professor": bubble_w * 0.78}.get(speaker, bubble_w * 0.5)
    t26 = int(26 * scale)
    draw.polygon(
        [(anchor - t26, bubble_h - 4), (anchor + t26, bubble_h - 4), (anchor, bubble_h + tail - 4)],
        fill=(18, 18, 26, 235),
        outline=color,
    )
    tag_w = int(240 * scale)
    draw.rounded_rectangle(
        (pad_x, pad_y, pad_x + tag_w, pad_y + name_h - 8),
        radius=int(16 * scale),
        fill=color,
    )
    draw.text(
        (pad_x + int(16 * scale), pad_y + int(4 * scale)), label, font=name_font, fill=(10, 10, 14)
    )
    y = pad_y + name_h
    for line in lines:
        draw.text((pad_x + int(6 * scale), y), line, font=body_font, fill=(245, 245, 250))
        y += line_h
    return img


def bubble_clip(
    speaker: str,
    text: str,
    start: float,
    duration: float,
    font_path: str,
    size: tuple[int, int] = (WIDTH, HEIGHT),
):
    """Bubble as an ImageClip, top-center with a quick fade-in."""
    import numpy as np
    from moviepy import ImageClip, vfx

    w, h = size
    img = bubble_image(speaker, text, font_path, max_width=int(w * 0.88))
    clip = (
        ImageClip(np.array(img))
        .with_start(start)
        .with_duration(max(0.05, duration))
        .with_position(("center", int(h * 0.055)))
        .with_effects([vfx.FadeIn(0.12)])
    )
    return clip


def overlay_text_clip(
    text: str,
    font_path: str,
    font_size: int,
    color: str,
    position: str,
    size: tuple[int, int],
    start: float = 0.0,
    duration: float | None = None,
):
    """Free-standing text clip (end cards, bait overlays, watermarks)."""
    from moviepy import TextClip

    w, h = size
    clip = TextClip(
        text=text,
        font=font_path,
        font_size=font_size,
        color=color,
        stroke_color="#000000",
        stroke_width=max(1, font_size // 22),
        method="caption",
        size=(int(w * 0.9), None),
        text_align="center",
        margin=(0, max(4, font_size // 4)),  # room for descenders (у, р, g)
    ).with_start(start)
    if duration is not None:
        clip = clip.with_duration(max(0.05, duration))
    y = {"top": int(h * 0.10), "center": "center", "bottom": int(h * 0.84)}[position]
    return clip.with_position(("center", y))
