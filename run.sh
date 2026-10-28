#!/usr/bin/env bash
# Runs a build-crew Python script with whatever Python 3.9+ this machine has: python3 on macOS and
# Linux, python or py on Windows (where python3 is often a Microsoft Store placeholder).
#   bash run.sh gates/checks.py --markdown      path relative to this folder; "-" reads the script from stdin
# No Python means exit 2, so the guard hook blocks commands instead of silently letting them through.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
script="${1:?usage: run.sh <script.py> [args]}"
shift
[ "$script" = - ] || script="$here/$script"

for py in python3 python py; do
  # </dev/null: the probe must not eat the hook's JSON input
  if "$py" -c 'import sys; sys.exit(sys.version_info < (3, 9))' </dev/null >/dev/null 2>&1; then
    exec "$py" "$script" "$@"
  fi
done

msg="build-crew needs Python 3.9+ (tried python3, python and py). Install it from https://www.python.org/downloads/"
echo "{\"ok\": false, \"error\": \"$msg\"}"
echo "$msg" >&2
exit 2
