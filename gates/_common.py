"""Shared helpers for build-crew gates.

Gates are plain code. They decide pass/fail; agents only read the result.
Every gate prints one JSON object to stdout and exits 0 (pass) or 1 (fail),
including when something unexpected breaks: errors fail closed.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

IS_WINDOWS = os.name == "nt"


def _gh_command() -> list[str]:
    """gh executable; BUILD_CREW_GH overrides it (tests): a JSON list or a shell-style string."""
    raw = os.environ.get("BUILD_CREW_GH", "gh")
    if raw.lstrip().startswith("["):
        return json.loads(raw)
    return shlex.split(raw, posix=not IS_WINDOWS)


def find_bash() -> str | None:
    """bash for running shell-style command strings. On Windows prefer Git Bash over WSL's System32 bash."""
    if not IS_WINDOWS:
        return shutil.which("bash")
    candidates = []
    git_exe = shutil.which("git")
    if git_exe:
        base = Path(git_exe).resolve().parent.parent          # ...\Git\cmd\git.exe -> ...\Git
        candidates += [base / "bin" / "bash.exe", base / "usr" / "bin" / "bash.exe"]
    candidates += [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"]
    which = shutil.which("bash")
    if which and "system32" not in which.lower():
        candidates.insert(0, Path(which))
    return next((str(c) for c in candidates if c.exists()), None)


class GateError(Exception):
    pass


def run(cmd: list[str] | str, timeout: int = 900, cwd: str | None = None,
        env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, "CI": "1", **(env or {})}
    shell = False
    if isinstance(cmd, str):          # project commands (Done-when, npm scripts) are written for bash
        bash = find_bash()
        cmd, shell = ([bash, "-c", cmd], False) if bash else (cmd, True)
    try:
        return subprocess.run(cmd, shell=shell, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, cwd=cwd, env=full_env)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", f"timed out after {timeout}s")
    except FileNotFoundError as e:
        raise GateError(f"command not found: {e.filename}") from e


def gh(*args: str) -> subprocess.CompletedProcess:
    return run([*_gh_command(), *args], timeout=120)


def gh_json(*args: str) -> Any:
    res = gh(*args)
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise GateError(f"gh {' '.join(args)} failed: {(res.stderr or res.stdout).strip() or 'no output'}") from e


def git(*args: str, cwd: str | None = None) -> str:
    """Best-effort git: returns stdout, '' on failure (including git not installed). Optional lookups only."""
    try:
        return run(["git", *args], timeout=60, cwd=cwd).stdout.strip()
    except GateError:
        return ""


def git_checked(*args: str, cwd: str | None = None) -> str:
    """git that must succeed: raises GateError instead of returning empty output."""
    res = run(["git", *args], timeout=60, cwd=cwd)
    if res.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout.strip()


def repo_root() -> str:
    return git_checked("rev-parse", "--show-toplevel")


def default_branch() -> str:
    try:
        return gh_json("repo", "view", "--json", "defaultBranchRef")["defaultBranchRef"]["name"]
    except Exception:
        ref = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        if ref:
            return ref.split("/", 1)[1]
        for name in ("main", "master"):
            if git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
                return name
        return "main"


def resolve_base(explicit: str | None = None) -> tuple[str, str]:
    """Return (base_ref, merge_base_sha) for "what this branch changed".

    Order: explicit ref > origin/HEAD > origin/<default> > local <default>.
    Fails closed (GateError) rather than silently comparing against HEAD.
    """
    candidates = [explicit] if explicit else []
    if not explicit:
        head = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        if head:
            candidates.append(head)
        name = default_branch()
        candidates += [f"origin/{name}", name]
    for ref in candidates:
        if ref and git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"):
            mb = git("merge-base", ref, "HEAD")
            if mb:
                return ref, mb
    raise GateError(f"could not find a base branch to compare against (tried: {', '.join(c for c in candidates if c)}). "
                    "Run `git fetch origin` or pass the base ref explicitly.")


def changed_files(merge_base: str, root: str) -> list[str]:
    """Files changed since merge_base: committed + staged + unstaged + untracked (repo-root paths)."""
    files = set(git_checked("diff", "--name-only", merge_base, cwd=root).splitlines())
    files |= set(git_checked("ls-files", "--others", "--exclude-standard", cwd=root).splitlines())
    return sorted(f for f in files if f)


def emit(result: dict, ok: bool) -> None:
    result["ok"] = ok
    print(json.dumps(result, indent=2))
    sys.exit(0 if ok else 1)


def main_guarded(gate: str, fn: Callable[[], None]) -> None:
    """Run a gate; any unexpected error becomes a failing JSON result, never a bare traceback."""
    try:
        fn()
    except SystemExit:
        raise
    except GateError as e:
        emit({"gate": gate, "error": str(e)}, False)
    except Exception as e:  # pragma: no cover - defensive
        emit({"gate": gate, "error": f"{type(e).__name__}: {e}",
              "trace": traceback.format_exc().splitlines()[-3:]}, False)
