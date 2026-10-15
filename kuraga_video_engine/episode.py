"""Mode A — episodic brainrot/lore renderer (vertical 9:16 MP4).

Per scene: Ken Burns background (mascot asset / file / color / gradient),
dialogue lines synthesized per character via edge-tts, an optional mascot
reaction insert, speech bubbles and a word-by-word karaoke strip. Scene
transitions: ``cut`` (default), ``fade``, or ``glitch`` (noise burst + sfx).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import assets, characters, subtitles, tts
from . import audio as audio_mod
from . import sfx as sfxmod
from .constants import (
    DEFAULT_OUT_DIR,
    DEFAULT_WORK_DIR,
    REACTION_MARGIN,
    REACTION_SIZE,
    REPO_ROOT,
)
from .fonts import bold_font
from .models import DEFAULT_CAST, Episode, Scene, VoiceCast

GLITCH_SECONDS = 0.18
FADE_SECONDS = 0.3
SCENE_TAIL = 0.35
LINE_GAP = 0.15


@dataclass(slots=True)
class RenderReport:
    out: Path
    seconds: float
    lines: int
    synthesized: int
    estimated: int
    warnings: list[str] = field(default_factory=list)


def _resolve_cast(ep: Episode, speaker: str) -> VoiceCast:
    return ep.cast.get(speaker, DEFAULT_CAST.get(speaker, VoiceCast(voice="ru-RU-DmitryNeural")))


def _line_audios(
    ep: Episode, mode: str, warnings: list[str], workdir: Path
) -> list[list[tts.LineAudio]]:
    """Synthesize (auto) or estimate (off) audio for every scene line."""
    texts: list[tuple[str, VoiceCast]] = []
    for scene in ep.scenes:
        for line in scene.lines:
            texts.append((line.text, _resolve_cast(ep, line.speaker)))
    if mode == "off":
        warnings.append("tts=off — dialogue timing estimated, output is muted subtitles-only")
        return [[tts.estimate_line(line.text) for line in scene.lines] for scene in ep.scenes]
    ok, reason = tts.tts_available()
    if not ok:
        warnings.append(f"{reason}; falling back to estimated muted timings")
        return [[tts.estimate_line(line.text) for line in scene.lines] for scene in ep.scenes]
    errors: list[str] = []
    try:
        audios = tts.synth_lines_sync(texts, workdir / "tts", errors=errors)
    except tts.TtsError as exc:
        warnings.append(f"{exc}; falling back to estimated muted timings")
        return [[tts.estimate_line(line.text) for line in scene.lines] for scene in ep.scenes]
    warnings.extend(errors)
    out: list[list[tts.LineAudio]] = []
    i = 0
    for scene in ep.scenes:
        out.append(audios[i : i + len(scene.lines)])
        i += len(scene.lines)
    return out


def _ken_burns(clip, duration: float, mode: str, size: tuple[int, int]):
    """Pan/zoom a still: crop a moving window, scale it back to full frame."""
    if mode == "still" or duration <= 0:
        return clip
    w, h = size

    def scale_at(t: float) -> float:
        p = min(1.0, max(0.0, t / duration))
        if mode == "zoom_in":
            return 1.0 + 0.22 * p
        if mode == "zoom_out":
            return 1.22 - 0.22 * p
        return 1.14

    def anchor_at(t: float) -> tuple[float, float]:
        p = min(1.0, max(0.0, t / duration))
        return {
            "pan_left": (1.0 - p, 0.5),
            "pan_right": (p, 0.5),
            "pan_up": (0.5, 1.0 - p),
            "pan_down": (0.5, p),
        }.get(mode, (0.5, 0.5))

    from PIL import Image

    def frame_at(get_frame, t: float):
        img = Image.fromarray(get_frame(t))
        iw, ih = img.size
        s = scale_at(t)
        cw, ch = max(8, iw / s), max(8, ih / s)
        ax, ay = anchor_at(t)
        x = min(max(0.0, (iw - cw) * ax), iw - cw)
        y = min(max(0.0, (ih - ch) * ay), ih - ch)
        img = img.crop((int(x), int(y), int(x + cw), int(y + ch)))
        img = img.resize((w, h), Image.Resampling.LANCZOS)
        return np.array(img)

    return clip.transform(frame_at)


def _fit_font_size(text: str, font_path: str, size: int, max_width: int) -> int:
    """Largest size <= ``size`` at which ``text`` fits on one line."""
    from PIL import ImageFont

    while size > 12 and ImageFont.truetype(font_path, size).getlength(text) > max_width:
        size -= 4
    return size


def _background(scene: Scene, index: assets.AssetIndex, duration: float, size):
    path, warn = assets.cover_image(scene.bg, index, size)
    from moviepy import ImageClip

    base = ImageClip(np.array(assets.load_pil_image(path, size))).with_duration(duration)
    return _ken_burns(base, duration, scene.ken_burns, size), warn, path.name


def _reaction_clip(scene: Scene, index: assets.AssetIndex, duration: float, size):
    """Bottom-right mascot reaction insert with a soft pop-in and idle bob."""
    if not scene.reaction:
        return None, None
    warn = None
    w, h = size
    side = min(REACTION_SIZE, int(w * 0.36))
    character = characters.parse_character(scene.reaction)
    path = None if character else assets.resolve_image(scene.reaction, index)
    if path is None:
        if character is None and scene.reaction not in assets.SPEC_STEMS:
            return None, f"reaction {scene.reaction!r} not found — skipped"
        if character is None:
            warn = f"reaction {scene.reaction!r} missing — generated КУРАГА insert used"
        path = characters.character_sprite(character or "kuraga", side)
    import numpy as np
    from moviepy import ImageClip, vfx
    from PIL import Image

    img = Image.open(path).convert("RGB")
    iw, ih = img.size
    img = img.crop(((iw - min(iw, ih)) // 2, 0, (iw + min(iw, ih)) // 2, min(iw, ih)))
    img = img.resize((side, side), Image.Resampling.LANCZOS)
    margin = int(REACTION_MARGIN * w / 1080)

    def pos(t: float):
        bob = int(8 * w / 1080) * math.sin(2 * math.pi * 1.4 * t)
        return (w - side - margin, int(h * 0.72) - side + bob)

    clip = (
        ImageClip(np.array(img))
        .with_duration(duration)
        .with_position(pos)
        .with_effects([vfx.FadeIn(0.15)])
    )
    return clip, warn


def _glitch_clip(size, seconds: float = GLITCH_SECONDS):
    """Short RGB noise burst used as the ``glitch`` transition."""
    from moviepy import VideoClip

    rng = np.random.default_rng(0xC0FFEE)

    def make_frame(t: float):
        frame = rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)
        frame[::7] //= 3  # dark scanlines
        return frame

    return VideoClip(make_frame, duration=seconds)


def _scene_events(line_audios, scene_start: float, scene: Scene, ep: Episode):
    """Absolute-timed audio events for a scene (lines + per-line sfx)."""
    events = []
    t = scene_start
    for line, audio in zip(scene.lines, line_audios, strict=True):
        if audio.mp3 is not None:
            events.append(audio_mod.AudioEvent(audio.mp3, t))
        if line.sfx:
            try:
                sfx_path, _ = sfxmod.cue_audio_path(line.sfx, _sfx_dir(ep))
                events.append(audio_mod.AudioEvent(sfx_path, t))
            except KeyError:
                pass
        t += audio.duration + line.pause_after + LINE_GAP
    return events


def _sfx_dir(ep: Episode) -> Path | None:
    if ep.sfx_dir:
        p = Path(ep.sfx_dir).expanduser()
        return p if p.is_absolute() else REPO_ROOT / p
    return None


def _schedule(
    ep: Episode, line_audios
) -> tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]:
    """Scene (start, end) times + each line's absolute (start,end) per scene."""
    scene_spans: list[tuple[float, float]] = []
    line_spans: list[list[tuple[float, float]]] = []
    cursor = 0.0
    for i, scene in enumerate(ep.scenes):
        start = cursor
        t = start
        spans: list[tuple[float, float]] = []
        for line, audio in zip(scene.lines, line_audios[i], strict=True):
            spans.append((t, t + audio.duration))
            t += audio.duration + line.pause_after + LINE_GAP
        end = max(start + scene.min_seconds, t - LINE_GAP + SCENE_TAIL)
        scene_spans.append((start, end))
        line_spans.append(spans)
        transition = ep.scenes[i + 1].transition if i + 1 < len(ep.scenes) else "cut"
        if transition == "fade":
            cursor = end - FADE_SECONDS
        elif transition == "glitch":
            cursor = end + GLITCH_SECONDS
        else:
            cursor = end
    return scene_spans, line_spans


