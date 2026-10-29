# Changelog

## [Unreleased]

## [0.2.0] - 2026-10-28
### Added
- Runs on macOS, Linux and Windows. Gates and hooks start through `run.sh`, which finds Python 3.9+ as `python3`, `python` or `py`. (#4)

### Changed
- Done-when and check commands run in bash on every OS (Git Bash on Windows), the shell Claude's Bash tool uses. (#4)

### Fixed
- Windows: plans, settings and commit messages are read and written as UTF-8, so non-ASCII text survives. (#4)
- Windows: agent and command files check out with LF line endings, which Claude Code needs to read their frontmatter. (#4)
- Windows: `checks.py` finds virtualenv tools (`Scripts\*.exe`) and handles project paths with spaces. (#4)
- `install.sh` no longer hangs on Windows with Python 3.13+. (#4)

### Security
- The guard hook blocks every Bash command when Python is missing. Before, it let them all through. (#4)
- The guard catches Windows spellings of git and gh: `git.exe`, `GH.EXE`, full paths with backslashes. (#4)
- The guard checks commands inside `{ …; }` groups and `if`/`for`/`while` bodies, and after `!`. (#9)
- The guard looks inside more shells: ksh, mksh, ash, fish, csh, tcsh, `cmd /c` (`cmd //c` in Git Bash), and `pwsh`/`powershell` however they're given a command. `-EncodedCommand` can't be read, so it's blocked. (#9)
- An empty argument no longer splits a command, so `git push origin "" --force` is blocked. (#9)

## [0.1.0] - 2026-10-27
### Added
- Agents: architect, planner, researcher, debugger, pr-creator, pr-reviewer, release-manager, deployer.
- Commands: /kickoff, /build-phase, /ship, /fix, /research, /handoff, /release, /deploy.
- Code gates: `phase_gate`, `checks`, `secret_scan`, `merge_gate`, `next_version`.
- Guard hook blocking destructive git/gh commands; session hook loading the last handoff.
- Plugin + marketplace manifests, and `install.sh` / `uninstall.sh` for manual global installs.
- Two human-facing docs per project: `HOW_IT_WORKS.md` (≤ 150 lines) and `PLAN.md`. Agents treat the code as the spec.
- Merging is done only by `merge_gate.py`. Direct `gh pr merge` is blocked.
