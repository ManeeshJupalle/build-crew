from conftest import git, run_gate

# Built at runtime so this file never contains a real-looking secret itself.
FAKE_GH_TOKEN = "ghp_" + "Ab3" * 12
FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"


def feature(repo):
    git(repo, "switch", "-q", "-c", "feat/x")
    return repo


def test_clean_change_passes(repo):
    feature(repo)
    (repo / "app.py").write_text("import os\nAPI_KEY = os.environ['API_KEY']\n", encoding="utf-8")
    code, out = run_gate("secret_scan.py", cwd=repo)
    assert code == 0 and out["findings"] == [] and out["files_scanned"] == 1


def test_detects_tokens_and_masks(repo):
    feature(repo)
    (repo / "config.py").write_text(f"token = '{FAKE_GH_TOKEN}'\naws = '{FAKE_AWS}'\n", encoding="utf-8")
    code, out = run_gate("secret_scan.py", cwd=repo)
    assert code == 1
    issues = {f["issue"] for f in out["findings"]}
    assert "GitHub token" in issues and "AWS access key" in issues
    assert all(FAKE_GH_TOKEN not in str(f) for f in out["findings"]), "values must be masked"


def test_catches_secret_already_committed_on_branch_without_origin(repo):
    feature(repo)
    (repo / "config.py").write_text(f"token = '{FAKE_GH_TOKEN}'\n", encoding="utf-8")
    git(repo, "add", "config.py")
    git(repo, "commit", "-q", "-m", "feat: config")
    code, out = run_gate("secret_scan.py", cwd=repo)          # no origin: falls back to local main
    assert code == 1 and out["base"] == "main"


def test_works_from_a_subdirectory(repo):
    feature(repo)
    (repo / "src").mkdir()
    (repo / "src" / "config.py").write_text(f"token = '{FAKE_GH_TOKEN}'\n", encoding="utf-8")
    git(repo, "add", "src/config.py")
    git(repo, "commit", "-q", "-m", "feat: config")
    code, out = run_gate("secret_scan.py", cwd=repo / "src")
    assert code == 1 and out["findings"][0]["file"] == "src/config.py"


def test_fails_closed_without_a_base(tmp_path):
    git(tmp_path, "init", "-q", "-b", "scratch")
    code, out = run_gate("secret_scan.py", cwd=tmp_path)
    assert code == 1 and "base" in out["error"]


def test_blocks_secret_files_allows_example(repo):
    feature(repo)
    (repo / ".env").write_text("X=1\n", encoding="utf-8")
    (repo / ".env.example").write_text("X=\n", encoding="utf-8")
    (repo / "server.pem").write_text("x\n", encoding="utf-8")
    code, out = run_gate("secret_scan.py", cwd=repo)
    assert code == 1 and {f["file"] for f in out["findings"]} == {".env", "server.pem"}


def test_vendor_dirs_blocked_but_nested_build_folders_allowed(repo):
    feature(repo)
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "x.js").write_text("x", encoding="utf-8")
    (repo / "src" / "build").mkdir(parents=True)
    (repo / "src" / "build" / "steps.py").write_text("x = 1\n", encoding="utf-8")
    code, out = run_gate("secret_scan.py", cwd=repo)
    flagged = {f["file"] for f in out["findings"]}
    assert code == 1 and flagged == {"node_modules/x.js"}
