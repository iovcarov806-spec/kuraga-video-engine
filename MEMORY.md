# Project Memory

Durable project notes for kuraga-video-engine.

- Origin: ported from `video_pipeline/` in iovcarov806-spec/gost-academic-assistant (PR #47, closed unmerged). Package renamed to `kuraga_video_engine`; all `gost_bot` imports removed — the 19 mascot stems are a bundled constant (`assets.SPEC_STEMS`).
- Private mascot art is never committed (`assets/mascot/*` gitignored except README). Missing stems -> generated КУРАГА placeholder scene; `character:kuraga|student|duo` specs are drawn by `characters.py` (Pillow) and work with zero assets.
- Relative paths in defs resolve against the project root: `$KURAGA_VIDEO_ROOT` > source checkout (dir with `pyproject.toml`) > cwd. Asset dir: `$KURAGA_ASSETS_DIR` > `assets/mascot`.
- edge-tts: only `ru-RU-DmitryNeural` and `ru-RU-SvetlanaNeural` exist for ru-RU (Dariya was removed). It sporadically returns "No audio was received"; `tts.synth_lines_sync` retries each line 3x and falls back per line to estimated muted timing.
- Tests: `.venv/bin/python -m pytest -q` (offline, a few seconds, includes tiny real renders); lint: `ruff check . && ruff format --check .`.
- Rendered samples live in `samples/` (committed, ~1–3 MB each); `out/` and `.video_work/` are scratch (gitignored).
