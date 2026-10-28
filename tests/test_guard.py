import json
import os
import subprocess
import sys

import pytest

from conftest import BASH, HOOKS, ROOT

BLOCKED = [
    # force push, every spelling
    "git push --force origin feat/x",
    "git push -f",
    "git push -fu origin feat/x",
    "git push --force-with-lease",
    "git push origin +feat/x",
    "git -C . push --force",
    "git --no-pager push --force",
    # protected branches, every spelling
    "git push origin main",
    "git push origin HEAD:master",
    "git push origin feat/x:main",
    "git push origin HEAD:refs/heads/main",
    "git push origin release/1.2",
    "git push --all",
    "git push origin --delete feat/old",
    # skipping hooks
    "git commit -m x --no-verify",
    "git commit -n -m x",
    "git commit -anm x",
    "git -c core.hooksPath=/dev/null commit -m x",
    # discarding work
    "git reset --hard HEAD~1",
    "git -C . reset --hard",
    "git clean -fd",
    "git clean --force",
    "git checkout -- .",
    "git restore .",
    "git branch -D main",
    # sloppy staging
    "git add -A",
    "git add .",
    "git add --all",
    # merging outside merge_gate
    "gh pr merge 12 --squash",
    "\"gh\" pr merge 12",
    "/usr/bin/gh pr merge 12",
    "gh api -X PUT repos/o/r/pulls/7/merge",
    "gh api repos/o/r/merges -f base=main -f head=x",
    "gh api -X DELETE repos/o/r/branches/main/protection",
    "gh repo delete me/x",
    # recursive deletes of things that matter
    "rm -rf /",
    "rm -rf ~",
    "rm -rf ./",
    "rm -rf ..",
    'rm -rf "$HOME"',
    "rm --recursive --force ~",
    "sudo rm -rf /",
    # hidden inside other commands
    "npm test && git push --force",
    "echo ok; git reset --hard",
    "bash -c 'git push --force'",
    "echo $(git push --force)",
    "FOO=1 git push -f",
    "eval git push --force",
    # second-review cases
    "timeout 60 git push --force",
    "timeout 30 gh pr merge 7",
    "nice -n 10 git push --force",
    "bash -lc 'git push --force'",
    "git status  # check\ngit push --force",
    "HUSKY=0 git commit -m x",
    "export HUSKY=0",
    "SKIP=lint git commit -m x",
    "gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
    "git checkout main && git merge feat/x && git push",
    "git checkout main && git commit -m x",
    "git checkout main\ngit commit -m x",
    # Windows and macOS spellings of the same programs
    "git.exe push --force",
    "\"/c/Program Files/Git/cmd/git.exe\" push --force",
    "GH.EXE pr merge 7",
]

ALLOWED = [
    "git push -u origin feat/resume-export",
    "git push",
    "git push origin feat/x",
    "git push -u origin feat/x && gh pr create --base main --title 'feat: x'",
    "gh pr create --title 'support -f flag' --body 'no --force here'",
    "git commit -m 'docs: explain why we never use --no-verify'",
    "git commit -m 'feat: add x'",
    "git commit -am 'fix: n things'",
    "git restore --staged .",
    "git add src/app.ts tests/app.test.ts",
    "git switch main && git pull --ff-only && git switch -c feat/new",
    "rm -rf node_modules",
    "rm -rf ./dist",
    "rm -f .",
    "gh pr diff 12",
    "gh pr view 12 --json state",
    "gh api repos/o/r/pulls/7",
    "python3 gates/merge_gate.py 12 --merge",
    "git status",
    "git log --oneline -5 | head -3",
    # heredoc messages are data, not commands (Claude Code writes commits and PRs this way)
    "git commit -m \"$(cat <<'EOF'\nfix: don't crash on empty input\n\nWe don't retry. git push --force is never used.\nEOF\n)\"",
    "git commit -F - <<'EOF'\nfeat: it's faster\nEOF",
    "gh pr create --title 'feat: x' --body \"$(cat <<'EOF'\n## What\nIt's faster; don't worry.\nEOF\n)\"",
    "git status  # just looking",
    "timeout 120 npm test",
    "git checkout -- src/app.ts",
    "git commit -m 'fix: 修复 naïve — ✓'",
]


def payload(cmd: str, tool: str = "Bash") -> bytes:
    # raw UTF-8, as Claude Code sends it
    return json.dumps({"tool_name": tool, "tool_input": {"command": cmd}}, ensure_ascii=False).encode("utf-8")


def guard(cmd: str, tool: str = "Bash", cwd=None) -> int:
    return subprocess.run([sys.executable, str(HOOKS / "guard.py")], input=payload(cmd, tool),
                          capture_output=True, cwd=cwd).returncode


@pytest.fixture
def feature_repo(repo):
    subprocess.run(["git", "switch", "-q", "-c", "feat/x"], cwd=repo, check=True)
    return repo


@pytest.mark.parametrize("cmd", BLOCKED)
def test_blocks(cmd, feature_repo):
    assert guard(cmd, cwd=feature_repo) == 2


@pytest.mark.parametrize("cmd", ALLOWED)
def test_allows(cmd, feature_repo):
    assert guard(cmd, cwd=feature_repo) == 0


def test_blocks_commit_and_bare_push_on_protected_branch(repo):
    assert guard("git commit -m x", cwd=repo) == 2  # repo fixture is on main
    assert guard("git push", cwd=repo) == 2


def test_tracks_branch_switch_inside_one_command(repo):
    assert guard("git switch -c feat/y && git commit -m 'feat: y'", cwd=repo) == 0
    assert guard("git switch main && git commit -m x", cwd=repo.parent) == 2


def test_push_head_resolves_to_current_branch(repo, feature_repo=None):
    assert guard("git push -u origin HEAD", cwd=repo) == 2     # on main
    assert guard("git push origin HEAD:refs/heads/main", cwd=repo) == 2


def test_push_head_allowed_on_feature_branch(feature_repo):
    assert guard("git push -u origin HEAD", cwd=feature_repo) == 0


def test_checkout_to_feature_branch_then_commit_is_allowed(repo):
    subprocess.run(["git", "branch", "feat/z"], cwd=repo, check=True)
    assert guard("git checkout feat/z && git commit -m 'feat: z'", cwd=repo) == 0


def test_ignores_other_tools():
    assert guard("git push --force", tool="Read") == 0


def test_fails_closed():
    res = subprocess.run([sys.executable, str(HOOKS / "guard.py")], input="not json", text=True, capture_output=True)
    assert res.returncode == 2
    assert guard("git commit -m 'unbalanced") == 2


def hook_command() -> str:
    """The guard command from hooks.json, with the plugin path filled in the way Claude Code does it."""
    hooks = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    return hooks[0]["hooks"][0]["command"].replace("${CLAUDE_PLUGIN_ROOT}", ROOT.as_posix())


@pytest.mark.parametrize("cmd,code", [("git push --force", 2), ("git push", 0)])
def test_hook_command_finds_python_on_this_os(feature_repo, cmd, code):
    res = subprocess.run([BASH, "-c", hook_command()], input=payload(cmd), capture_output=True, cwd=feature_repo)
    assert res.returncode == code, res.stderr


def test_hook_blocks_when_python_is_missing(feature_repo, tmp_path):
    # any exit code but 2 is a non-blocking hook error, which would let every command through
    res = subprocess.run([BASH, str(ROOT / "run.sh"), "hooks/guard.py"], input=payload("git status"),
                         capture_output=True, cwd=feature_repo, env={**os.environ, "PATH": str(tmp_path)})
    assert res.returncode == 2 and b"needs Python 3.9+" in res.stderr
