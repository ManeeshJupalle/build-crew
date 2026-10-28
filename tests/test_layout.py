"""Structural checks: every file the crew references exists and is well-formed."""
import json
import re

import pytest

from conftest import ROOT

AGENTS = sorted((ROOT / "agents").glob("*.md"))
COMMANDS = sorted((ROOT / "commands").glob("*.md"))
CODE = sorted((ROOT / "gates").glob("*.py")) + sorted((ROOT / "hooks").glob("*.py")) + \
    [ROOT / "install.sh", ROOT / "uninstall.sh"]


def frontmatter(path):
    m = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    assert m, f"{path.name}: missing frontmatter"
    return dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.name)
def test_agent_frontmatter(path):
    fm = frontmatter(path)
    assert fm["name"].strip() == path.stem
    assert len(fm["description"].strip()) > 40
    assert fm.get("tools")


@pytest.mark.parametrize("path", COMMANDS, ids=lambda p: p.name)
def test_command_frontmatter(path):
    assert frontmatter(path).get("description")


@pytest.mark.parametrize("path", AGENTS + COMMANDS, ids=lambda p: p.name)
def test_lf_line_endings(path):
    # with CRLF, Claude Code drops the frontmatter; .gitattributes keeps Windows checkouts on LF
    assert b"\r\n" not in path.read_bytes()


@pytest.mark.parametrize("path", AGENTS + COMMANDS, ids=lambda p: p.name)
def test_references_resolve(path):
    text = path.read_text(encoding="utf-8")
    for agent in re.findall(r"`build-crew:([a-z-]+)`", text):
        assert (ROOT / "agents" / f"{agent}.md").exists(), f"{path.name} references missing agent {agent}"
    for gate in re.findall(r"gates/([a-z_]+\.py)", text):
        assert (ROOT / "gates" / gate).exists(), f"{path.name} references missing gate {gate}"
    # Python is python3, python or py depending on the OS, so gates run through run.sh, which finds it.
    # Shell variables don't survive between Claude's Bash calls, so run.sh is called by full path.
    assert "python3" not in text, f"{path.name}: run gates with run.sh, not python3"
    for call in re.findall(r"`([^`]*gates/[a-z_]+\.py)", text):
        assert call.startswith('bash "${CLAUDE_PLUGIN_ROOT}/run.sh" gates/'), f"{path.name}: gate called as {call}"


@pytest.mark.parametrize("path", CODE, ids=lambda p: p.name)
def test_files_are_read_and_written_as_utf8(path):
    # Windows defaults to a legacy encoding (cp1252), which garbles anything outside ASCII
    calls = re.findall(r"\b(?:read_text|write_text|open)\(((?:[^()]|\([^()]*\))*)\)", path.read_text(encoding="utf-8"))
    for args in calls:
        assert "encoding=" in args, f"{path.name}: ({args}) needs encoding=\"utf-8\""


def test_non_editing_agents_have_no_write_tools():
    for name in ("pr-reviewer", "researcher", "deployer"):
        tools = frontmatter(ROOT / "agents" / f"{name}.md")["tools"]
        assert "Write" not in tools and "Edit" not in tools, f"{name} must be read-only"


def test_plugin_manifests():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert plugin["name"] == "build-crew" == market["plugins"][0]["name"]
    hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]
    for entries in hooks.values():
        for e in entries:
            for h in e["hooks"]:
                files = re.findall(r"\b((?:hooks|gates)/[\w.]+|run\.sh)\b", h["command"])
                assert files and all((ROOT / f).exists() for f in files), h["command"]
