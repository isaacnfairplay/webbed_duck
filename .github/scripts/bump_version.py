#!/usr/bin/env python3
"""Compute diff size, bump pyproject version, and emit outputs for CI."""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
from typing import Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
MAX_FILES = int(os.environ.get("MAX_FILES_FOR_PATCH", "0"))
MAX_LINES = int(os.environ.get("MAX_LINES_FOR_PATCH", "0"))
GITHUB_OUTPUT = os.environ.get("GITHUB_OUTPUT")
BEFORE_SHA = os.environ.get("GITHUB_BEFORE", "")
AFTER_SHA = os.environ.get("GITHUB_SHA", "")


def _run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _resolve_base(before: str) -> str:
    before = before.strip()
    if before and not set(before) == {"0"}:
        return before
    # Fall back to previous commit when before is unavailable (e.g. first commit).
    try:
        return _run_git("rev-parse", "HEAD^")
    except subprocess.CalledProcessError:
        # Single-commit history, use HEAD directly
        return _run_git("rev-parse", "HEAD")


def _shortstat(base: str, head: str) -> Tuple[int, int]:
    if not head:
        head = _run_git("rev-parse", "HEAD")
    diff = _run_git("diff", "--shortstat", base, head)
    files = 0
    lines = 0
    for part in diff.split(","):
        part = part.strip()
        if not part:
            continue
        if part.endswith("files changed") or part.endswith("file changed"):
            files = int(part.split()[0])
        elif part.endswith("insertions(+)") or part.endswith("insertion(+)"):
            lines += int(part.split()[0])
        elif part.endswith("deletions(-)") or part.endswith("deletion(-)"):
            lines += int(part.split()[0])
    return files, lines


def _read_version(text: str) -> Tuple[int, int, int]:
    match = re.search(r"^version\s*=\s*\"(\d+)\.(\d+)\.(\d+)\"", text, re.MULTILINE)
    if not match:
        raise SystemExit("Version line not found in pyproject.toml")
    return tuple(map(int, match.groups()))  # type: ignore[return-value]


def main() -> None:
    base_commit = _resolve_base(BEFORE_SHA)
    files_changed, lines_changed = _shortstat(base_commit, AFTER_SHA)

    text = PYPROJECT.read_text()
    major, minor, patch = _read_version(text)

    bump_minor = files_changed > MAX_FILES or lines_changed > MAX_LINES
    if bump_minor:
        minor += 1
        patch = 0
        level = "minor"
    else:
        patch += 1
        level = "patch"

    new_version = f"{major}.{minor}.{patch}"
    new_line = f'version = "{new_version}"'
    new_text = re.sub(r'^version\s*=\s*"\d+\.\d+\.\d+"', new_line, text, flags=re.MULTILINE)
    if new_text == text:
        print("Version unchanged; nothing to do")
        return
    PYPROJECT.write_text(new_text)

    print(f"Base commit: {base_commit}")
    print(f"Files changed: {files_changed}")
    print(f"Lines changed: {lines_changed}")
    print(f"Bump level: {level}")
    print(f"New version: {new_version}")

    if GITHUB_OUTPUT:
        with open(GITHUB_OUTPUT, "a", encoding="utf-8") as fh:
            fh.write(f"version={new_version}\n")
            fh.write(f"files_changed={files_changed}\n")
            fh.write(f"lines_changed={lines_changed}\n")
            fh.write(f"bump_minor={str(bump_minor).lower()}\n")


if __name__ == "__main__":
    main()
