#!/usr/bin/env python3
"""SessionStart hook: every new session starts with where things stand.

Prints the last /handoff (docs/PROGRESS.md) and phase progress (docs/PLAN.md);
Claude Code adds the output to the session's context. Silent in projects
without build-crew docs. Never fails the session.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def main() -> int:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    docs = root / "docs"
    out: list[str] = []

    progress = read(docs / "PROGRESS.md")
    if progress:
        out.append("=== build-crew: last handoff (docs/PROGRESS.md) ===")
        out += progress.split("## History", 1)[0].splitlines()[:60]

    plan = read(docs / "PLAN.md")
    phases = re.findall(r"^- \[[ xX]\] Phase .*$", plan, re.M)
    if phases:
        out.append("=== build-crew: phases (docs/PLAN.md) ===")
        out += phases[:40]

    if (docs / "HOW_IT_WORKS.md").exists():
        out.append("=== build-crew: docs/HOW_IT_WORKS.md holds the decisions and non-goals. "
                   "The code is the source of truth for everything else. ===")

    if out:
        sys.stdout.buffer.write(("\n".join(out) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # context is a convenience; never block a session over it
