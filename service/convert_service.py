import argparse
import fnmatch
import os
import shlex
import subprocess
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

SOURCE_DIR = Path("/workspace/documents")
OUTPUT_DIR = Path("/workspace/outputs")
STATE_FILE = OUTPUT_DIR / ".processed_state"

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".html",
    ".htm",
    ".odt",
    ".rtf",
    ".txt",
    ".epub",
    ".md",
}

DEFAULT_MAX_LOG_LINES = 15
DEFAULT_MAX_LOG_CHARS = 2000
TRACEBACK_MAX_LOG_LINES = 300
TRACEBACK_MAX_LOG_CHARS = 50000

MAX_LOG_LINES = int(os.getenv("DOC_TO_MD_MAX_LOG_LINES", str(DEFAULT_MAX_LOG_LINES)))
MAX_LOG_CHARS = int(os.getenv("DOC_TO_MD_MAX_LOG_CHARS", str(DEFAULT_MAX_LOG_CHARS)))


@dataclass
class ConversionAttempt:
    engine: str
    command: list[str]
    success: bool
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert documents from /workspace/documents to Markdown in /workspace/outputs"
        )
    )
    parser.add_argument(
        "--mode",
        choices=["once", "watch"],
        default="once",
        help="Run once or continuously watch for new/changed files.",
    )
    parser.add_argument(
        "--select",
        nargs="*",
        default=None,
        help=(
            "Optional file patterns to process (example: --select '*.pdf' 'meeting-notes.docx'). "
            "Matches are relative to /workspace/documents."
        ),
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Polling interval in seconds when --mode watch is used.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess selected files even if unchanged.",
    )
    return parser.parse_args()


def ensure_directories() -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> dict[str, float]:
    state: dict[str, float] = {}
    if not STATE_FILE.exists():
        return state

    for line in STATE_FILE.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        rel_path, mtime = line.split("\t", 1)
        try:
            state[rel_path] = float(mtime)
        except ValueError:
            continue
    return state


def save_state(state: dict[str, float]) -> None:
    lines = [f"{path}\t{mtime}" for path, mtime in sorted(state.items())]
    STATE_FILE.write_text("\n".join(lines), encoding="utf-8")


def discover_documents() -> list[Path]:
    files: list[Path] = []
    for path in SOURCE_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    return sorted(files)


def matches_selection(path: Path, patterns: list[str] | None) -> bool:
    if not patterns:
        return True

    relative = str(path.relative_to(SOURCE_DIR))
    name = path.name
    for pattern in patterns:
        if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern):
            return True
    return False


def target_markdown_path(source_path: Path) -> Path:
    relative = source_path.relative_to(SOURCE_DIR)
    destination = OUTPUT_DIR / relative
    return destination.with_suffix(".md")


def truncate_output(output: str, max_lines: int = MAX_LOG_LINES, max_chars: int = MAX_LOG_CHARS) -> str:
    output = output.strip()
    if not output:
        return "<empty>"

    is_traceback = "Traceback (most recent call last):" in output
    if is_traceback:
        max_lines = max(max_lines, TRACEBACK_MAX_LOG_LINES)
        max_chars = max(max_chars, TRACEBACK_MAX_LOG_CHARS)

    lines = output.splitlines()
    if len(lines) > max_lines:
        hidden_lines = len(lines) - max_lines
        if is_traceback and max_lines >= 10:
            head_lines = max(3, max_lines // 3)
            tail_lines = max(3, max_lines - head_lines - 1)
            lines = (
                lines[:head_lines]
                + [f"... ({hidden_lines} more line(s))"]
                + lines[-tail_lines:]
            )
        else:
            lines = lines[:max_lines] + [f"... ({hidden_lines} more line(s))"]

    trimmed = "\n".join(lines)
    if len(trimmed) > max_chars:
        hidden_chars = len(trimmed) - max_chars
        trimmed = f"{trimmed[:max_chars]}... ({hidden_chars} more character(s))"
    return trimmed


def run_command(engine: str, command: list[str]) -> ConversionAttempt:
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError as error:
        return ConversionAttempt(
            engine=engine,
            command=command,
            success=False,
            error=f"{type(error).__name__}: {error}",
        )
    except Exception as error:
        return ConversionAttempt(
            engine=engine,
            command=command,
            success=False,
            error=f"{type(error).__name__}: {error}",
        )

    return ConversionAttempt(
        engine=engine,
        command=command,
        success=result.returncode == 0,
        returncode=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
    )


def format_attempt_error(attempt: ConversionAttempt) -> str:
    lines = [
        f"  engine: {attempt.engine}",
        f"  command: {' '.join(shlex.quote(part) for part in attempt.command)}",
    ]

    if attempt.error:
        lines.append(f"  error: {attempt.error}")
        return "\n".join(lines)

    lines.append(f"  exit code: {attempt.returncode}")
    if attempt.stderr.strip():
        lines.append("  stderr:")
        lines.append(textwrap.indent(truncate_output(attempt.stderr), "    "))
    if attempt.stdout.strip():
        lines.append("  stdout:")
        lines.append(textwrap.indent(truncate_output(attempt.stdout), "    "))
    return "\n".join(lines)


def run_markitdown(source: Path, destination: Path) -> ConversionAttempt:
    command = ["markitdown", str(source), "-o", str(destination)]
    return run_command("markitdown", command)


def run_pandoc(source: Path, destination: Path) -> ConversionAttempt:
    command = ["pandoc", str(source), "-t", "gfm", "-o", str(destination)]
    return run_command("pandoc", command)


def convert_one(source: Path) -> tuple[bool, str, list[ConversionAttempt]]:
    destination = target_markdown_path(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    attempts: list[ConversionAttempt] = []

    markitdown_attempt = run_markitdown(source, destination)
    attempts.append(markitdown_attempt)
    if markitdown_attempt.success:
        return True, "markitdown", attempts

    pandoc_attempt = run_pandoc(source, destination)
    attempts.append(pandoc_attempt)
    if pandoc_attempt.success:
        return True, "pandoc", attempts

    return False, "none", attempts


def process_documents(patterns: list[str] | None, force: bool) -> int:
    state = load_state()
    changed = False
    converted_count = 0

    for source in discover_documents():
        if not matches_selection(source, patterns):
            continue

        relative = str(source.relative_to(SOURCE_DIR))
        mtime = source.stat().st_mtime

        if not force and state.get(relative) == mtime:
            continue

        success, engine, attempts = convert_one(source)
        if success:
            print(f"[ok] {relative} -> {target_markdown_path(source).relative_to(OUTPUT_DIR)} ({engine})")
            state[relative] = mtime
            changed = True
            converted_count += 1
        else:
            print(
                f"[error] Failed to convert {relative} -> {target_markdown_path(source).relative_to(OUTPUT_DIR)}"
            )
            for attempt in attempts:
                print(format_attempt_error(attempt))

    if changed:
        save_state(state)

    return converted_count


def main() -> None:
    args = parse_args()
    ensure_directories()

    if args.mode == "once":
        converted = process_documents(args.select, args.force)
        print(f"Completed. Converted {converted} file(s).")
        return

    print("Watching /workspace/documents for changes...")
    while True:
        process_documents(args.select, args.force)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
