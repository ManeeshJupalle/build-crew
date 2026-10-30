"""install.sh / uninstall.sh against a throwaway HOME."""
import json
import os
import re
import subprocess

import pytest

from conftest import BASH, ROOT


def sh(script, home):
    return subprocess.run([BASH, str(ROOT / script)], env={**os.environ, "HOME": str(home)},
                          capture_output=True, text=True, timeout=60)


@pytest.fixture
def home(tmp_path):
    c = tmp_path / ".claude"
    (c / "agents").mkdir(parents=True)
    (c / "commands").mkdir()
    (c / "settings.json").write_text(json.dumps({
        "model": "opus",
        "statusLine": {"type": "command", "command": "echo 'build → ✓ 修复'"},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "bash ~/myhooks/audit.sh"},
            {"type": "command", "command": "python3 ~/myhooks/guard.py"}]}]},
    }, ensure_ascii=False), encoding="utf-8")
    (c / "agents" / "debugger.md").write_text("---\nname: debugger\ndescription: my own agent\n---\nmine\n")
    return tmp_path


def settings(home):
    return json.loads((home / ".claude/settings.json").read_text(encoding="utf-8"))


def our_guard(cmds):
    return sum('build-crew/run.sh" hooks/guard.py' in c for c in cmds)


def test_install_keeps_user_files_and_hooks(home):
    res = sh("install.sh", home)
    assert res.returncode == 0, res.stderr
    s = settings(home)
    cmds = [h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert "bash ~/myhooks/audit.sh" in cmds and "python3 ~/myhooks/guard.py" in cmds  # user's hooks untouched
    assert our_guard(cmds) == 1
    assert s["model"] == "opus" and s["statusLine"]["command"] == "echo 'build → ✓ 修复'"   # survives on Windows too
    backups = list((home / ".claude/build-crew").glob("backup-*/agents/debugger.md"))
    assert backups and "mine" in backups[0].read_text()                                 # user's agent backed up


def test_install_is_idempotent_and_renders_paths(home):
    sh("install.sh", home)
    sh("install.sh", home)
    s = settings(home)
    assert len(s["hooks"]["SessionStart"]) == 1
    cmds = [h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert our_guard(cmds) == 1
    ours = [g["matcher"] for g in s["hooks"]["PreToolUse"] if our_guard(h["command"] for h in g["hooks"])]
    assert ours == ["Bash|PowerShell"]
    for f in (home / ".claude/agents").glob("*.md"):
        text = f.read_text(encoding="utf-8")
        assert "CLAUDE_PLUGIN_ROOT" not in text and "`build-crew:" not in text
    ship = (home / ".claude/commands/ship.md").read_text(encoding="utf-8")
    # Git Bash spells HOME /c/Users/..., so match the folder names rather than the whole path
    m = re.search(r'bash "([^"]+)/\.claude/build-crew/run\.sh" gates/merge_gate\.py', ship)
    assert m and m.group(1).endswith(home.name)


def test_bad_settings_aborts_without_changes(home):
    (home / ".claude/settings.json").write_text("{not json")
    res = sh("install.sh", home)
    assert res.returncode != 0 and (home / ".claude/settings.json").read_text() == "{not json"


def test_uninstall_removes_only_ours(home):
    sh("install.sh", home)
    (home / ".claude/agents/my-agent.md").write_text("---\nname: my-agent\n---\n")
    res = sh("uninstall.sh", home)
    assert res.returncode == 0, res.stderr
    assert (home / ".claude/agents/my-agent.md").exists()
    assert not (home / ".claude/agents/pr-reviewer.md").exists()
    cmds = [h["command"] for g in settings(home)["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert cmds == ["bash ~/myhooks/audit.sh", "python3 ~/myhooks/guard.py"]


def test_user_file_mentioning_build_crew_names_is_backed_up_not_lost(home):
    own = home / ".claude/agents/architect.md"
    own.write_text("---\nname: architect\ndescription: mine, hands off to pr-reviewer\n---\nmine\n")
    sh("install.sh", home)
    assert list((home / ".claude/build-crew").glob("backup-*/agents/architect.md"))
    sh("uninstall.sh", home)
    assert any("mine" in p.read_text() for p in (home / ".claude/build-crew").glob("backup-*/agents/architect.md"))


def test_upgrade_retires_old_kit_files(home):
    (home / ".claude/agents/spec-writer.md").write_text("---\nname: spec-writer\n---\nSPEC_WRITER_RESULT: WRITTEN\n")
    (home / ".claude/agents/docs-keeper.md").write_text("---\nname: docs-keeper\n---\nmy own docs agent\n")
    sh("install.sh", home)
    assert not (home / ".claude/agents/spec-writer.md").exists()
    assert (home / ".claude/agents/docs-keeper.md").exists()   # not the old kit's: left alone
