# Changelog

## [Unreleased]
### Added
- Native Windows support: `install.ps1`, a `scripts/py` launcher that finds Python as `python3`, `python` or `py -3` (skipping the Microsoft Store stub), and Windows in CI.
- Hooks no longer need a shell for manual installs: they run Python by absolute path (exec form), and the guard blocks if it can't start.

### Changed
- One installer (`scripts/install.py`) behind `install.sh` and `install.ps1`; `uninstall.sh` and `install.ps1 -Uninstall` use it too.
- Gates read and write UTF-8 explicitly and run project commands through Git Bash on Windows.

## [0.1.0] - 2026-10-27
### Added
- Agents: architect, planner, researcher, debugger, pr-creator, pr-reviewer, release-manager, deployer.
- Commands: /kickoff, /build-phase, /ship, /fix, /research, /handoff, /release, /deploy.
- Code gates: `phase_gate`, `checks`, `secret_scan`, `merge_gate`, `next_version`.
- Guard hook blocking destructive git/gh commands; session hook loading the last handoff.
- Plugin + marketplace manifests, and `install.sh` / `uninstall.sh` for manual global installs.
- Two human-facing docs per project: `HOW_IT_WORKS.md` (≤ 150 lines) and `PLAN.md`. Agents treat the code as the spec.
- Merging is done only by `merge_gate.py`. Direct `gh pr merge` is blocked.
