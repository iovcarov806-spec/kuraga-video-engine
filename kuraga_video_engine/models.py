"""Episode (Mode A) and microloop (Mode B) definition schemas.

Definitions load from ``.json`` / ``.yaml`` / ``.yml`` or are built in code.
Validation errors carry the field path so a broken def fails fast with a
readable message instead of a stack trace mid-render.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .constants import HEIGHT, SPEAKERS, WIDTH

Speaker = Literal["student", "professor", "kuraga", "narrator"]
KenBurnsMode = Literal[
    "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "still"
]
Transition = Literal["cut", "fade", "glitch"]
SubtitleMode = Literal["karaoke", "bubble", "both", "none"]
SfxName = Literal["glitch", "thud", "bass_drop", "whoosh", "tick"]

_KNOWN_SFX = {"glitch", "thud", "bass_drop", "whoosh", "tick"}


class VoiceCast(BaseModel):
    """edge-tts voice per speaker; rate/pitch are edge-tts strings (``+10%``/``-5Hz``)."""

    voice: str
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"


DEFAULT_CAST: dict[str, VoiceCast] = {
    # High, fast, nervous — the panicking student.
    "student": VoiceCast(voice="ru-RU-SvetlanaNeural", rate="+18%", pitch="+15Hz"),
    # Deep and slow-angry — the professor.
    "professor": VoiceCast(voice="ru-RU-DmitryNeural", rate="-8%", pitch="-25Hz"),
    # Confident streetwise mascot — quick low-mid delivery.
    "kuraga": VoiceCast(voice="ru-RU-DmitryNeural", rate="+10%", pitch="+12Hz"),
    "narrator": VoiceCast(voice="ru-RU-SvetlanaNeural", rate="+0%", pitch="-12Hz"),
}


class SfxCue(BaseModel):
    """A sound cue: ``at`` = seconds in the timeline, or ``line`` index inside a scene."""

    name: SfxName
    file: str | None = None  # custom wav/mp3; synthesized fallback when absent
    at: float | None = None
    line: int | None = None
    volume: float = Field(default=1.0, ge=0.0, le=4.0)


class Line(BaseModel):
    """One spoken line inside a scene."""

    speaker: Speaker
    text: str
    sfx: SfxName | None = None  # shortcut cue fired at this line's start
    bubble: bool = True  # draw a speech bubble for this line
    pause_after: float = Field(default=0.25, ge=0.0, le=5.0)  # tail hold, seconds


class Scene(BaseModel):
    """Episode scene: one background + sequential dialogue lines."""

    bg: str = "#101018"  # mascot stem | image path | "#RRGGBB" | "gradient:#111111:#333333"
    ken_burns: KenBurnsMode = "zoom_in"
    reaction: str | None = None  # mascot stem shown as bottom-right reaction insert
    lines: list[Line] = Field(default_factory=list)
    min_seconds: float = Field(default=0.0, ge=0.0)
    transition: Transition = "cut"
    sfx: SfxName | None = None  # cue at scene start (shortcut)

    @field_validator("lines")
    @classmethod
    def _lines_nonempty_text(cls, lines: list[Line]) -> list[Line]:
        for line in lines:
            if not line.text.strip():
                raise ValueError("line text must not be empty")
        return lines


class MusicBed(BaseModel):
    file: str | None = None  # mp3/wav path
    synth: Literal["phonk"] | None = None  # generated bed when no file
    volume: float = Field(default=0.14, ge=0.0, le=1.0)


class Episode(BaseModel):
    """Mode A — episodic brainrot/lore video definition."""

    type: Literal["episode"] = "episode"
    title: str = "Kuraga Lore"
    fps: int = Field(default=30, ge=10, le=60)
    size: tuple[int, int] = (WIDTH, HEIGHT)
    subtitles: SubtitleMode = "both"  # karaoke strip + speech bubbles
    font: str | None = None
    cast: dict[str, VoiceCast] = Field(default_factory=lambda: dict(DEFAULT_CAST))
    music: MusicBed | None = None
    sfx_dir: str | None = None  # custom sfx directory searched before synth fallback
    scenes: list[Scene]
    end_card_text: str | None = "@KuragaHelperBot"
    end_card_seconds: float = Field(default=1.2, ge=0.0, le=10.0)

    @field_validator("size")
    @classmethod
    def _vertical(cls, size: tuple[int, int]) -> tuple[int, int]:
        w, h = size
        if w <= 0 or h <= 0 or w >= h:
            raise ValueError(f"size must be vertical (w<h), got {w}x{h}")
        return size

    @model_validator(mode="after")
    def _cast_only_speakers(self) -> Episode:
        unknown = set(self.cast) - set(SPEAKERS)
        if unknown:
            raise ValueError(f"cast has unknown speakers: {sorted(unknown)} (allowed: {SPEAKERS})")
        return self


class OverlaySpec(BaseModel):
    text: str
    position: Literal["top", "center", "bottom"] = "top"
    font_size: int = Field(default=64, ge=12, le=300)
    color: str = "#ffffff"
    bg_color: str | None = None  # optional band behind the text


class FrameSpec(BaseModel):
    """One microloop frame: text card, image, or styled «билет» card."""

    text: str | None = None
    image: str | None = None  # mascot stem or file path
    card: bool = False  # render as «Билет N» card
    number: int | None = None
    font_size: int = Field(default=72, ge=12, le=400)
    color: str = "#ffffff"
    bg: str = "#0d0d12"


class MicroLoop(BaseModel):
    """Mode B — ultra-short loop / high-speed slideshow definition."""

    type: Literal["microloop"] = "microloop"
    title: str = "Kuraga microloop"
    fps: int = Field(default=30, ge=10, le=60)
    size: tuple[int, int] = (WIDTH, HEIGHT)
    font: str | None = None
    frame_seconds: float = Field(default=0.35, gt=0.0, le=1.0)
    loops: int | None = Field(default=None, ge=1, le=200)
    target_seconds: float | None = Field(default=None, gt=0.0, le=300.0)
    boomerang: bool = False  # append frames reversed for a seamless loop
    shuffle_seed: int | None = None  # deterministic shuffle of the frame order
    overlay: OverlaySpec | None = None  # bait text on every frame
    watermark: str | None = "@KuragaHelperBot"
    frames: list[FrameSpec] = Field(default_factory=list)
    cards_from: str | None = None  # file: one question per line -> «Билет N» cards
    card_prefix: str = "Билет на сессию"
    sfx: SfxName | None = "tick"  # cue at every frame switch
    music: MusicBed | None = None

    @model_validator(mode="after")
    def _frames_present(self) -> MicroLoop:
        if not self.frames and not self.cards_from:
            raise ValueError("microloop needs `frames` and/or `cards_from`")
        if self.loops is None and self.target_seconds is None:
            self.target_seconds = 8.0
        return self


DefType = Annotated[Episode | MicroLoop, Field(discriminator="type")]


class DefinitionError(ValueError):
    """Bad or unreadable definition file."""


def load_definition(path: str | Path) -> Episode | MicroLoop:
    """Load a JSON/YAML definition file and validate it against the schemas."""
    path = Path(path)
    if not path.is_file():
        raise DefinitionError(f"definition file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:
            raise DefinitionError(
                f"{path.name} is not JSON and PyYAML is not installed "
                "(pip install pyyaml) — YAML definitions unavailable"
            ) from exc
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise DefinitionError(f"{path}: YAML parse error: {exc}") from exc
    if not isinstance(data, dict):
        raise DefinitionError(f"{path}: top level must be a mapping, got {type(data).__name__}")
    kind = data.get("type")
    if kind not in ("episode", "microloop"):
        raise DefinitionError(f"{path}: `type` must be 'episode' or 'microloop', got {kind!r}")
    model = Episode if kind == "episode" else MicroLoop
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise DefinitionError(f"{path}: {exc}") from exc


def definition_kind(path: str | Path) -> str | None:
    """Peek at a file's ``type`` field (None when unreadable/unrecognized)."""
    try:
        definition = load_definition(path)
    except DefinitionError:
        return None
    return definition.type