def plan_episode(ep: Episode, tts_mode: str = "auto") -> dict:
    """Timeline + asset plan without rendering anything (--dry-run)."""
    warnings: list[str] = []
    audios = _line_audios(ep, tts_mode, warnings, DEFAULT_WORK_DIR)
    scene_spans, _ = _schedule(ep, audios)
    index = assets.index_assets()
    bg_report = {}
    missing: list[str] = []
    for i, scene in enumerate(ep.scenes):
        _, warn, name = _background(scene, index, 0.1, ep.size)
        bg_report[f"scene_{i}"] = name
        if warn:
            warnings.append(f"scene {i}: {warn}")
            missing.append(scene.bg)
        if (
            scene.reaction
            and characters.parse_character(scene.reaction) is None
            and assets.resolve_image(scene.reaction, index) is None
        ):
            warnings.append(f"scene {i}: reaction {scene.reaction!r} not found")
            missing.append(scene.reaction)
    total = scene_spans[-1][1] if scene_spans else 0.0
    total += ep.end_card_seconds if ep.end_card_text else 0.0
    return {
        "title": ep.title,
        "seconds": round(total, 2),
        "scenes": len(ep.scenes),
        "lines": sum(len(s.lines) for s in ep.scenes),
        "backgrounds": bg_report,
        "warnings": warnings,
        "missing_images": sorted(set(filter(None, missing))),
    }


