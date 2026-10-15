"""Multi-voice TTS via edge-tts, with a graceful offline fallback.

Each dialogue line is synthesized to MP3 while ``WordBoundary`` events are
captured, giving exact per-word timings for the karaoke subtitle strip.

``--tts off`` (or edge-tts missing / network down) falls back to estimated
timings and silence, so validation, tests and offline batch runs still work.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path

from .constants import DEFAULT_WORK_DIR
from .models import VoiceCast

_CHAR_SECONDS = 0.085  # rough Russian speech rate (~12 chars/s)
_MIN_LINE_SECONDS = 1.0


@dataclass(slots=True)
class WordTiming:
    text: str
    start: float  # seconds from the line audio start
    end: float


@dataclass(slots=True)
class LineAudio:
    """One synthesized (or estimated) dialogue line."""

    mp3: Path | None
    duration: float
    words: list[WordTiming] = field(default_factory=list)
    synthesized: bool = True  # False => estimated timings, no audio


class TtsError(RuntimeError):
    """edge-tts not installed or synthesis failed."""


def tts_available() -> tuple[bool, str]:
    """(importable, reason-if-not)."""
    try:
        import edge_tts  # noqa: F401

        return True, ""
    except ImportError:
        return False, "edge-tts not installed (pip install -r requirements.txt)"


def estimate_line(text: str) -> LineAudio:
    """Offline path: uniform word timing over a text-length duration."""
    duration = max(_MIN_LINE_SECONDS, len(text) * _CHAR_SECONDS)
    words = text.split()
    timings: list[WordTiming] = []
    if words:
        span = duration * 0.85
        step = span / len(words)
        for i, word in enumerate(words):
            timings.append(WordTiming(text=word, start=i * step, end=(i + 1) * step))
    return LineAudio(mp3=None, duration=duration, words=timings, synthesized=False)


async def _synthesize(text: str, cast: VoiceCast, out: Path) -> tuple[float, list[WordTiming]]:
    import edge_tts

    comm = edge_tts.Communicate(
        text,
        voice=cast.voice,
        rate=cast.rate,
        pitch=cast.pitch,
        volume=cast.volume,
        boundary="WordBoundary",
    )
    audio = bytearray()
    words: list[WordTiming] = []
    async for chunk in comm.stream():
        kind = chunk.get("type")
        if kind == "audio":
            audio += chunk["data"]
        elif kind == "WordBoundary":
            offset = int(chunk["offset"]) / 10_000_000  # 100ns ticks -> s
            dur = int(chunk["duration"]) / 10_000_000
            words.append(WordTiming(text=chunk["text"], start=offset, end=offset + dur))
    if not audio:
        raise TtsError(f"edge-tts returned no audio for voice {cast.voice}")

    def _write() -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(bytes(audio))

    await asyncio.to_thread(_write)
    duration = words[-1].end if words else _probe_duration(out)
    return max(duration, _probe_duration(out)), words


def _probe_duration(path: Path) -> float:
    """Duration of an mp3 via moviepy's bundled ffmpeg (already a dep)."""
    try:
        from moviepy import AudioFileClip

        with AudioFileClip(str(path)) as clip:
            return float(clip.duration)
    except Exception:
        return _MIN_LINE_SECONDS


def _cache_path(text: str, cast: VoiceCast, cache_dir: Path) -> Path:
    key = f"{cast.voice}|{cast.rate}|{cast.pitch}|{cast.volume}|{text}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{digest}.mp3"


async def synth_line(
    text: str,
    cast: VoiceCast,
    cache_dir: Path | None = None,
) -> LineAudio:
    """Synthesize one line to a cached mp3 and return it with word timings."""
    cache_dir = cache_dir or (DEFAULT_WORK_DIR / "tts")
    out = _cache_path(text, cast, cache_dir)
    if out.is_file() and out.stat().st_size > 0:
        duration, words = await _boundaries(text, cast)
        return LineAudio(mp3=out, duration=duration or _probe_duration(out), words=words)
    try:
        duration, words = await _synthesize(text, cast, out)
    except Exception as exc:
        raise TtsError(f"edge-tts failed for voice {cast.voice}: {exc}") from exc
    return LineAudio(mp3=out, duration=duration, words=words)


async def _boundaries(text: str, cast: VoiceCast) -> tuple[float, list[WordTiming]]:
    """Re-stream a cached line for its word timings (audio bytes discarded)."""
    import edge_tts

    comm = edge_tts.Communicate(
        text,
        voice=cast.voice,
        rate=cast.rate,
        pitch=cast.pitch,
        volume=cast.volume,
        boundary="WordBoundary",
    )
    words: list[WordTiming] = []
    async for chunk in comm.stream():
        if chunk.get("type") == "WordBoundary":
            offset = int(chunk["offset"]) / 10_000_000
            dur = int(chunk["duration"]) / 10_000_000
            words.append(WordTiming(text=chunk["text"], start=offset, end=offset + dur))
    return (words[-1].end if words else 0.0), words


def synth_lines_sync(
    items: list[tuple[str, VoiceCast]],
    cache_dir: Path | None = None,
    *,
    errors: list[str] | None = None,
    attempts: int = 3,
) -> list[LineAudio]:
    """Blocking wrapper: synthesize a list of (text, cast) sequentially.

    Each line is retried ``attempts`` times (edge-tts sporadically returns
    "No audio was received"). With ``errors`` given, a line that still fails
    falls back to estimated muted timing and the reason is appended there;
    without it the first failure raises :class:`TtsError`.
    """

    async def _one(text: str, cast: VoiceCast) -> LineAudio:
        last: TtsError | None = None
        for attempt in range(max(1, attempts)):
            try:
                return await synth_line(text, cast, cache_dir)
            except TtsError as exc:
                last = exc
                await asyncio.sleep(0.5 * (attempt + 1))
        assert last is not None
        if errors is None:
            raise last
        errors.append(f"{last} (line {text[:40]!r} — estimated, muted)")
        return estimate_line(text)

    async def _run() -> list[LineAudio]:
        return [await _one(text, cast) for text, cast in items]

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run())
    raise TtsError("synth_lines_sync called inside a running event loop")


def silence_wav(path: Path, seconds: float) -> Path:
    """Write a short silent wav (used to keep audio tracks present offline)."""
    import struct
    import wave

    frames = max(1, int(22050 * max(0.05, seconds)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(struct.pack("<h", 0) * frames)
    return path


def estimated_total(texts: list[str]) -> float:
    """Rough duration estimate for --dry-run output."""
    return (
        sum(max(_MIN_LINE_SECONDS, len(t) * _CHAR_SECONDS) for t in texts)
        + math.ceil(len(texts) / 2) * 0.4
    )
