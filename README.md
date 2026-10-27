# build-crew

A small crew of Claude Code agents that plan, build, review, merge, release and deploy, so you approve work instead of babysitting it.

**Code for agents, docs for humans.**
Agents read the code. The few docs that exist are for people who want to understand and verify what happened. The checks that matter (did tests pass, did a review approve *this exact commit*, did the phase's Done-when commands pass) are decided by code gates that print JSON, not by an agent saying "looks good". See [Limits](#limits) for where the edges are.

---

## Install

**As a plugin (recommended)**, from inside Claude Code:
```
/plugin marketplace add ManeeshJupalle/build-crew
/plugin install build-crew@build-crew
```
Plugin commands are namespaced, e.g. `/build-crew:ship`.

**Or manually**, globally for every project, with plain `/ship`-style names:
```bash
# macOS / Linux
git clone https://github.com/ManeeshJupalle/build-crew && ./build-crew/install.sh
```
```powershell
# Windows (PowerShell)
git clone https://github.com/ManeeshJupalle/build-crew; .\build-crew\install.ps1
```
Re-run the same command to upgrade; add `--uninstall` (or `-Uninstall` on Windows) to remove.

**Needs:** Python 3.9+, git, and the [GitHub CLI](https://cli.github.com) (`gh auth login`). macOS, Linux and Windows are all tested in CI. On Windows, install [Git for Windows](https://git-scm.com/download/win) (Claude Code runs commands through its Git Bash) and Python from python.org; the Microsoft Store `python3` stub is detected and skipped.

## Use

```
/kickoff "a URL shortener with analytics"   → docs/HOW_IT_WORKS.md + docs/PLAN.md
/build-phase 0                              → builds Phase 0, proven by its Done-when commands
/ship                                       → PR → review → merge (if every gate passes)
/build-phase 1 → /ship → …
/release → /deploy
```
Also: `/fix <bug>` · `/research <question>` · `/handoff` (the next session picks up where you left off).

## How it works

```mermaid
flowchart LR
  A(architect) --> P(planner) --> PG1{{phase_gate check}} --> B(build) --> PG2{{phase_gate done}}
  PG2 --> C(pr-creator) --> SG{{secret_scan + checks}} --> R(pr-reviewer) --> MG{{merge_gate}}
  MG --> RL(release notes) --> D(deploy) --> H[/you approve production/]
```
Rounded boxes are AI, hexagons are code, and the slanted box is you. Each step below has the same label and a way to verify it yourself. Gate commands are relative to the build-crew folder; `scripts/py` finds Python on any OS.

1. **Plan:** `AI`
   `architect` writes `docs/HOW_IT_WORKS.md` (≤ 150 lines: picture, steps, decisions, non-goals). `planner` writes `docs/PLAN.md`: small phases, each ending in runnable *Done when* commands.
   Verify: read both files. They're meant for you.
2. **May this phase start?** `Code`
   `phase_gate.py check` refuses if a dependency isn't done or the working tree is dirty.
   Verify: `scripts/py gates/phase_gate.py check 1`
3. **Build:** `AI`
   Claude builds the phase, following the existing code as the spec.
4. **Is it done?** `Code`
   `phase_gate.py done` runs the phase's Done-when commands and ticks the box only if they all pass.
   Verify: `scripts/py gates/phase_gate.py verify 1`
5. **Safe to commit?** `Code`
   `secret_scan.py` scans everything the branch changed since it left the base branch, committed or not, for keys, `.env` files and vendor folders (values are masked). `checks.py` runs the project's own lint, typecheck, tests and build. Missing tools show as SKIPPED, never PASS, and if nothing ran the gate fails as NOT VERIFIED, unless the change is docs-only.
   Verify: `scripts/py gates/checks.py --markdown`. The table is pasted into every PR.
6. **Review:** `AI`
   `pr-reviewer` has no file-writing tools. It judges what tools can't (logic, security, test quality, fit with your decisions) and posts a verdict pinned to the exact head commit.
   Verify: the review comment on the PR.
7. **Merge:** `Code`
   `merge_gate.py` merges only if the PR is open and mergeable, the latest verdict is APPROVE *for the current commit* and was posted from your own GitHub account (comments from anyone else are ignored), CI is green (or not configured; "not started yet" counts as pending), and the branch contains the latest base commit. The merge uses `--match-head-commit`, so a late push makes GitHub refuse it.
   Verify: `scripts/py gates/merge_gate.py <PR>` (check only).
8. **Release:** `Code` + `AI`
   `next_version.py` computes the SemVer from Conventional Commits. The AI writes release notes a person would want to read, and you approve them.
9. **Deploy:** `AI` + `Human`
   Staging plus smoke tests, then production **only after you say yes**, for the exact commit that passed staging. Failed production smoke tests trigger a rollback.

### Always on: `Code`
- **Guard hook** (`hooks/guard.py`) parses each shell command, including chained, nested (`bash -c`) and `$(…)` commands, and blocks the destructive things agents actually do: force-push (any spelling), pushes or merges onto protected branches, skipping git hooks (`--no-verify`, `-n`, `HUSKY=0`, `core.hooksPath`), `reset --hard`, `git add -A`, recursive deletes of `/`, `~` or `.`, and merging PRs outside `merge_gate` (CLI, REST or GraphQL). Heredoc commit and PR messages are treated as text, not commands. It fails closed on anything it can't parse. 90+ test cases cover it.
- **Session hook** (`hooks/session_start.py`) loads your last `/handoff` and phase progress into every new session.

## The crew

| Agent | Judges (AI) | Can write |
|---|---|---|
| `architect` | system shape, decisions, non-goals | `docs/HOW_IT_WORKS.md` |
| `planner` | phase order and size | `docs/PLAN.md` |
| `researcher` | which library/service, with live sources | nothing |
| `debugger` | root cause and the smallest fix | code + regression test |
| `pr-creator` | commits and PR description | branch, PR |
| `pr-reviewer` | correctness, security, tests, fit | one PR comment |
| `release-manager` | release notes | version files, CHANGELOG |
| `deployer` | deploy method, reading smoke results | nothing (runs the deploy) |

| Gate (code) | Decides |
|---|---|
| `phase_gate.py` | may a phase start, and is it done |
| `checks.py` | do lint, typecheck, test and build pass |
| `secret_scan.py` | is anything sensitive about to be committed |
| `merge_gate.py` | may this PR merge, and merges it |
| `next_version.py` | what the next version is |

See `examples/` for what `HOW_IT_WORKS.md` and `PLAN.md` look like.

## Limits

Gates make the important checks repeatable and visible. They are not a security boundary against a determined model, so you should know where the edges are:

- **The guard is a seatbelt, not a sandbox.** It stops the mistakes agents actually make. A command written specifically to evade it (an obfuscated script, or a file it writes and then runs) can get past. Use branch protection on GitHub for hard guarantees.
- **The reviewer and the builder share your GitHub account.** `merge_gate` ignores verdicts from other accounts, but it can't tell the reviewer agent from the main session. Branch protection with required human reviews closes that gap.
- **"Read-only" agents still have Bash** to run `gh` and `git`. They have no Write/Edit tools, and their instructions forbid changes, but that part is enforced by the prompt, not by code.
- **PLAN.md is editable.** A phase is "done" when its Done-when commands pass, but those commands live in a file the AI can edit. The reviewer flags changes to Done-when lines and phase ticks, and they show up in the PR diff.
- **Production approval** is enforced by the `/deploy` flow asking you. The deployer refuses without it, but that check is in the prompt.
- The guard needs Python to run. If it can't start, the hook is set to **block** rather than silently allow (manual installs call Python by its absolute path; the plugin finds it via `scripts/py`).

## Contributing

Issues and PRs are welcome, especially new gates, agents, and stack support in `checks.py`. Start with [CONTRIBUTING.md](CONTRIBUTING.md). `pytest -q` runs 160+ tests in about 15 seconds, with no network.

## Acknowledgements

The "docs for humans to verify, code for agents" principle and the `Code` / `AI` step labels were inspired by the [Equalify Iris how-it-works page](https://iris.equalify.uic.edu/how-it-works).

MIT © Maneesh Jupalle
