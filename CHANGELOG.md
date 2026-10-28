# Changelog

## [Unreleased]
### Added
- `install.ps1` / `uninstall.ps1` for manual global installs on Windows, tested in CI on Windows PowerShell 5.1 and PowerShell 7.
- `.gitattributes` keeps shell scripts on LF line endings, so hooks run from Windows checkouts.

## [0.1.0] - 2026-10-27
### Added
- Agents: architect, planner, researcher, debugger, pr-creator, pr-reviewer, release-manager, deployer.
- Commands: /kickoff, /build-phase, /ship, /fix, /research, /handoff, /release, /deploy.
- Code gates: `phase_gate`, `checks`, `secret_scan`, `merge_gate`, `next_version`.
- Guard hook blocking destructive git/gh commands; session hook loading the last handoff.
- Plugin + marketplace manifests, and `install.sh` / `uninstall.sh` for manual global installs.
- Two human-facing docs per project: `HOW_IT_WORKS.md` (≤ 150 lines) and `PLAN.md`. Agents treat the code as the spec.
- Merging is done only by `merge_gate.py`. Direct `gh pr merge` is blocked.
