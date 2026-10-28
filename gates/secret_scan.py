#!/usr/bin/env python3
"""secret_scan: block secrets and junk before they reach a commit.

Usage: secret_scan.py [base-ref]

Scans everything this branch changed since it left the base branch: commits,
staged, unstaged and untracked files. Values are always masked. If no base
branch can be found it fails instead of guessing.
"""
from __future__ import annotations

import os
import re
import sys
from fnmatch import fnmatch
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import changed_files, emit, main_guarded, repo_root, resolve_base  # noqa: E402

FORBIDDEN_FILES = [".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
                   "*credentials*.json", "*.keystore", ".DS_Store"]
ALLOWED_FILES = [".env.example", ".env.sample", ".env.template"]
VENDOR_ANYWHERE = ["node_modules", "__pycache__", ".venv", "venv"]   # never source code
BUILD_AT_ROOT = ["dist", "build", "target"]                          # only flagged at repo root
MAX_BYTES = 5 * 1024 * 1024

SECRET_PATTERNS = {
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "GitHub token": r"(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}",
    "Anthropic key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "OpenAI-style key": r"sk-(proj-)?[A-Za-z0-9]{32,}",
    "Slack token": r"xox[abprs]-[A-Za-z0-9-]{10,}",
    "Google API key": r"AIza[0-9A-Za-z_\-]{35}",
    "Stripe live key": r"(sk|rk)_live_[0-9a-zA-Z]{20,}",
    "Private key block": r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
    "Hardcoded credential": r"""(?i)(api[_-]?key|secret|token|passw(or)?d)\s*[:=]\s*['"][^'"\s$<{]{12,}['"]""",
}


def mask(s: str) -> str:
    return s[:4] + "****" if len(s) > 4 else "****"


def path_issue(f: str) -> str | None:
    parts = f.split("/")
    if any(p in VENDOR_ANYWHERE for p in parts[:-1]):
        return "vendor/cache directory"
    if len(parts) > 1 and parts[0] in BUILD_AT_ROOT:
        return "build output directory"
    name = parts[-1]
    if name not in ALLOWED_FILES and any(fnmatch(name, p) for p in FORBIDDEN_FILES):
        return "secret-like or junk file"
    return None


def scan() -> None:
    base, mb = resolve_base(sys.argv[1] if len(sys.argv) > 1 else None)
    root = repo_root()
    findings = []
    files = changed_files(mb, root)
    for f in files:
        issue = path_issue(f)
        if issue:
            findings.append({"file": f, "issue": issue})
            continue
        p = Path(root) / f
        if not p.is_file():
            continue  # deleted in this branch
        if p.stat().st_size > MAX_BYTES:
            findings.append({"file": f, "issue": f"large file ({p.stat().st_size // 1024} KB)"})
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pat in SECRET_PATTERNS.items():
                m = re.search(pat, line)
                if m:
                    findings.append({"file": f, "line": lineno, "issue": label, "match": mask(m.group(0))})
    emit({"gate": "secret_scan", "base": base, "merge_base": mb[:7], "files_scanned": len(files),
          "findings": findings}, not findings)


if __name__ == "__main__":
    main_guarded("secret_scan", scan)
