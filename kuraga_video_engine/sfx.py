"""Sound-effect cues: file lookup first, synthesized fallback always available.

Ships no binary audio — ``sfx_dir`` (def or ``--sfx-dir``) may provide real
``<name>.wav``/``.mp3`` files; anything missing is synthesized with numpy so a
cue never silently disappears. The ``phonk`` bed is a simple bass+hat loop,
a stand-in for licensed phonk you can drop in via ``music.file``.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from .constants import DEFAULT_WORK_DIR

SR = 44100
SYNTH_DIR = DEFAULT_WORK_DIR / "sfx_synth"

SYNTH_NAMES = ("glitch", "thud", "bass_drop", "whoosh", "tick", "phonk")


def _write_wav(path: Path, samples: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes(pcm.tobytes())
    return path


def _env(n: int, attack: float = 0.01, decay: float = 0.9) -> np.ndarray:
    t = np.linspace(0, 1, n)
    env = np.minimum(t / max(attack, 1e-4), 1.0) * np.exp(-decay * 6 * t)
    return env.astype(np.float32)


def _glitch(seconds: float = 0.22) -> np.ndarray:
    n = int(SR * seconds)
    rng = np.random.default_rng(7)
    noise = rng.uniform(-1, 1, n).astype(np.float32)
    # Stepped "bitcrush" + stuttered amplitude.
    crushed = np.round(noise * 6) / 6
    stutter = (np.sin(np.arange(n) * 2 * np.pi * 30 / SR) > 0).astype(np.float32)
    return crushed * stutter * _env(n, 0.005, 1.2) * 0.9


def _thud(seconds: float = 0.35) -> np.ndarray:
    n = int(SR * seconds)
    t = np.arange(n) / SR
    freq = 55 - 20 * (t / seconds)  # 55 -> 35 Hz drop
    body = np.sin(2 * np.pi * np.cumsum(freq) / SR)
    click = np.zeros(n, dtype=np.float32)
    click[: int(SR * 0.012)] = np.random.default_rng(3).uniform(-0.6, 0.6, int(SR * 0.012))
    return (body * _env(n, 0.004, 1.4) * 0.95 + click * 0.3).astype(np.float32)


def _bass_drop(seconds: float = 1.1) -> np.ndarray:
    n = int(SR * seconds)
    t = np.arange(n) / SR
    freq = 160 * np.exp(-2.2 * t / seconds) + 35  # 160 -> ~40 Hz
    wave_ = np.sin(2 * np.pi * np.cumsum(freq) / SR)
    driven = np.tanh(wave_ * 2.2)  # soft overdrive
    return (driven * _env(n, 0.02, 0.55)).astype(np.float32)


def _whoosh(seconds: float = 0.45) -> np.ndarray:
    n = int(SR * seconds)
    rng = np.random.default_rng(11)
    noise = rng.uniform(-1, 1, n).astype(np.float32)
    kernel = np.ones(48, dtype=np.float32) / 48
    smooth = np.convolve(noise, kernel, mode="same")
    t = np.linspace(0, np.pi, n)
    swell = np.sin(t) ** 1.5  # rises then falls
    return (smooth * swell * 1.6).astype(np.float32)


def _tick(seconds: float = 0.045) -> np.ndarray:
    n = int(SR * seconds)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 1800 * t) * _env(n, 0.001, 3.0) * 0.8).astype(np.float32)


def _phonk(seconds: float = 8.0) -> np.ndarray:
    """Loopable minimal phonk-ish bed: minor-key bass + hats (placeholder music)."""
    n = int(SR * seconds)
    out = np.zeros(n, dtype=np.float32)
    bpm = 140
    beat = 60 / bpm
    bass_notes = [41.2, 41.2, 49.0, 38.9]  # E1 E1 G1 D1
    pos = 0.0
    i = 0
    while pos < seconds:
        freq = bass_notes[i % len(bass_notes)]
        m = int(SR * beat * 0.9)
        seg = np.arange(m) / SR
        note = np.tanh(np.sin(2 * np.pi * freq * seg) * 1.6) * _env(m, 0.01, 0.7)
        s = int(pos * SR)
        out[s : s + m] += note[: max(0, min(m, n - s))] * 0.5
        # hat tick on each eighth
        for off in (0.0, beat / 2):
            hp = int((pos + off) * SR)
            hn = int(SR * 0.03)
            if hp + hn <= n:
                out[hp : hp + hn] += _tick(0.03) * 0.25
        pos += beat
        i += 1
    return out * 0.6


def _synth(name: str) -> np.ndarray:
    builders = {
        "glitch": _glitch,
        "thud": _thud,
        "bass_drop": _bass_drop,
        "whoosh": _whoosh,
        "tick": _tick,
        "phonk": _phonk,
    }
    if name not in builders:
        raise KeyError(name)
    return builders[name]()


def find_sfx_file(name: str, sfx_dir: Path | None) -> Path | None:
    """Locate a real ``<name>.wav|.mp3|.ogg`` in ``sfx_dir`` (or packaged dir)."""
    candidates = [sfx_dir] if sfx_dir else []
    candidates.append(Path(__file__).resolve().parent / "sfx")
    for base in candidates:
        if base is None or not base.is_dir():
            continue
        for ext in (".wav", ".mp3", ".ogg", ".m4a"):
            path = base / f"{name}{ext}"
            if path.is_file():
                return path
    return None


def cue_audio_path(name: str, sfx_dir: Path | None = None) -> tuple[Path, bool]:
    """Resolve a cue name to an audio file.

    Returns (path, synthesized). Real files win; otherwise the synth wav is
    generated under .video_work/sfx_synth. Unknown names raise KeyError.
    """
    found = find_sfx_file(name, sfx_dir)
    if found is not None:
        return found, False
    if name not in SYNTH_NAMES:
        raise KeyError(
            f"unknown sfx {name!r}: no file found and no synth fallback "
            f"(known synths: {', '.join(SYNTH_NAMES)})"
        )
    path = SYNTH_DIR / f"{name}.wav"
    if not path.is_file():
        _write_wav(path, _synth(name))
    return path, True
