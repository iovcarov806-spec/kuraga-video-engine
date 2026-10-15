"""Offline tests for the Kuraga video pipeline.

Everything here runs without network and without TTS: schemas, asset
asset resolution (19 stems, placeholders when the private art is absent),
generated characters, sfx synthesis, karaoke layout, scheduling, and tiny
end-to-end renders (skipped when moviepy/ffmpeg are absent).
"""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kuraga_video_engine import assets, characters, sfx, subtitles, tts
from kuraga_video_engine.microloop import expand_frames, loop_duration, plan_microloop
from kuraga_video_engine.models import (
    DefinitionError,
    Episode,
    FrameSpec,
    Line,
    MicroLoop,
    OverlaySpec,
    Scene,
    load_definition,
)

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"


# ---- definitions ----------------------------------------------------------


def test_load_episode_json() -> None:
    ep = load_definition(EXAMPLES / "episodes" / "ep01_gost_deadline.json")
    assert isinstance(ep, Episode)
    assert len(ep.scenes) == 3
    assert ep.scenes[1].transition == "glitch"
    assert ep.scenes[2].reaction == "05_work_ready_positive"


def test_load_episode_yaml() -> None:
    ep = load_definition(EXAMPLES / "episodes" / "ep02_tokens_empty.yaml")
    assert isinstance(ep, Episode)
    assert ep.music is not None and ep.music.synth == "phonk"


def test_load_microloop_yaml() -> None:
    loop = load_definition(EXAMPLES / "microloops" / "bilet_na_sessiyu.yaml")
    assert isinstance(loop, MicroLoop)
    assert loop.cards_from and loop.overlay is not None


def test_definition_requires_type(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"scenes": []}))
    with pytest.raises(DefinitionError, match="type"):
        load_definition(bad)


def test_episode_rejects_landscape_size() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Episode(scenes=[], size=(1920, 1080))


def test_microloop_needs_frames_or_cards() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MicroLoop()


# ---- mascot assets --------------------------------------------------------


def _fake_assets(directory: Path, stems: list[str]) -> None:
    from PIL import Image

    directory.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        Image.new("RGB", (64, 96), (200, 120, 40)).save(directory / f"{stem}.jpg")


def test_spec_has_19_stems() -> None:
    assert assets.stem_count() == 19
    assert len(set(assets.spec_stems())) == 19


def test_all_19_assets_resolve_from_dir(tmp_path: Path) -> None:
    _fake_assets(tmp_path, list(assets.spec_stems()))
    audit = assets.audit(tmp_path)
    assert len(audit) == 19
    assert all(src.startswith("file:") for src in audit.values()), audit


def test_manifest_and_prefix_resolution(tmp_path: Path) -> None:
    _fake_assets(tmp_path, ["custom_name", "03_library_v2"])
    (tmp_path / "manifest.json").write_text(json.dumps({"01_welcome_study": "custom_name.jpg"}))
    index = assets.index_assets(tmp_path)
    assert index.resolve("01_welcome_study") == tmp_path / "custom_name.jpg"
    assert index.resolve("03_library_sourcing") == tmp_path / "03_library_v2.jpg"
    assert assets.resolve_image("no_such_stem", index) is None


def test_assets_dir_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_assets(tmp_path, ["07_padik_break"])
    monkeypatch.setenv("KURAGA_ASSETS_DIR", str(tmp_path))
    assert assets.assets_dir() == tmp_path
    assert assets.audit()["07_padik_break"] == "file:07_padik_break.jpg"


def test_missing_dir_is_empty_not_error(tmp_path: Path) -> None:
    audit = assets.audit(tmp_path / "nope")
    assert set(audit.values()) == {"missing"}


def test_cover_image_placeholders() -> None:
    index = assets.AssetIndex({})
    path, warn = assets.cover_image("#224466", index, (360, 640))
    assert warn is None and path.is_file()
    path, warn = assets.cover_image("missing_stem_xyz", index, (360, 640))
    assert path.is_file() and warn
    # A known-but-absent mascot stem falls back to a generated КУРАГА scene.
    path, warn = assets.cover_image("14_error_iv_drip", index, (360, 640))
    assert path.is_file() and warn and "КУРАГА" in warn


