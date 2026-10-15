"""Mode B — viral micro-loop / high-speed slideshow renderer.

Frames switch every ``frame_seconds`` (0.1–1 s). Sources: text cards, images
(mascot stems or files), and auto-generated «билет» cards from a question
file (``cards_from``). Bait overlays like «Пауза чтоб прочитать» /
«Скриншотни свой билет на сессию» sit on top of every frame.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import assets, subtitles
from . import audio as audio_mod
from . import sfx as sfxmod
from .constants import DEFAULT_OUT_DIR, DEFAULT_WORK_DIR, REPO_ROOT
from .fonts import bold_font
from .models import FrameSpec, MicroLoop


@dataclass(slots=True)
class LoopReport:
    out: Path
    seconds: float
    frames: int  # frames per loop
    repeats: int
    warnings: list[str] = field(default_factory=list)


def _wrap(text: str, font, max_width: int, draw) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) > max_width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def _text_image(spec: FrameSpec, size, font_path: str) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont

    w, h = size
    img = Image.new("RGB", size, assets.parse_color(spec.bg) if spec.bg else (13, 13, 18))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, spec.font_size)
    lines = _wrap(spec.text or "", font, int(w * 0.86), draw)
    line_h = int(spec.font_size * 1.25)
    total = line_h * len(lines)
    y = (h - total) // 2
    for line in lines:
        tw = draw.textlength(line, font=font)
        draw.text(
            ((w - tw) / 2, y),
            line,
            font=font,
            fill=spec.color,
            stroke_width=3,
            stroke_fill="#000000",
        )
        y += line_h
    return np.array(img)


def _card_image(spec: FrameSpec, loop: MicroLoop, size, font_path: str) -> np.ndarray:
    """A «Билет на сессию №N» exam-ticket card."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = size
    img = Image.new("RGB", size, (14, 14, 22))
    draw = ImageDraw.Draw(img)
    # Gradient backdrop + double border = "official" ticket look.
    for y in range(h):
        t = y / max(1, h - 1)
        row = tuple(int(16 + 26 * t) for _ in range(3))
        draw.line([(0, y), (w, y)], fill=row)
    draw.rectangle((46, 60, w - 46, h - 60), outline=(255, 210, 63), width=6)
    draw.rectangle((62, 76, w - 62, h - 76), outline=(120, 120, 140), width=2)

    scale = w / 1080
    title_font = ImageFont.truetype(font_path, int(64 * scale))
    num_font = ImageFont.truetype(font_path, int(150 * scale))
    body_font = ImageFont.truetype(font_path, int(58 * scale))

    # Titles sit below a top bait overlay (overlay occupies ~0.10..0.17 h).
    title = loop.card_prefix
    tw = draw.textlength(title, font=title_font)
    draw.text(((w - tw) / 2, int(h * 0.19)), title, font=title_font, fill="#ffd23f")

    number = f"№{spec.number}" if spec.number is not None else "№?"
    tw = draw.textlength(number, font=num_font)
    draw.text(((w - tw) / 2, int(h * 0.25)), number, font=num_font, fill="#ffffff")

    lines = _wrap(spec.text or "", body_font, w - int(220 * scale), draw)
    line_h = int(74 * scale)
    y = int(h * 0.36)
    for line in lines[:10]:
        tw = draw.textlength(line, font=body_font)
        draw.text(((w - tw) / 2, y), line, font=body_font, fill="#f0f0f5")
        y += line_h
    return np.array(img)


def _frame_image(
    spec: FrameSpec, loop: MicroLoop, index: assets.AssetIndex, size, font_path: str, warnings
) -> np.ndarray:
    if spec.card:
        return _card_image(spec, loop, size, font_path)
    if spec.image:
        path = assets.resolve_image(spec.image, index)
        if path is None:
            warnings.append(f"frame image {spec.image!r} not found — placeholder used")
            path, _ = assets.cover_image(spec.image, index, size)
        return np.array(assets.load_pil_image(path, size))
    return _text_image(spec, size, font_path)


def expand_frames(loop: MicroLoop, warnings: list[str]) -> list[FrameSpec]:
    """Materialize ``cards_from`` into «Билет» frames and apply ordering."""
    frames = list(loop.frames)
    if loop.cards_from:
        path = Path(loop.cards_from).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            warnings.append(f"cards_from {loop.cards_from!r} not found — skipped")
        else:
            questions = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            start = len(frames) + 1
            frames += [
                FrameSpec(card=True, number=start + i, text=q) for i, q in enumerate(questions)
            ]
    if loop.shuffle_seed is not None and frames:
        random.Random(loop.shuffle_seed).shuffle(frames)
    if loop.boomerang and len(frames) > 2:
        frames = frames + frames[-2:0:-1]
    return frames


def loop_duration(loop: MicroLoop) -> tuple[int, int, float]:
    """(frames_per_loop, repeats, total_seconds)."""
    n = len(loop.frames)
    per_loop = n * loop.frame_seconds
    if loop.loops is not None:
        repeats = loop.loops
    elif loop.target_seconds is not None:
        repeats = max(1, math.ceil(loop.target_seconds / max(per_loop, 0.05)))
    else:
        repeats = 1
    return n, repeats, per_loop * repeats


