"""Structural checks: every file the crew references exists and is well-formed."""
import json
import re

import pytest

from conftest import ROOT

AGENTS = sorted((ROOT / "agents").glob("*.md"))
COMMANDS = sorted((ROOT / "commands").glob("*.md"))


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
def test_references_resolve(path):
    text = path.read_text(encoding="utf-8")
    for agent in re.findall(r"`build-crew:([a-z-]+)`", text):
        assert (ROOT / "agents" / f"{agent}.md").exists(), f"{path.name} references missing agent {agent}"
    for gate in re.findall(r"gates/([a-z_]+\.py)", text):
        assert (ROOT / "gates" / gate).exists(), f"{path.name} references missing gate {gate}"
    # gates go through the launcher (finds Python on any OS) by full path:
    # shell variables don't survive between Claude's Bash calls
    assert "python3 " not in text, f"{path.name}: call gates via scripts/py, not python3 (Windows has no python3)"
    for call in re.findall(r'bash "([^"]+)" gates/', text):
        assert call == "${CLAUDE_PLUGIN_ROOT}/scripts/py", f"{path.name}: gate launched via {call}"


def test_non_editing_agents_have_no_write_tools():
    for name in ("pr-reviewer", "researcher", "deployer"):
        tools = frontmatter(ROOT / "agents" / f"{name}.md")["tools"]
        assert "Write" not in tools and "Edit" not in tools, f"{name} must be read-only"


def test_plugin_manifests():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert plugin["name"] == "build-crew" == market["plugins"][0]["name"]
    hooks = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
    for entries in hooks.values():
        for e in entries:
            for h in e["hooks"]:
                assert "scripts/py" in h["command"], "hooks must go through the Python launcher"
                rel = re.search(r"\s(hooks/[\w.]+)", h["command"]).group(1)
                assert (ROOT / rel).exists()
    guard = hooks["PreToolUse"][0]["hooks"][0]
    assert guard.get("onFailure") == "block", "the guard must fail closed if it can't start"


def test_all_python_file_io_is_explicit_utf8():
    """Windows defaults to its own code page; every text read/write must say utf-8."""
    offenders = []
    for folder in ("gates", "hooks", "scripts", "tests"):
        for f in (ROOT / folder).glob("*.py"):
            lines = f.read_text(encoding="utf-8").splitlines()
            for n, line in enumerate(lines):
                call = " ".join(lines[n:n + 3])            # calls may wrap onto following lines
                if re.search(r"\.(read_text|write_text)\(", line) and "encoding" not in call:
                    offenders.append(f"{folder}/{f.name}:{n + 1}")
    assert not offenders, "missing encoding=: " + ", ".join(offenders)
