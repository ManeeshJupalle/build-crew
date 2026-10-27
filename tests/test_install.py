"""scripts/install.py (behind install.sh / install.ps1) against a throwaway home folder."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT

USER_HOOKS = ["bash ~/myhooks/audit.sh", "python3 ~/myhooks/guard.py"]


def run_installer(home, *args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"), *args],
                          env={**os.environ, "BUILD_CREW_HOME": str(home), "PYTHONUTF8": "1"},
                          capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def home(tmp_path):
    c = tmp_path / ".claude"
    (c / "agents").mkdir(parents=True)
    (c / "commands").mkdir()
    (c / "settings.json").write_text(json.dumps({
        "model": "opus",
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": USER_HOOKS[0]}, {"type": "command", "command": USER_HOOKS[1]}]}]},
    }), encoding="utf-8")
    (c / "agents" / "debugger.md").write_text("---\nname: debugger\ndescription: my own agent\n---\nmine\n",
                                              encoding="utf-8")
    return tmp_path


def settings(home):
    return json.loads((home / ".claude/settings.json").read_text(encoding="utf-8"))


def handlers(home, event):
    return [h for g in settings(home)["hooks"].get(event, []) for h in g["hooks"]]


def ours(h):
    return "build-crew/hooks/" in " ".join(h.get("args", []))


def test_install_keeps_user_files_and_hooks(home):
    res = run_installer(home)
    assert res.returncode == 0, res.stdout + res.stderr
    cmds = [h["command"] for h in handlers(home, "PreToolUse")]
    assert USER_HOOKS[0] in cmds and USER_HOOKS[1] in cmds
    assert sum(ours(h) for h in handlers(home, "PreToolUse")) == 1
    assert settings(home)["model"] == "opus"
    backups = list((home / ".claude/build-crew").glob("backup-*/agents/debugger.md"))
    assert backups and "mine" in backups[0].read_text(encoding="utf-8")


def test_hooks_are_exec_form_with_this_python_and_guard_fails_closed(home):
    run_installer(home)
    guard = next(h for h in handlers(home, "PreToolUse") if ours(h))
    assert guard["command"] == sys.executable.replace("\\", "/")   # no shell, no PATH lookup for python3
    assert guard["args"][0].endswith("build-crew/hooks/guard.py")
    assert guard["onFailure"] == "block"
    assert os.path.exists(guard["args"][0])


def test_install_is_idempotent_and_renders_paths(home):
    run_installer(home)
    run_installer(home)
    assert sum(ours(h) for h in handlers(home, "PreToolUse")) == 1
    assert sum(ours(h) for h in handlers(home, "SessionStart")) == 1
    for f in (home / ".claude/agents").glob("*.md"):
        text = f.read_text(encoding="utf-8")
        assert "CLAUDE_PLUGIN_ROOT" not in text and "`build-crew:" not in text
    ship = (home / ".claude/commands/ship.md").read_text(encoding="utf-8")
    assert (home / ".claude/build-crew/scripts/py").as_posix() in ship


def test_bad_settings_aborts_without_changes(home):
    (home / ".claude/settings.json").write_text("{not json", encoding="utf-8")
    res = run_installer(home)
    assert res.returncode != 0
    assert (home / ".claude/settings.json").read_text(encoding="utf-8") == "{not json"


def test_uninstall_removes_only_ours(home):
    run_installer(home)
    (home / ".claude/agents/my-agent.md").write_text("---\nname: my-agent\n---\n", encoding="utf-8")
    res = run_installer(home, "--uninstall")
    assert res.returncode == 0, res.stderr
    assert (home / ".claude/agents/my-agent.md").exists()
    assert not (home / ".claude/agents/pr-reviewer.md").exists()
    assert [h["command"] for h in handlers(home, "PreToolUse")] == USER_HOOKS


def test_user_file_mentioning_build_crew_names_is_backed_up_not_lost(home):
    (home / ".claude/agents/architect.md").write_text(
        "---\nname: architect\ndescription: mine, hands off to pr-reviewer\n---\nmine\n", encoding="utf-8")
    run_installer(home)
    run_installer(home, "--uninstall")
    assert any("mine" in p.read_text(encoding="utf-8")
               for p in (home / ".claude/build-crew").glob("backup-*/agents/architect.md"))


def test_upgrade_retires_old_kit_files_and_old_hooks(home):
    c = home / ".claude"
    (c / "agents/spec-writer.md").write_text("---\nname: spec-writer\n---\nSPEC_WRITER_RESULT: WRITTEN\n", encoding="utf-8")
    (c / "agents/docs-keeper.md").write_text("---\nname: docs-keeper\n---\nmy own docs agent\n", encoding="utf-8")
    s = settings(home)
    s["hooks"]["SessionStart"] = [{"hooks": [{"type": "command", "command": 'bash "$HOME/.claude/hooks/session_start.sh"'}]}]
    (c / "settings.json").write_text(json.dumps(s), encoding="utf-8")
    run_installer(home)
    assert not (c / "agents/spec-writer.md").exists()
    assert (c / "agents/docs-keeper.md").exists()        # not the old kit's: left alone
    assert not any("session_start.sh" in h.get("command", "") for h in handlers(home, "SessionStart"))


@pytest.mark.skipif(os.name == "nt", reason="bash wrapper; Windows uses install.ps1")
def test_install_sh_wrapper(home):
    res = subprocess.run(["bash", str(ROOT / "install.sh")], capture_output=True, text=True,
                         env={**os.environ, "BUILD_CREW_HOME": str(home)})
    assert res.returncode == 0, res.stderr
    assert (home / ".claude/agents/pr-reviewer.md").exists()


@pytest.mark.skipif(not shutil.which("pwsh") and not shutil.which("powershell"), reason="PowerShell not installed")
def test_install_ps1_wrapper(home):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    res = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install.ps1")],
                         capture_output=True, text=True, env={**os.environ, "BUILD_CREW_HOME": str(home)})
    assert res.returncode == 0, res.stdout + res.stderr
    assert (home / ".claude/agents/pr-reviewer.md").exists()


def test_launcher_runs_python_files():
    sys.path.insert(0, str(ROOT / "gates"))
    from _common import find_bash
    bash = find_bash()
    if not bash:
        pytest.skip("bash not available")
    res = subprocess.run([bash, str(ROOT / "scripts" / "py"), "hooks/session_start.py"], capture_output=True,
                         env={**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT / "examples")})
    assert res.returncode == 0, res.stderr


def test_session_start_reports_plan(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "PLAN.md").write_text((ROOT / "examples/PLAN.md").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "docs" / "PROGRESS.md").write_text("# Progress\n## Now\n- next: 1\n---\n## History\n- old\n",
                                                   encoding="utf-8")
    res = subprocess.run([sys.executable, str(ROOT / "hooks" / "session_start.py")], capture_output=True,
                         env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)})
    out = res.stdout.decode("utf-8")
    assert res.returncode == 0 and "Phase 0 — Foundation" in out and "next: 1" in out and "old" not in out


def test_session_start_is_silent_elsewhere(tmp_path):
    res = subprocess.run([sys.executable, str(ROOT / "hooks" / "session_start.py")], capture_output=True,
                         env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert res.returncode == 0 and res.stdout == b""
