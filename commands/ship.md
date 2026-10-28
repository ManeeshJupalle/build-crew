---
description: Ship current work — open PR, AI review, fix blockers, then merge only if code gates pass. Usage: /ship [note]
argument-hint: [note]
---

Ship the current work. Note: $ARGUMENTS

1. **Create (AI + Code).** Run the `build-crew:pr-creator` subagent. If it returns STOPPED, show the reason and END.
2. **Review (AI).** Run the `build-crew:pr-reviewer` subagent with the PR number.
3. **Fix loop (max 3 rounds).** On CHANGES_REQUESTED, fix only the listed BLOCKERS on the same branch, run `bash "${CLAUDE_PLUGIN_ROOT}/run.sh" gates/checks.py`, push with a plain `git push`, then re-run `build-crew:pr-reviewer`. If it still has blockers after 3 rounds, STOP and show them.
4. **Merge (Code).** Run `bash "${CLAUDE_PLUGIN_ROOT}/run.sh" gates/merge_gate.py <PR> --merge`. If CI is pending, wait with `gh pr checks <PR> --watch` and run it again.
   - `"ok": false` with "review was for … re-review" means go back to step 2, once.
   - Any other failure: STOP and show the failing gate's `detail`. Never merge any other way; the guard hook blocks `gh pr merge`.
5. **Report:** PR link · MERGED or STOPPED · review rounds · the gates JSON summary.

Never say something passed or merged unless a gate's JSON says so.
