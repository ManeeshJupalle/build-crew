# Contributing

Thanks for helping! The one rule: **if it must be true, make it code.** Put judgment in agents and guarantees in gates.

## Setup
```bash
git clone https://github.com/ManeeshJupalle/build-crew && cd build-crew
pip install pytest
pytest -q                      # ~15s, no network, no GitHub account needed
claude --plugin-dir .          # try your changes live in Claude Code
claude plugin validate .       # manifest check
```

## Layout
```
agents/      AI judgment: one job per agent, Markdown + frontmatter
commands/    slash commands that wire agents and gates together
gates/       code that decides pass/fail; prints one JSON object, exit 0 or 1
hooks/       guard (blocks dangerous commands) + session start (loads handoff)
tests/       pytest for every gate, the guard, install/uninstall, plus layout checks
examples/    sample HOW_IT_WORKS.md and PLAN.md
```

## Adding a gate
- Python standard library only. Use `gates/_common.py` (`emit`, `gh`, `git`, `run`).
- Print **one JSON object** with `"gate"` and `"ok"`, and exit `0` (pass) or `1` (fail). Never print secrets.
- Wrap the entry point in `main_guarded(...)`, so crashes become failing JSON, never a traceback or an accidental pass. If you're unsure, fail closed.
- Talk to GitHub only through `gh()`, so tests can swap in `tests/fake_gh.py` via `BUILD_CREW_GH`.
- Add tests for pass, every refusal path, and "never does the dangerous thing on failure".

## Adding or changing an agent
- Frontmatter: `name` (matches the filename), a `description` that says *when* to use it, minimal `tools`, `model`.
- Include a **Code vs AI** section: what gates already decide, and what this agent judges.
- Agents that shouldn't change code (reviewer, researcher, deployer) don't get `Write`/`Edit` tools. A test enforces this; their Bash use is limited by their instructions.
- End with a fixed-format report block, so other steps can parse it.
- Reference gates as `${CLAUDE_PLUGIN_ROOT}/gates/<gate>.py` and other agents as `` `build-crew:<name>` ``. `install.sh` and `install.ps1` rewrite both for manual installs.

## Extending `checks.py` to a new stack
Add a `<stack>_checks(root)` that returns `(name, command, tool)` tuples and add it to `detect()`, plus a test.

## Pull requests
- Conventional Commit titles (`feat(gates): …`, `fix(guard): …`). `next_version.py` uses them to pick the next version.
- CI must be green: tests on Linux and macOS, shellcheck, and plugin validation.
- Keep docs short. If the code already says it clearly, don't repeat it in Markdown.
