"""One-command CLI for the Kuraga Lore video pipeline.

python -m kuraga_video_engine check                        # dependency + asset audit
python -m kuraga_video_engine assets                       # the 19 mascot stems -> files
python -m kuraga_video_engine voices                       # TTS cast table
python -m kuraga_video_engine episode DEF.json -o out.mp4  # Mode A
python -m kuraga_video_engine microloop DEF.yaml -o out.mp4# Mode B
python -m kuraga_video_engine batch DIR -o OUTDIR          # render a whole folder
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, assets
from .constants import DEFAULT_OUT_DIR
from .models import DEFAULT_CAST, DefinitionError, load_definition


def _ffmpeg_version() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe is None:
        try:
            import imageio_ffmpeg

            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=15)
        return out.stdout.splitlines()[0] if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _dep_status() -> dict[str, str]:
    status: dict[str, str] = {}
    for mod in ("moviepy", "edge_tts", "PIL", "numpy", "yaml"):
        try:
            m = __import__(mod)
            status[mod] = getattr(m, "__version__", "ok")
        except ImportError:
            status[mod] = "MISSING"
    status["ffmpeg"] = _ffmpeg_version() or "MISSING"
    try:
        from .fonts import bold_font, regular_font

        status["font_bold"] = bold_font()
        status["font_regular"] = regular_font()
    except Exception as exc:
        status["font"] = f"MISSING ({exc})"
    return status


def cmd_check(args: argparse.Namespace) -> int:
    status = _dep_status()
    audit = assets.audit()
    found = sum(1 for v in audit.values() if v.startswith("file:"))
    payload = {
        "version": __version__,
        "deps": status,
        "mascot_assets": {"resolved": found, "expected": assets.stem_count(), "detail": audit},
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("dependencies:")
        for name, value in status.items():
            print(f"  {name:<14} {value}")
        print(
            f"\nmascot assets: {found}/{assets.stem_count()} resolved under {assets.assets_dir()}"
        )
        if found < assets.stem_count():
            print("  (missing stems render as generated КУРАГА placeholders)")
        for stem, src in audit.items():
            print(f"  {stem:<26} {src}")
        missing = [n for n, v in status.items() if v == "MISSING" or str(v).startswith("MISSING")]
        if missing:
            print("\nmissing deps: " + ", ".join(missing))
            print("install: uv pip install -r requirements.txt")
    ok = all(v != "MISSING" and not str(v).startswith("MISSING") for v in status.values())
    return 0 if ok else 1


def cmd_assets(args: argparse.Namespace) -> int:
    audit = assets.audit()
    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        for stem, src in audit.items():
            print(f"{stem:<26} {src}")
        found = sum(1 for v in audit.values() if v.startswith("file:"))
        print(f"\n{found}/{assets.stem_count()} of the 19 approved assets resolved")
    if getattr(args, "strict", False):
        return 0 if all(v.startswith("file:") for v in audit.values()) else 1
    return 0


def cmd_voices(_args) -> int:
    for speaker, cast in DEFAULT_CAST.items():
        print(f"{speaker:<10} {cast.voice:<22} rate={cast.rate} pitch={cast.pitch}")
    print("\noverride per episode via the `cast:` mapping in the definition file")
    return 0


def _moviepy_guard() -> bool:
    try:
        import moviepy  # noqa: F401

        return True
    except ImportError:
        print(
            "error: moviepy is not installed — uv pip install -r requirements.txt",
            file=sys.stderr,
        )
        return False


def _print_report(kind: str, result, out: Path) -> None:
    print(f"{kind}: {result.out}  ({result.seconds}s)")
    for warn in result.warnings:
        print(f"  warning: {warn}")


def cmd_episode(args: argparse.Namespace) -> int:
    try:
        definition = load_definition(args.definition)
    except DefinitionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    from .episode import plan_episode, render_episode
    from .models import Episode

    if not isinstance(definition, Episode):
        print(f"error: {args.definition} is a microloop, not an episode", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps(plan_episode(definition, args.tts), ensure_ascii=False, indent=2))
        return 0
    if not _moviepy_guard():
        return 2
    try:
        result = render_episode(
            definition,
            Path(args.out) if args.out else None,
            tts_mode=args.tts,
            workdir=Path(args.workdir) if args.workdir else None,
            keep_work=args.keep_work,
        )
    except Exception as exc:
        print(f"error: render failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    _print_report("episode", result, result.out)
    return 0


def cmd_microloop(args: argparse.Namespace) -> int:
    try:
        definition = load_definition(args.definition)
    except DefinitionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    from .microloop import plan_microloop, render_microloop
    from .models import MicroLoop

    if not isinstance(definition, MicroLoop):
        print(f"error: {args.definition} is an episode, not a microloop", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps(plan_microloop(definition), ensure_ascii=False, indent=2))
        return 0
    if not _moviepy_guard():
        return 2
    try:
        result = render_microloop(
            definition,
            Path(args.out) if args.out else None,
            workdir=Path(args.workdir) if args.workdir else None,
        )
    except Exception as exc:
        print(f"error: render failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    _print_report("microloop", result, result.out)
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2
    if not args.dry_run and not _moviepy_guard():
        return 2
    from .batch import run_batch, write_report

    report = run_batch(
        directory,
        Path(args.outdir) if args.outdir else None,
        tts_mode=args.tts,
        dry_run=args.dry_run,
        fail_fast=args.fail_fast,
    )
    if args.report:
        write_report(report, Path(args.report))
        print(f"report: {args.report}")
    for item in report.items:
        if item.status == "ok":
            extra = f" -> {item.out}" if item.out and item.out != "-" else ""
            print(f"ok      {item.file}{extra}")
            for warn in item.warnings:
                print(f"          warning: {warn}")
        elif item.status == "skipped":
            print(f"skipped {item.file}: {item.error}")
        else:
            print(f"FAILED  {item.file}: {item.error}")
    print(f"\nbatch: {report.ok} ok, {report.failed} failed")
    return 1 if report.failed or report.ok == 0 else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m kuraga_video_engine",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="audit dependencies + mascot assets")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("assets", help="show the 19 mascot asset -> file mapping")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true", help="exit 1 unless all 19 resolve")
    p.set_defaults(func=cmd_assets)

    p = sub.add_parser("voices", help="show the TTS voice cast")
    p.set_defaults(func=cmd_voices)

    p = sub.add_parser("episode", help="Mode A: render an episode definition")
    p.add_argument("definition", help="episode .json/.yaml file")
    p.add_argument("-o", "--out", help=f"output mp4 (default: {DEFAULT_OUT_DIR}/<slug>.mp4)")
    p.add_argument(
        "--tts",
        choices=("auto", "off"),
        default="auto",
        help="auto: edge-tts voices; off: muted estimated timings (offline)",
    )
    p.add_argument("--workdir", help="scratch dir for tts/sfx caches")
    p.add_argument("--keep-work", action="store_true", help="keep intermediate files")
    p.add_argument("--dry-run", action="store_true", help="print the render plan, render nothing")
    p.set_defaults(func=cmd_episode)

    p = sub.add_parser("microloop", help="Mode B: render a microloop definition")
    p.add_argument("definition", help="microloop .json/.yaml file")
    p.add_argument("-o", "--out", help=f"output mp4 (default: {DEFAULT_OUT_DIR}/<slug>.mp4)")
    p.add_argument("--workdir", help="scratch dir")
    p.add_argument("--dry-run", action="store_true", help="print the render plan, render nothing")
    p.set_defaults(func=cmd_microloop)

    p = sub.add_parser("batch", help="render every definition in a directory")
    p.add_argument("directory", help="folder with .json/.yaml/.yml defs")
    p.add_argument("-o", "--outdir", help=f"output dir (default: {DEFAULT_OUT_DIR}/<dir>)")
    p.add_argument("--tts", choices=("auto", "off"), default="auto")
    p.add_argument("--dry-run", action="store_true", help="validate defs only")
    p.add_argument("--fail-fast", action="store_true", help="stop on first render failure")
    p.add_argument("--report", help="write a JSON batch report to this path")
    p.set_defaults(func=cmd_batch)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
