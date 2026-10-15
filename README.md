# Kuraga Video Engine

Standalone batch generator of vertical (9:16) MP4s for the «Kuraga Lore»
series (promo for **@KuragaHelperBot**), starring **КУРАГА** (a streetwise
apricot) and **Студент**. Two modes, one CLI:

- **Mode A — episodes** (`episode`): lore/brainrot clips with multi-voice
  edge-tts dialogue (Student / Professor / КУРАГА / narrator), Ken Burns
  backgrounds, reaction inserts, speech bubbles, word-by-word karaoke
  subtitles, sfx cues and a synth phonk bed.
- **Mode B — microloops** (`microloop`): ultra-short loop/slideshow clips
  (0.1–1 s per frame) with text-bait overlays («Пауза чтоб прочитать») and
  auto-generated «Билет №N» cards.

No dependency on the КУРАГА bot code or its private art: missing mascot
images are replaced by generated КУРАГА / Студент placeholder characters.

## Samples

Rendered with this repo, committed under [`samples/`](samples/):

| file | source | notes |
|------|--------|-------|
| `samples/kuraga_vs_student_microloop.mp4` | `examples/microloops/kuraga_vs_student.yaml` | 1080×1920, 30 fps, ~12.6 s, synth tick + phonk audio |
| `samples/ep03_kuraga_meets_student.mp4` | `examples/episodes/ep03_kuraga_meets_student.yaml` | 1080×1920, 30 fps, ~17 s, edge-tts voices (Svetlana/Dmitry), karaoke + bubbles, phonk bed |

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # runtime
.venv/bin/pip install -r requirements-dev.txt    # + pytest, ruff
# or as a package with the `kuraga-video` entrypoint:
.venv/bin/pip install -e ".[dev]"

# ffmpeg: apt install ffmpeg (system ffmpeg preferred; moviepy's bundled
# imageio-ffmpeg binary is the fallback)

python -m kuraga_video_engine check     # dependency + asset audit
python -m kuraga_video_engine assets    # the 19 mascot stems -> files
python -m kuraga_video_engine voices    # the TTS cast
```

## CLI

`python -m kuraga_video_engine <cmd>` or, after `pip install -e .`, `kuraga-video <cmd>`.

```bash
# Mode B — the Kuraga × Student sample (no network, no private assets)
python -m kuraga_video_engine microloop examples/microloops/kuraga_vs_student.yaml -o out/kuraga.mp4

# Mode A — episode (edge-tts needs network; --tts off = muted, estimated timing)
python -m kuraga_video_engine episode examples/episodes/ep03_kuraga_meets_student.yaml -o out/ep03.mp4
python -m kuraga_video_engine episode examples/episodes/ep02_tokens_empty.yaml --dry-run
python -m kuraga_video_engine episode EP.yaml --tts off

# Batch — every .json/.yaml/.yml def in a folder
python -m kuraga_video_engine batch examples/episodes -o out/episodes --report out/episodes_report.json
python -m kuraga_video_engine batch examples/microloops -o out/microloops
```

Exit codes: `0` ok · `1` render/deps failure · `2` bad args/def.

## Image specs

Anywhere a `bg:`, `image:` or `reaction:` is accepted:

| spec | result |
|------|--------|
| `character:kuraga` / `character:student` / `character:duo` | generated character art (always available) |
| `06_armchair_noodles` (one of the 19 mascot stems) | file from `assets/mascot/`; generated КУРАГА placeholder + warning if absent |
| `path/to/image.png` | that file (relative to the project root) |
| `#1a1a22`, `gradient:#111111:#333333` | flat / gradient card |

## Mode A definition (JSON or YAML)

```yaml
type: episode
title: "Сессия за 3 часа"
subtitles: both               # karaoke | bubble | both | none
fps: 30
size: [1080, 1920]
music: {synth: phonk, volume: 0.10}   # or {file: "music.mp3", volume: 0.12}
scenes:
  - bg: 06_armchair_noodles   # mascot stem | image path | "#1a1a22" | "gradient:#111:#333"
    ken_burns: zoom_in        # zoom_in|zoom_out|pan_left|pan_right|pan_up|pan_down|still
    transition: glitch        # for the NEXT scene: cut|fade|glitch
    reaction: 04_code_generation   # mascot stem shown bottom-right
    sfx: whoosh               # cue at scene start
    min_seconds: 0            # floor for silent scenes
    lines:
      - speaker: student
        text: "Профессор, я правда всё написал сам!"
        sfx: thud             # cue at this line's start
        pause_after: 0.25
        bubble: true
end_card_text: "@KuragaHelperBot"
end_card_seconds: 1.4
```

