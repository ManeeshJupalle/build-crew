---
description: Save where things stand to docs/PROGRESS.md; the next session loads it automatically. Usage: /handoff [note]
argument-hint: [note]
---

Write a handoff. Note: $ARGUMENTS

1. **Facts (check them, don't guess):** `git branch --show-current` · `git status --porcelain` · `git log --oneline -8` · `gh pr list --author @me --state open --json number,title,url` · `bash "${CLAUDE_PLUGIN_ROOT}/run.sh" gates/phase_gate.py next` (if `docs/PLAN.md` exists) · what happened this session.
2. **Write `docs/PROGRESS.md`.** Replace everything above `## History` and append one History line, keeping the latest 30. Stay under 40 lines above History:
```
# Progress
> <YYYY-MM-DD HH:MM> · branch <branch>

## Now
- Next phase: <id — name> · Open PRs: <#n title> · Tree: <clean | files>

## Done this session
- <concrete: what + where>

## Next (in order)
1. <exact next action, e.g. "/ship PR #14">

## Blockers / decisions / gotchas
- <item> (or "none")

---
## History
- <YYYY-MM-DD>: <one line>
```
3. Tell the user in 2 lines: "Saved. The next session loads it automatically." plus the #1 next step. No secrets.
