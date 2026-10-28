"""install.ps1 / uninstall.ps1 against a throwaway ~/.claude. Skipped where no PowerShell is installed.

BUILD_CREW_PS picks the shell (CI runs both Windows PowerShell 5.1 and pwsh 7)."""
import json
import os
import shutil
import subprocess

import pytest

from conftest import ROOT

PS = os.environ.get("BUILD_CREW_PS") or shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(not PS, reason="PowerShell not installed")


def ps(script, home):
    return subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / script),
                           "-ClaudeDir", str(home / ".claude")], capture_output=True, text=True, timeout=120)


@pytest.fixture
def home(tmp_path):
    c = tmp_path / ".claude"
    (c / "agents").mkdir(parents=True)
    (c / "commands").mkdir()
    (c / "settings.json").write_text(json.dumps({
        "model": "opus",
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "bash ~/myhooks/audit.sh"},
            {"type": "command", "command": "python3 ~/myhooks/guard.py"}]}]},
    }))
    (c / "agents" / "debugger.md").write_text("---\nname: debugger\ndescription: my own agent\n---\nmine\n")
    return tmp_path


def settings(home):
    return json.loads((home / ".claude/settings.json").read_text(encoding="utf-8-sig"))


def hook_cmds(home, event):
    return [h["command"] for g in settings(home)["hooks"].get(event, []) for h in g["hooks"]]


def test_install_keeps_user_files_and_hooks(home):
    res = ps("install.ps1", home)
    assert res.returncode == 0, res.stdout + res.stderr
    cmds = hook_cmds(home, "PreToolUse")
    assert "bash ~/myhooks/audit.sh" in cmds and "python3 ~/myhooks/guard.py" in cmds  # user's hooks untouched
    assert sum("build-crew/hooks/guard.py" in c for c in cmds) == 1
    assert settings(home)["model"] == "opus"
    backups = list((home / ".claude/build-crew").glob("backup-*/agents/debugger.md"))
    assert backups and "mine" in backups[0].read_text()                                 # user's agent backed up
    assert (home / ".claude/build-crew/gates/merge_gate.py").exists()


def test_install_is_idempotent_and_renders_paths(home):
    ps("install.ps1", home)
    res = ps("install.ps1", home)
    assert res.returncode == 0, res.stdout + res.stderr
    assert len(hook_cmds(home, "SessionStart")) == 1
    assert sum("build-crew/hooks/guard.py" in c for c in hook_cmds(home, "PreToolUse")) == 1
    for f in (home / ".claude/agents").glob("*.md"):
        raw = f.read_bytes()
        assert raw.startswith(b"---"), f"{f.name}: must start with frontmatter (no BOM)"
        text = raw.decode()
        assert "CLAUDE_PLUGIN_ROOT" not in text and "`build-crew:" not in text
    gate = (home / ".claude/build-crew/gates/merge_gate.py").as_posix()
    assert gate in (home / ".claude/commands/ship.md").read_text(encoding="utf-8")
    assert b"\r\n" not in (home / ".claude/build-crew/hooks/session_start.sh").read_bytes()


def test_bad_settings_aborts_without_changes(home):
    (home / ".claude/settings.json").write_text("{not json")
    res = ps("install.ps1", home)
    assert res.returncode != 0 and (home / ".claude/settings.json").read_text() == "{not json"


def test_settings_with_bom_is_accepted(home):
    path = home / ".claude/settings.json"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    res = ps("install.ps1", home)
    assert res.returncode == 0, res.stdout + res.stderr
    assert settings(home)["model"] == "opus"


def test_uninstall_removes_only_ours(home):
    ps("install.ps1", home)
    (home / ".claude/agents/my-agent.md").write_text("---\nname: my-agent\n---\n")
    res = ps("uninstall.ps1", home)
    assert res.returncode == 0, res.stdout + res.stderr
    assert (home / ".claude/agents/my-agent.md").exists()
    assert not (home / ".claude/agents/pr-reviewer.md").exists()
    assert hook_cmds(home, "PreToolUse") == ["bash ~/myhooks/audit.sh", "python3 ~/myhooks/guard.py"]
    assert hook_cmds(home, "SessionStart") == []


def test_upgrade_retires_old_kit_files(home):
    (home / ".claude/agents/spec-writer.md").write_text("---\nname: spec-writer\n---\nSPEC_WRITER_RESULT: WRITTEN\n")
    (home / ".claude/agents/docs-keeper.md").write_text("---\nname: docs-keeper\n---\nmy own docs agent\n")
    ps("install.ps1", home)
    assert not (home / ".claude/agents/spec-writer.md").exists()
    assert (home / ".claude/agents/docs-keeper.md").exists()   # not the old kit's: left alone