@pytest.mark.parametrize("name", ["kuraga", "student", "duo"])
def test_character_images(name: str) -> None:
    from PIL import Image

    assert characters.parse_character(f"character:{name}") == name
    path, warn = assets.cover_image(f"character:{name}", assets.AssetIndex({}), (270, 480))
    assert warn is None
    with Image.open(path) as img:
        assert img.size == (270, 480)
        # Not a flat placeholder: the character adds plenty of distinct colors.
        assert len(img.convert("RGB").getcolors(maxcolors=1 << 16) or []) > 20
    sprite = characters.character_sprite(name, 120)
    with Image.open(sprite) as img:
        assert img.size == (120, 120)


def test_parse_character_rejects_unknown() -> None:
    assert characters.parse_character("character:professor") is None
    assert characters.parse_character("01_welcome_study") is None


def test_package_is_standalone() -> None:
    pkg = REPO / "kuraga_video_engine"
    for src in pkg.glob("*.py"):
        text = src.read_text(encoding="utf-8")
        assert "gost_bot" not in text, src
        assert "video_pipeline" not in text, src


# ---- tts / subtitles ------------------------------------------------------


def test_estimate_line_timings() -> None:
    audio = tts.estimate_line("профессор я правда всё написал сам")
    assert audio.duration >= 1.0
    assert len(audio.words) == 6
    assert audio.words[0].start == 0
    assert all(w.end > w.start for w in audio.words)


def test_karaoke_word_boxes_wrap() -> None:
    audio = tts.estimate_line("раз два три четыре пять шесть семь восемь девять десять")
    from kuraga_video_engine.fonts import bold_font

    boxes, rows = subtitles.word_boxes(audio, 1.5, bold_font())
    assert len(boxes) == 10
    assert rows >= 1
    assert all(b.start >= 1.5 for b in boxes)


def test_bubble_image_renders() -> None:
    img = subtitles.bubble_image("student", "короткая тестовая реплика")
    assert img.size[0] > 100 and img.size[1] > 60
    assert img.mode == "RGBA"


# ---- sfx ------------------------------------------------------------------


@pytest.mark.parametrize("name", ["glitch", "thud", "bass_drop", "whoosh", "tick", "phonk"])
def test_synth_sfx(name: str) -> None:
    path, synthesized = sfx.cue_audio_path(name, None)
    assert synthesized is True
    with wave.open(str(path)) as wav:
        assert wav.getnframes() > 0


def test_unknown_sfx_raises() -> None:
    with pytest.raises(KeyError):
        sfx.cue_audio_path("does_not_exist")


# ---- microloop ------------------------------------------------------------


def test_expand_cards_from(tmp_path: Path) -> None:
    src = tmp_path / "q.txt"
    src.write_text("вопрос один\nвопрос два\n")
    loop = MicroLoop(cards_from=str(src), frame_seconds=0.3)
    warnings: list[str] = []
    frames = expand_frames(loop, warnings)
    assert len(frames) == 2 and all(f.card for f in frames)
    assert frames[0].number == 1


def test_boomerang_sequence() -> None:
    frames = [f"a{i}" for i in range(4)]
    loop = MicroLoop(frames=[FrameSpec(text=t) for t in frames], boomerang=True)
    expanded = expand_frames(loop, [])
    assert len(expanded) == 6  # 4 + reversed middle (2)


def test_loop_duration_target() -> None:
    loop = MicroLoop(frames=[FrameSpec(text="x"), FrameSpec(text="y")], frame_seconds=0.5)
    loop.target_seconds = 3.0
    n, repeats, total = loop_duration(loop)
    assert n == 2 and repeats == 3 and total == 3.0


def test_all_examples_load() -> None:
    defs = sorted(EXAMPLES.rglob("*.json")) + sorted(EXAMPLES.rglob("*.y*ml"))
    assert len(defs) >= 5
    for path in defs:
        assert isinstance(load_definition(path), (Episode, MicroLoop)), path


def test_example_cards_from_resolves() -> None:
    loop = load_definition(EXAMPLES / "microloops" / "bilet_na_sessiyu.yaml")
    assert isinstance(loop, MicroLoop)
    warnings: list[str] = []
    frames = expand_frames(loop, warnings)
    assert not warnings
    assert sum(1 for f in frames if f.card) >= 10


