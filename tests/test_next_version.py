import pytest

from conftest import git, run_gate


def commit(repo, msg):
    git(repo, "commit", "-q", "--allow-empty", "-m", msg)


@pytest.mark.parametrize("msgs,tag,expected,bump", [
    (["fix: a"], "v1.2.3", "1.2.4", "patch"),
    (["fix: a", "feat: b"], "v1.2.3", "1.3.0", "minor"),
    (["feat!: drop api"], "v1.2.3", "2.0.0", "major"),
    (["feat: x\n\nBREAKING CHANGE: gone"], "v1.2.3", "2.0.0", "major"),
    (["feat!: drop api"], "v0.4.1", "0.5.0", "minor"),   # 0.x: breaking -> minor
    (["perf(db): faster"], "v0.4.1", "0.4.2", "patch"),
])
def test_bumps(repo, msgs, tag, expected, bump):
    git(repo, "tag", tag)
    for m in msgs:
        commit(repo, m)
    code, out = run_gate("next_version.py", "HEAD", cwd=repo)
    assert code == 0 and out["next"] == expected and out["bump"] == bump


def test_nothing_to_release(repo):
    git(repo, "tag", "v1.0.0")
    commit(repo, "docs: readme")
    commit(repo, "chore: deps")
    code, out = run_gate("next_version.py", "HEAD", cwd=repo)
    assert code == 1 and "nothing user-facing" in out["note"]


def test_first_release(repo):
    commit(repo, "fix: first")
    code, out = run_gate("next_version.py", "HEAD", cwd=repo)
    assert code == 0 and out["next"] == "0.1.0"


def test_prerelease_tags_are_not_a_base(repo):
    git(repo, "tag", "v1.0.0")
    commit(repo, "feat: new")
    git(repo, "tag", "v1.1.0-rc.1")
    commit(repo, "fix: small")
    code, out = run_gate("next_version.py", "HEAD", cwd=repo)
    assert code == 0 and out["last_tag"] == "v1.0.0" and out["next"] == "1.1.0"


def test_non_ascii_commit_messages(repo):
    git(repo, "tag", "v1.0.0")
    commit(repo, "feat: 支持 naïve — ✓")
    code, out = run_gate("next_version.py", "HEAD", cwd=repo)
    assert code == 0 and out["decided_by"].endswith("feat: 支持 naïve — ✓")
