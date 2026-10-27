#!/usr/bin/env python3
"""build-crew manual installer: one implementation for macOS, Linux and Windows.

    python scripts/install.py              install / upgrade into ~/.claude
    python scripts/install.py --uninstall  remove it again

Wrapped by install.sh (bash) and install.ps1 (PowerShell). Safe to re-run:
  - files it writes carry a marker; any other file with the same name is backed up first
  - settings.json: only build-crew's own hook handlers are added/replaced (atomic write,
    timestamped backup), and an unreadable settings.json aborts without changes
  - hooks use exec form with this Python's absolute path, so they need no shell and
    work the same on Windows, and the guard is set to block if it can't start
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("BUILD_CREW_HOME") or Path.home())   # override for tests
CLAUDE = HOME / ".claude"
ROOT = CLAUDE / "build-crew"
MARKER = "<!-- installed by build-crew -->"
BACKUP = ROOT / f"backup-{time.strftime('%Y%m%d-%H%M%S')}"
PAYLOAD = ("gates", "hooks", "scripts")

# Files from the pre-plugin kit, recognised by a report line only that kit wrote.
RETIRED = {"agents/spec-writer.md": "SPEC_WRITER_RESULT", "agents/docs-keeper.md": "DOCS_KEEPER_RESULT",
           "agents/pr-merger.md": "PR_MERGER_RESULT", "agents/build-planner.md": "BUILD_PLANNER_RESULT",
           "commands/spec.md": "spec-writer"}
OLD_HOOK_FILES = ("hooks/guard.py", "hooks/session_start.sh")
DENY = ["Bash(git push --force:*)", "Bash(git push -f:*)", "Bash(gh pr merge:*)", "Bash(gh repo delete:*)",
        "Read(./.env)", "Read(./.env.local)", "Read(./.env.development)", "Read(./.env.production)",
        "Read(./.env.staging)", "Read(./.env.test)"]


def say(msg: str) -> None:
    print(msg, flush=True)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def backup(p: Path) -> None:
    dest = BACKUP / p.relative_to(CLAUDE)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), str(dest))


def ours(p: Path) -> bool:
    return p.is_file() and MARKER in read(p)


def is_our_hook(h: dict) -> bool:
    blob = (h.get("command", "") + " " + " ".join(map(str, h.get("args", [])))).replace("\\", "/")
    return ("build-crew/hooks/" in blob or "build-crew/scripts/py" in blob
            or "$HOME/.claude/hooks/guard.py" in blob or "$HOME/.claude/hooks/session_start.sh" in blob
            or f"{CLAUDE.as_posix()}/hooks/guard.py" in blob or f"{CLAUDE.as_posix()}/hooks/session_start.sh" in blob)


def render(src: Path, dest: Path) -> None:
    text = read(src).replace("${CLAUDE_PLUGIN_ROOT}", ROOT.as_posix())
    text = re.sub(r"`build-crew:([a-z-]+)`", r"`\1`", text)
    if dest.exists() and not ours(dest):
        backup(dest)
        say(f"Backed up existing {dest.parent.name}/{dest.name}")
    dest.write_text(text.rstrip("\n") + f"\n\n{MARKER}\n", encoding="utf-8", newline="\n")


def load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(read(path) or "{}")
    except json.JSONDecodeError as e:
        sys.exit(f"✗ {path} is not valid JSON ({e}). Fix it and re-run; nothing was changed.")


def write_settings(path: Path, s: dict) -> None:
    tmp = path.with_suffix(".json.build-crew.tmp")
    tmp.write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # atomic: never a half-written settings.json


def strip_our_hooks(s: dict) -> None:
    for event, groups in list(s.get("hooks", {}).items()):
        kept_groups = []
        for g in groups:
            kept = [h for h in g.get("hooks", []) if not is_our_hook(h)]
            if kept:
                kept_groups.append({**g, "hooks": kept})
        s["hooks"][event] = kept_groups


def install() -> None:
    if sys.version_info < (3, 9):
        sys.exit("✗ build-crew needs Python 3.9+")
    if not shutil.which("gh"):
        say("⚠️  GitHub CLI not found: install it from https://cli.github.com before using /ship")
    if os.name == "nt" and not shutil.which("bash") and not Path(r"C:\Program Files\Git\bin\bash.exe").exists():
        say("⚠️  Git Bash not found: install Git for Windows (https://git-scm.com/download/win); "
            "Claude Code uses it to run commands")
    settings_path = CLAUDE / "settings.json"
    settings = load_settings(settings_path)          # validate before touching anything

    for d in ("agents", "commands"):
        (CLAUDE / d).mkdir(parents=True, exist_ok=True)
    ROOT.mkdir(parents=True, exist_ok=True)

    for rel, signature in RETIRED.items():
        p = CLAUDE / rel
        if p.is_file() and not ours(p) and signature in read(p):
            backup(p)
    for rel in OLD_HOOK_FILES:
        p = CLAUDE / rel
        if p.is_file() and re.search(r"build-crew|pr-agents", read(p)):
            backup(p)

    for d in PAYLOAD:
        shutil.rmtree(ROOT / d, ignore_errors=True)
        shutil.copytree(KIT / d, ROOT / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    for d in ("agents", "commands"):
        for src in sorted((KIT / d).glob("*.md")):
            render(src, CLAUDE / d / src.name)

    if settings_path.exists():
        BACKUP.mkdir(parents=True, exist_ok=True)
        shutil.copy2(settings_path, BACKUP / "settings.json")
    strip_our_hooks(settings)
    py = Path(sys.executable).as_posix()
    hooks = settings.setdefault("hooks", {})
    hooks.setdefault("PreToolUse", []).append({"matcher": "Bash", "hooks": [
        {"type": "command", "command": py, "args": [(ROOT / "hooks/guard.py").as_posix()], "onFailure": "block"}]})
    hooks.setdefault("SessionStart", []).append({"hooks": [
        {"type": "command", "command": py, "args": [(ROOT / "hooks/session_start.py").as_posix()]}]})
    deny = settings.setdefault("permissions", {}).setdefault("deny", [])
    if "Read(./.env.*)" in deny:   # older versions also blocked .env.example
        deny.remove("Read(./.env.*)")
    deny += [r for r in DENY if r not in deny]
    write_settings(settings_path, settings)

    if BACKUP.exists():
        say(f"Backups: {BACKUP}")
    say(f"✅ build-crew installed globally ({ROOT}). Restart Claude Code in any repo.")
    say("   /kickoff → /build-phase → /ship → /release → /deploy   (+ /fix /research /handoff)")


def uninstall() -> None:
    for d in ("agents", "commands"):
        for src in (KIT / d).glob("*.md"):
            dest = CLAUDE / d / src.name
            if ours(dest):
                dest.unlink()
    settings_path = CLAUDE / "settings.json"
    if settings_path.exists():
        settings = load_settings(settings_path)
        shutil.copy2(settings_path, settings_path.with_name("settings.json.build-crew-uninstall.bak"))
        strip_our_hooks(settings)
        write_settings(settings_path, settings)
    for d in PAYLOAD:
        shutil.rmtree(ROOT / d, ignore_errors=True)
    say("✅ build-crew removed. Deny rules were left in settings.json; backup: settings.json.build-crew-uninstall.bak")


if __name__ == "__main__":
    uninstall() if "--uninstall" in sys.argv[1:] else install()
