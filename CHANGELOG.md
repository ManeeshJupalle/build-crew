# Changelog

## [Unreleased]

## [0.3.0] - 2026-10-29
### Changed
- Tested on Python 3.14 as well as 3.9 and 3.13, on macOS, Linux and Windows. (#15, by @Vamsi-2581)

### Fixed
- `checks.py` runs `pytest -q` in a Python repo with no `pyproject.toml`, `setup.py` or `requirements*.txt` (Pipenv, conda or plain scripts), when `conftest.py`, `test_*.py` or `*_test.py` sits directly in `tests/` and no other stack or Makefile target matched. Before, it reported NOT VERIFIED. (#17, by @babyhuey)

### Security
- `secret_scan` catches GitLab personal access tokens (`glpat-`), npm tokens (`npm_`) and Hugging Face tokens (`hf_`). (#10, by @babyhuey)

## [0.2.0] - 2026-10-28
### Added
- Runs on macOS, Linux and Windows. Gates and hooks start through `run.sh`, which finds Python 3.9+ as `python3`, `python` or `py`. (#4)

### Changed
- Done-when and check commands run in bash on every OS (Git Bash on Windows), the shell Claude's Bash tool uses. (#4)

### Fixed
- Windows: plans, settings and commit messages are read and written as UTF-8, so non-ASCII text survives. (#4)
- Windows: agent and command files check out with LF line endings, which Claude Code needs to read their frontmatter. (#4)
- Windows: `checks.py` finds virtualenv tools (`Scripts\*.exe`). (#4)
- `checks.py` handles project paths with spaces. (#4)
- `phase_gate done` keeps PLAN.md's own line endings, so ticking a phase is a one-line diff. Before, it could rewrite the ending of every line. (#4)

### Security
- The guard hook blocks every Bash command when Python is missing. Before, it let them all through. (#4)
- The guard catches Windows spellings of git and gh: `git.exe`, `GH.EXE`, full paths with backslashes. (#4)
- The guard checks commands inside `{ …; }` groups and `if`/`for`/`while` bodies, and after `!`. (#9, #14)
- The guard looks inside more shells: ksh, mksh, ash, fish, csh, tcsh, `cmd /c` (`cmd //c` in Git Bash), and the command given to `pwsh`/`powershell` with `-Command`, `-c` or as a bare first argument. A plain `-EncodedCommand` can't be read, so it's blocked. (#9)
- An empty argument no longer splits a command, so `git push origin "" --force` is blocked. (#9)
- Known gaps: on Windows, commands run through Claude Code's PowerShell tool aren't checked yet (#11). Smaller gaps, such as `(git reset --hard)` and `pwsh -i -enc …`, are tracked in #12.

## [0.1.0] - 2026-10-27
### Added
- Agents: architect, planner, researcher, debugger, pr-creator, pr-reviewer, release-manager, deployer.
- Commands: /kickoff, /build-phase, /ship, /fix, /research, /handoff, /release, /deploy.
- Code gates: `phase_gate`, `checks`, `secret_scan`, `merge_gate`, `next_version`.
- Guard hook blocking destructive git/gh commands; session hook loading the last handoff.
- Plugin + marketplace manifests, and `install.sh` / `uninstall.sh` for manual global installs.
- Two human-facing docs per project: `HOW_IT_WORKS.md` (≤ 150 lines) and `PLAN.md`. Agents treat the code as the spec.
- Merging is done only by `merge_gate.py`. Direct `gh pr merge` is blocked.
