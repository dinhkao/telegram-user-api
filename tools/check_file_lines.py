from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_EXCLUDES = (
    ".git",
    ".venv",
    "__pycache__",
    "frontend/node_modules",
    "frontend/.next",
    "node_modules",
    "docs",
    "static",
)

CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".sh"}


def iter_code_files(root: Path, excludes: tuple[str, ...]):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in CODE_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel == ex or rel.startswith(f"{ex}/") for ex in excludes):
            continue
        yield path


def line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--max", type=int, default=100)
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()

    root = Path(args.root).resolve()
    excludes = tuple(DEFAULT_EXCLUDES) + tuple(args.exclude)
    offenders = []
    for path in iter_code_files(root, excludes):
        count = line_count(path)
        if count > args.max:
            offenders.append((count, path.relative_to(root)))

    for count, path in sorted(offenders, reverse=True):
        print(f"{count:5d} {path}")
    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
