# Changelog

## [Unreleased]

## [0.4.0] - 2026-10-30
### Added
- The guard checks commands from Claude Code's PowerShell tool as well as Bash. PowerShell gets its own parser for quoting, escapes, here-strings, brackets and assignments, so `$out = git push --force` and `Remove-Item -Recurse -Force ~` are caught. (#26, #36)

### Changed
- The guard blocks a shell that reads its commands from stdin, because it can't see what they run. This covers `pwsh -Command -` (#28) and a pipe or heredoc into bash, sh or PowerShell, such as `echo … | bash`, `bash <<'EOF'` or `curl … | sh` (#35).
- It also blocks any command it can't check in time: when it crashes, when a command is over 100,000 characters, or after 10s of checking. Before, a crash or a hook timeout let the command run. (#35)

### Fixed
- Bash commands that were wrongly blocked are now allowed:
  - a single-quoted `$(git push --force)` in a commit message (#28)
  - `powershell -c 'Get-ChildItem "D:\"'` (#26)
  - `git status # it's fine` (#35)
  - `git commit -m $'fix: don\'t crash'` (#35)
  - `rm -Force *` inside `pwsh -c` (#36)

### Security
- More commands that got past the guard are now caught:
  - quoted separators, subshells, substitutions used as option values, `HUSKY=0` after `env`, `sudo` or `then`, `cmd /cgit`, and `pwsh -i -enc …` (#28)
  - a reset hidden between two apostrophes in comments (#35)
  - a command after `$'…'` quoting with `\'` in it, as in `echo $'a\'b' ; git push --force ; echo \'` (#35)
- From Bash, recursive deletes of `C:/` and `$env:USERPROFILE` are blocked. (#26)

## [0.3.1] - 2026-10-30
### Changed
- The repo is now `ManeeshJupalle/claude-build-crew`, so the install command is `/plugin marketplace add ManeeshJupalle/claude-build-crew`. The old name redirects, and the plugin is still called `build-crew`. (#23)

### Fixed
- `secret_scan` no longer flags `npm_` text inside a longer word, that is with a letter, digit or `_` right before `npm_` or right after its 36 characters. Real npm tokens are still caught. (#21, by @ungaaaabungaaa)

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
