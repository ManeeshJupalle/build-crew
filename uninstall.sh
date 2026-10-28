#!/usr/bin/env bash
# Remove a manual (install.sh) build-crew install. Plugin installs: use /plugin instead.
# Only removes files carrying the build-crew marker and build-crew's own hook entries.
set -euo pipefail
KIT="$(cd "$(dirname "$0")" && pwd)"
CLAUDE="$HOME/.claude"
MARKER="<!-- installed by build-crew -->"

for f in "$KIT"/agents/*.md "$KIT"/commands/*.md; do
  dest="$CLAUDE/$(basename "$(dirname "$f")")/$(basename "$f")"
  if [ -f "$dest" ] && grep -qF "$MARKER" "$dest"; then rm -f "$dest"; fi
done

if [ -f "$CLAUDE/settings.json" ]; then
  cp "$CLAUDE/settings.json" "$CLAUDE/settings.json.build-crew-uninstall.bak"
  bash "$KIT/run.sh" - "$CLAUDE/settings.json" <<'PY'
import json, os, sys
p = sys.argv[1]
s = json.load(open(p, encoding="utf-8"))
for event in ("PreToolUse", "SessionStart"):
    groups = []
    for g in s.get("hooks", {}).get(event, []):
        kept = [h for h in g.get("hooks", [])
                if not any(m in h.get("command", "") for m in ("build-crew/hooks/", "build-crew/run.sh"))]
        if kept:
            groups.append({**g, "hooks": kept})
    if event in s.get("hooks", {}):
        s["hooks"][event] = groups
tmp = p + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(s, f, indent=2)
os.replace(tmp, p)
PY
fi
rm -rf "$CLAUDE/build-crew/gates" "$CLAUDE/build-crew/hooks" "$CLAUDE/build-crew/run.sh"
echo "✅ build-crew removed. Deny rules were left in settings.json; a backup is at settings.json.build-crew-uninstall.bak"
