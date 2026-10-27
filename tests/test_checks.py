import os
import shutil

import pytest

from conftest import git, run_gate

needs_make = pytest.mark.skipif(not shutil.which("make"), reason="make not installed")


def env(path):
    return {"CLAUDE_PROJECT_DIR": str(path)}


def test_nothing_ran_is_not_verified_and_fails(repo):
    git(repo, "switch", "-q", "-c", "feat/x")
    (repo / "app.py").write_text("print(1)\n", encoding="utf-8")
    code, out = run_gate("checks.py", cwd=repo, env=env(repo))
    assert code == 1 and out["verdict"] == "NOT VERIFIED"


def test_docs_only_change_may_pass_without_checks(repo):
    git(repo, "switch", "-q", "-c", "docs/x")
    (repo / "GUIDE.md").write_text("# guide\n", encoding="utf-8")
    code, out = run_gate("checks.py", cwd=repo, env=env(repo))
    assert code == 0 and out["verdict"] == "NOT VERIFIED" and "only changes docs" in out["note"]


@needs_make
def test_make_targets_pass_and_fail(tmp_path):
    (tmp_path / "Makefile").write_text("lint:\n\ttrue\ntest:\n\t@echo boom; false\n", encoding="utf-8")
    code, out = run_gate("checks.py", "--markdown", cwd=tmp_path, env=env(tmp_path))
    status = {c["name"]: c["status"] for c in out["checks"]}
    assert code == 1 and status == {"lint": "PASS", "test": "FAIL"}
    assert "boom" in next(c for c in out["checks"] if c["name"] == "test")["output_tail"]
    assert "| test | `make test` | FAIL |" in out["markdown"]


@needs_make
def test_runs_in_project_root_not_cwd(tmp_path):
    (tmp_path / "Makefile").write_text("test:\n\ttest -f Makefile\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    code, out = run_gate("checks.py", cwd=tmp_path / "sub", env=env(tmp_path))
    assert code == 0 and out["checks"][0]["status"] == "PASS"


def test_all_skipped_is_not_a_pass(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    code, out = run_gate("checks.py", cwd=tmp_path, env={**env(tmp_path), "PATH": "/nonexistent"})
    assert code == 1 and all(c["status"] == "SKIPPED" for c in out["checks"])


@pytest.mark.skipif(os.name == "nt", reason="posix venv layout")
def test_prefers_project_virtualenv(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake = venv_bin / "pytest"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    code, out = run_gate("checks.py", cwd=tmp_path, env=env(tmp_path))
    assert code == 0 and out["checks"][0]["cmd"].startswith(str(fake))


def test_requirements_txt_is_not_docs(repo):
    git(repo, "switch", "-q", "-c", "chore/deps")
    (repo / "requirements.txt").write_text("requests\n", encoding="utf-8")
    code, out = run_gate("checks.py", cwd=repo, env=env(repo))
    assert code == 1
