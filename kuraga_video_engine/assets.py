"""Resolution of the 19 КУРАГА mascot asset stems — read-only, standalone.

The mascot illustrations are private and are NOT shipped with this repo.
Drop them into ``assets/mascot/`` (or point ``$KURAGA_ASSETS_DIR`` at a
folder) as ``<stem>.jpg|.png|.webp``, optionally with a ``manifest.json``
(``{"<stem>": "<filename>"}``). Missing stems never abort a render: a
generated КУРАГА placeholder scene is used and reported as a warning.

Also accepts plain file paths, ``#RRGGBB`` flats, ``gradient:#A:#B``
backgrounds and ``character:kuraga|student|duo`` generated characters.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import characters
from .constants import DEFAULT_WORK_DIR, HEIGHT, REPO_ROOT, WIDTH

DEFAULT_ASSETS_DIR = REPO_ROOT / "assets" / "mascot"
PLACEHOLDER_DIR = DEFAULT_WORK_DIR / "placeholders"
MANIFEST_NAME = "manifest.json"

# The 19 approved mascot stems (same order as the КУРАГА bot's spec).
SPEC_STEMS: tuple[str, ...] = (
    "01_welcome_study",
    "02_office_desk",
    "03_library_sourcing",
    "04_code_generation",
    "05_work_ready_positive",
    "06_armchair_noodles",
    "07_padik_break",
    "08_stairwell_variant",
    "09_tokens_depleted",
    "10_bbq_celebration",
    "11_paywall_main",
    "12_paywall_subway",
    "13_payment_terminal",
    "14_error_iv_drip",
    "15_error_alleyway_500",
    "16_error_bench_404",
    "17_vip_club",
    "18_paywall_90s_mugging",
    "19_maintenance_worker",
)

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def spec_stems() -> tuple[str, ...]:
    """The 19 canonical asset stems."""
    return SPEC_STEMS


def stem_count() -> int:
    """How many approved assets the spec expects (19)."""
    return len(SPEC_STEMS)


def assets_dir() -> Path:
    """``$KURAGA_ASSETS_DIR`` (relative = project root) or ``assets/mascot``."""
    raw = os.getenv("KURAGA_ASSETS_DIR", "").strip()
    if not raw:
        return DEFAULT_ASSETS_DIR
    path = Path(raw).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


@dataclass(frozen=True)
class AssetIndex:
    """Mascot stem -> absolute file path."""

    files: dict[str, Path]

    def resolve(self, stem: str) -> Path | None:
        return self.files.get(stem)


def _load_manifest(directory: Path) -> dict[str, str]:
    try:
        data = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def index_assets(directory: Path | None = None) -> AssetIndex:
    """Map every resolvable mascot stem to a local file (read-only scan).

    Order per stem: ``manifest.json`` entry > exact ``<stem>.<ext>`` >
    any image whose name starts with the stem's ``NN_`` number.
    """
    directory = directory or assets_dir()
    if not directory.is_dir():
        return AssetIndex({})
    images = sorted(
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
    )
    manifest = _load_manifest(directory)
    index: dict[str, Path] = {}
    for stem in SPEC_STEMS:
        mapped = manifest.get(stem)
        if mapped and (directory / mapped).is_file():
            index[stem] = directory / mapped
            continue
        exact = [p for p in images if p.stem.lower() == stem]
        prefix = [p for p in images if p.stem.lower().startswith(stem.split("_", 1)[0] + "_")]
        hit = (exact or prefix or [None])[0]
        if hit is not None:
            index[stem] = hit
    return AssetIndex(index)


def audit(directory: Path | None = None) -> dict[str, str]:
    """stem -> ``file:<name>`` or ``missing`` for the full 19-stem spec."""
    index = index_assets(directory)
    return {
        stem: (f"file:{index.files[stem].name}" if stem in index.files else "missing")
        for stem in SPEC_STEMS
    }


def is_hex_color(value: str) -> bool:
    return bool(_HEX_RE.match(value.strip()))


def parse_color(value: str) -> tuple[int, int, int]:
    """'#RGB' / '#RRGGBB' -> (r, g, b)."""
    raw = value.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def resolve_image(spec: str, index: AssetIndex) -> Path | None:
    """Resolve a bg/image spec to a file: mascot stem first, then a path."""
    spec = spec.strip()
    if not spec or is_hex_color(spec) or spec.startswith("gradient:"):
        return None
    character = characters.parse_character(spec)
    if character is not None:
        return characters.character_scene(character)
    hit = index.resolve(spec)
    if hit is not None:
        return hit
    path = Path(spec).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path if path.is_file() and path.suffix.lower() in _IMAGE_EXTS else None


def _placeholder_image(
    label: str,
    size: tuple[int, int] = (WIDTH, HEIGHT),
    top: tuple[int, int, int] = (24, 22, 32),
    bottom: tuple[int, int, int] | None = None,
) -> Path:
    """Labeled PNG stand-in (vertical gradient) for a missing/generated image."""
    from PIL import Image, ImageDraw, ImageFont

    from .fonts import bold_font

    bt: tuple[int, int, int] = (
        bottom
        if bottom is not None
        else (max(0, top[0] - 14), max(0, top[1] - 14), max(0, top[2] - 14))
    )
    safe = re.sub(r"[^0-9A-Za-z_]+", "_", label)[:40] or "blank"
    key = f"ph_{safe}_{size[0]}x{size[1]}_{top[0]}_{bt[0]}"
    path = PLACEHOLDER_DIR / f"{key}.png"
    if path.is_file():
        return path
    PLACEHOLDER_DIR.mkdir(parents=True, exist_ok=True)
    w, h = size
    img = Image.new("RGB", size, top)
    # Row-wise vertical gradient.
    px = img.load()
    assert px is not None
    for y in range(h):
        t = y / max(1, h - 1)
        row = tuple(int(top[i] + (bt[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = row
    draw = ImageDraw.Draw(img)
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont
    try:
        font = ImageFont.truetype(bold_font(), max(24, w // 24))
    except Exception:
        font = ImageFont.load_default()
    text = f"[ {label} ]"
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((w - (box[2] - box[0])) / 2, (h - (box[3] - box[1])) / 2),
        text,
        fill=(200, 200, 210),
        font=font,
    )
    img.save(path)
    return path


def cover_image(
    spec: str, index: AssetIndex, size: tuple[int, int] = (WIDTH, HEIGHT)
) -> tuple[Path, str | None]:
    """Resolve a bg spec to an image path + an optional warning.

    ``#hex`` -> flat card, ``gradient:#A:#B`` -> generated vertical gradient,
    unknown stems/paths -> labeled placeholder + warning string.
    """
    spec = spec.strip()
    if is_hex_color(spec):
        top = parse_color(spec)
        return _placeholder_image(spec.lstrip("#"), size=size, top=top, bottom=top), None
    if spec.startswith("gradient:"):
        parts = [p.strip() for p in spec.split(":", 1)[1].split(":") if p.strip()]
        top = parse_color(parts[0]) if len(parts) > 0 and is_hex_color(parts[0]) else (16, 16, 24)
        bottom = (
            parse_color(parts[1]) if len(parts) > 1 and is_hex_color(parts[1]) else (48, 44, 64)
        )
        return (
            _placeholder_image(f"grad{parts[0]}_{parts[-1]}", size=size, top=top, bottom=bottom),
            None,
        )
    character = characters.parse_character(spec)
    if character is not None:
        return characters.character_scene(character, size=size), None
    path = resolve_image(spec, index)
    if path is not None:
        return path, None
    if spec in SPEC_STEMS:
        return (
            characters.character_scene("kuraga", size=size, label=spec),
            f"mascot asset {spec!r} not in {assets_dir()} — generated КУРАГА placeholder used",
        )
    return (
        _placeholder_image(spec, size=size),
        f"image {spec!r} not found (mascot stem or file) — placeholder used",
    )


def load_pil_image(path: Path, size: tuple[int, int] = (WIDTH, HEIGHT)):
    """Open an image with Pillow, cover-cropped to ``size`` aspect."""
    from PIL import Image

    img = Image.open(path).convert("RGB")
    iw, ih = img.size
    tw, th = size
    scale = max(tw / iw, th / ih)
    img = img.resize((int(iw * scale + 0.5), int(ih * scale + 0.5)), Image.Resampling.LANCZOS)
    iw, ih = img.size
    x = max(0, (iw - tw) // 2)
    y = max(0, (ih - th) // 2)
    return img.crop((x, y, min(iw, x + tw), min(ih, y + th)))
