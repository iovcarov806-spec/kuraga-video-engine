"""Procedural placeholder art for the two lead characters: КУРАГА and Студент.

The real mascot illustrations are private, so the engine draws simple
stand-ins with Pillow: a streetwise apricot in sunglasses with a gold chain
(КУРАГА) and a nervous student in glasses and a hoodie (Студент). Images are
deterministic and cached under ``.video_work/placeholders``.

Spec syntax wherever an image is accepted: ``character:kuraga``,
``character:student`` or ``character:duo`` (both side by side).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .constants import DEFAULT_WORK_DIR, HEIGHT, WIDTH

CHARACTERS: tuple[str, ...] = ("kuraga", "student", "duo")
CHARACTER_PREFIX = "character:"
CHARACTER_LABELS = {"kuraga": "КУРАГА", "student": "СТУДЕНТ", "duo": "КУРАГА × СТУДЕНТ"}
_BG = {
    "kuraga": ((44, 22, 8), (12, 8, 16)),
    "student": ((10, 24, 52), (8, 8, 18)),
    "duo": ((40, 14, 40), (8, 10, 22)),
}
PLACEHOLDER_DIR = DEFAULT_WORK_DIR / "placeholders"


def parse_character(spec: str) -> str | None:
    """``character:kuraga`` -> ``kuraga``; anything else -> None."""
    spec = spec.strip().lower()
    if not spec.startswith(CHARACTER_PREFIX):
        return None
    name = spec[len(CHARACTER_PREFIX) :].strip()
    return name if name in CHARACTERS else None


def _draw_kuraga(img, cx: float, cy: float, r: float) -> None:
    """Apricot body, leaf, sunglasses, smirk and a gold chain with a «К»."""
    from PIL import ImageDraw, ImageFont

    from .fonts import bold_font

    d = ImageDraw.Draw(img)
    # Body: layered ellipses fake a warm gradient.
    for i, color in enumerate(((214, 104, 30), (236, 136, 44), (247, 166, 62), (252, 190, 96))):
        k = 1.0 - i * 0.12
        ox = -r * 0.10 * i
        oy = -r * 0.10 * i
        d.ellipse(
            (cx - r * k + ox, cy - r * 1.05 * k + oy, cx + r * k + ox, cy + r * 1.05 * k + oy),
            fill=color,
        )
    # Seam.
    d.arc(
        (cx - r * 0.25, cy - r * 1.0, cx + r * 0.55, cy + r * 1.0),
        100,
        250,
        fill=(196, 92, 26),
        width=max(2, int(r * 0.04)),
    )
    # Stem + leaf.
    d.line(
        (cx, cy - r * 1.02, cx + r * 0.08, cy - r * 1.28),
        fill=(92, 58, 30),
        width=max(3, int(r * 0.07)),
    )
    d.chord(
        (cx + r * 0.05, cy - r * 1.50, cx + r * 0.75, cy - r * 1.12), 180, 360, fill=(76, 160, 70)
    )
    d.chord(
        (cx + r * 0.05, cy - r * 1.42, cx + r * 0.75, cy - r * 1.20), 0, 180, fill=(58, 128, 54)
    )
    # Sunglasses.
    ey = cy - r * 0.22
    lw, lh = r * 0.40, r * 0.24
    for sx in (-1, 1):
        x0 = cx + sx * r * 0.06 + (0 if sx > 0 else -lw)
        d.rounded_rectangle(
            (x0, ey - lh / 2, x0 + lw, ey + lh / 2), radius=lh * 0.4, fill=(14, 14, 18)
        )
        d.line(
            (x0 + lw * 0.18, ey - lh * 0.18, x0 + lw * 0.42, ey - lh * 0.18),
            fill=(120, 120, 140),
            width=max(1, int(r * 0.03)),
        )
    d.line(
        (cx - r * 0.08, ey - lh * 0.2, cx + r * 0.08, ey - lh * 0.2),
        fill=(14, 14, 18),
        width=max(2, int(r * 0.05)),
    )
    # Smirk.
    d.arc(
        (cx - r * 0.18, cy + r * 0.02, cx + r * 0.38, cy + r * 0.36),
        15,
        140,
        fill=(90, 34, 10),
        width=max(2, int(r * 0.05)),
    )
    # Gold chain + pendant.
    n = 11
    for i in range(n):
        t = i / (n - 1)
        x = cx - r * 0.55 + t * r * 1.1
        y = cy + r * 0.62 + (1 - (2 * t - 1) ** 2) * r * 0.22
        s = r * 0.05
        d.ellipse((x - s, y - s, x + s, y + s), fill=(255, 205, 60), outline=(170, 120, 20))
    py = cy + r * 0.84 + r * 0.14
    s = r * 0.17
    d.ellipse(
        (cx - s, py - s, cx + s, py + s),
        fill=(255, 210, 63),
        outline=(170, 120, 20),
        width=max(1, int(r * 0.02)),
    )
    try:
        font = ImageFont.truetype(bold_font(), max(10, int(s * 1.3)))
        box = d.textbbox((0, 0), "К", font=font)
        d.text(
            (cx - (box[2] - box[0]) / 2 - box[0], py - (box[3] - box[1]) / 2 - box[1]),
            "К",
            fill=(120, 60, 0),
            font=font,
        )
    except Exception:
        pass


def _draw_student(img, cx: float, cy: float, r: float) -> None:
    """Hoodie, head, messy hair, round glasses, worried mouth, sweat drop."""
    from PIL import ImageDraw

    d = ImageDraw.Draw(img)
    # Hoodie torso.
    d.rounded_rectangle(
        (cx - r * 1.0, cy + r * 0.55, cx + r * 1.0, cy + r * 2.0),
        radius=r * 0.45,
        fill=(52, 96, 190),
    )
    d.polygon(
        [(cx - r * 0.35, cy + r * 0.6), (cx + r * 0.35, cy + r * 0.6), (cx, cy + r * 1.05)],
        fill=(36, 70, 150),
    )
    d.line(
        (cx - r * 0.18, cy + r * 0.9, cx - r * 0.22, cy + r * 1.35),
        fill=(230, 230, 240),
        width=max(2, int(r * 0.04)),
    )
    d.line(
        (cx + r * 0.18, cy + r * 0.9, cx + r * 0.22, cy + r * 1.35),
        fill=(230, 230, 240),
        width=max(2, int(r * 0.04)),
    )
    # Head.
    d.ellipse((cx - r * 0.62, cy - r * 0.75, cx + r * 0.62, cy + r * 0.72), fill=(241, 194, 140))
    # Hair: chord on top + a few spikes.
    d.chord(
        (cx - r * 0.66, cy - r * 0.90, cx + r * 0.66, cy + r * 0.10), 180, 360, fill=(58, 38, 28)
    )
    for i in range(5):
        x = cx - r * 0.5 + i * r * 0.25
        d.polygon(
            [(x, cy - r * 0.62), (x + r * 0.16, cy - r * 1.02), (x + r * 0.28, cy - r * 0.62)],
            fill=(58, 38, 28),
        )
    # Round glasses.
    ey = cy - r * 0.05
    gr = r * 0.19
    for sx in (-1, 1):
        ex = cx + sx * r * 0.26
        d.ellipse(
            (ex - gr, ey - gr, ex + gr, ey + gr),
            fill=(250, 250, 255),
            outline=(30, 30, 36),
            width=max(2, int(r * 0.05)),
        )
        d.ellipse(
            (ex - gr * 0.32, ey - gr * 0.1, ex + gr * 0.32, ey + gr * 0.54), fill=(30, 30, 36)
        )
    d.line((cx - r * 0.07, ey, cx + r * 0.07, ey), fill=(30, 30, 36), width=max(2, int(r * 0.04)))
    # Worried eyebrows + mouth.
    for sx in (-1, 1):
        ex = cx + sx * r * 0.26
        d.line(
            (
                ex - r * 0.14,
                ey - gr - r * 0.06 - (0 if sx < 0 else r * 0.06),
                ex + r * 0.14,
                ey - gr - r * 0.06 - (r * 0.06 if sx < 0 else 0),
            ),
            fill=(58, 38, 28),
            width=max(2, int(r * 0.05)),
        )
    d.arc(
        (cx - r * 0.18, cy + r * 0.32, cx + r * 0.18, cy + r * 0.56),
        200,
        340,
        fill=(120, 40, 40),
        width=max(2, int(r * 0.05)),
    )
    # Sweat drop.
    sx0, sy0 = cx + r * 0.62, cy - r * 0.36
    d.polygon(
        [(sx0, sy0 - r * 0.2), (sx0 - r * 0.09, sy0), (sx0 + r * 0.09, sy0)], fill=(130, 200, 255)
    )
    d.ellipse(
        (sx0 - r * 0.09, sy0 - r * 0.07, sx0 + r * 0.09, sy0 + r * 0.11), fill=(130, 200, 255)
    )


def _gradient(size: tuple[int, int], top, bottom):
    from PIL import Image

    w, h = size
    column = Image.new("RGB", (1, h))
    px = column.load()
    assert px is not None
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return column.resize((w, h))


def draw_character(name: str, img, box: tuple[float, float, float, float]) -> None:
    """Draw ``kuraga`` / ``student`` / ``duo`` inside ``box`` on a PIL image."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    if name == "duo":
        draw_character("student", img, (x0, y0 + bh * 0.08, x0 + bw * 0.52, y1))
        draw_character("kuraga", img, (x0 + bw * 0.46, y0, x1, y1))
        return
    cx = x0 + bw / 2
    if name == "kuraga":
        r = min(bw / 2.1, bh / 3.0)
        _draw_kuraga(img, cx, y0 + bh * 0.52, r)
    else:
        r = min(bw / 2.2, bh / 3.0)
        _draw_student(img, cx, y0 + bh * 0.36, r)


