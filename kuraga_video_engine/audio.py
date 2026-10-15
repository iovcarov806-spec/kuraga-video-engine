"""Timeline audio mixing — one flat wav instead of a 200-clip composite.

Every cue/voice/music file is decoded once into a mono float array, summed
at its absolute start time, and written to a single wav which becomes the
video's only audio clip. This sidesteps moviepy's shared-reader quirks with
many short file clips and makes mixing deterministic (and unit-testable).
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 44100


@dataclass(slots=True)
class AudioEvent:
    path: Path
    start: float  # seconds on the video timeline
    volume: float = 1.0


def _ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def decode(path: Path, sr: int = SR) -> np.ndarray:
    """Decode any audio file to a mono float32 array at ``sr`` Hz."""
    path = Path(path)
    if path.suffix.lower() == ".wav":
        try:
            return _decode_wav(path, sr)
        except Exception:
            pass
    exe = _ffmpeg()
    if exe:
        proc = subprocess.run(
            [exe, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout:
            pcm = np.frombuffer(proc.stdout, dtype="<i2").astype(np.float32) / 32768.0
            return pcm
    # Last resort: moviepy's reader (also ffmpeg under the hood).
    from moviepy import AudioFileClip

    with AudioFileClip(str(path)) as clip:
        arr = clip.to_soundarray(fps=sr)
    if arr.ndim == 2:
        arr = arr.mean(axis=1)
    return arr.astype(np.float32)


def _decode_wav(path: Path, sr: int) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        n_channels = wav.getnchannels()
        sampwidth = wav.getsampwidth()
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if sampwidth == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sampwidth == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    elif sampwidth == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported wav sampwidth {sampwidth}")
    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)
    if rate != sr:
        data = _resample_linear(data, rate, sr)
    return data


def _resample_linear(data: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if len(data) == 0:
        return data
    n_out = int(len(data) * sr_out / sr_in)
    x = np.linspace(0, len(data) - 1, n_out)
    return np.interp(x, np.arange(len(data)), data).astype(np.float32)


def loop_samples(data: np.ndarray, seconds: float, sr: int = SR) -> np.ndarray:
    """Tile/trim a sample array to exactly ``seconds``."""
    n = int(sr * seconds)
    if n <= 0 or len(data) == 0:
        return np.zeros(max(0, n), dtype=np.float32)
    reps = int(np.ceil(n / len(data)))
    return np.tile(data, reps)[:n]


def mix_events(
    events: list[AudioEvent],
    total_seconds: float,
    out_path: Path,
    sr: int = SR,
    bed: tuple[Path, float] | None = None,
    _cache: dict | None = None,
) -> Path:
    """Sum every event into one mono wav of ``total_seconds`` at ``out_path``.

    ``bed`` is an optional (path, volume) music bed looped under everything.
    Peak-limits at 0.98 so a stacked cue can't clip hard.
    """
    n = int(sr * total_seconds) + 1
    out = np.zeros(n, dtype=np.float32)
    cache: dict[str, np.ndarray] = {} if _cache is None else _cache

    def samples(path: Path) -> np.ndarray:
        key = str(path)
        if key not in cache:
            cache[key] = decode(path, sr)
        return cache[key]

    if bed is not None:
        bed_path, bed_vol = bed
        bed_arr = loop_samples(samples(bed_path), total_seconds, sr)
        out[: len(bed_arr)] += bed_arr * bed_vol

    for event in events:
        data = samples(event.path)
        if event.volume != 1.0:
            data = data * event.volume
        s = int(event.start * sr)
        if s >= n:
            continue
        end = min(n, s + len(data))
        out[s:end] += data[: end - s]

    peak = float(np.abs(out).max()) if n else 0.0
    if peak > 0.98:
        out *= 0.98 / peak

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(out, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm.tobytes())
    return out_path


def silence(total_seconds: float, out_path: Path, sr: int = SR) -> Path:
    """Silent wav — keeps an aac track present when TTS is off."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(struct.pack("<h", 0) * int(sr * max(0.05, total_seconds)))
    return out_path