def plan_microloop(loop: MicroLoop) -> dict:
    warnings: list[str] = []
    frames = expand_frames(loop, warnings)
    tmp = loop.model_copy(update={"frames": frames, "boomerang": False, "shuffle_seed": None})
    n, repeats, total = loop_duration(tmp)
    return {
        "title": loop.title,
        "frames_per_loop": n,
        "frame_seconds": loop.frame_seconds,
        "repeats": repeats,
        "seconds": round(total, 2),
        "boomerang": loop.boomerang,
        "warnings": warnings,
    }


def render_microloop(
    loop: MicroLoop,
    out: Path | None = None,
    *,
    workdir: Path | None = None,
    logger=None,
) -> LoopReport:
    """Render a Mode B microloop to a vertical MP4."""
    out = Path(out) if out else None
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeVideoClip,
        ImageClip,
    )

    warnings: list[str] = []
    index = assets.index_assets()
    font = bold_font(loop.font)
    frames = expand_frames(loop, warnings)
    if not frames:
        raise ValueError("microloop has no frames to render")

    base = loop.model_copy(update={"frames": frames, "boomerang": False, "shuffle_seed": None})
    n, repeats, total = loop_duration(base)

    clips = []
    seq = frames * repeats
    for i, spec in enumerate(seq):
        arr = _frame_image(spec, loop, index, loop.size, font, warnings)
        clips.append(
            ImageClip(arr).with_start(i * loop.frame_seconds).with_duration(loop.frame_seconds)
        )

    if loop.overlay is not None:
        ov = loop.overlay
        text_clip = subtitles.overlay_text_clip(
            ov.text,
            font,
            ov.font_size,
            ov.color,
            ov.position,
            loop.size,
            duration=total,
        )
        if ov.bg_color:
            w, h = loop.size
            text_y = {
                "top": int(h * 0.10),
                "center": int((h - text_clip.h) / 2),
                "bottom": int(h * 0.84),
            }[ov.position]
            pad = int(ov.font_size * 0.35)
            clips.append(
                ColorClip(
                    (w, int(text_clip.h + pad * 2)),
                    color=assets.parse_color(ov.bg_color),
                )
                .with_start(0)
                .with_duration(total)
                .with_position((0, text_y - pad))
            )
        clips.append(text_clip)
    if loop.watermark:
        from moviepy import TextClip

        wm = (
            TextClip(
                text=loop.watermark,
                font=font,
                font_size=34,
                color="#ffffffaa",
                method="label",
            )
            .with_start(0)
            .with_duration(total)
        )
        w, h = loop.size
        clips.append(wm.with_position((w - wm.w - 24, h - wm.h - 24)))

    video = CompositeVideoClip(clips, size=loop.size, bg_color=(0, 0, 0))
    video = video.with_duration(total)

    audio_events: list[audio_mod.AudioEvent] = []
    if loop.sfx and loop.frame_seconds >= 0.12:
        try:
            path, _ = sfxmod.cue_audio_path(loop.sfx)
            n_ticks = int(total / loop.frame_seconds)
            if n_ticks <= 600:
                audio_events += [
                    audio_mod.AudioEvent(path, i * loop.frame_seconds) for i in range(n_ticks)
                ]
        except KeyError:
            warnings.append(f"unknown sfx {loop.sfx!r} — skipped")
    elif loop.sfx:
        warnings.append("frame_seconds < 0.12 — per-frame sfx disabled")

    bed: tuple[Path, float] | None = None
    if loop.music is not None:
        try:
            if loop.music.file:
                music_path = Path(loop.music.file)
                if not music_path.is_absolute():
                    music_path = REPO_ROOT / music_path
                if not music_path.is_file():
                    raise FileNotFoundError(music_path)
                bed = (music_path, loop.music.volume)
            elif loop.music.synth:
                bed = (sfxmod.cue_audio_path(loop.music.synth)[0], loop.music.volume)
        except (KeyError, FileNotFoundError, OSError) as exc:
            warnings.append(f"music bed unavailable ({exc}) — skipped")

    workdir = workdir or DEFAULT_WORK_DIR
    mix_path = workdir / "mix" / f"{out.stem if out else 'microloop'}_mix.wav"
    if audio_events or bed is not None:
        audio_mod.mix_events(audio_events, total, mix_path, bed=bed)
    else:
        audio_mod.silence(total, mix_path)
    video = video.with_audio(AudioFileClip(str(mix_path)))

    out = Path(out) if out else DEFAULT_OUT_DIR / f"{_slug(loop.title)}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    video.write_videofile(
        str(out),
        fps=loop.fps,
        codec="libx264",
        audio_codec="aac",
        bitrate="5000k",
        preset="medium",
        threads=max(2, min(8, __import__("os").cpu_count() or 2)),
        logger=logger,
    )
    video.close()
    return LoopReport(
        out=out,
        seconds=round(total, 2),
        frames=n,
        repeats=repeats,
        warnings=warnings,
    )


def _slug(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_").lower()
    return text or "microloop"