def test_plan_microloop_example() -> None:
    loop = load_definition(EXAMPLES / "microloops" / "pauza_chitat.yaml")
    assert isinstance(loop, MicroLoop)
    plan = plan_microloop(loop)
    assert plan["frames_per_loop"] == 7
    assert plan["seconds"] > 0


# ---- end-to-end render (needs moviepy + ffmpeg) ----------------------------


def _render_deps() -> None:
    pytest.importorskip("moviepy")
    pytest.importorskip("PIL")
    pytest.importorskip("numpy")


def test_microloop_render_smoke(tmp_path: Path) -> None:
    _render_deps()
    loop = MicroLoop(
        title="smoke",
        size=(270, 480),
        fps=15,
        frame_seconds=0.2,
        loops=2,
        frames=[FrameSpec(text="раз"), FrameSpec(text="два"), FrameSpec(text="три")],
        overlay=OverlaySpec(text="ТЕСТ", position="top", font_size=30),
        sfx=None,
        watermark=None,
    )
    from kuraga_video_engine.microloop import render_microloop

    report = render_microloop(loop, tmp_path / "smoke.mp4")
    assert report.out.is_file() and report.out.stat().st_size > 1000
    assert report.seconds == pytest.approx(1.2, abs=0.2)


def test_episode_render_smoke(tmp_path: Path) -> None:
    _render_deps()
    ep = Episode(
        title="smoke ep",
        size=(270, 480),
        fps=15,
        subtitles="karaoke",
        end_card_text=None,
        scenes=[
            Scene(
                bg="14_error_iv_drip",
                ken_burns="zoom_in",
                reaction="character:student",
                lines=[Line(speaker="kuraga", text="проверка связи раз два")],
            )
        ],
    )
    from kuraga_video_engine.episode import render_episode

    report = render_episode(ep, tmp_path / "ep.mp4", tts_mode="off")
    assert report.out.is_file() and report.out.stat().st_size > 1000
    assert report.estimated == 1


def test_microloop_render_characters(tmp_path: Path) -> None:
    _render_deps()
    loop = MicroLoop(
        title="chars",
        size=(270, 480),
        fps=10,
        frame_seconds=0.3,
        loops=1,
        frames=[
            FrameSpec(image="character:kuraga"),
            FrameSpec(image="character:student"),
            FrameSpec(image="11_paywall_main"),
        ],
        watermark=None,
    )
    from kuraga_video_engine.microloop import render_microloop

    report = render_microloop(loop, tmp_path / "chars.mp4", workdir=tmp_path / "work")
    assert report.out.is_file() and report.out.stat().st_size > 1000


def test_cli_dry_run_and_check(capsys: pytest.CaptureFixture[str]) -> None:
    from kuraga_video_engine.cli import main

    assert main(["microloop", str(EXAMPLES / "microloops" / "pauza_chitat.yaml"), "--dry-run"]) == 0
    assert (
        main(
            [
                "episode",
                str(EXAMPLES / "episodes" / "ep01_gost_deadline.json"),
                "--dry-run",
                "--tts",
                "off",
            ]
        )
        == 0
    )
    assert main(["check"]) == 0
    out = capsys.readouterr().out
    assert "mascot assets" in out


def test_tts_per_line_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    async def fake_synth(text, cast, cache_dir=None):
        calls.append(text)
        if text == "bad":
            raise tts.TtsError("no audio")
        return tts.LineAudio(mp3=tmp_path / "ok.mp3", duration=1.0, words=[])

    monkeypatch.setattr(tts, "synth_line", fake_synth)
    cast = tts.VoiceCast(voice="ru-RU-SvetlanaNeural")
    errors: list[str] = []
    out = tts.synth_lines_sync([("ok", cast), ("bad", cast)], tmp_path, errors=errors, attempts=2)
    assert out[0].mp3 is not None and out[1].mp3 is None
    assert calls.count("bad") == 2 and len(errors) == 1
    with pytest.raises(tts.TtsError):
        tts.synth_lines_sync([("bad", cast)], tmp_path, attempts=1)