def _cache_key(*parts: object) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def character_scene(
    name: str,
    size: tuple[int, int] = (WIDTH, HEIGHT),
    label: str | None = None,
) -> Path:
    """Full-frame background PNG: gradient + character + name/label caption."""
    from PIL import ImageDraw, ImageFont

    from .fonts import bold_font

    name = name if name in CHARACTERS else "kuraga"
    caption = label or CHARACTER_LABELS[name]
    path = PLACEHOLDER_DIR / f"char_{name}_{size[0]}x{size[1]}_{_cache_key(caption, 'v2')}.png"
    if path.is_file():
        return path
    PLACEHOLDER_DIR.mkdir(parents=True, exist_ok=True)
    w, h = size
    top, bottom = _BG[name]
    img = _gradient(size, top, bottom)
    # Spotlight.
    d = ImageDraw.Draw(img)
    d.ellipse((w * 0.08, h * 0.22, w * 0.92, h * 0.70), fill=tuple(min(255, c + 22) for c in top))
    draw_character(name, img, (w * 0.12, h * 0.22, w * 0.88, h * 0.72))
    try:
        font = ImageFont.truetype(bold_font(), max(12, w // 22))
        box = d.textbbox((0, 0), caption, font=font)
        # Just under the character, above the karaoke strip (~0.79h+).
        d.text(
            ((w - (box[2] - box[0])) / 2, h * 0.725),
            caption,
            fill=(255, 210, 63),
            font=font,
            stroke_width=max(1, w // 270),
            stroke_fill=(0, 0, 0),
        )
    except Exception:
        pass
    img.save(path)
    return path


def character_sprite(name: str, side: int) -> Path:
    """Square RGB reaction insert (dark rounded tile + character)."""
    from PIL import Image, ImageDraw

    name = name if name in CHARACTERS else "kuraga"
    path = PLACEHOLDER_DIR / f"sprite_{name}_{side}.png"
    if path.is_file():
        return path
    PLACEHOLDER_DIR.mkdir(parents=True, exist_ok=True)
    top, bottom = _BG[name]
    img = _gradient((side, side), top, bottom)
    ImageDraw.Draw(img).rectangle(
        (0, 0, side - 1, side - 1), outline=(255, 210, 63), width=max(2, side // 60)
    )
    draw_character(name, img, (side * 0.1, side * 0.12, side * 0.9, side * 0.98))
    img = img.convert("RGB") if isinstance(img, Image.Image) else img
    img.save(path)
    return path
