"""Batch runner: render every definition file in a directory in one command."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .constants import DEFAULT_OUT_DIR
from .episode import RenderReport, render_episode
from .microloop import LoopReport, render_microloop
from .models import DefinitionError, Episode, MicroLoop, load_definition

_DEF_EXTS = (".json", ".yaml", ".yml")


@dataclass(slots=True)
class BatchItem:
    file: str
    kind: str | None = None
    status: str = "pending"  # ok | failed | skipped
    out: str | None = None
    seconds: float | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BatchReport:
    items: list[BatchItem] = field(default_factory=list)

    @property
    def ok(self) -> int:
        return sum(1 for i in self.items if i.status == "ok")

    @property
    def failed(self) -> int:
        return sum(1 for i in self.items if i.status == "failed")

    def to_dict(self) -> dict:
        import dataclasses

        return {
            "ok": self.ok,
            "failed": self.failed,
            "skipped": sum(1 for i in self.items if i.status == "skipped"),
            "items": [
                {
                    k: v
                    for k, v in dataclasses.asdict(item).items()
                    if v not in (None, [], "pending")
                }
                for item in self.items
            ],
        }


def find_definitions(directory: Path) -> list[Path]:
    """All definition files under ``directory`` (non-recursive, sorted)."""
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _DEF_EXTS)


def run_batch(
    directory: Path,
    outdir: Path | None = None,
    *,
    tts_mode: str = "auto",
    dry_run: bool = False,
    fail_fast: bool = False,
    workdir: Path | None = None,
    logger=None,
) -> BatchReport:
    """Render every episode/microloop def in ``directory``.

    One bad def never kills the batch (unless ``fail_fast``) — its error is
    recorded and the run continues. Exit-code mapping is done by the CLI.
    """
    report = BatchReport()
    outdir = outdir or (DEFAULT_OUT_DIR / directory.name)
    files = find_definitions(directory)
    if not files:
        return report
    for path in files:
        item = BatchItem(file=path.name)
        report.items.append(item)
        try:
            definition = load_definition(path)
        except DefinitionError as exc:
            item.status = "skipped"
            item.error = str(exc)
            continue
        item.kind = definition.type
        try:
            if dry_run:
                item.status = "ok"
                item.out = "-"
                continue
            target = outdir / f"{path.stem}.mp4"
            result: RenderReport | LoopReport
            if isinstance(definition, Episode):
                result = render_episode(
                    definition, target, tts_mode=tts_mode, workdir=workdir, logger=logger
                )
            elif isinstance(definition, MicroLoop):
                result = render_microloop(definition, target, workdir=workdir, logger=logger)
            else:  # pragma: no cover - load_definition restricts the type
                raise DefinitionError(f"unsupported type {definition.type!r}")
            item.status = "ok"
            item.out = str(result.out)
            item.seconds = result.seconds
            item.warnings = result.warnings
        except Exception as exc:  # render failures isolated per file
            item.status = "failed"
            item.error = f"{type(exc).__name__}: {exc}"
            if fail_fast:
                break
    return report


def write_report(report: BatchReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path