def render_episode(
    ep: Episode,
    out: Path | None = None,
    *,
    tts_mode: str = "auto",
    workdir: Path | None = None,
    keep_work: bool = False,
    logger=None,
) -> RenderReport:
    """Render a Mode A episode to a vertical MP4. Returns a RenderReport."""
    out = Path(out) if out else None
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeVideoClip,
        vfx,
    )

    workdir = workdir or DEFAULT_WORK_DIR
    warnings: list[str] = []
    index = assets.index_assets()
    font = bold_font(ep.font)
    line_audios = _line_audios(ep, tts_mode, warnings, workdir)
    scene_spans, line_spans = _schedule(ep, line_audios)
    total_lines = sum(len(s.lines) for s in ep.scenes)
    synth_n = sum(1 for rows in line_audios for a in rows if a.synthesized)

    video_clips = []
    audio_events: list[audio_mod.AudioEvent] = []
    for i, scene in enumerate(ep.scenes):
        start, end = scene_spans[i]
        duration = end - start
        bg, warn, _ = _background(scene, index, duration, ep.size)
        if warn:
            warnings.append(f"scene {i}: {warn}")
        video_clips.append(bg.with_start(start))
        if i > 0 and scene.transition == "fade":
            video_clips[-1] = video_clips[-1].with_effects([vfx.FadeIn(FADE_SECONDS)])
        if i > 0 and scene.transition == "glitch":
            video_clips.append(_glitch_clip(ep.size).with_start(start - GLITCH_SECONDS))
            try:
                path, _ = sfxmod.cue_audio_path("glitch", _sfx_dir(ep))
                audio_events.append(audio_mod.AudioEvent(path, start - GLITCH_SECONDS))
            except KeyError:
                pass
        if scene.sfx:
            try:
                path, _ = sfxmod.cue_audio_path(scene.sfx, _sfx_dir(ep))
                audio_events.append(audio_mod.AudioEvent(path, start))
            except KeyError:
                warnings.append(f"scene {i}: unknown sfx {scene.sfx!r} — skipped")

        reaction, warn = _reaction_clip(scene, index, duration, ep.size)
        if warn:
            warnings.append(f"scene {i}: {warn}")
        if reaction is not None:
            video_clips.append(reaction.with_start(start))

        audio_events += _scene_events(line_audios[i], start, scene, ep)
        for (lstart, lend), line, audio in zip(
            line_spans[i], scene.lines, line_audios[i], strict=True
        ):
            if ep.subtitles in ("bubble", "both") and line.bubble:
                video_clips.append(
                    subtitles.bubble_clip(
                        line.speaker, line.text, lstart, lend - lstart + 0.4, font, ep.size
                    )
                )
            if ep.subtitles in ("karaoke", "both"):
                video_clips += subtitles.karaoke_clips(audio, lstart, lend, font, ep.size)

    end_seconds = scene_spans[-1][1] if scene_spans else 0.0
    if ep.end_card_text and ep.end_card_seconds > 0:
        card = ColorClip(ep.size, color=(12, 12, 18)).with_duration(ep.end_card_seconds)
        text = subtitles.overlay_text_clip(
            ep.end_card_text,
            font,
            _fit_font_size(ep.end_card_text, font, 96, int(ep.size[0] * 0.72)),
            "#ffd23f",
            "center",
            ep.size,
            duration=ep.end_card_seconds,
        )
        video_clips += [card.with_start(end_seconds), text.with_start(end_seconds)]
        end_seconds += ep.end_card_seconds

    video = CompositeVideoClip(video_clips, size=ep.size, bg_color=(0, 0, 0))
    video = video.with_duration(end_seconds)

    bed: tuple[Path, float] | None = None
    if ep.music is not None:
        try:
            if ep.music.file:
                music_path = Path(ep.music.file)
                if not music_path.is_absolute():
                    music_path = REPO_ROOT / music_path
                if not music_path.is_file():
                    raise FileNotFoundError(music_path)
                bed = (music_path, ep.music.volume)
            elif ep.music.synth:
                bed = (sfxmod.cue_audio_path(ep.music.synth)[0], ep.music.volume)
        except (KeyError, FileNotFoundError, OSError) as exc:
            warnings.append(f"music bed unavailable ({exc}) — skipped")

    mix_path = workdir / "mix" / f"{out.stem if out else 'episode'}_mix.wav"
    if audio_events or bed is not None:
        audio_mod.mix_events(audio_events, end_seconds, mix_path, bed=bed)
    else:
        audio_mod.silence(end_seconds, mix_path)
    video = video.with_audio(AudioFileClip(str(mix_path)))

    out = out or (DEFAULT_OUT_DIR / f"{_slug(ep.title)}.mp4")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    video.write_videofile(
        str(out),
        fps=ep.fps,
        codec="libx264",
        audio_codec="aac",
        bitrate="6000k",
        preset="medium",
        threads=max(2, min(8, __import__("os").cpu_count() or 2)),
        logger=logger,
    )
    video.close()
    if not keep_work:
        # Cached TTS/placeholders are cheap to keep; only frame tmp is dropped.
        pass
    return RenderReport(
        out=out,
        seconds=round(end_seconds, 2),
        lines=total_lines,
        synthesized=synth_n,
        estimated=total_lines - synth_n,
        warnings=warnings,
    )


def _slug(text: str) -> str:
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_").lower()
    return text or "episode"