### Voices (`cast:` override, per speaker)

| speaker   | default voice         | delivery            |
|-----------|-----------------------|---------------------|
| student   | ru-RU-SvetlanaNeural  | +18% rate, +15 Hz — high & nervous |
| professor | ru-RU-DmitryNeural    | −8% rate, −25 Hz — deep & angry |
| kuraga    | ru-RU-DmitryNeural    | +10% rate, +12 Hz — confident/streetwise |
| narrator  | ru-RU-SvetlanaNeural  | ±0% rate, −12 Hz |

```yaml
cast:
  student: {voice: "ru-RU-DmitryNeural", rate: "+30%", pitch: "+30Hz"}
```

`python -m video_pipeline voices` prints the live cast table.

## Mode B definition (JSON or YAML)

```yaml
type: microloop
title: "Скриншотни свой билет"
frame_seconds: 0.3            # 0.1 .. 1.0 per frame
target_seconds: 8             # or loops: N — exact repeat count
shuffle_seed: 42              # deterministic shuffle
boomerang: false              # true = ping-pong loop
overlay: {text: "СКРИНШОТНИ СВОЙ БИЛЕТ", position: top, font_size: 62, color: "#ffd23f", bg_color: "#c00000"}
watermark: "@KuragaHelperBot"
card_prefix: "Билет на сессию"
cards_from: "examples/microloops/questions.txt"   # one question per line
frames:
  - {text: "Пауза чтоб прочитать", bg: "#141018", font_size: 70, color: "#ffffff"}
  - {image: "11_paywall_main"}            # mascot stem or file path
  - {card: true, number: 1, text: "Поля страницы по ГОСТ 7.32?"}
sfx: tick                     # per-frame switch (glitch|thud|bass_drop|whoosh|tick)
music: {synth: phonk, volume: 0.08}
```

## Assets

The 19 mascot stems are bundled in `kuraga_video_engine/assets.py`
(`SPEC_STEMS`); the images themselves are private and not in git. See
[`assets/mascot/README.md`](assets/mascot/README.md) for how to drop them in
(`$KURAGA_ASSETS_DIR` overrides the folder). Relative paths in definitions
resolve against the project root: `$KURAGA_VIDEO_ROOT` > this checkout > cwd.

## Sound cues

`sfx:` names (`glitch`, `thud`, `bass_drop`, `whoosh`, `tick`) resolve to a
real `<name>.wav|.mp3` in the def's `sfx_dir:` first; missing files fall back
to built-in numpy synthesis so a cue never silently drops. `music.file` wins
over `music.synth: phonk` (a minimal generated bed — stand-in for a licensed
track).

## Offline / degraded operation

- `--tts off`: no network — dialogue timing is estimated, video is muted
  (karaoke/bubbles still work).
- edge-tts failures are retried 3× per line; a line that still fails falls
  back to estimated muted timing (reported as a warning), the rest keep voice.
- Missing moviepy/Pillow/numpy: `check` lists them; renders exit with an
  install hint. Missing ffmpeg: `check` reports `MISSING`.
- Fonts: `--font` / def `font:` > `$KURAGA_VIDEO_FONT` > DejaVu/Liberation
  system fonts (Cyrillic-capable).

## Tests

```bash
.venv/bin/python -m pytest -q        # offline, a few seconds, includes tiny real renders
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

## Layout

```
kuraga_video_engine/   package (cli, episode, microloop, assets, characters, tts, sfx, subtitles, audio, batch)
examples/              episode + microloop definitions, questions.txt for «Билет» cards
tests/                 pytest suite
assets/mascot/         drop-in folder for the private mascot art (gitignored)
samples/               rendered sample MP4s
```

Generated files go to `out/` and `.video_work/` (TTS cache, mixes,
placeholders) — both gitignored.
