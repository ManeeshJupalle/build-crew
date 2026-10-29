#!/usr/bin/env python3
"""checks: detect and run the project's own lint / typecheck / test / build.

Usage:
  checks.py              run, print JSON
  checks.py --markdown   also produce a Markdown table (for PR bodies)

"Tests passed" becomes a fact produced by code, not a claim made by a model.
Missing tools are SKIPPED, never PASS. If nothing actually ran, the gate fails
(NOT VERIFIED) unless this branch only changed docs.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import GateError, changed_files, emit, git, main_guarded, resolve_base, run  # noqa: E402

TIMEOUT = int(os.environ.get("BUILD_CREW_CHECK_TIMEOUT", "900"))
DOC_SUFFIXES = (".md", ".mdx", ".rst", ".png", ".jpg", ".jpeg", ".gif", ".webp")  # not .txt (requirements.txt) or .svg


def node_checks(root: Path) -> list[tuple[str, str, str]]:
    pkg = root / "package.json"
    if not pkg.exists():
        return []
    scripts = json.loads(pkg.read_text(encoding="utf-8") or "{}").get("scripts", {})
    pm = ("pnpm" if (root / "pnpm-lock.yaml").exists() else
          "yarn" if (root / "yarn.lock").exists() else
          "bun" if (root / "bun.lockb").exists() or (root / "bun.lock").exists() else "npm")
    return [(n, f"{pm} run {n}", pm) for n in ("lint", "typecheck", "test", "build") if n in scripts]


def python_tool(root: Path, tool: str) -> str:
    """Prefer the project's virtualenv over whatever is on PATH."""
    scripts, exe = ("Scripts", ".exe") if os.name == "nt" else ("bin", "")
    for venv in (".venv", "venv"):
        cand = root / venv / scripts / (tool + exe)
        if cand.exists():
            return cand.as_posix()  # forward slashes: checks run in bash on every OS
    return tool


def python_checks(root: Path) -> list[tuple[str, str, str]]:
    py = root / "pyproject.toml"
    if not (py.exists() or list(root.glob("requirements*.txt")) or (root / "setup.py").exists()):
        return []
    cfg = py.read_text(encoding="utf-8") if py.exists() else ""
    out = []
    if "[tool.ruff" in cfg or (root / "ruff.toml").exists() or (root / ".ruff.toml").exists():
        t = python_tool(root, "ruff")
        out.append(("lint", f"{shlex.quote(t)} check .", t))
    if "[tool.mypy" in cfg or (root / "mypy.ini").exists():
        t = python_tool(root, "mypy")
        out.append(("typecheck", f"{shlex.quote(t)} .", t))
    if (root / "tests").is_dir() or "[tool.pytest" in cfg or (root / "pytest.ini").exists():
        t = python_tool(root, "pytest")
        out.append(("test", f"{shlex.quote(t)} -q", t))
    return out


def rust_checks(root: Path) -> list[tuple[str, str, str]]:
    if not (root / "Cargo.toml").exists():
        return []
    return [("format", "cargo fmt --check", "cargo"),
            ("lint", "cargo clippy -- -D warnings", "cargo"),
            ("test", "cargo test", "cargo")]


def go_checks(root: Path) -> list[tuple[str, str, str]]:
    if not (root / "go.mod").exists():
        return []
    return [("lint", "go vet ./...", "go"), ("test", "go test ./...", "go")]


def make_checks(root: Path) -> list[tuple[str, str, str]]:
    mk = root / "Makefile"
    if not mk.exists():
        return []
    targets = set(re.findall(r"^([A-Za-z][\w-]*):", mk.read_text(encoding="utf-8"), re.M))
    return [(t, f"make {t}", "make") for t in ("lint", "test") if t in targets]


def pytest_suite_checks(root: Path) -> list[tuple[str, str, str]]:
    tests = root / "tests"
    if not ((tests / "conftest.py").exists() or any(tests.glob("test_*.py")) or any(tests.glob("*_test.py"))):
        return []
    t = python_tool(root, "pytest")
    return [("test", f"{shlex.quote(t)} -q", t)]


def detect(root: Path) -> list[tuple[str, str, str]]:
    found = node_checks(root) + python_checks(root) + rust_checks(root) + go_checks(root)
    return found or make_checks(root) or pytest_suite_checks(root)


def docs_only_change(root: Path) -> bool | None:
    """True if this branch only touched docs; None if we can't tell (no git / no base)."""
    if not git("rev-parse", "--git-dir", cwd=str(root)):
        return None
    try:
        _, mb = resolve_base()
        files = changed_files(mb, str(root))
    except GateError:
        return None
    return bool(files) and all(f.lower().endswith(DOC_SUFFIXES) for f in files)


def checks() -> None:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or git("rev-parse", "--show-toplevel") or os.getcwd())
    results = []
    for name, cmd, tool in detect(root):
        if not (shutil.which(tool) or Path(tool).exists()):
            results.append({"name": name, "cmd": cmd, "status": "SKIPPED", "detail": f"{Path(tool).name} not installed"})
            continue
        t0 = time.time()
        res = run(cmd, timeout=TIMEOUT, cwd=str(root))
        status = "PASS" if res.returncode == 0 else "FAIL"
        entry = {"name": name, "cmd": cmd, "status": status, "seconds": round(time.time() - t0, 1)}
        if status == "FAIL":
            entry["output_tail"] = "\n".join((res.stdout + res.stderr).strip().splitlines()[-30:])
        results.append(entry)

    ran = [r for r in results if r["status"] != "SKIPPED"]
    out: dict = {"gate": "checks", "root": str(root), "checks": results}
    ok = bool(ran) and all(r["status"] == "PASS" for r in ran)
    if not ran:
        docs_only = docs_only_change(root)
        out["verdict"] = "NOT VERIFIED"
        out["note"] = ("no lint/test/build ran" + (" (all tools missing)" if results else " (none detected)"))
        if docs_only:
            ok = True
            out["note"] += ": allowed because this branch only changes docs"
        else:
            out["note"] += ": add a test command, or install the missing tools"
    if "--markdown" in sys.argv:
        rows = "\n".join(f"| {r['name']} | `{r['cmd']}` | {r['status']}"
                         f"{' (' + r['detail'] + ')' if r.get('detail') else ''} |" for r in results)
        out["markdown"] = "| Check | Command | Result |\n|---|---|---|\n" + (rows or "| none | — | NOT VERIFIED |")
    emit(out, ok)


if __name__ == "__main__":
    main_guarded("checks", checks)
