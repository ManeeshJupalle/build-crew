#!/usr/bin/env bash
# build-crew manual install (alternative to the plugin install in README).
# Installs globally into ~/.claude so it works in every project.
#
# Safe to re-run:
#   - files it installs carry a "build-crew" marker; anything else with the same
#     name is backed up first, never silently overwritten
#   - settings.json: only build-crew's own hook entries are added/replaced, a
#     timestamped backup is kept, and an unreadable settings file aborts the install
set -euo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
CLAUDE="$HOME/.claude"
ROOT="$CLAUDE/build-crew"                 # gates + hooks live here
MARKER="<!-- installed by build-crew -->"
STAMP="$(date +%Y%m%d-%H%M%S)"
BK="$ROOT/backup-$STAMP"

# run.sh says which Python is missing. <<<'' rather than </dev/null: Windows' NUL device looks like a terminal,
# so Python 3.13+ would open its interactive prompt and wait forever.
bash "$KIT/run.sh" - <<<'' >/dev/null || exit 1
command -v gh >/dev/null || echo "⚠️  GitHub CLI not found: install it from https://cli.github.com before using /ship"

mkdir -p "$CLAUDE/agents" "$CLAUDE/commands" "$ROOT"

backup() {  # move a file into this run's backup folder, keeping its relative path
  local rel="${1#"$CLAUDE"/}"
  mkdir -p "$BK/$(dirname "$rel")"
  mv "$1" "$BK/$rel"
}

is_ours() {  # only files this installer wrote carry the marker; anything else gets backed up
  grep -qF "$MARKER" "$1" 2>/dev/null
}

# 1. Retire files from the pre-plugin kit, recognised by the report line only that kit wrote.
retire() {  # retire <file> <signature>
  if [ -f "$1" ] && ! is_ours "$1" && grep -qF "$2" "$1"; then backup "$1"; fi
}
retire "$CLAUDE/agents/spec-writer.md"   "SPEC_WRITER_RESULT"
retire "$CLAUDE/agents/docs-keeper.md"   "DOCS_KEEPER_RESULT"
retire "$CLAUDE/agents/pr-merger.md"     "PR_MERGER_RESULT"
retire "$CLAUDE/agents/build-planner.md" "BUILD_PLANNER_RESULT"
retire "$CLAUDE/commands/spec.md"        "spec-writer"
for f in "$CLAUDE"/hooks/guard.py "$CLAUDE"/hooks/session_start.sh; do
  [ -f "$f" ] && grep -qE 'build-crew|pr-agents' "$f" && backup "$f"
done

# 2. Gates, hooks and the Python launcher (build-crew's own folder: replaced wholesale).
rm -rf "$ROOT/gates" "$ROOT/hooks"
cp -R "$KIT/gates" "$KIT/hooks" "$KIT/run.sh" "$ROOT/"
chmod +x "$ROOT"/gates/*.py "$ROOT"/hooks/*.py "$ROOT"/hooks/*.sh

# 3. Agents and commands: resolve the plugin path variable and namespace, add the marker.
# shellcheck disable=SC2016  # backticks are literal Markdown, not expansions
render() {
  local dest="$2"
  if [ -f "$dest" ] && ! is_ours "$dest"; then
    backup "$dest"   # includes files from the pre-plugin kit: harmless, and nothing is ever lost
    echo "Backed up existing $(basename "$(dirname "$dest")")/$(basename "$dest")"
  fi
  sed -e "s#\${CLAUDE_PLUGIN_ROOT}#$ROOT#g" -e 's/`build-crew:\([a-z-]*\)`/`\1`/g' "$1" > "$dest"
  printf '\n%s\n' "$MARKER" >> "$dest"
}
for f in "$KIT"/agents/*.md;   do render "$f" "$CLAUDE/agents/$(basename "$f")";   done
for f in "$KIT"/commands/*.md; do render "$f" "$CLAUDE/commands/$(basename "$f")"; done

# 4. Settings: add/replace only build-crew hook entries; add deny rules.
SETTINGS="$CLAUDE/settings.json"
if [ -f "$SETTINGS" ]; then
  mkdir -p "$BK"
  cp "$SETTINGS" "$BK/settings.json"
fi
bash "$KIT/run.sh" - "$SETTINGS" "$ROOT" "$CLAUDE" <<'PY'
import json, os, sys
path, root, claude = sys.argv[1:4]
if os.path.exists(path):
    try:
        s = json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"✗ {path} is not valid JSON ({e}); fix it and re-run. Nothing was changed.")
else:
    s = {}

OURS = (f"{root}/hooks/", f"{root}/run.sh", f"{claude}/hooks/guard.py", f"{claude}/hooks/session_start.sh",
        '$HOME/.claude/hooks/guard.py', '$HOME/.claude/hooks/session_start.sh', '$HOME/.claude/build-crew/hooks/')
def ours(h):  # one hook handler
    return any(o in h.get("command", "") for o in OURS)

hooks = s.setdefault("hooks", {})
mine = {
    "PreToolUse": {"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": f'bash "{root}/run.sh" hooks/guard.py'}]},
    "SessionStart": {"hooks": [{"type": "command", "command": f'bash "{root}/hooks/session_start.sh"'}]},
}
for event, entry in mine.items():
    groups = []
    for g in hooks.get(event, []):
        kept = [h for h in g.get("hooks", []) if not ours(h)]   # drop only our handlers
        if kept:
            groups.append({**g, "hooks": kept})
    hooks[event] = groups + [entry]

deny = s.setdefault("permissions", {}).setdefault("deny", [])
if "Read(./.env.*)" in deny:  # older versions also blocked .env.example
    deny.remove("Read(./.env.*)")
for rule in ["Bash(git push --force:*)", "Bash(git push -f:*)", "Bash(gh pr merge:*)", "Bash(gh repo delete:*)",
             "Read(./.env)", "Read(./.env.local)", "Read(./.env.development)", "Read(./.env.production)",
             "Read(./.env.staging)", "Read(./.env.test)"]:
    if rule not in deny:
        deny.append(rule)

tmp = path + ".build-crew.tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(s, f, indent=2)
os.replace(tmp, path)   # atomic: never leaves a half-written settings.json
PY

[ -d "$BK" ] && echo "Backups: $BK"
echo "✅ build-crew installed globally ($ROOT). Restart Claude Code in any repo."
echo "   /kickoff → /build-phase → /ship → /release → /deploy   (+ /fix /research /handoff)"
